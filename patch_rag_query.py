#!/usr/bin/env python3
"""Envuelve TODAS las OllamaEmbeddingFunction de rag.py con fallback."""
import re, shutil, sys, pathlib

A = pathlib.Path("/home/marc/Proyectos/JarvisBot/rag.py")
shutil.copy2(A, A.with_suffix(".py.bak_rag2"))
t = A.read_text(encoding="utf-8", errors="replace")

spans = []
patron = re.compile(r"(\s*)(self\.embed_fn\s*=\s*embedding_functions\.OllamaEmbeddingFunction\s*\()")
for m in patron.finditer(t):
    j, prof = m.end() - 1, 0
    while j < len(t):
        if t[j] == "(": prof += 1
        elif t[j] == ")":
            prof -= 1
            if prof == 0: break
        j += 1
    spans.append((m.start(2), j + 1, m.group(1)))

print(f"[INFO] Ocurrencias encontradas: {len(spans)}")

for start, end, indent in reversed(spans):
    line_start = t.rfind("\n", 0, start) + 1
    prev = [l.strip() for l in t[max(0, line_start-300):line_start].strip().splitlines() if l.strip()]
    if prev and prev[-1] == "try:":
        print("[SKIP] Ocurrencia ya envuelta")
        continue
    bloque = t[start:end]
    lineas = bloque.splitlines()
    nuevo = [indent + "try:"]
    nuevo += [indent + "    " + l if l.strip() else "" for l in lineas]
    nuevo += [
        indent + "except Exception:",
        indent + "    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction",
        indent + "    self.embed_fn = DefaultEmbeddingFunction()",
        indent + "    print('[RAG] Ollama no disponible -> embeddings default')",
    ]
    t = t[:start] + "\n".join(nuevo) + t[end:]

A.write_text(t, encoding="utf-8")
try:
    compile(t, "rag.py", "exec")
    print("[OK] SINTAXIS VERIFICADA — todas las rutas de embedding tienen fallback")
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_rag2"), A)
    print(f"[FALLO] {e} — restaurado"); sys.exit(1)
