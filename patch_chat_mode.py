#!/usr/bin/env python3
"""Convierte imports de audio/voz de assistant.py en condicionales (modo chat)."""
import re, shutil, pathlib

ARCHIVO = pathlib.Path("/home/marc/Proyectos/JarvisBot/assistant.py")

# imports que no se necesitan en modo chat
OBJETIVO = [
    r"^import sounddevice as sd$",
    r"^import soundfile as sf$",
    r"^import pyaudio$",
    r"^import edge_tts$",
    r"^import pygame$",
    r"^from faster_whisper import WhisperModel$",
    r"^from openwakeword\.model import Model$",
    r"^import speech_recognition$",
]

def main():
    backup = ARCHIVO.with_suffix(".py.bak_chat")
    shutil.copy2(ARCHIVO, backup)
    t = ARCHIVO.read_text(encoding="utf-8", errors="replace")

    if "[PATCH_CHAT_MODE]" in t:
        print("[SKIP] Ya aplicado.")
        return

    total = 0
    for pat in OBJETIVO:
        m = re.search(pat, t, flags=re.M)
        if not m:
            continue
        linea = m.group(0)
        nuevo = ("# [PATCH_CHAT_MODE]\n"
                 "try:\n"
                 f"    {linea}\n"
                 "except Exception:\n"
                 "    pass")
        t = re.sub(pat, nuevo.replace("\\", "\\\\"), t, count=1, flags=re.M)
        total += 1
        print(f"[OK] condicional: {linea}")

    ARCHIVO.write_text(t, encoding="utf-8")
    print(f"[OK] Backup: {backup.name} | imports convertidos: {total}")

if __name__ == "__main__":
    main()
