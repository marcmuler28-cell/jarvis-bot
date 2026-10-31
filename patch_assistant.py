#!/usr/bin/env python3
"""Llama(...) -> JarvisLLM(tier=...) en assistant.py. Backup + idempotente."""
import re, shutil, pathlib

ARCHIVO = pathlib.Path("/home/marc/Proyectos/JarvisBot/assistant.py")


def tier_por_nombre(nombre):
    n = nombre.lower()
    if any(k in n for k in ("fast", "small", "ligero", "quick")):
        return "fast"
    if any(k in n for k in ("powerful", "big", "large", "grande", "smart")):
        return "powerful"
    return None


def saltar_parentesis(t, i):
    prof = 0
    while i < len(t):
        c = t[i]
        if c == "(":
            prof += 1
        elif c == ")":
            prof -= 1
            if prof == 0:
                return i + 1
        i += 1
    return i


def main():
    if not ARCHIVO.exists():
        print("[ERROR] No existe assistant.py"); raise SystemExit(1)
    backup = ARCHIVO.with_suffix(".py.bak_tiers")
    shutil.copy2(ARCHIVO, backup)
    t = ARCHIVO.read_text(encoding="utf-8", errors="replace")

    if "JarvisLLM(tier=" in t:
        print("[SKIP] Ya aplicado."); return

    n_imp = 0
    for pat in (r"^from llama_cpp import .*$", r"^import llama_cpp.*$"):
        t, n = re.subn(pat, "from llm_provider import JarvisLLM", t, flags=re.M)
        n_imp += n
    if n_imp == 0 and "from llm_provider import JarvisLLM" in t:
        print("[INFO] Import ya estaba migrado.")

    patron = re.compile(r"((?:self\.)?\w+)\s*=\s*Llama\s*\(")
    out, i, total = [], 0, 0
    m = patron.search(t)
    while m:
        var = m.group(1)
        tier = tier_por_nombre(var)
        nuevo = (f"{var} = JarvisLLM(tier='{tier}')" if tier
                 else f"{var} = JarvisLLM()")
        out.append(t[i:m.start()]); out.append(nuevo)
        i = saltar_parentesis(t, m.end() - 1)
        total += 1
        print(f"  [OK] {var} -> JarvisLLM(tier='{tier}')")
        m = patron.search(t, i)
    out.append(t[i:])
    t = "".join(out)

    ARCHIVO.write_text(t, encoding="utf-8")
    print(f"[OK] Backup: {backup.name} | imports: {n_imp} | instancias: {total}")

    restos = [(n, l.strip()[:90]) for n, l in enumerate(t.splitlines(), 1)
              if re.search(r"\bLlama\s*\(|llama_cpp", l)]
    if restos:
        print("[AVISO] Restos de llama_cpp (revisar):")
        for n, l in restos[:15]:
            print(f"  linea {n}: {l}")
    else:
        print("[OK] Sin referencias a llama_cpp")


if __name__ == "__main__":
    main()
