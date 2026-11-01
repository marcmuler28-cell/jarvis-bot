"""
llm_provider.py v3 - OpenRouter -> Groq, failover + autodescubrimiento de modelos.
JarvisLLM(prompt, max_tokens=N) -> str (misma interfaz que llama_cpp)
Los modelos gratuitos rotan: v3 consulta /models y elige uno disponible.
"""
import os
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[llm_provider] WARNING: falta python-dotenv; el .env no se cargara")

PREFS = {
    "openrouter": {
        "fast":     ["deepseek-chat", "llama-3.3", "qwen2.5-72b", "mistral-7b", "gemini-flash"],
        "powerful": ["deepseek-r1", "deepseek-chat", "qwen2.5-72b", "llama-3.3-70b", "gemini-flash"],
        "default":  ["deepseek-chat", "llama-3.3", "qwen2.5-72b", "mistral-7b", "gemini-flash"],
    },
    "groq": {
        "fast":     ["8b", "instant", "gemma"],
        "powerful": ["70b", "versatile"],
        "default":  ["70b", "versatile", "8b"],
    },
}

FALLBACK = {
    "openrouter": ["deepseek/deepseek-chat:free", "qwen/qwen-2.5-72b-instruct:free",
                   "mistralai/mistral-7b-instruct:free", "google/gemini-2.0-flash-exp:free"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
}

EXCLUIR = ("whisper", "tts", "guard", "embed", "vision-audio")


class JarvisLLM:
    """Drop-in replacement de llama_cpp.Llama, via API, con autocuracion."""

    def __init__(self, tier=None):
        if tier not in (None, "fast", "powerful"):
            raise ValueError(f"tier invalido: {tier}")
        self.tier = tier
        self.providers = []
        self._armar()
        if not self.providers:
            raise RuntimeError("[llm_provider] Sin claves API en .env")
        p = self.providers[0]
        print(f"[llm_provider] tier={tier or 'default'} | {p['nombre']} -> {p['modelos'][0]}")

    def _pedir(self, url, clave):
        import requests
        r = requests.get(url, headers={"Authorization": f"Bearer {clave}"}, timeout=15)
        if r.status_code == 401:
            return None
        return r.json().get("data", [])

    def _elegir(self, disponibles, prov):
        prefs = PREFS[prov][self.tier or "default"]
        outs = []
        for pref in prefs:
            for m in disponibles:
                if pref in m.lower() and m not in outs:
                    outs.append(m)
        for m in disponibles:
            if m not in outs:
                outs.append(m)
        return outs[:6]

    def _armar(self):
        tier = self.tier or "default"

        if os.getenv("OPENROUTER_API_KEY"):
            try:
                data = self._pedir("https://openrouter.ai/api/v1/models",
                                   os.getenv("OPENROUTER_API_KEY"))
                gratis = [m["id"] for m in (data or [])
                          if str(m.get("pricing", {}).get("prompt", "1")) == "0"
                          and str(m.get("pricing", {}).get("completion", "1")) == "0"]
                modelos = self._elegir(gratis, "openrouter") if gratis else []
                print(f"[llm_provider] openrouter: {len(gratis)} modelos gratis hoy")
            except Exception as e:
                print(f"[llm_provider] openrouter /models fallo ({e}) -> lista estatica")
                modelos = []
            if not modelos:
                modelos = list(FALLBACK["openrouter"])
            override = (os.getenv(f"OPENROUTER_MODEL_{tier.upper()}")
                        or os.getenv("LLM_MODEL"))
            if override and override not in modelos:
                modelos.insert(0, override)
            self.providers.append({
                "nombre": "openrouter",
                "cliente": OpenAI(base_url="https://openrouter.ai/api/v1",
                                  api_key=os.getenv("OPENROUTER_API_KEY")),
                "modelos": modelos,
            })

        if os.getenv("GROQ_API_KEY"):
            try:
                data = self._pedir("https://api.groq.com/openai/v1/models",
                                   os.getenv("GROQ_API_KEY"))
                if data is None:
                    print("[llm_provider] GROQ_API_KEY invalida -> groq desactivado")
                    data = []
                limpio = [m["id"] for m in data
                          if not any(x in m["id"].lower() for x in EXCLUIR)]
                modelos = self._elegir(limpio, "groq") if limpio else []
                print(f"[llm_provider] groq: {len(limpio)} modelos disponibles hoy")
            except Exception as e:
                print(f"[llm_provider] groq /models fallo ({e}) -> lista estatica")
                modelos = []
            if not modelos:
                modelos = list(FALLBACK["groq"])
            override = (os.getenv(f"GROQ_MODEL_{tier.upper()}")
                        or os.getenv("GROQ_MODEL"))
            if override and override not in modelos:
                modelos.insert(0, override)
            if modelos:
                self.providers.append({
                    "nombre": "groq",
                    "cliente": OpenAI(base_url="https://api.groq.com/openai/v1",
                                      api_key=os.getenv("GROQ_API_KEY")),
                    "modelos": modelos,
                })

    # Frases que delatan que el modelo esta repitiendo el schema/instrucciones
    # en vez de contestar al usuario (modelos gratis rotativos).
    _MARCAS_ECO = (
        "herramientas disponibles:",
        "tools available:",
        "analyze the request",
        "(final message to user)",
        "(tu mensaje final al usuario)",
        "herramienta|argumento1",
    )

    @classmethod
    def _es_eco(cls, texto):
        """True si la salida es un eco del prompt y no una respuesta util."""
        bajo = (texto or "").lower()
        return any(m in bajo for m in cls._MARCAS_ECO)

    @staticmethod
    def _opciones_api(kw):
        """Traduce kwargs estilo llama_cpp a lo que acepta la API OpenAI.

        La API ignora los parametros desconocidos, asi que sin esta traduccion
        se perdian `stop`/`repeat_penalty` y el modelo seguia escribiendo
        despues del turno del usuario (devolvia un eco del prompt).
        """
        extra = {}
        stop = kw.get("stop")
        if stop:
            if isinstance(stop, str):
                stop = [stop]
            limpio = [s for s in stop if s]
            if limpio:
                extra["stop"] = limpio[:4]  # la API admite maximo 4 secuencias
        freq = kw.get("frequency_penalty", kw.get("repeat_penalty"))
        if freq is not None:
            # repeat_penalty 1.0 es neutro en llama_cpp; 0.0 lo es en la API
            extra["frequency_penalty"] = max(0.0, min(float(freq) - 1.0, 2.0))
        return extra

    def __call__(self, prompt, max_tokens=512, temperature=0.7, **kw):
        opciones = self._opciones_api(kw)
        try:
            return self._intentar(prompt, max_tokens, temperature, opciones)
        except RuntimeError:
            # La lista pudo quedar obsoleta (rotacion de modelos gratis) o el
            # arranque ocurrio antes de que hubiera red: se redescubre una vez.
            print("[llm_provider] cadena agotada -> redescubriendo modelos")
            self.providers = []
            try:
                self._armar()
            except Exception as e:
                print(f"[llm_provider] redescubrimiento fallo: {e}")
            if not self.providers:
                raise
            return self._intentar(prompt, max_tokens, temperature, opciones)

    def _intentar(self, prompt, max_tokens, temperature, opciones):
        errores = []
        for prov in self.providers:
            for modelo in prov["modelos"]:
                try:
                    r = prov["cliente"].chat.completions.create(
                        model=modelo,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens, temperature=temperature,
                        **opciones)
                    txt = (r.choices[0].message.content or "").strip()
                    if txt and self._es_eco(txt):
                        # El modelo repitio el prompt en vez de responder:
                        # se descarta y se intenta con el siguiente.
                        errores.append(f"{prov['nombre']}/{modelo}: eco del prompt")
                        print(f"[llm_provider] eco del prompt en {modelo} -> siguiente modelo")
                        continue
                    if txt:
                        if prov["modelos"][0] != modelo:
                            prov["modelos"].remove(modelo)
                            prov["modelos"].insert(0, modelo)
                            print(f"[llm_provider] Modelo estable: {modelo}")
                        return txt
                except Exception as e:
                    errores.append(f"{prov['nombre']}/{modelo}: {str(e)[:100]}")
        raise RuntimeError("[llm_provider] Todos los intentos fallaron:\n"
                           + "\n".join(errores[:6]))
