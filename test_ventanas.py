#!/usr/bin/env python3
"""
test_ventanas.py — pruebas de jarvis_windows.py y jarvis_skills_bridge.py
con un hyprctl FALSO (sin Hyprland, sin X, sin nada). Corre en cualquier sitio:
    python3 test_ventanas.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from jarvis_windows import Ventanas, parse_mover  # noqa: E402
import jarvis_skills_bridge as bridge  # noqa: E402

CLIENTES = [
    {"address": "0x1", "class": "firefox", "initialClass": "firefox",
     "title": "YouTube — Mozilla Firefox", "mapped": True, "focused": False,
     "pid": 111, "workspace": {"id": 2, "name": "2"}},
    {"address": "0x2", "class": "kitty", "initialClass": "kitty",
     "title": "~/proyectos — kitty", "mapped": True, "focused": True,
     "pid": 222, "workspace": {"id": 2, "name": "2"}},
    {"address": "0x3", "class": "Spotify", "initialClass": "spotify",
     "title": "Spotify Premium", "mapped": True, "focused": False,
     "pid": 333, "workspace": {"id": 3, "name": "3"}},
    {"address": "0x4", "class": "org.kde.kcalc", "initialClass": "kcalc",
     "title": "Calculadora", "mapped": True, "focused": False,
     "pid": 444, "workspace": {"id": 1, "name": "1"}},
    {"address": "0x5", "class": "Code", "initialClass": "code-oss",
     "title": "assistant.py - Visual Studio Code", "mapped": True,
     "focused": False, "pid": 555, "workspace": {"id": 4, "name": "4"}},
    {"address": "0x6", "class": "steam_app_570", "initialClass": "steam_app_570",
     "title": "Dota 2", "mapped": True, "focused": False,
     "pid": 666, "workspace": {"id": 5, "name": "5"}},
    {"address": "0x7", "class": "", "initialClass": "", "title": "zzz",
     "mapped": False, "pid": 0, "workspace": {"id": -1, "name": ""}},
]


# hyprctl FALSO autocontenido (el test NO depende de rutas externas)
FAKE_HYPRCTL = r'''#!/usr/bin/env bash
# hyprctl FALSO para probar jarvis_windows.py sin Hyprland.
set -u
LOG="${FAKE_HYPR_LOG:-/tmp/fake_hyprctl.log}"
echo "CMD: $*" >> "$LOG"
if [[ "${1:-}" == "-j" ]]; then
  case "${2:-}" in
    clients)
      cat "${FAKE_CLIENTS_JSON:?define FAKE_CLIENTS_JSON}"; exit 0;;
    activeworkspace)
      echo '{"id":2,"name":"2"}'; exit 0;;
    activewindow)
      echo '{"address":"0x2","class":"kitty","initialClass":"kitty","title":"~/proyectos","mapped":true,"focused":true,"workspace":{"id":2,"name":"2"},"pid":123}'; exit 0;;
  esac
fi
if [[ "${FAKE_FAIL_DISPATCH:-0}" == "1" && "${1:-}" == "dispatch" ]]; then
  echo "invalid dispatcher"; exit 0
fi
echo "ok"
'''


class BaseConFakeHyprctl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis_test_")
        self.clients_json = os.path.join(self.tmp, "clients.json")
        with open(self.clients_json, "w", encoding="utf-8") as f:
            json.dump(CLIENTES, f)
        self.log = os.path.join(self.tmp, "hypr.log")
        self.bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin_dir)
        fake = os.path.join(self.bin_dir, "hyprctl")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(FAKE_HYPRCTL)
        os.chmod(fake, 0o755)
        self.env = dict(os.environ)
        self.env["PATH"] = self.bin_dir + os.pathsep + self.env["PATH"]
        self.env["FAKE_CLIENTS_JSON"] = self.clients_json
        self.env["FAKE_HYPR_LOG"] = self.log
        self.ventanas = Ventanas()

    def _correr_en_env(self, fn, *a, **k):
        """Ejecuta fn parcheando subprocess para usar nuestro PATH fake."""
        real_run = subprocess.run
        real_popen = subprocess.Popen

        def run_fake(argv, *aa, **kk):
            if argv and argv[0] == "hyprctl":
                argv = [os.path.join(self.bin_dir, "hyprctl")] + list(argv[1:])
                kk["env"] = self.env
            return real_run(argv, *aa, **kk)

        def popen_fake(argv, *aa, **kk):
            if argv and argv[0] in ("hyprctl", "hyprctl "):
                argv = [os.path.join(self.bin_dir, "hyprctl")] + list(argv[1:])
                kk["env"] = self.env
            return real_popen(argv, *aa, **kk)

        subprocess.run = run_fake
        subprocess.Popen = popen_fake
        try:
            return fn(*a, **k)
        finally:
            subprocess.run = real_run
            subprocess.Popen = real_popen

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestParseMover(unittest.TestCase):
    def _ok(self, frase, accion, app, ws, follow=False):
        r = parse_mover(frase)
        self.assertIsNotNone(r, f"debería parsear: {frase}")
        self.assertEqual(r["accion"], accion, frase)
        self.assertEqual(r["app"], app, frase)
        self.assertEqual(r["ws"], ws, frase)
        self.assertEqual(r.get("follow", False), follow, frase)

    def _none(self, frase):
        self.assertIsNone(parse_mover(frase), f"NO debería parsear: {frase}")

    def test_formas_basicas(self):
        self._ok("mueve spotify al workspace 3", "mover", "spotify", "3")
        self._ok("mueve spotify al 3", "mover", "spotify", "3")
        self._ok("mover firefox al 2", "mover", "firefox", "2")
        self._ok("manda spotify al 3", "mover", "spotify", "3")
        self._ok("pasa el spotify al 3", "mover", "spotify", "3")
        self._ok("lleva la ventana de spotify al 3", "mover", "spotify", "3")
        self._ok("mueve la ventana de firefox al workspace 4", "mover", "firefox", "4")

    def test_variantes_que_antes_fallaban(self):
        # estas frases eran las que provocaban el «burro»:
        self._ok("mueves firefox al 2", "mover", "firefox", "2")
        self._ok("mueva spotify al 3", "mover", "spotify", "3")
        self._ok("mueven spotify al 3", "mover", "spotify", "3")
        self._ok("envia spotify al workspace 3", "mover", "spotify", "3")
        self._ok("devuelve firefox al 2", "mover", "firefox", "2")
        self._ok("mueve spotify al 3 conmigo", "mover", "spotify", "3", follow=True)
        self._ok("mueve spotify al 3 y estate siguiendo", "mover", "spotify", "3", follow=True)

    def test_destinos_especiales(self):
        self._ok("mueve firefox al siguiente", "mover", "firefox", "e+1")
        self._ok("mueve firefox al anterior", "mover", "firefox", "e-1")
        self._ok("lleva kitty al escritorio de juegos", "mover", "kitty", "juegos")
        self._ok("mueve kitty al escritorio 3", "mover", "kitty", "3")
        self._ok("mueve spotify al workspace numero 4", "mover", "spotify", "4")
        self._ok("mueve spotify a la 3", "mover", "spotify", "3")
        self._ok("mueve dota 2 al 5", "mover", "dota 2", "5")

    def test_traer(self):
        self._ok("trae spotify", "traer", "spotify", None, follow=True)
        self._ok("traeme el firefox", "traer", "firefox", None, follow=True)
        self._ok("trae firefox aqui", "traer", "firefox", None, follow=True)
        # trae + destino explícito → mover siguiendo
        self._ok("trae firefox al 3", "mover", "firefox", "3", follow=True)

    def test_guardas_no_ventana(self):
        self._none("sube el volumen")
        self._none("baja el brillo")
        self._none("mueve el raton a la esquina")
        self._none("mueve el mouse al centro")
        self._none("pon la pantalla completa")
        self._none("abre firefox")
        self._none("pon la playlist focus")
        self._none("que ventanas hay")

    def test_ambiguos_devuelven_none(self):
        self._none("mueve spotify")              # sin destino
        self._none("mueve spotify al chat")      # destino no-numérico sin keyword
        self._none("pasalo al 3")                # sin app (no sabemos cuál)
        self._none("organiza descargas")         # no es mover
        self._none("")


class TestResolver(BaseConFakeHyprctl):
    def test_clase_exacta_y_capitalizada(self):
        c = self._correr_en_env(self.ventanas.resolver, "spotify")
        self.assertEqual(c["address"], "0x3")
        c = self._correr_en_env(self.ventanas.resolver, "kitty")
        self.assertEqual(c["address"], "0x2")

    def test_titulo(self):
        c = self._correr_en_env(self.ventanas.resolver, "visual studio")
        self.assertEqual(c["address"], "0x5")
        c = self._correr_en_env(self.ventanas.resolver, "dota")
        self.assertEqual(c["address"], "0x6")
        c = self._correr_en_env(self.ventanas.resolver, "calculadora")
        self.assertEqual(c["address"], "0x4")

    def test_errata_fuzzy(self):
        c = self._correr_en_env(self.ventanas.resolver, "spotifi")
        self.assertEqual(c["address"], "0x3")

    def test_activa(self):
        c = self._correr_en_env(self.ventanas.resolver, "activa")
        self.assertEqual(c["address"], "0x2")

    def test_inexistente(self):
        c = self._correr_en_env(self.ventanas.resolver, "noexiste123")
        self.assertIsNone(c)


class TestAcciones(BaseConFakeHyprctl):
    def _log(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def test_listar(self):
        salida = self._correr_en_env(self.ventanas.listar)
        self.assertIn("6 ventana", salida)          # 7 clientes - 1 no mapeado
        self.assertIn("Workspace 2  ← donde estás", salida)
        self.assertIn("●foco", salida)
        self.assertIn("firefox — YouTube", salida)

    def test_mover(self):
        salida = self._correr_en_env(self.ventanas.mover, "spotify", "3")
        self.assertIn("movida al workspace 3", salida)
        self.assertIn("dispatch movetoworkspacesilent 3,address:0x3", self._log())

    def test_mover_conmigo_usa_movetoworkspace(self):
        self._correr_en_env(self.ventanas.mover, "spotify", "3", True)
        self.assertIn("dispatch movetoworkspace 3,address:0x3", self._log())

    def test_mover_inexistente_lista_abiertas(self):
        salida = self._correr_en_env(self.ventanas.mover, "zzz", "3")
        self.assertIn("No encontré", salida)
        self.assertIn("firefox", salida)

    def test_mover_siguiente(self):
        self._correr_en_env(self.ventanas.mover, "spotify", "siguiente")
        self.assertIn("dispatch movetoworkspacesilent e+1,address:0x3", self._log())

    def test_traer(self):
        salida = self._correr_en_env(self.ventanas.traer, "firefox")
        self.assertIn("Traje", salida)
        self.assertIn("dispatch movetoworkspacesilent 2,address:0x1", self._log())
        self.assertIn("dispatch focuswindow address:0x1", self._log())

    def test_cerrar(self):
        salida = self._correr_en_env(self.ventanas.cerrar, "spotify")
        self.assertIn("Cerré la ventana", salida)
        self.assertIn("dispatch closewindow address:0x3", self._log())

    def test_maximizar_y_minimizar(self):
        salida = self._correr_en_env(self.ventanas.maximizar)
        self.assertIn("Maximicé", salida)
        self.assertIn("dispatch fullscreen 1", self._log())
        salida = self._correr_en_env(self.ventanas.minimizar)
        self.assertIn("Minimizé", salida)
        self.assertIn("dispatch minimize", self._log())

    def test_dispatch_fallo_mensaje_honesto(self):
        self.env["FAKE_FAIL_DISPATCH"] = "1"
        salida = self._correr_en_env(self.ventanas.mover, "spotify", "3")
        self.assertIn("rechazó", salida)


class TestPuenteSkills(unittest.TestCase):
    """jarvis_skills_bridge con skills falsos en ~/.config/hypr/scripts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis_bridge_")
        self.skill_dir = os.path.join(self.tmp, "scripts")
        os.makedirs(self.skill_dir)
        self._escribir("jarvis-organizador.sh",
                       '#!/usr/bin/env bash\necho "MOVIDOS_HOY: 3 | PENDIENTES: 1"\n')
        self._escribir("jarvis-buscar",
                       '#!/usr/bin/env bash\n'
                       'if [[ "$1" == *zzz_no_hay* ]]; then echo "No encontré nada para $1";\n'
                       'else echo "/home/x/.config/hypr/$1.conf"; fi\n')
        self._escribir("jarvis-peli",
                       '#!/usr/bin/env bash\necho "PIPELINE OK: 0 entrada, 1 sub"\n')
        self._orig = (bridge.ORGANIZADOR, bridge.BUSCAR, bridge.PELI, bridge.SKILL_DIR)
        bridge.ORGANIZADOR = os.path.join(self.skill_dir, "jarvis-organizador.sh")
        bridge.BUSCAR = os.path.join(self.skill_dir, "jarvis-buscar")
        bridge.PELI = os.path.join(self.skill_dir, "jarvis-peli")
        bridge.SKILL_DIR = self.skill_dir
        # fake home para resolver_video
        self._orig_expanduser = os.path.expanduser
        home_fake = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(home_fake, "Descargas"))
        os.makedirs(os.path.join(home_fake, "Peliculas", "Entrada"))
        with open(os.path.join(home_fake, "Descargas", "dune.mkv"), "w") as f:
            f.write("x")
        self.home_fake = home_fake
        os.path.expanduser = lambda p: p.replace("~", home_fake)

    def _escribir(self, nombre, contenido):
        ruta = os.path.join(self.skill_dir, nombre)
        with open(ruta, "w") as f:
            f.write(contenido)
        os.chmod(ruta, 0o755)

    def tearDown(self):
        bridge.ORGANIZADOR, bridge.BUSCAR, bridge.PELI, bridge.SKILL_DIR = self._orig
        os.path.expanduser = self._orig_expanduser
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_organiza(self):
        self.assertIn("MOVIDOS_HOY", bridge.intentar("organiza"))
        self.assertIn("MOVIDOS_HOY", bridge.intentar("ordena descargas por favor"))

    def test_organiza_frase_ajena_no_roba(self):
        self.assertIsNone(bridge.intentar("ordena mis ideas sobre el proyecto"))

    def test_estados(self):
        self.assertIn("MOVIDOS_HOY", bridge.intentar("estado de descargas"))
        self.assertIn("PIPELINE OK", bridge.intentar("estado de pelis"))
        self.assertIn("PIPELINE OK", bridge.intentar("como van las peliculas"))

    def test_transcribe_resuelve_video(self):
        resp = bridge.intentar("transcribe dune")
        self.assertIn("Lanzado", resp)
        self.assertIn("dune.mkv", resp)

    def test_transcribe_video_inexistente(self):
        resp = bridge.intentar("transcribe pelicula_que_no_existe")
        self.assertIn("No encontré el vídeo", resp)

    def test_buscar(self):
        self.assertIn("hyprland.conf", bridge.buscar_termino("hyprland"))
        self.assertIsNone(bridge.buscar_termino("zzz_no_hay"))

    def test_registrar_herramientas(self):
        tools = bridge.registrar()
        self.assertIn("organize_downloads", tools)
        self.assertIn("find_file", tools)
        self.assertIn("peli_estado", tools)
        self.assertIn("PIPELINE OK", tools["peli_estado"]())


if __name__ == "__main__":
    unittest.main(verbosity=2)
