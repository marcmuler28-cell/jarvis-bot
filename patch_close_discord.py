#!/usr/bin/env python3
"""close_app: mapa de procesos ampliado + match por clase + mensaje claro."""
import re, shutil, sys, pathlib

A = pathlib.Path("/home/marc/Proyectos/JarvisBot/utils.py")
shutil.copy2(A, A.with_suffix(".py.bak_close"))
t = A.read_text(encoding="utf-8", errors="replace")

if "[PATCH_CLOSE_V2]" in t:
    print("[SKIP] Ya aplicado."); sys.exit(0)

# 1) Discord y forks en el app_map (al lado de spotify)
ancla = '"spotify": ["spotify"],'
if ancla not in t:
    print("[ERROR] ancla del app_map no encontrada"); sys.exit(1)
t = t.replace(ancla,
    '"spotify": ["spotify"],\n'
    '            # [PATCH_CLOSE_V2]\n'
    '            "discord": ["discord", "com.discordapp.Discord", "webcord", "vesktop", "armcord"],\n'
    '            "webcord": ["webcord"],\n'
    '            "vencord": ["discord", "vesktop"],', 1)

# 2) _list_open_windows debe incluir la clase (para matchear por clase)
t = t.replace(
    "windows.append({'id': c.get('address', ''),\n"
    "                                    'pid': str(c.get('pid', '')),\n"
    "                                    'title': c.get('title', '')})",
    "windows.append({'id': c.get('address', ''),\n"
    "                                    'pid': str(c.get('pid', '')),\n"
    "                                    'title': c.get('title', ''),\n"
    "                                    'class': (c.get('class') or '').lower(),\n"
    "                                    'initialClass': (c.get('initialClass') or '').lower()})")

# 3) Match por clase ademas de titulo
viejo = ("            title = win.get('title', '').lower()\n"
         "            if cleaned in title or any(token in title for token in cleaned.split()):")
nuevo = ("            # [PATCH_CLOSE_V2] match por titulo Y por clase\n"
         "            title = (win.get('title') or '').lower()\n"
         "            clase = (win.get('class') or '') + (win.get('initialClass') or '')\n"
         "            if cleaned in title or cleaned in clase or any(token in title for token in cleaned.split()):")
n3 = t.count(viejo)
t = t.replace(viejo, nuevo)

# 4) Mensaje de salida claro (verbo correcto para el agente)
t = t.replace('return f"Intenté cerrar: {\', \'.join(killed)}."',
              'return f"Cerré {cleaned} (procesos finalizados: {\', \'.join(killed)})."  # [PATCH_CLOSE_V2]')

A.write_text(t, encoding="utf-8")
try:
    compile(t, "utils.py", "exec")
    print(f"[OK] SINTAXIS VERIFICADA | match por clase en {n3} sitio(s)")
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_close"), A)
    print(f"[FALLO] {e} — backup restaurado"); sys.exit(1)
