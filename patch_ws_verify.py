#!/usr/bin/env python3
"""utils.py: (1) spawn+poll+move a workspace (patron spawn_ws.sh en Python),
(2) limpieza de SingletonLock al cerrar instancias (fix Discord-zombi)."""
import shutil, sys, pathlib

BASE = pathlib.Path("/home/marc/Proyectos/JarvisBot")
A = BASE / "utils.py"
shutil.copy2(A, A.with_suffix(".py.bak_ws"))
t = A.read_text(encoding="utf-8", errors="replace")

if "[PATCH_WS_VERIFY]" in t:
    print("[SKIP] Ya aplicado."); sys.exit(0)

NUEVOS_METODOS = '''    # [PATCH_WS_VERIFY]
    # App -> workspace destino (REGLAS DE ALEX: editar aqui)
    WORKSPACES = {
        "spotify": 3,
        "discord": 4,
        # "firefox": 1,
    }

    LOCKS_SINGLETON = {
        "discord": [
            "~/.config/discord/SingletonLock",
            "~/.config/discord/SingletonSocket",
            "~/.config/discord/SingletonCookie",
            "~/.var/app/com.discordapp.Discord/config/discord/Singleton*",
        ],
        "spotify": [
            "~/.config/spotify/SingletonLock",
            "~/.config/spotify/SingletonSocket",
            "~/.config/spotify/SingletonCookie",
        ],
    }

    def _esperar_y_mover(self, hints, workspace, timeout=10):
        """Poll por clase sobre hyprctl -j clients; mueve la ventana al
        workspace con movetoworkspacesilent por address (sin windowrules)."""
        if not workspace:
            return ""
        import json as _json, time as _time
        hints = [str(h).lower() for h in hints if h]
        fin = _time.time() + timeout
        while _time.time() < fin:
            try:
                r = subprocess.run(['hyprctl', '-j', 'clients'],
                                   capture_output=True, text=True, timeout=3)
                for c in _json.loads(r.stdout or "[]"):
                    if not c.get('mapped', False):
                        continue
                    clase = (c.get('class') or '').lower()
                    inicial = (c.get('initialClass') or '').lower()
                    if any(h in clase or h in inicial for h in hints):
                        addr = c.get('address', '')
                        if addr:
                            subprocess.run(
                                ['hyprctl', 'dispatch', 'movetoworkspacesilent',
                                 f'{workspace},address:{addr}'],
                                capture_output=True, text=True, timeout=3)
                            return f" | Ventana verificada en ws{workspace}"
            except Exception:
                pass
            _time.sleep(0.4)
        return ""

    def _limpiar_singleton_locks(self, killed):
        """Elimina locks huerfanos que bloquean la siguiente instancia."""
        import glob as _g
        removidos = 0
        for patron in killed:
            for plantilla in self.LOCKS_SINGLETON.get(patron, []):
                for ruta in _g.glob(os.path.expanduser(plantilla)):
                    try:
                        os.remove(ruta)
                        removidos += 1
                    except OSError:
                        pass
        if removidos:
            print(f"[CLOSE] SingletonLock eliminados: {removidos}")

'''
anchor = "    def open_app(self, app_name):"
if anchor not in t:
    print("[ERROR] ancla 'def open_app' no encontrada"); sys.exit(1)
t = t.replace(anchor, NUEVOS_METODOS + anchor, 1)

# Hook en _open_desktop_entry: tras el spawn, verificar y mover
lineas = t.splitlines(keepends=True)
n_hook = n_locks = 0
for i, l in enumerate(lineas):
    if "iniciada (Exec directo)" in l and n_hook == 0:
        ind = l[:len(l) - len(l.lstrip())]
        hook = [
            ind + "hints = [desktop_path.stem, os.path.basename(parts[0])]",
            ind + "ws = self.WORKSPACES.get(desktop_path.stem.lower())",
            ind + "verif = self._esperar_y_mover(hints, ws)",
            ind + "return f\"Aplicación '{desktop_path.stem}' iniciada (Exec directo)\" + verif",
        ]
        lineas[i] = "\n".join(hook) + "\n"
        n_hook += 1
    if "Intenté cerrar" in l and n_locks == 0:
        ind = l[:len(l) - len(l.lstrip())]
        lineas[i] = ind + "self._limpiar_singleton_locks(killed)\n" + l
        n_locks += 1
t = "".join(lineas)

A.write_text(t, encoding="utf-8")
try:
    compile(t, "utils.py", "exec")
    print(f"[OK] SINTAXIS VERIFICADA | hook open: {n_hook} | hook locks: {n_locks}")
except SyntaxError as e:
    shutil.copy2(A.with_suffix(".py.bak_ws"), A)
    print(f"[FALLO] {e} — backup restaurado"); sys.exit(1)
