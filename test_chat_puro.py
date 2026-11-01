#!/usr/bin/env python3
"""Chat puro: instancia el agente de assistant.py y conversa por terminal.
Uso:  python test_chat_puro.py              (usa mensaje de prueba interno)
      python test_chat_puro.py "tu mensaje" (usa tu mensaje)"""
import inspect, sys, time, traceback

sys.path.insert(0, "/home/marc/Proyectos/JarvisBot")

def ram_mb():
    try:
        with open("/proc/self/status") as f:
            for l in f:
                if l.startswith("VmRSS:"):
                    return int(l.split()[1]) // 1024
    except Exception:
        pass
    return -1

print(f"[RAM inicial] {ram_mb()} MB")

print("[INFO] Importando assistant.py ... (si se cuelga >60s, Ctrl+C y pega la salida)")
import assistant
print(f"[RAM tras import] {ram_mb()} MB")

# Buscar la clase principal: definida en assistant.py Y con metodo 'process'
candidatas = [
    (n, o) for n, o in inspect.getmembers(assistant, inspect.isclass)
    if o.__module__ == assistant.__name__ and callable(getattr(o, "process", None))
]
if not candidatas:
    defs = [n for n, o in inspect.getmembers(assistant, inspect.isclass)
            if o.__module__ == assistant.__name__]
    print(f"[ERROR] Ninguna clase con metodo 'process'. Clases definidas: {defs}")
    sys.exit(1)

print(f"[INFO] Clase(s) con 'process': {[n for n, _ in candidatas]}")
nombre, clase = candidatas[0]

# Ver si __init__ exige argumentos obligatorios
try:
    params = [p for p in inspect.signature(clase.__init__).parameters.values()
              if p.name != "self"]
    oblig = [p.name for p in params
             if p.default is inspect.Parameter.empty
             and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
except (ValueError, TypeError):
    oblig = []

if oblig:
    print(f"[ALTO] {nombre}.__init__ exige argumentos: {oblig}")
    print("[ALTO] Pasa estos nombres a GLM/Qwen; no instancio a ciegas.")
    sys.exit(1)

print(f"[INFO] Instanciando {nombre}() ...")
t0 = time.time()
try:
    agente = clase()
except Exception:
    print("[ERROR] Fallo la instanciacion:")
    traceback.print_exc()
    sys.exit(1)
print(f"[OK] Instanciado en {time.time()-t0:.1f}s | [RAM tras instanciar] {ram_mb()} MB")

mensajes = sys.argv[1:] or ["¿Qué hora es?"]
for msg in mensajes:
    print(f"\n[MARC] {msg}")
    t0 = time.time()
    try:
        resp = agente.process(msg)
    except Exception:
        print("[ERROR] process() lanzo excepcion:")
        traceback.print_exc()
        sys.exit(1)
    print(f"[JARVIS] ({time.time()-t0:.1f}s) {resp if resp is not None else '(retorno None)'}")

print("\n[OK] CHAT PURO FUNCIONA")
