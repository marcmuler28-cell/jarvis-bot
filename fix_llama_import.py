#!/usr/bin/env python3
import re, shutil, pathlib, sys

A = pathlib.Path("/home/marc/Proyectos/JarvisBot/utils.py")
shutil.copy2(A, A.with_suffix(".py.bak_llama"))
t = A.read_text(encoding="utf-8", errors="replace")

nuevo = ("# [PATCH_CHAT_MODE]\n"
         "try:\n"
         "    from llama_cpp import Llama\n"
         "except Exception:\n"
         "    Llama = None")
t, n = re.subn(r"^from llama_cpp import Llama$", nuevo, t, flags=re.M)
if n == 0:
    print("[AVISO] No encontre el import (ya convertido?)")
A.write_text(t, encoding="utf-8")

try:
    compile(t, "utils.py", "exec")
    print(f"[OK] SINTAXIS VERIFICADA | imports convertidos: {n}")
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_llama"), A)
    print(f"[FALLO] {e} - backup restaurado")
    sys.exit(1)
