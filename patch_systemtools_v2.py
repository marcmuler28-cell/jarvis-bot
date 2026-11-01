#!/usr/bin/env python3
"""v2: re-aplica cambios a utils.py preservando indentacion, con rollback."""
import re, shutil, sys, pathlib

BASE = pathlib.Path("/home/marc/Proyectos/JarvisBot")
ARCHIVO = BASE / "utils.py"

BACKUP = None
for cand in (BASE / "utils.py.bak_systemtools", BASE / "utils.py.bak_report"):
    if cand.exists():
        BACKUP = cand
        break
if not BACKUP:
    print("[ERROR] No hay backup sano")
    sys.exit(1)

original = BACKUP.read_text(encoding="utf-8", errors="replace")
try:
    compile(original, "utils.py", "exec")
except SyntaxError as e:
    print(f"[ERROR] El backup tampoco compila: {e}")
    sys.exit(1)
print(f"[OK] Backup sano cargado: {BACKUP.name}")

t = original

# 1) Imports de audio/voz -> condicionales (modo chat)
condicionales = [
    r"^import sounddevice as sd$",
    r"^import soundfile as sf$",
    r"^import pyaudio$",
    r"^import edge_tts$",
    r"^import pygame$",
    r"^from faster_whisper import WhisperModel$",
    r"^from openwakeword\.model import Model$",
]
total = 0
for pat in condicionales:
    def envolver(m):
        return ("try:\n    " + m.group(0) + "\nexcept Exception:\n    pass")
    t, n = re.subn(pat, envolver, t, flags=re.M)
    total += n

# 2) _list_open_windows -> version hyprctl (reemplazo de funcion completa)
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
t, n_list = re.subn(r"    def _list_open_windows\(self\):.*?(?=    def )",
                    NUEVA_LIST, t, flags=re.S)

# 3) Cierre de ventanas: linea por linea, PRESERVANDO la indentacion original
lineas = t.splitlines(keepends=True)
n_close = 0
for i, l in enumerate(lineas):
    if "xdotool" in l and "windowclose" in l:
        ind = l[:len(l) - len(l.lstrip())]
        lineas[i] = (ind + "subprocess.run(['hyprctl', 'dispatch', 'closewindow',\n"
                     + ind + "     f\"address:{win['id']}\"],\n"
                     + ind + "     stdin=subprocess.DEVNULL,\n"
                     + ind + "     stdout=subprocess.DEVNULL,\n"
                     + ind + "     stderr=subprocess.DEVNULL)\n")
        n_close += 1
    elif "shutil.which('xdotool')" in l:
        ind = l[:len(l) - len(l.lstrip())]
        lineas[i] = ind + re.sub(r"shutil\.which\('xdotool'\)",
                                 "shutil.which('hyprctl')", l.strip()) + "\n"
        n_close += 1
t = "".join(lineas)

# 4) Auto-verificacion: si la sintaxis falla, restaurar backup y abortar
ARCHIVO.write_text(t, encoding="utf-8")
try:
    compile(t, "utils.py", "exec")
    print(f"[OK] SINTAXIS VERIFICADA | imports: {total} | "
          f"list_open_windows: {n_list} | lineas de cierre: {n_close}")
except SyntaxError as e:
    shutil.copy2(BACKUP, ARCHIVO)
    print(f"[FALLO] Sintaxis invalida: {e}")
    print("[FALLO] Backup restaurado automaticamente. Reportar a GLM.")
    sys.exit(1)

# 5) Reporte de restos
restos = [(n, l.strip()[:80]) for n, l in enumerate(t.splitlines(), 1)
          if "xdotool" in l]
if restos:
    print("[AVISO] Lineas restantes con xdotool (reportar):")
    for n, l in restos[:10]:
        print(f"  linea {n}: {l}")
else:
    print("[OK] Sin referencias a xdotool")
