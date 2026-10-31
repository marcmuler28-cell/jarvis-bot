#!/usr/bin/env python3
"""Convierte TODOS los imports de voz/audio del proyecto en condicionales."""
import re, shutil, pathlib

BASE = pathlib.Path("/home/marc/Proyectos/JarvisBot")
PATRONES = [
    r"^import sounddevice as sd$",
    r"^import soundfile as sf$",
    r"^import pyaudio$",
    r"^import edge_tts$",
    r"^import pygame$",
    r"^from faster_whisper import WhisperModel$",
    r"^from openwakeword\.model import Model$",
    r"^import speech_recognition as sr$",
    r"^import speech_recognition$",
    r"^from spotapi\.public import Public$",
]

total_arch, total_camb = 0, 0
for py in BASE.rglob("*.py"):
    if "__pycache__" in py.parts:
        continue
    if py.name.startswith(("patch_", "test_", "fix_", "smoke_", "setup")):
        continue
    t = py.read_text(encoding="utf-8", errors="replace")
    if "[PATCH_VOICE_GLOBAL]" in t:
        continue
    cambios = 0
    for pat in PATRONES:
        while re.search(pat, t, flags=re.M):
            linea = re.search(pat, t, flags=re.M).group(0)
            nuevo = ("# [PATCH_VOICE_GLOBAL]\ntry:\n    " + linea +
                     "\nexcept Exception:\n    pass")
            t = re.sub(pat, nuevo, t, count=1, flags=re.M)
            cambios += 1
    if cambios:
        backup = py.with_suffix(".py.bak_voice")
        shutil.copy2(py, backup)
        py.write_text(t, encoding="utf-8")
        try:
            compile(t, str(py), "exec")
            print(f"[OK] {py.name}: {cambios} import(s) -> condicional")
            total_arch += 1
            total_camb += cambios
        except SyntaxError as e:
            shutil.copy2(backup, py)
            print(f"[FALLO] {py.name}: {e} — restaurado")
print(f"\n=== TOTAL: {total_camb} imports en {total_arch} archivos ===")
