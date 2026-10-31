#!/usr/bin/env python3
"""
test_whatsapp.py — pruebas de jarvis_whatsapp.py SIN Node, SIN WhatsApp y SIN red:
  - parser de frases (parse_mensaje / intentar)
  - agenda de contactos en un directorio temporal
  - puente HTTP FALSO (http.server en un hilo) para enviar()/estado()
Corre en cualquier sitio:
    python3 test_whatsapp.py -v
"""
import collections
import importlib
import json
import os
import re
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

TMP = tempfile.mkdtemp(prefix="test_wa_")
os.environ["JARVIS_WA_CONTACTOS"] = os.path.join(TMP, "contactos.json")
os.environ["JARVIS_WA_BRIDGE_URL"] = "http://127.0.0.1:0"  # se reconfigura por test
os.environ["JARVIS_WA_BRIDGE_TOKEN"] = "secreto-test"

import jarvis_whatsapp as wa  # noqa: E402


# ─────────────────────────────────────────────────────────────
# Puente HTTP falso
# ─────────────────────────────────────────────────────────────

class PuenteFalso(BaseHTTPRequestHandler):
    """Imita server.js: /status y /send con token. Modo por variable de clase."""
    modo = "ok"  # ok | sin_sesion | qr

    def log_message(self, *a):  # silencioso
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _autorizado(self):
        return self.headers.get("X-Jarvis-Token") == "secreto-test"

    def do_GET(self):
        if not self._autorizado():
            return self._json(401, {"error": "token invalido"})
        if self.path.startswith("/status"):
            if PuenteFalso.modo == "ok":
                return self._json(200, {"ready": True, "iniciando": False,
                                        "conQR": False,
                                        "info": {"pushname": "Marc", "wid": "51999999999"}})
            return self._json(200, {"ready": False, "iniciando": False, "conQR": True,
                                    "info": None})
        self._json(404, {"error": "ruta"})

    def do_POST(self):
        if not self._autorizado():
            return self._json(401, {"error": "token invalido"})
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        if self.path.startswith("/send"):
            if PuenteFalso.modo != "ok":
                return self._json(503, {"error": "WhatsApp todavia no esta listo"})
            if len(re.sub(r"\D", "", str(data.get("to", "")))) < 9:
                return self._json(400, {"error": "numero invalido"})
            return self._json(200, {"ok": True, "chatId": f"{data.get('to')}@c.us",
                                    "id": "FAKE_1"})
        self._json(404, {"error": "ruta"})


class BaseWa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), PuenteFalso)
        cls.puerto = cls.servidor.server_address[1]
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def setUp(self):
        PuenteFalso.modo = "ok"
        os.environ["JARVIS_WA_BRIDGE_URL"] = f"http://127.0.0.1:{self.puerto}"
        # contactos limpios por test
        with open(os.environ["JARVIS_WA_CONTACTOS"], "w", encoding="utf-8") as f:
            json.dump({"mama": "+51987654321", "luis": "+51999888777"}, f)
        importlib.reload(wa)


# ─────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────

class TestParser(BaseWa):
    CASOS_OK = [
        ("manda un whatsapp a mama diciendo que ya llegue",
         {"destino": "mama", "mensaje": "que ya llegue"}),
        ("manda whatsapp a mama: no te preocupes",
         {"destino": "mama", "mensaje": "no te preocupes"}),
        ("enviale un wsp a luis que mañana hay examen",
         {"destino": "luis", "mensaje": "mañana hay examen"}),
        ("whatsapp a mama dile hola",
         {"destino": "mama", "mensaje": "hola"}),
        ("escribe un wasap a luis k me esperes afuera",
         {"destino": "luis", "mensaje": "me esperes afuera"}),
        ("manda un whatsapp al 51999888777 diciendo prueba",
         {"destino": "51999888777", "mensaje": "prueba"}),
        ("Manda un WhatsApp a mamá diciendo que ya llegué",
         {"destino": "mama", "mensaje": "que ya llegué"}),
    ]

    def test_parseos_validos(self):
        for frase, esperado in self.CASOS_OK:
            with self.subTest(frase=frase):
                p = wa.parse_mensaje(frase)
                self.assertIsNotNone(p, frase)
                self.assertEqual(p["destino"], esperado["destino"], frase)
                self.assertEqual(p["mensaje"], esperado["mensaje"], frase)

    CASOS_NO = [
        "pon musica de anime",
        "manda un whatsapp a mama",          # sin mensaje -> no es envío completo
        "whatsapp",
        "abre whatsapp web en firefox",
        "cual es el estado del clima",
        "manda un correo a mama diciendo hola",
    ]

    def test_frases_que_no_son_suyas(self):
        for frase in self.CASOS_NO:
            with self.subTest(frase=frase):
                self.assertIsNone(wa.parse_mensaje(frase), frase)

    def test_intentar_devuelve_none_en_frases_ajenas(self):
        self.assertIsNone(wa.intentar("pon la playlist de focas"))


# ─────────────────────────────────────────────────────────────
# Contactos
# ─────────────────────────────────────────────────────────────

class TestContactos(BaseWa):
    def test_resolver_exacto_fuzzy_subcadena(self):
        self.assertEqual(wa.resolver("mama"), ("mama", "+51987654321"))
        self.assertIsNotNone(wa.resolver("mami"))      # fuzzy
        self.assertEqual(wa.resolver("luis")[0], "luis")
        self.assertIsNone(wa.resolver("desconocido"))

    def test_guardar_contacto(self):
        r = wa.guardar_contacto("ana", "51 987 654 321")
        self.assertIn("Contacto guardado", r)
        self.assertEqual(wa.resolver("ana"), ("ana", "+51987654321"))

    def test_guardar_contacto_invalido(self):
        r = wa.guardar_contacto("x", "123")
        self.assertIn("no parece", r)

    def test_listar(self):
        r = wa.intentar("mis contactos")
        self.assertIn("mama", r)
        self.assertIn("luis", r)

    def test_guarda_por_frase(self):
        r = wa.intentar("guarda contacto papa +51987000123")
        self.assertIn("Contacto guardado", r)
        self.assertEqual(wa.resolver("papa"), ("papa", "+51987000123"))

    def test_plantilla_autocreada(self):
        os.remove(os.environ["JARVIS_WA_CONTACTOS"])
        agenda = wa.contactos()  # recrea la plantilla
        self.assertEqual(agenda, {})


# ─────────────────────────────────────────────────────────────
# Envío (puente falso)
# ─────────────────────────────────────────────────────────────

class TestEnvio(BaseWa):
    def test_enviar_ok(self):
        r = wa.enviar("mama", "prueba desde jarvis")
        self.assertIn("Enviado", r)
        self.assertIn("mama", r)

    def test_enviar_frase_completa(self):
        r = wa.intentar("manda un whatsapp a luis diciendo nos vemos")
        self.assertIn("Enviado", r)
        self.assertIn("luis", r)

    def test_contacto_desconocido(self):
        r = wa.enviar("fulanito", "hola")
        self.assertIn("No tengo", r)
        self.assertIn("guarda contacto", r)

    def test_mensaje_vacio(self):
        r = wa.enviar("mama", "   ")
        self.assertIn("¿Qué mensaje", r)

    def test_puente_apagado(self):
        os.environ["JARVIS_WA_BRIDGE_URL"] = "http://127.0.0.1:1"
        importlib.reload(wa)
        r = wa.enviar("mama", "hola")
        self.assertIn("no está corriendo", r)

    def test_token_incorrecto(self):
        os.environ["JARVIS_WA_BRIDGE_TOKEN"] = "otro-token"
        importlib.reload(wa)
        r = wa.enviar("mama", "hola")
        self.assertIn("rechazó el token", r)
        os.environ["JARVIS_WA_BRIDGE_TOKEN"] = "secreto-test"

    def test_sin_sesion_qr(self):
        PuenteFalso.modo = "sin_sesion"
        r = wa.enviar("mama", "hola")
        self.assertIn("QR", r)

    def test_estado_conectado(self):
        r = wa.intentar("estado de whatsapp")
        self.assertIn("conectado", r)

    def test_estado_sin_sesion(self):
        PuenteFalso.modo = "sin_sesion"
        r = wa.intentar("whatsapp estado")
        self.assertIn("QR", r)


# ─────────────────────────────────────────────────────────────
# Hablarse a sí mismo: enviar a «yo» + escucha del chat propio
# ─────────────────────────────────────────────────────────────

class TestYoYEscucha(BaseWa):
    def test_enviar_a_yo_usa_el_wid_del_puente(self):
        r = wa.enviar("yo", "nota mental")
        self.assertIn("Enviado", r)

    def test_es_yo_variantes(self):
        self.assertTrue(wa._es_yo("yo"))
        self.assertTrue(wa._es_yo("  Yo "))
        self.assertTrue(wa._es_yo("mismo"))
        self.assertFalse(wa._es_yo("mama"))

    def test_mi_numero_vacio_si_puente_muerto(self):
        os.environ["JARVIS_WA_BRIDGE_URL"] = "http://127.0.0.1:1"
        importlib.reload(wa)
        self.assertEqual(wa._mi_numero(), "")
        self.assertIn("no puedo enviarte a ti mismo", wa.enviar("yo", "hola").lower())

    def _fake_cb(self, resp):
        return types.SimpleNamespace(intentar=lambda t: resp)

    def test_responder_prioriza_comandos_whatsapp(self):
        r = wa.responder_como_jarvis("mis contactos", cb=self._fake_cb("NO"))
        self.assertIn("mama", r)

    def test_responder_consulta_del_aula(self):
        r = wa.responder_como_jarvis("mis notas", cb=self._fake_cb("NOTAS-FAKE"))
        self.assertEqual(r, "NOTAS-FAKE")

    def test_responder_por_defecto_ayuda(self):
        r = wa.responder_como_jarvis("hazme un sandwich", cb=self._fake_cb(None))
        self.assertEqual(r, wa.RESPUESTA_POR_DEFECTO)

    def test_procesar_responde_una_sola_vez_por_id(self):
        vistos = collections.deque(maxlen=50)
        enviados = []
        cb = types.SimpleNamespace(
            intentar=lambda t: "NOTAS-FAKE" if "notas" in t else None)
        ts = wa.procesar_mensajes(
            [{"id": "A", "ts": 100, "texto": "mis notas"},
             {"id": "A", "ts": 100, "texto": "mis notas"},   # duplicado
             {"id": "B", "ts": 105, "texto": "hola"},
             {"id": "C", "ts": 110, "texto": ""}],           # sin texto
            vistos, cb=cb, enviar_fn=enviados.append)
        self.assertEqual(ts, 110)
        self.assertEqual(enviados, ["NOTAS-FAKE", wa.RESPUESTA_POR_DEFECTO])

    def test_procesar_lista_vacia(self):
        enviados = []
        ts = wa.procesar_mensajes([], collections.deque(),
                                  enviar_fn=enviados.append)
        self.assertEqual(ts, 0)
        self.assertEqual(enviados, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
