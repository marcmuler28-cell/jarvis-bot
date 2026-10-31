#!/usr/bin/env python3
"""Instalador VISIBLE de dependencias faltantes de assistant.py."""
import faulthandler, importlib, subprocess, sys

sys.path.insert(0, "/home/marc/Proyectos/JarvisBot")
PIP = "/home/marc/jarvis_venv/bin/pip"

# nombres de import -> nombre real en PyPI
MAPA = {
    "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml",
    "dotenv": "python-dotenv", "sklearn": "scikit-learn",
    "speech_recognition": "SpeechRecognition", "doctor": "pydoctor",
}

for intento in range(1, 11):
    print(f"\n--- Intento {intento}: importando assistant.py (visible) ---")
    faulthandler.dump_traceback_later(180, exit=True)  # alarma anti-cuelgue
    try:
        importlib.import_module("assistant")
        print("\n[OK] IMPORTS OK — todo instalado")
        break
    except ModuleNotFoundError as e:
        mod = (e.name or "?").split(".")[0]
        paquete = MAPA.get(mod, mod)
        print(f"[FALTA] modulo '{mod}' -> instalando paquete '{paquete}'")
        subprocess.run([PIP, "install", paquete])
    except Exception as e:
        print(f"\n[ERROR DISTINTO] {type(e).__name__}: {e}")
        print("-> Copia este error completo y envialo a GLM")
        break
