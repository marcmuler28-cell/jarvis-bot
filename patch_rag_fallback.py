#!/usr/bin/env python3
"""RAG: si Ollama no esta disponible, usa embeddings default de ChromaDB."""
import re, shutil, sys, pathlib

A = pathlib.Path("/home/marc/Proyectos/JarvisBot/rag.py")
if not A.exists():
    print("[ERROR] No existe rag.py"); sys.exit(1)

shutil.copy2(A, A.with_suffix(".py.bak_rag"))
t = A.read_text(encoding="utf-8", errors="replace")

if "DefaultEmbeddingFunction" in t:
    print("[SKIP] Ya aplicado."); sys.exit(0)

patron = re.compile(r"self\.embed_fn\s*=\s*embedding_functions\.OllamaEmbeddingFunction\s*\(")
m = patron.search(t)
if not m:
    print("[ERROR] No encontre OllamaEmbeddingFunction en rag.py"); sys.exit(1)

# Balancear parentesis hasta el cierre de la llamada
j = m.end() - 1
prof = 0
while j < len(t):
    if t[j] == "(": prof += 1
    elif t[j] == ")":
        prof -= 1
        if prof == 0: break
    j += 1

line_start = t.rfind("\n", 0, m.start()) + 1
indent = t[line_start:m.start()]
bloque = t[line_start:j+1]

lineas = bloque.splitlines()
salida = [indent + "try:"]
for l in lineas:
    salida.append(indent + "    " + l if l.strip() else "")
salida += [
    indent + "except Exception:",
    indent + "    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction",
    indent + "    self.embed_fn = DefaultEmbeddingFunction()",
    indent + "    print('[RAG] Ollama no disponible -> embeddings default de ChromaDB (ONNX)')",
]
t2 = t[:line_start] + "\n".join(salida) + t[j+1:]

A.write_text(t2, encoding="utf-8")
try:
    compile(t2, "rag.py", "exec")
    print("[OK] SINTAXIS VERIFICADA — fallback de embeddings aplicado")
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_rag"), A)
    print(f"[FALLO] {e} — backup restaurado"); sys.exit(1)
