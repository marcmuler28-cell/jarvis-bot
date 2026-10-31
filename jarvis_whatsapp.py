#!/usr/bin/env python3
"""
jarvis_whatsapp.py v1 — WhatsApp con TU PROPIO número (sin la API de Meta).

Arquitectura:
    cerebro (assistant.py) ──HTTP local──> whatsapp_bridge/server.js (Node)
                                              └─ whatsapp-web.js + LocalAuth
                                                 (sesión de WhatsApp Web de
                                                  tu propio número)

Este módulo:
  - interpreta las frases de envío en el fast-path (a través de intentar()):
      «manda un whatsapp a mamá diciendo que ya llegué»
      «envíale un wsp a Luis que mañana hay examen»
      «whatsapp a mama: no te preocupes»
      «estado de whatsapp» / «whatsapp estado»
      «mis contactos» / «agenda de whatsapp»
      «guarda contacto luis 51 999 888 777»
  - resuelve apodos → número con ~/.jarvis/contactos.json
  - habla con el puente Node en 127.0.0.1 (nunca sale a internet por sí solo;
    quien habla con WhatsApp es el puente, con TU sesión).

Variables de entorno (opcionales):
  JARVIS_WA_CONTACTOS    ruta del archivo de contactos
                         (por defecto ~/.jarvis/contactos.json)
  JARVIS_WA_BRIDGE_URL   http://127.0.0.1:5015
  JARVIS_WA_BRIDGE_TOKEN token compartido (debe coincidir con el del puente)

Solo stdlib. 100% testeable sin Node ni WhatsApp (ver test_whatsapp.py).

CLI de prueba:
  python3 jarvis_whatsapp.py estado
  python3 jarvis_whatsapp.py contactos
  python3 jarvis_whatsapp.py guarda luis +51999888777
  python3 jarvis_whatsapp.py enviar mama "ya llegué"
  python3 jarvis_whatsapp.py enviar yo "nota mental"
  python3 jarvis_whatsapp.py escuchar   # responde lo que te escribas a ti mismo
"""

import difflib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request


def _cargar_env(ruta=None):
    """Lee KEY=VALOR del .env de la raíz del proyecto (solo stdlib).

    No pisa variables ya exportadas en la sesión; si el archivo no existe,
    sigue silenciosamente. Así el JARVIS_WA_BRIDGE_TOKEN del .env sirve
    igual para el cerebro (api_gateway) que para la CLI de prueba.
    """
    if ruta is None:
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, _, valor = linea.partition("=")
                clave = clave.strip()
                valor = valor.strip().strip('"').strip("'")
                if clave and clave not in os.environ:
                    os.environ[clave] = valor
    except OSError:
        pass


_cargar_env()

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────

RUTA_CONTACTOS = os.environ.get(
    "JARVIS_WA_CONTACTOS", os.path.join(os.path.expanduser("~"), ".jarvis", "contactos.json"))
BRIDGE_URL = os.environ.get("JARVIS_WA_BRIDGE_URL", "http://127.0.0.1:5015").rstrip("/")
BRIDGE_TOKEN = os.environ.get("JARVIS_WA_BRIDGE_TOKEN", "")

PLANTILLA_CONTACTOS = {
    "_ayuda": "Apodos -> números con código de país. Borra los ejemplos y pon "
              "los tuyos. Las claves que empiezan con _ se ignoran.",
    "_ejemplo": {"mama": "+51987654321", "luis": "+51999988887"},
}

MSG_BRIDGE_APAgado = ("🔌 El puente de WhatsApp no está corriendo. En una terminal:\n"
                      "    cd ~/Proyectos/JarvisBot/whatsapp_bridge && ./iniciar.sh\n"
                      "(la primera vez pide escanear un QR con tu WhatsApp).")

RESPUESTA_POR_DEFECTO = (
    "🤖 Aquí Jarvis. Desde este chat puedes pedirme:\n"
    "  • «mis notas»  /  «notas de <curso>»\n"
    "  • «mis mensajes» del aula\n"
    "  • «mi horario»  /  «mis cursos»\n"
    "  • «estado»  /  «envia whatsapp a <alguien>: texto»\n"
    "Si el aula responde sin datos, pídelo en la PC: «abre cibertec» "
    "(y si pide código SMS, corre antes `python3 login_unificado.py`).")


def _norm(texto: str) -> str:
    """minúsculas + sin acentos; conserva : y signos para partir la frase."""
    t = (texto or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s:,\.\-!\?¡¿'\"]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ─────────────────────────────────────────────────────────────
# Contactos (~/.jarvis/contactos.json)
# ─────────────────────────────────────────────────────────────

def contactos():
    """Lee (y crea si falta) el archivo de contactos. Devuelve dict apodo->número."""
    if not os.path.isfile(RUTA_CONTACTOS):
        try:
            os.makedirs(os.path.dirname(RUTA_CONTACTOS), exist_ok=True)
            with open(RUTA_CONTACTOS, "w", encoding="utf-8") as f:
                json.dump(PLANTILLA_CONTACTOS, f, ensure_ascii=False, indent=2)
        except Exception:
            return {}
    try:
        with open(RUTA_CONTACTOS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and str(v).strip()}


def _norm_apodo(s):
    return _norm(s).replace(" ", "")


def resolver(nombre):
    """apodo aproximado -> (clave_real, numero) o None."""
    agenda = contactos()
    if not agenda or not nombre:
        return None
    q = _norm_apodo(nombre)
    if not q:
        return None
    if q in agenda:
        return q, str(agenda[q])
    claves = {_norm_apodo(k): k for k in agenda}
    cerca = difflib.get_close_matches(q, list(claves), n=1, cutoff=0.75)
    if cerca:
        real = claves[cerca[0]]
        return real, str(agenda[real])
    for nk, real in claves.items():
        if q in nk or nk in q:
            return real, str(agenda[real])
    return None


def _normalizar_numero(num):
    """+51 999 888 777 -> 51999888777 (lo que espera WhatsApp: <codigo><numero>)."""
    return re.sub(r"\D", "", str(num))


def guardar_contacto(apodo, numero):
    """Añade/reemplaza un contacto y confirma. Devuelve str para el chat."""
    agenda = contactos()
    if not os.path.isfile(RUTA_CONTACTOS):
        agenda = dict(PLANTILLA_CONTACTOS)
    try:
        with open(RUTA_CONTACTOS, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = dict(PLANTILLA_CONTACTOS)
    limpio = _normalizar_numero(numero)
    if len(limpio) < 9:
        return f"«{numero}» no parece un teléfono con código de país. Ej: +51999888777"
    raw[apodo.strip().lower()] = "+" + limpio
    try:
        os.makedirs(os.path.dirname(RUTA_CONTACTOS), exist_ok=True)
        with open(RUTA_CONTACTOS, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"No pude escribir {RUTA_CONTACTOS}: {e}"
    return f"Contacto guardado: {apodo.strip().lower()} -> +{limpio}"


# ─────────────────────────────────────────────────────────────
# Puente Node (whatsapp_bridge/server.js)
# ─────────────────────────────────────────────────────────────

def _get(path, timeout=8):
    req = urllib.request.Request(BRIDGE_URL + path,
                                 headers={"X-Jarvis-Token": BRIDGE_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _post(path, data, timeout=25):
    req = urllib.request.Request(
        BRIDGE_URL + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "X-Jarvis-Token": BRIDGE_TOKEN},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _error_bridge(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            detalle = json.loads(e.read().decode("utf-8", "replace")).get("error", "")
        except Exception:
            detalle = ""
        if e.code == 401:
            return "🔒 El puente de WhatsApp rechazó el token (JARVIS_WA_BRIDGE_TOKEN en .env y en el entorno del puente)."
        if e.code == 409 or e.code == 503 or "qr" in detalle.lower():
            return ("📱 WhatsApp todavía no tiene sesión: escanea el QR del puente "
                    "(en la terminal, o abre http://127.0.0.1:5015/qr?t=TU_TOKEN).")
        return f"El puente de WhatsApp respondió {e.code}: {detalle}"
    if isinstance(e, urllib.error.URLError) or isinstance(e, ConnectionError) or isinstance(e, OSError):
        return MSG_BRIDGE_APAgado
    return f"No pude hablar con el puente de WhatsApp: {e}"


def estado():
    try:
        d = _get("/status")
    except Exception as e:
        return _error_bridge(e)
    if d.get("ready"):
        info = d.get("info") or {}
        return (f"✅ WhatsApp conectado con tu número "
                f"({info.get('pushname') or info.get('wid') or 'sesión local'}).")
    if d.get("iniciando"):
        return ("⏳ El puente está arrancando WhatsApp. Si es la primera vez, "
                "escanea el QR que imprime la terminal.")
    return "📱 WhatsApp sin sesión: escanea el QR del puente (terminal o /qr)."


def _mi_numero():
    """Tu propio número (wid del puente) o "" si aún no hay sesión."""
    try:
        d = _get("/status")
        return str((d.get("info") or {}).get("wid") or "")
    except Exception:
        return ""


def _es_yo(destinatario):
    """True si el destinatario es uno mismo («yo», «mi», «mismo»)."""
    return _norm_apodo(destinatario or "") in ("yo", "mi", "mismo", "mimeamo")


def enviar(destinatario, mensaje):
    """Envía `mensaje` al contacto/número. Devuelve str para el chat."""
    destino = None
    if _es_yo(destinatario):
        destino = _mi_numero()
        if not destino:
            return "No sé todavía cuál es tu número (¿el puente ya arrancó?)."
    elif destinatario:
        res = resolver(destinatario)
        if res:
            destino = _normalizar_numero(res[1])
        elif _normalizar_numero(destinatario):
            destino = _normalizar_numero(destinatario)
    if not destino or len(destino) < 9:
        return (f"No tengo a «{destinatario}» en {RUTA_CONTACTOS}.\n"
                f"Agrega: «guarda contacto {destinatario} +51999888777».")
    if not (mensaje or "").strip():
        return "¿Qué mensaje quieres que le mande?"
    try:
        d = _post("/send", {"to": destino, "message": mensaje})
    except Exception as e:
        return _error_bridge(e)
    if d.get("ok"):
        return f"📤 Enviado por WhatsApp a {destinatario}: «{mensaje}»"
    return f"El puente no confirmó el envío: {d}"


def listar_contactos():
    agenda = contactos()
    if not agenda:
        return ("Tu agenda está vacía. Ejemplo:\n"
                "  «guarda contacto mama +51987654321»")
    lineas = [f"  • {k}: {v}" for k, v in sorted(agenda.items())]
    return "📇 Tus contactos de WhatsApp:\n" + "\n".join(lineas)


# ─────────────────────────────────────────────────────────────
# Parser de frases (fast-path del cerebro)
# ─────────────────────────────────────────────────────────────

_APP = r"(?:whats\s?app|wsp|wasap|wasapea|whatsapp)"
_RE_ENVIA = re.compile(
    rf"^(?:manda|mandar|envia|enviar|escribe|escribir|escribele|mandale|enviale|"
    rf"saluda|pasa)\s+(?:un\s+|una\s+|le\s+|por\s+|el\s+)*{_APP}\b\s*(?:a\s+|al\s+|para\s+|de\s+)?(.+)$")
_RE_APP_DESNUDA = re.compile(rf"^{_APP}\s+(?:a\s+|para\s+)(.+)$")
_RE_ESTADO = re.compile(
    rf"^(?:estado|status|conexion)\s+(?:del?\s+)?(?:de\s+)?{_APP}\b"
    rf"|^{_APP}\s+(?:estado|status)\b"
    rf"|^(?:esta|estas|sigue)\s+(?:el\s+)?{_APP}\s+(?:conectado|andando|vivo|funcionando)"
    rf"|^sabes\s+si\s+{_APP}\s+(?:esta\s+)?(?:conectado|andando)")
_RE_CONTACTOS = re.compile(r"^(?:mis\s+contactos|los\s+contactos|contactos|agenda)"
                           r"(?:\s+(?:de\s+)?(?:whatsapp|wsp|wasap))?$")
_RE_GUARDA = re.compile(r"^(?:guarda|agrega|añade|anade|registra)\s+(?:el\s+|un\s+)?"
                        r"contacto\s+(\S+)\s+(?:con\s+(?:el\s+)?)?(.+)$")
# separadores destinatario / mensaje
_RE_SEP = re.compile(r"\s+(?:diciendo|diciendole|dile|que|k)\s+(.+)$")

APP_PALABRAS = ("whatsapp", "whats app", "wsp", "wasap", "whats")

_KEPT_RE = re.compile(r"[\w\s:,\.\-!\?\u00a1\u00bf'\"]")


def _map_norm(texto):
    """(texto_normalizado, mapa): mapa[j] = índice del carácter j en el original.
    Igual que _norm() pero conservando dónde vive cada carácter, para poder
    recuperar el MENSAJE con sus tildes/ñ reales (lo que se envía)."""
    nfkd_por_caracter = (texto or "").lower()
    out, mapa = [], []
    for i, ch in enumerate(nfkd_por_caracter):
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            if _KEPT_RE.match(c):
                out.append(c)
            else:
                out.append(" ")
            mapa.append(i)  # índice en el TEXTO ORIGINAL, no en el NFKD
    # recorte de bordes
    ini, fin = 0, len(out)
    while ini < fin and out[ini] == " ":
        ini += 1
    while fin > ini and out[fin - 1] == " ":
        fin -= 1
    # colapso de espacios consecutivos
    res, rmap, prev = [], [], False
    for j in range(ini, fin):
        if out[j] == " ":
            if prev:
                continue
            prev = True
        else:
            prev = False
        res.append(out[j])
        rmap.append(mapa[j])
    return "".join(res), rmap


def _orig_slice(orig, mapa, a, b):
    """Trozo ORIGINAL equivalente a mapa[a:b] (con clamps)."""
    if not mapa or a >= len(mapa) or b <= a:
        return ""
    a = max(0, min(a, len(mapa) - 1))
    b = max(a + 1, min(b, len(mapa)))
    return orig[mapa[a]:mapa[b - 1] + 1]


def parse_mensaje(texto):
    """
    «manda un whatsapp a mama diciendo que ya llegué» ->
        {'destino': 'mama', 'mensaje': 'que ya llegué'}   (con tildes reales)
    Devuelve None si la frase no es un envío de WhatsApp.
    """
    orig = (texto or "")
    t, mapa = _map_norm(orig)
    if not t:
        return None
    m = _RE_ENVIA.match(t) or _RE_APP_DESNUDA.match(t)
    if not m:
        return None
    off = m.start(1)          # dónde empieza el «resto» dentro de t
    resto = m.group(1)

    destino_norm, msg = None, None
    # 1) dos puntos tras el destinatario: «mama: no te preocupes»
    if ":" in resto:
        c = resto.index(":")
        destino_norm = resto[:c].strip()
        j = off + c + 1
        while j < len(mapa) and t[j] == " ":
            j += 1
        msg = _orig_slice(orig, mapa, j, len(mapa)) if j < len(mapa) else ""
    else:
        # 2) «... diciendo que ...» / «... que ...» (primer separador gana)
        s = _RE_SEP.search(resto)
        if s:
            destino_norm = resto[:s.start()].strip()
            msg = _orig_slice(orig, mapa, off + s.start(1), off + s.end(1))
    if destino_norm is None:
        destino_norm = resto

    destino_norm = re.sub(r"\s+(?:un\s+)?saludo|hola|buenas$", "", destino_norm).strip()
    destino_norm = destino_norm.strip(",. ").strip('"\'')
    if msg is not None:
        msg = msg.strip().strip('"\'').strip()

    if not destino_norm or not msg:
        # «manda whatsapp a mama» sin mensaje -> no es un envío completo
        return None
    destino = re.sub(r"^(?:el|la|los|las|mi|un|una)\s+", "", destino_norm).strip()
    return {"destino": destino, "mensaje": msg}


def intentar(texto):
    """Fast-path del cerebro: str si la frase es mía, None si no."""
    t = _norm(texto)
    if not t:
        return None
    # guarda contacto (antes que nada, para no chocar con «manda»)
    m = _RE_GUARDA.match(t)
    if m:
        return guardar_contacto(m.group(1), m.group(2))
    if _RE_CONTACTOS.match(t):
        return listar_contactos()
    if _RE_ESTADO.match(t):
        return estado()
    p = parse_mensaje(texto)
    if p:
        return enviar(p["destino"], p["mensaje"])
    return None


# ─────────────────────────────────────────────────────────────
# Escucha tu chat propio: te escribes desde el celular y Jarvis responde
# ─────────────────────────────────────────────────────────────

def _modulo_cibertec():
    """cibertec_bridge si se puede importar (corre desde la raíz del repo)."""
    try:
        import cibertec_bridge
        return cibertec_bridge
    except Exception:
        return None


def responder_como_jarvis(texto, cb=None):
    """Respuesta de Jarvis a un mensaje escrito en TU chat propio.
    Orden: comandos WhatsApp -> aula CIBERTEC -> menú de ayuda."""
    if not _norm(texto):
        return None
    r = intentar(texto)  # estado, agenda, envíos, guarda contacto…
    if r:
        return r
    if cb is None:
        cb = _modulo_cibertec()
    if cb is not None:
        try:
            r = cb.intentar(texto)  # notas / mensajes / horario / cursos
            if r:
                return r
        except Exception:
            pass
    return RESPUESTA_POR_DEFECTO


def procesar_mensajes(mensajes, vistos, cb=None, enviar_fn=None):
    """Procesa la lista {id, ts, texto} que trae el puente; responde UNA vez
    por id (vistos: deque de ids ya contestados). Devuelve el mayor ts visto."""
    enviar_fn = enviar_fn or (lambda txt: enviar("yo", txt))
    ultimo_ts = 0
    for m in mensajes or []:
        mid = str(m.get("id") or "")
        ts = int(m.get("ts") or 0)
        texto = str(m.get("texto") or "").strip()
        ultimo_ts = max(ultimo_ts, ts)
        if not texto or not mid or mid in vistos:
            continue
        vistos.append(mid)
        r = responder_como_jarvis(texto, cb=cb)
        if r:
            print(f"   🤖 respondo: {str(r).splitlines()[0][:60]}", flush=True)
            salida = enviar_fn(r)
            print(f"      {str(salida).splitlines()[0][:90]}", flush=True)
    return ultimo_ts


def escuchar():
    """Bucle: lee TU chat propio desde el puente y responde como Jarvis.
    Escríbete «ayuda» desde el celular para ver qué entiende."""
    import collections
    import time
    print("👂 Jarvis escucha tu chat propio. Escríbete «ayuda» desde el celular "
          "(Ctrl+C para salir).", flush=True)
    vistos = collections.deque(maxlen=200)
    desde = int(time.time())
    cb = _modulo_cibertec()
    aviso_puente = False
    while True:
        try:
            d = _get(f"/mensajes?desde={desde}", timeout=15)
            aviso_puente = False
            nuevo = procesar_mensajes(d.get("mensajes"), vistos, cb=cb)
            if nuevo > desde:
                desde = nuevo
        except KeyboardInterrupt:
            raise
        except Exception:
            if not aviso_puente:
                print(MSG_BRIDGE_APAgado, flush=True)
                aviso_puente = True
        time.sleep(3)


# ─────────────────────────────────────────────────────────────
# Herramientas para el LLM (ReAct)
# ─────────────────────────────────────────────────────────────

def _tool_whatsapp_enviar(destinatario="", mensaje="", *_a):
    return enviar(destinatario, mensaje)


def _tool_whatsapp_estado(*_a):
    return estado()


def registrar():
    """Dict de herramientas extra para SystemTools.actions."""
    return {
        "whatsapp_enviar": _tool_whatsapp_enviar,
        "whatsapp_estado": _tool_whatsapp_estado,
    }


# ─────────────────────────────────────────────────────────────
# CLI manual
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]
        if cmd == "estado":
            print(estado())
        elif cmd == "contactos":
            print(listar_contactos())
        elif cmd == "guarda" and len(sys.argv) >= 4:
            print(guardar_contacto(sys.argv[2], sys.argv[3]))
        elif cmd == "enviar" and len(sys.argv) >= 4:
            print(enviar(sys.argv[2], sys.argv[3]))
        elif cmd == "escuchar":
            escuchar()
        else:
            print(__doc__)
    else:
        print(__doc__)
