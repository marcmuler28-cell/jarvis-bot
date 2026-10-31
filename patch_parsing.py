#!/usr/bin/env python3
"""Convierte accesos estilo-dict de llama_cpp a string directo (todo el proyecto)."""
import re, shutil, pathlib

BASE = pathlib.Path("/home/marc/Proyectos/JarvisBot")
PATRONES = [
    (re.compile(r'''(\w+)\[\s*["']choices["']\s*\]\s*\[\s*0\s*\]\s*\[\s*["']text["']\s*\]'''), r'\1'),
    (re.compile(r'''(\w+)\[\s*["']choices["']\s*\]\s*\[\s*0\s*\]\s*\[\s*["']message["']\s*\]\s*\[\s*["']content["']\s*\]'''), r'\1'),
]

for py in BASE.rglob("*.py"):
    if ("__pycache__" in py.parts or py.name == "llm_provider.py"
            or py.name.startswith(("patch_", "test_", "fix_", "smoke_"))):
        continue
    t = py.read_text(encoding="utf-8", errors="replace")
    if '["choices"]' not in t and "['choices']" not in t:
        continue
    if "[PATCH_STRING_LLM]" in t:
        continue
    cambios = 0
    for pat, rep in PATRONES:
        t, n = pat.subn(rep + "  # [PATCH_STRING_LLM]", t)
        cambios += n
    if not cambios:
        continue
    backup = py.with_suffix(".py.bak_parse")
    shutil.copy2(py, backup)
    py.write_text(t, encoding="utf-8")
    try:
        compile(t, str(py), "exec")
        print(f"[OK] {py.name}: {cambios} acceso(s) dict -> string")
    except SyntaxError as e:
        shutil.copy2(backup, py)
        print(f"[FALLO] {py.name}: {e} — restaurado")

# Reporte de restos sospechosos (usage, finish_reason, logprobs)
print("\n[REPORTE] Accedos restantes al dict del LLM (si aparecen, avisar):")
for py in BASE.rglob("*.py"):
    if "__pycache__" in py.parts or py.name.startswith(("patch_", "test_")):
        continue
    for n, l in enumerate(py.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if re.search(r'''(\["(usage|finish_reason|logprobs)"\]|\['(usage|finish_reason|logprobs)'\])''', l):
            print(f"  {py.name}:{n}: {l.strip()[:80]}")
print("=== BLOQUE 1 OK ===")
