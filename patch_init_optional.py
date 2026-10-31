#!/usr/bin/env python3
"""Convierte fast_model_path/powerful_model_path en opcionales (=None)."""
import re, shutil, sys, pathlib

A = pathlib.Path("/home/marc/Proyectos/JarvisBot/assistant.py")
shutil.copy2(A, A.with_suffix(".py.bak_init"))
t = A.read_text(encoding="utf-8", errors="replace")

# Localizar la clase ReActAgent y su def __init__(...)
m_cls = re.search(r"^class ReActAgent\b", t, flags=re.M)
if not m_cls:
    print("[ERROR] No encontre class ReActAgent"); sys.exit(1)

m_init = re.compile(r"^    def __init__\s*\(", flags=re.M).search(t, m_cls.end())
if not m_init:
    print("[ERROR] No encontre __init__ de ReActAgent"); sys.exit(1)

# Encontrar el cierre del parentesis de la firma
i = m_init.end() - 1  # posicion del "("
prof, j = 0, i
while j < len(t):
    if t[j] == "(": prof += 1
    elif t[j] == ")":
        prof -= 1
        if prof == 0: break
    j += 1
firma = t[i:j+1]

nueva_firma = firma.replace("fast_model_path", "fast_model_path=None")
nueva_firma = nueva_firma.replace("powerful_model_path", "powerful_model_path=None")
nueva_firma = nueva_firma.replace("=None=", "=None, ")  # si estaban juntos sin coma visible

t2 = t[:i] + nueva_firma + t[j+1:]

A.write_text(t2, encoding="utf-8")
try:
    compile(t2, "assistant.py", "exec")
    n = nueva_firma.count("=None")
    print(f"[OK] SINTAXIS VERIFICADA | params opcionales: {n}")
    print("[INFO] Firma ahora:", " ".join(nueva_firma.split())[:200])
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_init"), A)
    print(f"[FALLO] {e} — backup restaurado"); sys.exit(1)
