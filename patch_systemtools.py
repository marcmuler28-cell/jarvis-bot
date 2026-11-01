#!/usr/bin/env python3
"""Adapta el archivo con SystemTools a: modo chat (sin voz local) + Wayland."""
import re, shutil, pathlib

DIRECTORIO = pathlib.Path("/home/marc/Proyectos/JarvisBot")

# --- Localizar el archivo que contiene class SystemTools ---
ARCHIVO = None
for py in DIRECTORIO.glob("*.py"):
    try:
        if "class SystemTools" in py.read_text(encoding="utf-8", errors="replace"):
            ARCHIVO = py
            break
    except Exception:
        continue
if not ARCHIVO:
    print("[ERROR] No encontré ningún .py con 'class SystemTools'")
    raise SystemExit(1)
print(f"[INFO] Archivo detectado: {ARCHIVO.name}")

backup = ARCHIVO.with_suffix(".py.bak_systemtools")
shutil.copy2(ARCHIVO, backup)
texto = ARCHIVO.read_text(encoding="utf-8", errors="replace")

if "[PATCH_SYSTEMTOOLS_V1]" not in texto:
    texto = texto.replace('"""', '"""\n# [PATCH_SYSTEMTOOLS_V1]\n', 1) if texto.startswith('"""') else "# [PATCH_SYSTEMTOOLS_V1]\n" + texto

cambios = []

# --- 1) Imports duros -> condicionales (modo chat: sin voz local, sin llama local) ---
condicionales = [
    (r"^from faster_whisper import WhisperModel$",
     "try:\n    from faster_whisper import WhisperModel\nexcept Exception:\n    WhisperModel = None"),
    (r"^from llama_cpp import Llama$",
     "try:\n    from llama_cpp import Llama\nexcept Exception:\n    Llama = None"),
    (r"^from openwakeword\.model import Model$",
     "try:\n    from openwakeword.model import Model\nexcept Exception:\n    Model = None"),
    (r"^import sounddevice as sd$",
     "try:\n    import sounddevice as sd\nexcept Exception:\n    sd = None"),
]
for patron, reemplazo in condicionales:
    texto, n = re.subn(patron, reemplazo, texto, flags=re.M)
    if n:
        cambios.append(f"import condicional aplicado ({n}): {patron}")

# --- 2) _list_open_windows -> hyprctl -j clients ---
NUEVA_LIST = '''    def _list_open_windows(self):
        windows = []
        try:
            import json as _json
            result = subprocess.run(['hyprctl', '-j', 'clients'],
                                    capture_output=True, text=True, timeout=3)
            clients = _json.loads(result.stdout or "[]")
            for c in clients:
                if c.get('mapped', False) and not c.get('hidden', False):
                    windows.append({'id': c.get('address', ''),
                                    'pid': str(c.get('pid', '')),
                                    'title': c.get('title', '')})
        except Exception:
            pass
        return windows

'''
patron_func = re.compile(r"    def _list_open_windows\(self\):.*?(?=    def )", re.S)
texto, n = patron_func.subn(NUEVA_LIST, texto)
if n:
    cambios.append("_list_open_windows reemplazada por version hyprctl")

# --- 3) Cierre de ventanas xdotool -> hyprctl dispatch ---
patron_close = re.compile(
    r"if shutil\.which\('xdotool'\):\s*\n"
    r"\s*try:\s*\n"
    r"\s*subprocess\.run\(\['xdotool', 'windowclose', win\['id'\]\][^\n]*\n"
    r"\s*closed\.append\(win\['id'\]\)\s*\n"
    r"\s*except Exception:\s*\n\s*pass"
)
reemplazo_close = (
    "try:\n"
    "                        subprocess.run(['hyprctl', 'dispatch', 'closewindow',\n"
    "                                       f\"address:{win['id']}\"],\n"
    "                                      stdin=subprocess.DEVNULL,\n"
    "                                      stdout=subprocess.DEVNULL,\n"
    "                                      stderr=subprocess.DEVNULL)\n"
    "                        closed.append(win['id'])\n"
    "                    except Exception:\n"
    "                        pass"
)
texto, n = patron_close.subn(reemplazo_close, texto)
cambios.append(f"cierre de ventanas xdotool->hyprctl: {n} reemplazo(s)")

# --- 4) Reportar usos que quedan de los modelos de voz/LLM (no tocar, solo avisar) ---
avisos = []
for num, linea in enumerate(texto.splitlines(), 1):
    if re.search(r"WhisperModel\(|Llama\(|Model\(|\bsd\.rec|\bsd\.play", linea):
        avisos.append(f"  linea {num}: {linea.strip()[:90]}")

ARCHIVO.write_text(texto, encoding="utf-8")

print(f"[OK] Backup en {backup.name}")
for c in cambios:
    print(f"[OK] {c}")
if avisos:
    print("[AVISO] Usos restantes de voz/LLM local (revisar):")
    print("\n".join(avisos[:20]))
else:
    print("[OK] Sin instanciaciones de voz/LLM local en este archivo")
