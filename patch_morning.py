#!/usr/bin/env python3
"""Llama(...) -> JarvisLLM en scripts/morning_briefing.py. Backup + idempotente."""
import re, shutil, pathlib

ARCHIVO = pathlib.Path("/home/marc/Proyectos/JarvisBot/scripts/morning_briefing.py")
BOOTSTRAP = ("import sys as _sys, os as _os\n"
             "_sys.path.insert(0, _os.path.dirname(_os.path.dirname("
             "_os.path.abspath(__file__))))\n"
             "from llm_provider import JarvisLLM")


def tier_por_nombre(nombre):
    n = nombre.lower()
    if any(k in n for k in ("fast", "small", "ligero")):
        return "fast"
    if any(k in n for k in ("powerful", "big", "large", "grande")):
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
        print("[ERROR] No existe scripts/morning_briefing.py"); raise SystemExit(1)
    backup = ARCHIVO.with_suffix(".py.bak_llm")
    shutil.copy2(ARCHIVO, backup)
    t = ARCHIVO.read_text(encoding="utf-8", errors="replace")

    if "from llm_provider import JarvisLLM" in t:
        print("[SKIP] Ya aplicado."); return

    t, n_imp = re.subn(r"^from llama_cpp import .*$", BOOTSTRAP, t, flags=re.M)

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
        for n, l in restos[:10]:
            print(f"  linea {n}: {l}")
    else:
        print("[OK] Sin referencias a llama_cpp")


if __name__ == "__main__":
    main()
