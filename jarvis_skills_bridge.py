"""
jarvis_skills_bridge.py v3 — Puente entre el cerebro (assistant.py) y tus skills
de JARVIS instalados en ~/.config/hypr/scripts/:

  - jarvis-organizador.sh   (organiza ~/Descargas, --stats)
  - jarvis-buscar           (¿dónde está X? — búsqueda real en disco)
  - jarvis-peli             (pipeline de pelis: estado / transcribir / quemar / prompt)

Expone:
  - intentar(texto) → str|None  : interpreta verbos de skills; None = "no es mío"
  - buscar_termino(t) → str|None: búsqueda en disco para la rama «donde esta»
  - registrar() → dict          : herramientas {nombre: fn} para el LLM (ReAct)

Solo stdlib. Sin Hyprland. 100% testeable fuera de tu máquina.
"""

import os
import re
import shlex
import subprocess
import unicodedata

SKILL_DIR = os.path.expanduser("~/.config/hypr/scripts")
ORGANIZADOR = os.path.join(SKILL_DIR, "jarvis-organizador.sh")
BUSCAR = os.path.join(SKILL_DIR, "jarvis-buscar")
PELI = os.path.join(SKILL_DIR, "jarvis-peli")


def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s\.\-\+]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ─────────────────────────────────────────────────────────────
# Ejecución
# ─────────────────────────────────────────────────────────────

def _disponible(ruta):
    return os.path.isfile(ruta) and os.access(ruta, os.X_OK)


def _correr(argv, timeout=25):
    """Corre un skill y devuelve su salida (o None si falta/no responde)."""
    if not (argv and _disponible(argv[0])):
        return None
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return (r.stdout or "").strip() or (r.stderr or "").strip() or None
    except Exception:
        return None


def lanzar_bg(argv, unidad="jarvis-skill"):
    """Lanza un skill largo (whisper, ffmpeg) en 2º plano con notificaciones."""
    env = dict(os.environ)
    env["JARVIS_NOTIFICAR"] = "1"
    if not (argv and _disponible(argv[0])):
        return "No encuentro el skill " + (argv[0] if argv else "(vacío)")
    stamp = subprocess.run(["date", "+%H%M%S"], capture_output=True, text=True)
    sufijo = (stamp.stdout or "").strip() or "bg"
    try:
        subprocess.Popen(
            ["systemd-run", "--user", "--unit", f"{unidad}-{sufijo}",
             "-E", "JARVIS_NOTIFICAR=1", *argv],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        return "Lanzado en 2º plano (systemd-run); te aviso con una notificación al terminar."
    except Exception:
        try:
            subprocess.Popen(
                ["nohup", "setsid", *argv],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            return "Lanzado en 2º plano; te aviso con una notificación al terminar."
        except Exception as e:
            return f"No pude lanzarlo en 2º plano: {e}"


# ─────────────────────────────────────────────────────────────
# Resolver rutas de vídeo para pelis
# ─────────────────────────────────────────────────────────────

def _resolver_video(nombre):
    """Busca el vídeo en ~/Descargas y en ~/Peliculas/Entrada."""
    nombre = nombre.strip().strip("'\"")
    if not nombre:
        return None
    if os.path.isfile(os.path.expanduser(nombre)):
        return os.path.expanduser(nombre)
    bases = ["~/Descargas", "~/Peliculas/Entrada"]
    for b in bases:
        base = os.path.expanduser(b)
        if not os.path.isdir(base):
            continue
        # coincidencia exacta
        p = os.path.join(base, nombre)
        if os.path.isfile(p):
            return p
        # coincidencia por subcadena (sin extensión, tolerante)
        aguja = _norm(os.path.splitext(nombre)[0])
        if not aguja:
            continue
        mejor = None
        for f in sorted(os.listdir(base)):
            if aguja in _norm(f) and not f.endswith((".srt", ".jpg", ".png", ".md")):
                mejor = os.path.join(base, f)
                break
        if mejor:
            return mejor
    return None


# ─────────────────────────────────────────────────────────────
# Interpretación de verbos
# ─────────────────────────────────────────────────────────────

_RE_ORGANIZA = re.compile(r"^(?:organiza|organizar|ordena|ordenar|limpia|limpiar)\b")
_RE_ESTADO_DESC = re.compile(
    r"(?:estado|status|como van|como va|resumen)\s+(?:de\s+)?(?:las\s+)?descargas"
    r"|^estado descargas$|^descargas estado$")
_RE_ESTADO_PELIS = re.compile(
    r"(?:estado|status|como van|como va|resumen)\s+(?:de\s+)?(?:las\s+)?pel[ií]culas?\b"
    r"|(?:estado|status)\s+(?:de\s+)?(?:las\s+)?pelis\b"
    r"|(?:estado|status)\s+(?:del\s+)?pipeline")
_RE_TRANSCRIBE = re.compile(r"^(?:transcribe|transcribir|subtitula|subtítulos?\s+de)\s+(?:el\s+|la\s+|los\s+|las\s+)?(.+)$")
_RE_QUEMA = re.compile(r"^(?:quema|quemar|hardsub|incorpora?r?\s+subt[ií]tulos?)\s+(?:el\s+|la\s+)?(.+)$")
_RE_PROMPT = re.compile(r"^(?:prompt|genera\s+prompt|prompt\s+pelis)\b(.*)$")
_RE_DONDE = re.compile(
    r"^(?:donde\s+esta|donde\s+guarde|donde\s+dej[eo])\s+(?:el|la|los|las|mi|un|una)?\s*(.+)$")


def intentar(texto):
    """
    Devuelve la respuesta de un skill si la frase le pertenece,
    o None si ninguna rama aplica (el cerebro sigue con lo suyo).
    """
    t = _norm(texto)
    if not t:
        return None

    # ── organizar descargas ──
    # Solo si habla de descargas/archivos/carpeta… o el verbo va desnudo
    # (evita robar frases como «ordena mis ideas» → se las deja al LLM).
    if _RE_ORGANIZA.match(t):
        desnudo = t in ("organiza", "organizar", "ordena", "ordenar")
        contexto = any(w in t for w in (
            "descarga", "archivo", "carpeta", "comprimido", "barrido",
            "papelera", "todo", "limpio", "limpia"))
        if desnudo or contexto:
            if not _disponible(ORGANIZADOR):
                return ("No tengo el organizador instalado "
                        "(~/.config/hypr/scripts/jarvis-organizador.sh).")
            if "estado" in t or "stats" in t:
                salida = _correr([ORGANIZADOR, "--stats"])
                return salida or "No pude leer el estado del organizador."
            salida = _correr([ORGANIZADOR], timeout=60)
            return salida or "Organizador ejecutado sin salida."

    # ── estado de descargas ──
    if _RE_ESTADO_DESC.search(t):
        if not _disponible(ORGANIZADOR):
            return "No tengo el organizador instalado."
        salida = _correr([ORGANIZADOR, "--stats"])
        return salida or "No pude leer el estado de las descargas."

    # ── estado de pelis ──
    if _RE_ESTADO_PELIS.search(t):
        if not _disponible(PELI):
            return "No tengo jarvis-peli instalado."
        salida = _correr([PELI, "estado"])
        return salida or "No pude leer el estado del pipeline de pelis."

    # ── transcribir (2º plano) ──
    m = _RE_TRANSCRIBE.match(t)
    if m:
        if not _disponible(PELI):
            return "No tengo jarvis-peli instalado."
        video = _resolver_video(m.group(1))
        if not video:
            return (f"No encontré el vídeo «{m.group(1).strip()}» en "
                    f"~/Descargas ni en ~/Peliculas/Entrada.")
        return lanzar_bg([PELI, "transcribir", video], unidad="jarvis-transcribe") \
            + f"\nVídeo: {os.path.basename(video)}"

    # ── quemar subtítulos (2º plano) ──
    m = _RE_QUEMA.match(t)
    if m:
        if not _disponible(PELI):
            return "No tengo jarvis-peli instalado."
        resto = m.group(1).strip()
        srt = None
        mcon = re.search(r"\s+con\s+(?:el\s+|la\s+)?(.+)$", resto)
        if mcon:
            srt = mcon.group(1).strip()
            resto = resto[:mcon.start()].strip()
        video = _resolver_video(resto)
        if not video:
            return (f"No encontré el vídeo «{resto}» en ~/Descargas "
                    f"ni en ~/Peliculas/Entrada.")
        argv = [PELI, "quemar", video]
        if srt:
            argv += ["con", srt]
        return lanzar_bg(argv, unidad="jarvis-quema") \
            + f"\nVídeo: {os.path.basename(video)}"

    # ── prompt para la IA potente ──
    m = _RE_PROMPT.match(t)
    if m:
        if not _disponible(PELI):
            return "No tengo jarvis-peli instalado."
        args = m.group(1).strip()
        argv = [PELI, "prompt"] + (shlex.split(args) if args else [])
        salida = _correr(argv, timeout=20)
        return salida or "No pude generar el prompt (mira la terminal de jarvis-peli)."

    return None


def buscar_termino(termino):
    """
    Búsqueda real en disco para «¿dónde está X?».
    Devuelve str si hay resultados; None si el skill no existe o no encontró nada
    (así el cerebro cae a su historial de archivos).
    """
    termino = (termino or "").strip()
    if not termino or not _disponible(BUSCAR):
        return None
    salida = _correr([BUSCAR, termino], timeout=25)
    if not salida:
        return None
    if "no encontr" in salida.lower() or "ningun" in salida.lower():
        return None
    return salida


# ─────────────────────────────────────────────────────────────
# Herramientas para el LLM (ReAct)
# ─────────────────────────────────────────────────────────────

def _tool_organize_downloads(*_a):
    salida = _correr([ORGANIZADOR], timeout=60) if _disponible(ORGANIZADOR) else None
    return salida or "Organizador no disponible en esta máquina."


def _tool_find_file(termino="", *_a):
    res = buscar_termino(termino)
    return res if res else f"No encontré «{termino}» en tu home (con prune de cachés)."


def _tool_peli_estado(*_a):
    salida = _correr([PELI, "estado"]) if _disponible(PELI) else None
    return salida or "jarvis-peli no disponible en esta máquina."


def registrar():
    """Dict de herramientas extra para SystemTools.actions."""
    return {
        "organize_downloads": _tool_organize_downloads,
        "find_file": _tool_find_file,
        "peli_estado": _tool_peli_estado,
    }
