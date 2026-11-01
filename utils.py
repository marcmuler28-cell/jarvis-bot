import os
import sys
import json
import time
import subprocess
import platform
import tempfile
import wave
import re
from datetime import datetime
import random
import glob
from pathlib import Path
try:
    if platform.system() == "Windows":
        import pygetwindow as gw
    else:
        gw = None
except Exception:
    gw = None
import urllib.parse
import shlex
import shutil
import pyperclip

import numpy as np
try:
    import sounddevice as sd
except Exception:
    pass

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import pygame
except Exception:
    pygame = None
try:
    from faster_whisper import WhisperModel
except Exception:
    pass
# [PATCH_CHAT_MODE]
try:
    from llama_cpp import Llama
except Exception:
    Llama = None

try:
    if platform.system() == "Windows":
        from pynput import mouse as pynput_mouse, keyboard as pynput_keyboard
    else:
        pynput_mouse = None
        pynput_keyboard = None
except Exception:
    pynput_mouse = None
    pynput_keyboard = None

try:
    from openwakeword.model import Model
except Exception:
    pass
from build_app_cache import find_app as _find_app_cached  # <-- nueva importación

if pyautogui is not None:
    pyautogui.FAILSAFE = True  # Si mueves el ratón a una esquina, aborta

# ---------- 3. HERRAMIENTAS DEL SISTEMA (CORREGIDO) ----------
class SystemTools:
    # Traducciones de nombres comunes a comandos reales (Windows y Linux)
    APP_ALIASES = {
        # Windows
        "notas": "gedit",
        "bloc de notas": "gedit",
        "bloc de not": "gedit",
        "block de notas": "gedit",
        "blanco": "gedit",
        "blog de notas": "gedit",
        "notes": "gedit",
        "notepad": "gedit",
        "notepad++": "gedit",
        "explorador": "xdg-open .",
        "explorador de archivos": "xdg-open .",
        "explorer": "xdg-open .",
        "calculadora": "kcalc",
        "calc": "kcalc",
        "cmd": "konsole",
        "terminal": "konsole",
        "powershell": "konsole",
        "word": "libreoffice --writer",
        "excel": "libreoffice --calc",
        "powerpoint": "libreoffice --impress",
        # Linux (ejemplos)
        "navegador": "firefox",
        "chrome": "google-chrome",
        "google chrome": "google-chrome",
        "brave": "brave-browser",
        "edge": "microsoft-edge",
        "opera": "opera",
        "opera browser": "opera",
        "spotify": "spotify",
        "editor de texto": "gedit",
        "nautilus": "nautilus",
        "dolphin": "dolphin",
    }

    def __init__(self):
        self.linux_calc_binaries = [
            "gnome-calculator",
            "kcalc",
            "qalculate-gtk",
            "galculator",
            "mate-calc",
            "deepin-calculator",
            "lxqt-calc",
            "xcalc",
        ]
        self.actions = {
            "open_app": self.open_app,
            "close_app": self.close_app,
            "move_window": self.move_window_to_workspace,
            "move_mouse": self.move_mouse,
            "click": self.click,
            "double_click": self.double_click,
            "right_click": self.right_click,
            "type_text": self.type_text,
            "press_key": self.press_key,
            "screenshot": self.screenshot,
            "locate_on_screen": self.locate_on_screen,
            "practice_session": self.practice_session,
            "copy_file": self.copy_file,
            "move_file": self.move_file,
            "create_folder": self.create_folder,
            "list_folder": self.list_folder,
            "drag_file": self.drag_file,
            "write_file": self.write_file,
            "read_file": self.read_file,
            "list_recent_files": self.list_recent_files,
            "run_command": self.run_command,
            "open_terminal_command": self.open_terminal_command,
            "run_python_script": self.run_python_script,
            "list_processes": self.list_processes,
            "spotify_liked_songs": self.spotify_liked_songs,
        }

    def _wants_linux_calculator(self, cleaned: str) -> bool:
        t = cleaned.lower().strip()
        if "calculadora" in t or "calculator" in t or "kcalc" in t:
            return True
        return bool(re.search(r"(?<![a-z])calc(?![a-z])", t))

    def _spawn_linux_detach(self, args):
        """Lanza un proceso gráfico en el contexto de la sesión de usuario."""
        import os as _os, shutil as _sh

        # Copiar entorno actual y asegurar variables críticas
        env = _os.environ.copy()
        uid = _os.getuid()
        env['XDG_RUNTIME_DIR'] = env.get('XDG_RUNTIME_DIR', f'/run/user/{uid}')

        if 'WAYLAND_DISPLAY' not in env:
            env['WAYLAND_DISPLAY'] = 'wayland-0'

        if 'XAUTHORITY' not in env or not _os.path.exists(env.get('XAUTHORITY', '')):
            import glob
            xauth_files = glob.glob(f'/run/user/{uid}/xauth_*')
            if xauth_files:
                env['XAUTHORITY'] = sorted(xauth_files, key=_os.path.getmtime)[-1]

        # Wayland: agregar flags a apps problemáticas
        is_wayland = env.get('XDG_SESSION_TYPE', '').lower() == 'wayland'
        if is_wayland and args:
            app_name = args[0].split('/')[-1].lower() if isinstance(args[0], str) else ''
            wayland_flags = {
                'spotify': ['--enable-features=UseOzonePlatform', '--ozone-platform=wayland'],
                'discord': ['--enable-features=UseOzonePlatform', '--ozone-platform=wayland'],
                'code': ['--ozone-platform=wayland'],
                'code-oss': ['--ozone-platform=wayland'],
                'vscodium': ['--ozone-platform=wayland'],
            }
            for app, flags in wayland_flags.items():
                if app in app_name:
                    args = list(args) + flags
                    print(f"[WAYLAND] Agregando flags a {app}: {flags}")
                    break

        # Abrir un archivo para capturar errores ocultos de las apps
        err_log = open('/tmp/jarvis_app_errors.log', 'a')
        err_log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        err_log.write(f"Comando: {args}\n")
        err_log.flush()

        # Usar systemd-run --user --scope para ejecutar en el contexto gráfico correcto
        systemd_run = _sh.which('systemd-run')
        if systemd_run:
            cmd = [systemd_run, '--user', '--scope', '--quiet', '--collect'] + list(args)
            try:
                subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=err_log, stderr=err_log, env=env)
                return
            except Exception as e:
                err_log.write(f"[SPAWN] systemd-run falló ({e}), usando Popen directo")
                err_log.flush()

        # Fallback: Popen directo
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=err_log,
            stderr=err_log,
            start_new_session=True,
            env=env
        )

    def _open_linux_calculator(self):
        """Prueba varias calculadoras (GNOME/KDE/etc.); antes solo se probaba kcalc."""
        if platform.system() != "Linux":
            return "La calculadora en este acceso rápido es solo Linux."
        for name in self.linux_calc_binaries:
            exe = shutil.which(name)
            if exe:
                self._spawn_linux_detach([exe])
                return f"Aplicación '{name}' abierta (Linux)."
        gtk = shutil.which("gtk-launch") or shutil.which("gtk4-launch")
        if gtk:
            de = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
            desk = (
                "org.kde.kcalc"
                if "KDE" in de or "PLASMA" in de
                else "org.gnome.Calculator"
            )
            self._spawn_linux_detach([gtk, desk])
            return f"Calculadora solicitada ({desk} vía gtk-launch)."
        if shutil.which("flatpak"):
            try:
                self._spawn_linux_detach(
                    ["flatpak", "run", "org.gnome.Calculator"]
                )
                return "Calculadora lanzada vía Flatpak (org.gnome.Calculator)."
            except OSError:
                pass
        return (
            "Error: no se encontró calculadora instalada "
            "(prueba: pacman -S gnome-calculator o kde-applications-meta para kcalc)."
        )

    # [PATCH_WS_VERIFY]
    # App -> workspace destino (REGLAS DE ALEX: editar aqui)
    WORKSPACES = {
        "spotify": 3,
        "discord": 4,
        # "firefox": 1,
    }

    # Categorias de .desktop -> workspace. Replica el mapa de
    # ~/.config/quickshell/scripts/launch_app.sh para que Jarvis abra cada app
    # en el mismo workspace que el lanzador del escritorio.
    CATEGORY_WORKSPACES = {
        "desarrollo": 1, "sistema": 1, "oficina": 1, "utilidades": 1,
        "multimedia": 3, "graficos": 3,
        "internet": 4,
        "juegos": 5,
    }

    # Palabras de Categories= (freedesktop) -> bucket de CATEGORY_WORKSPACES
    _CATEGORY_HINTS = (
        ("utilidades", ("utility", "calculator")),
        ("juegos", ("game",)),
        ("internet", ("network", "webbrowser", "email", "chat",
                      "instantmessaging", "p2p", "remoteaccess")),
        ("multimedia", ("audio", "video", "player", "tv", "recorder")),
        ("graficos", ("graphics", "photography", "scanning", "3dgraphics")),
        ("desarrollo", ("development", "ide", "texteditor", "debugger",
                        "revisioncontrol")),
        ("oficina", ("office", "wordprocessor", "spreadsheet", "presentation",
                     "calendar", "finance")),
        ("sistema", ("system", "settings", "monitor", "filesystem",
                     "terminalemulator", "security")),
    )

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

    def _workspace_for_desktop(self, desktop_path):
        """Deduce el workspace destino leyendo Categories= del .desktop."""
        try:
            import configparser
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(desktop_path)
            cats = cfg['Desktop Entry'].get('Categories', '').lower()
        except Exception:
            return None
        if not cats:
            return None
        for bucket, pistas in self._CATEGORY_HINTS:
            if any(p in cats for p in pistas):
                return self.CATEGORY_WORKSPACES.get(bucket)
        return None

    def _hyprctl_json(self, *args):
        """Ejecuta `hyprctl -j <args>` y devuelve el JSON ya parseado."""
        import json as _json
        try:
            r = subprocess.run(['hyprctl', '-j', *args],
                               capture_output=True, text=True, timeout=3)
            return _json.loads(r.stdout or 'null')
        except Exception as e:
            print(f"[HYPR] hyprctl {' '.join(args)} fallo: {e}")
            return None

    def _app_name_hints(self, app_name):
        """Nombres alternativos de una app (desktop/ejecutable) segun el catalogo."""
        pistas = []
        try:
            ruta = self._find_desktop_entry(app_name)
        except Exception:
            ruta = None
        if ruta:
            pistas.append(ruta.stem.lower())
            try:
                import configparser
                cfg = configparser.ConfigParser(interpolation=None)
                cfg.read(ruta)
                ex = (cfg['Desktop Entry'].get('Exec', '') or '').split()
                if ex:
                    pistas.append(os.path.basename(ex[0]).lower())
            except Exception:
                pass
        return [p for p in pistas if p]

    def _resolve_client(self, app_name):
        """Busca el cliente de Hyprland que corresponde al nombre pedido."""
        needle = re.sub(r"[^\w\s\+\.\-]", " ", (app_name or "").lower())
        needle = re.sub(r"\s+", " ", needle).strip()
        if not needle:
            return None
        if needle in ("activa", "actual", "esta", "esta ventana", "ventana activa"):
            return self._hyprctl_json('activewindow') or None
        clientes = [c for c in (self._hyprctl_json('clients') or []) if c.get('mapped')]

        def buscar(patron):
            exacto = parcial = titulo = None
            for c in clientes:
                clase = (c.get('class') or '').lower()
                inicial = (c.get('initialClass') or '').lower()
                tit = (c.get('title') or '').lower()
                c_pc = clase.replace(" ", "").replace("-", "")
                i_pc = inicial.replace(" ", "").replace("-", "")
                p_pc = patron.replace(" ", "").replace("-", "")
                t_pc = tit.replace(" ", "").replace("-", "")
                if patron in (clase, inicial) or p_pc in (c_pc, i_pc):
                    exacto = exacto or c
                elif (patron in clase or clase in patron or patron in inicial or inicial in patron
                      or (p_pc and (p_pc in c_pc or c_pc in p_pc))
                      or (p_pc and (p_pc in i_pc or i_pc in p_pc))):
                    parcial = parcial or c
                elif patron in tit or (p_pc and p_pc in t_pc):
                    titulo = titulo or c
            return exacto or parcial or titulo

        encontrado = buscar(needle)
        if encontrado:
            return encontrado
        # El nombre puede ser un alias ("calculadora" -> org.kde.kcalc)
        for pista in self._app_name_hints(app_name):
            if pista != needle:
                encontrado = buscar(pista)
                if encontrado:
                    return encontrado
        return None

    def move_window_to_workspace(self, app_name, workspace, follow=False):
        """Mueve una ventana ya abierta al workspace indicado (Hyprland)."""
        nombre = (app_name or "").strip().strip("'\"")
        ws = str(workspace or "").strip().lower()
        if not nombre:
            return "No me dijiste que ventana mover."
        if not ws:
            return "No me dijiste a que workspace moverla."
        ws = {"siguiente": "e+1", "next": "e+1",
              "anterior": "e-1", "prev": "e-1"}.get(ws, ws)
        cliente = self._resolve_client(nombre)
        if not cliente or not cliente.get('address'):
            abiertas = sorted({w['class'] for w in self._list_open_windows() if w['class']})
            lista = ", ".join(abiertas) if abiertas else "ninguna"
            return f"No encontre una ventana de '{nombre}'. Ventanas abiertas: {lista}."
        addr = cliente['address']
        dispatch = 'movetoworkspace' if follow else 'movetoworkspacesilent'
        r = subprocess.run(['hyprctl', 'dispatch', dispatch, f"{ws},address:{addr}"],
                           capture_output=True, text=True, timeout=3)
        salida = (r.stdout or '').strip()
        if 'ok' not in salida.lower():
            return f"Hyprland rechazo mover '{nombre}' al workspace {ws}: {salida or r.stderr.strip()}"
        titulo = cliente.get('title') or cliente.get('class') or nombre
        return f"'{titulo}' movida al workspace {ws}."

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

    def open_app(self, app_name):
        """Intenta abrir una aplicación por nombre, resolviendo alias."""
        # Limpia el nombre (quita comillas, artículos y ruido de transcripción)
        original = app_name.strip().lower().strip("'\"")
        cleaned = re.sub(r"[^\w\s\+]", " ", original)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for prefix in ("el ", "la ", "los ", "las ", "un ", "una "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        # 1. PRIORIZAR .desktop entries (evita errores de X11/Wayland auth en systemd)
        if platform.system() == "Linux":
            desktop_match = self._find_desktop_entry(cleaned)
            if desktop_match:
                desktop_path = desktop_match  # _find_desktop_entry ahora devuelve solo Path
                res = self._open_desktop_entry(desktop_path)
                if "Error" not in res and "No pude abrir" not in res:
                    return res

        # 2. Calculadora de Linux (alias especial)
        if platform.system() == "Linux" and self._wants_linux_calculator(cleaned):
            return self._open_linux_calculator()

        # 3. Resolver alias definidos
        resolved = self.APP_ALIASES.get(cleaned)
        if not resolved:
            # Alias por contenido para casos como "el blog de notas"
            for alias, target in self.APP_ALIASES.items():
                if alias in cleaned:
                    resolved = target
                    break

        # 4. Si no se resolvió con alias, usar el nombre limpio
        if not resolved:
            resolved = cleaned or original

        # 5. Intentar abrir con el resolved (ruta o ejecutable)
        res = self._try_open(resolved)
        if "Error" in res:
            # Fallback 1: Buscar en PATH
            found_path = self._find_executable(resolved)
            if not found_path:
                # Fallback 2: Buscar en disco (Program Files)
                found_path = self._find_executable_on_disk(resolved)

            if found_path:
                print(f"DEBUG: Encontrado ejecutable en {found_path}")
                res = self._try_open(found_path)
        return res

    def _parse_desktop_entry(self, desktop_file):
        try:
            content = desktop_file.read_text(encoding='utf-8', errors='ignore').splitlines()
        except Exception:
            return {}
        entry = {}
        for line in content:
            if line.strip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            entry[key.strip()] = value.strip()
        return entry

    def _find_desktop_entry(self, cleaned_name):
        """Busca un archivo .desktop para la app solicitada usando cache."""
        import os as _os

        # Mapeo de aliases comunes
        aliases = {
            "navegador": "firefox",
            "browser": "firefox",
            "internet": "firefox",
            "calculadora": "org.kde.kcalc",
            "calc": "org.kde.kcalc",
            "terminal": "org.kde.konsole",
            "consola": "org.kde.konsole",
            "editor": "org.kde.kate",
            "texto": "org.kde.kate",
            "notas": "org.kde.kate",
        }
        cleaned_lower = cleaned_name.lower()
        if cleaned_lower in aliases:
            cleaned_name = aliases[cleaned_lower]

        # 1. Buscar en cache (rápido)
        try:
            app = _find_app_cached(cleaned_name)
            if app:
                desktop_path = None
                # 1a) ruta exacta guardada por build_app_cache (cubre flatpak/snap)
                ruta_cache = app.get('desktop_path')
                if ruta_cache and _os.path.exists(ruta_cache):
                    desktop_path = Path(ruta_cache)
                # 1b) buscar el .desktop por nombre en los directorios clasicos
                for d in ([] if desktop_path else
                          ["/usr/share/applications", _os.path.expanduser("~/.local/share/applications")]):
                    p = _os.path.join(d, app['desktop_file'])
                    if _os.path.exists(p):
                        desktop_path = Path(p)
                        break
                if desktop_path:
                    print(f"[APP_CACHE] Encontrada: {app['name']} → {app['desktop_file']}")
                    return desktop_path  # ahora devuelve solo Path
        except Exception as e:
            print(f"[APP_CACHE] Búsqueda falló: {e}")

        # 2. Fallback: buscar directo en disco (lento)
        desktop_dirs = [
            "/usr/share/applications",
            _os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            _os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
            "/var/lib/snapd/desktop/applications",
        ]
        for d in desktop_dirs:
            for ext in (cleaned_name, cleaned_name.lower(), cleaned_name.replace(" ", "-")):
                p = _os.path.join(d, ext + ".desktop")
                if _os.path.exists(p):
                    return Path(p)
        return None

    def _open_desktop_entry(self, desktop_path, entry=None):
        """Abre una app usando su archivo .desktop de forma robusta."""
        try:
            if desktop_path and desktop_path.exists():
                # Opción 1 DESACTIVADA: gtk-launch falla en systemd con Wayland.
                # Usamos la Opción 2 (Exec directo) que aplica los flags de Wayland correctamente.

                # Opción 2: Parsear el .desktop y ejecutar el comando Exec
                try:
                    import configparser
                    # interpolation=None evita que Python se rompa con los %u, %f de los .desktop
                    config = configparser.ConfigParser(interpolation=None)
                    config.read(desktop_path)
                    if 'Desktop Entry' in config:
                        exec_cmd = config['Desktop Entry'].get('Exec', '')
                        if exec_cmd:
                            # Eliminar códigos de campo como %U, %f, etc.
                            exec_cmd = re.sub(r'%[a-zA-Z]', '', exec_cmd).strip()
                            # Separar el comando en una lista (maneja comillas simples/dobles)
                            parts = shlex.split(exec_cmd)
                            # Limpiar argumentos vacíos o con '=' sueltos (ej: --uri=)
                            parts = [p for p in parts if p and not p.endswith('=')]
                            if parts:
                                self._spawn_linux_detach(parts)
                                hints = [desktop_path.stem, os.path.basename(parts[0]),
                                         config['Desktop Entry'].get('StartupWMClass', '')]
                                ws = (self.WORKSPACES.get(desktop_path.stem.lower())
                                      or self._workspace_for_desktop(desktop_path))
                                # Java/.jar tardan mucho en mapear su ventana
                                lento = ('java' in exec_cmd.lower() or '.jar' in exec_cmd.lower())
                                verif = self._esperar_y_mover(hints, ws,
                                                              timeout=30 if lento else 12)
                                return f"Aplicación '{desktop_path.stem}' iniciada (Exec directo)" + verif
                except Exception as parse_err:
                    print(f"[DESKTOP] Error parseando .desktop: {parse_err}")

                # Opción 3: Fallback final con xdg-open
                subprocess.Popen(['xdg-open', str(desktop_path)], start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Aplicación '{desktop_path.stem}' abierta con xdg-open (fallback)."
            return "No se pudo abrir la aplicación (archivo .desktop no encontrado)."
        except Exception as e:
            print(f"Error abriendo desktop: {e}")
            return f"Error al abrir la aplicación: {e}"

    def _list_open_windows(self):
        windows = []
        try:
            import json as _json
            result = subprocess.run(['hyprctl', '-j', 'clients'],
                                    capture_output=True, text=True, timeout=3)
            clients = _json.loads(result.stdout or "[]")
            for c in clients:
                if c.get('mapped', False) and not c.get('hidden', False):
                    windows.append({'id': c.get('address', ''),
                                    'pid': str(c.get('pid', '')),
                                    'title': c.get('title', ''),
                                    'class': (c.get('class') or '').lower(),
                                    'initialClass': (c.get('initialClass') or '').lower()})
        except Exception:
            pass
        return windows

    def close_app(self, app_name):
        original = app_name.strip().lower().strip('"\'')
        cleaned = re.sub(r"[^\w\s\+]", " ", original)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for prefix in ("el ", "la ", "los ", "las ", "un ", "una "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        if platform.system() != "Linux":
            return "Cerrar aplicaciones solo está soportado en Linux."

        app_map = {
            "spotify": ["spotify"],
            # [PATCH_CLOSE_V2]
            "discord": ["discord", "com.discordapp.Discord", "webcord", "vesktop", "armcord"],
            "webcord": ["webcord"],
            "vencord": ["discord", "vesktop"],
            "calculadora": ["gnome-calculator", "kcalc", "qalculate-gtk", "galculator", "mate-calc", "deepin-calculator", "lxqt-calc", "xcalc"],
            "calc": ["gnome-calculator", "kcalc", "qalculate-gtk", "galculator", "mate-calc", "deepin-calculator", "lxqt-calc", "xcalc"],
            "terminal": ["konsole", "gnome-terminal", "xterm", "alacritty", "kitty", "terminator", "urxvt"],
            "explorador": ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"],
            "firefox": ["firefox"],
            "navegador": ["firefox"],
            "browser": ["firefox"],
            "chrome": ["google-chrome", "chromium", "brave-browser", "chromium-browser"],
            "brave": ["brave-browser", "brave"],
        }
        candidates = app_map.get(cleaned, [cleaned])
        killed = []
        for pat in candidates:
            try:
                result = subprocess.run([
                    "pkill", "-f", pat
                ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    killed.append(pat)
            except Exception:
                continue

        if killed:
            self._limpiar_singleton_locks(killed)
            return f"Cerré {cleaned} (procesos finalizados: {', '.join(killed)})."  # [PATCH_CLOSE_V2]

        windows = self._list_open_windows()
        closed = []
        for win in windows:
            # [PATCH_CLOSE_V2] match por titulo Y por clase
            title = (win.get('title') or '').lower()
            clase = (win.get('class') or '') + (win.get('initialClass') or '')
            if cleaned in title or cleaned in clase or any(token in title for token in cleaned.split()):
                if shutil.which('hyprctl'):
                    try:
                        subprocess.run(['hyprctl', 'dispatch', 'closewindow',
                             f"address:{win['id']}"],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
                        closed.append(win['id'])
                    except Exception:
                        pass
        if closed:
            return f"Cerré ventanas abiertas que coincidían con '{cleaned}' ({', '.join(closed)})."

        return f"No encontré ningún proceso o ventana abierta para '{cleaned}'."

    def _find_executable_on_disk(self, name):
        """Busca un ejecutable que contenga 'name' en Program Files y otras rutas comunes."""
        if platform.system() != "Windows": return None
        search_paths = [
            "C:\\Program Files\\*\\*.exe",
            "C:\\Program Files (x86)\\*\\*.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "*", "*.exe")
        ]
        name_lower = name.lower()
        for pattern in search_paths:
            try:
                # limitamos la búsqueda para no tardar una eternidad
                files = glob.glob(pattern, recursive=True)
                for exe in files:
                    if name_lower in os.path.basename(exe).lower():
                        return exe
            except: continue
        return None

    def get_explorer_path(self):
        """Devuelve la ruta de la carpeta que está abierta en el Explorador de Windows."""
        if platform.system() != "Windows":
            return "No disponible en Linux. Usa 'xdg-open' para abrir carpetas."
        try:
            # Buscar ventana del Explorador con pygetwindow
            explorer_windows = [w for w in gw.getWindowsWithTitle('') if "explorador" in w.title.lower() or "file explorer" in w.title.lower()]
            if not explorer_windows:
                return "No se encontró ninguna ventana del Explorador abierta."

            # Método de PowerShell para obtener la ruta real vía COM (más fiable que el título)
            cmd = '$shell = New-Object -ComObject Shell.Application; $shell.Windows() | Where-Object {$_.LocationURL -like "file://*"} | Select-Object -First 1 | ForEach-Object { $_.LocationURL }'
            result = subprocess.run(['powershell', '-command', cmd], capture_output=True, text=True)
            if result.stdout.strip():
                # Convertir URL a ruta de Windows (file:///C:/... -> C:\...)
                path = result.stdout.strip().replace("file:///", "").replace("/", "\\")
                # Manejar espacios codificados
                import urllib.parse
                path = urllib.parse.unquote(path)
                return f"Ruta detectada: {path}"

            # Fallback al título de la ventana
            title = explorer_windows[0].title
            if "\\" in title or ":" in title:
                return f"Ruta detectada (vía título): {title}"
            return f"Ventana abierta: {title} (no se pudo extraer ruta completa)"
        except Exception as e:
            return f"Error obteniendo ruta: {e}"

    def _try_open(self, cmd):
        system = platform.system()
        try:
            if system == "Windows":
                subprocess.Popen(["start", "", cmd], shell=True)
                return f"Aplicación '{cmd}' abierta (Windows)."
            else:  # Linux
                if cmd.startswith("xdg-open"):
                    parts = shlex.split(cmd)
                    subprocess.Popen(parts)
                    return f"Aplicación '{cmd}' abierta (Linux)."
                if os.path.exists(cmd):
                    subprocess.Popen(["xdg-open", cmd])
                    return f"Ruta o archivo '{cmd}' abierto con xdg-open."
                if len(cmd.strip().split()) > 1 and not cmd.startswith(
                    ("http://", "https://", "mailto:", "spotify:")
                ):
                    try:
                        parts = shlex.split(cmd)
                        if parts:
                            exe0 = shutil.which(parts[0])
                            if exe0:
                                subprocess.Popen(
                                    [exe0] + parts[1:],
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    start_new_session=True,
                                )
                                return f"Aplicación '{cmd}' abierta (Linux)."
                    except ValueError:
                        pass
                exe = shutil.which(cmd)
                if exe:
                    subprocess.Popen([exe])
                    return f"Aplicación '{cmd}' abierta (Linux)."
                if cmd.startswith(("http://", "https://", "mailto:", "spotify:")):
                    subprocess.Popen(["xdg-open", cmd])
                    return f"URI '{cmd}' abierto con xdg-open."
                return f"Error: ejecutable '{cmd}' no encontrado en Linux."
        except Exception as e:
            return f"Error al abrir {cmd}: {e}"

    def _find_executable(self, name):
        """Busca un ejecutable en el sistema."""
        if shutil.which(name):
            return shutil.which(name)

        if platform.system() == "Windows":
            # 1. Probar con 'where' (busca en PATH)
            try:
                res = subprocess.check_output(["where", name], stderr=subprocess.STDOUT, shell=True)
                return res.decode().splitlines()[0].strip()
            except:
                pass
            # 2. Extensiones comunes
            if not name.lower().endswith(".exe"):
                for ext in [".exe", ".lnk"]:
                    try:
                        res = subprocess.check_output(["where", name + ext], stderr=subprocess.STDOUT, shell=True)
                        return res.decode().splitlines()[0].strip()
                    except:
                        continue
        return None

    def read_file(self, filepath):
        if not os.path.exists(filepath):
            return f"Archivo no encontrado: {filepath}"
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()[:1000]
            return f"Contenido de {filepath}:\n{content}"
        except Exception as e:
            return f"Error al leer {filepath}: {e}"

    def list_recent_files(self, directory=".", limit=5):
        try:
            files = sorted(
                [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))],
                key=lambda x: os.path.getmtime(os.path.join(directory, x)),
                reverse=True
            )[:limit]
            return "Archivos recientes en " + directory + ": " + ", ".join(files)
        except Exception as e:
            return f"Error listando archivos: {e}"

    def run_command(self, command):
        """Ejecuta un comando de terminal y devuelve la salida."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
            return f"Salida:\n{result.stdout}\nError:\n{result.stderr}"
        except Exception as e:
            return f"Error ejecutando comando: {e}"

    def open_terminal_command(self, command):
        """Abre un terminal y ejecuta un comando en él."""
        terminals = [
            ["gnome-terminal", "--", "bash", "-lc", command],
            ["konsole", "-e", "bash", "-lc", command],
            ["xfce4-terminal", "-e", "bash", "-lc", command],
            ["terminator", "-e", "bash", "-lc", command],
            ["kitty", "-e", "bash", "-lc", command],
            ["alacritty", "-e", "bash", "-lc", command],
            ["xterm", "-e", "bash", "-lc", command],
            ["urxvt", "-e", "bash", "-lc", command],
        ]
        for cmd in terminals:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Terminal abierto con comando: {command}"
                except Exception as e:
                    continue
        return "No encontré un emulador de terminal para abrir el comando."

    def run_python_script(self, script_path):
        """Lanza un script Python en un nuevo proceso sin bloquear."""
        try:
            if not os.path.exists(script_path):
                return f"No se encontró el script: {script_path}"
            python_executable = sys.executable or "python"
            subprocess.Popen([python_executable, script_path], shell=False)
            return f"Script lanzado: {script_path}"
        except Exception as e:
            return f"Error lanzando script Python: {e}"

    def list_processes(self):
        """Devuelve una lista de los procesos activos en el sistema."""
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                processes.append(f"PID {proc.info['pid']}: {proc.info['name']} ({proc.info['cpu_percent']}%)")
            return "\n".join(processes[:20]) # Limitamos a los 20 primeros por brevedad
        except Exception as e:
            return f"Error al listar procesos: {e}"

    def spotify_liked_songs(self):
        """
        Abre Spotify en «Tus me gusta» (URI spotify:collection:tracks) e intenta iniciar reproducción.
        Requiere Spotify instalado y el protocolo spotify registrado.
        """
        uri = "spotify:collection:tracks"
        try:
            if platform.system() == "Windows":
                try:
                    os.startfile(uri)
                except OSError:
                    subprocess.run(f'cmd /c start "" "{uri}"', shell=True)
            else:
                if shutil.which("xdg-open"):
                    subprocess.Popen(["xdg-open", uri])
                else:
                    return "xdg-open no está disponible en Linux."

            return "Spotify URI abierto en el sistema. Comprueba tu reproductor Spotify."
        except Exception as e:
            return f"Error lanzando Spotify: {e}"

    # ----- Nuevas funciones de automatización -----
    def move_mouse(self, x, y, duration=0.5):
        """Mueve el mouse a coordenadas (x,y). Ej: move_mouse|100,200,0.3"""
        try:
            pyautogui.moveTo(int(x), int(y), duration=float(duration))
            return f"Mouse movido a ({x}, {y})"
        except Exception as e:
            return f"Error moviendo mouse: {e}"

    def click(self, button="left"):
        """Clic izquierdo (por defecto) o derecho. Ej: click|left"""
        try:
            pyautogui.click(button=button)
            return f"Clic {button} realizado en {pyautogui.position()}"
        except Exception as e:
            return f"Error al hacer clic: {e}"

    def double_click(self):
        """Doble clic izquierdo."""
        try:
            pyautogui.doubleClick()
            return f"Doble clic en {pyautogui.position()}"
        except Exception as e:
            return f"Error en doble clic: {e}"

    def right_click(self):
        """Clic derecho."""
        return self.click(button="right")

    def type_text(self, text, interval=0.05):
        """Escribe texto carácter por carácter. Ej: type_text|Hola mundo,0.05"""
        try:
            pyautogui.typewrite(text, interval=float(interval))
            return f"Texto escrito: '{text}'"
        except Exception as e:
            return f"Error escribiendo: {e}"

    def press_key(self, key):
        """Presiona una tecla o combinación. Ej: press_key|enter, press_key|ctrl+c"""
        try:
            if "+" in key:
                # Separa las teclas y usa hotkey (maneja automáticamente el orden)
                keys = [k.strip() for k in key.split("+")]
                pyautogui.hotkey(*keys)
                return f"Combinación de teclas {key} ejecutada"
            else:
                pyautogui.press(key)
                return f"Tecla {key} presionada"
        except Exception as e:
            return f"Error en press_key: {e}"

    def screenshot(self, filename=None):
        """Captura pantalla y guarda la imagen. Ej: screenshot|pantalla.png"""
        try:
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(filename)
            return f"Captura guardada como {filename}"
        except Exception as e:
            return f"Error al capturar: {e}"

    def locate_on_screen(self, image_path, confidence=0.8):
        """Busca una imagen en pantalla y devuelve coordenadas. Ej: locate_on_screen|boton.png,0.9"""
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=float(confidence))
            if location:
                center = pyautogui.center(location)
                return f"Encontrado en x={center.x}, y={center.y}"
            else:
                return "No se encontró la imagen en pantalla"
        except Exception as e:
            return f"Error buscando imagen: {e}"

    def practice_session(self, duration=10):
        """Realiza una práctica de mouse y teclado durante 'duration' segundos."""
        if platform.system() != "Windows":
            return "practice_session no está disponible en Linux."
        start = time.time()
        actions_done = []
        # Secuencia de acciones de prueba
        try:
            # Mover a la esquina superior izquierda
            self.move_mouse(100, 100, 0.3)
            actions_done.append("move 100,100")
            # Clic izquierdo
            self.click("left")
            actions_done.append("click left")
            # Escribir algo (si hay una ventana activa, cuidado)
            self.press_key("win")  # abre menú inicio
            actions_done.append("press win")
            time.sleep(0.5)
            self.type_text("notepad", 0.05)
            actions_done.append("type notepad")
            self.press_key("enter")
            actions_done.append("press enter")
            time.sleep(1.0)  # esperar que abra el bloc de notas
            self.type_text("Hola, soy Jarvis practicando solo.", 0.05)
            actions_done.append("type frase")
            # Mover y hacer doble clic en algún sitio
            self.move_mouse(500, 400, 0.5)
            actions_done.append("move 500,400")
            self.double_click()
            actions_done.append("double click")
            # Presionar combinación Ctrl+A para seleccionar todo
            self.press_key("ctrl+a")
            actions_done.append("ctrl+a")
            time.sleep(0.2)
            # Borrar
            self.press_key("delete")
            actions_done.append("delete")
            # Cerrar ventana (Alt+F4)
            self.press_key("alt+f4")
            actions_done.append("alt+f4")
        except Exception as e:
            return f"Práctica interrumpida: {e}"
        elapsed = time.time() - start
        return f"Práctica completada en {elapsed:.1f}s. Acciones: {', '.join(actions_done)}"

    def verify_action(self, action_name, args, result_str):
        """
        Comprueba si la acción ha tenido éxito.
        Devuelve True si todo OK, False si se detecta un conflicto,
        y un mensaje explicativo.
        """
        # Si la acción devolvió un error, está claro
        if "Error" in result_str or "error" in result_str.lower():
            return False, result_str

        if action_name == "open_app":
            if platform.system() != "Windows":
                return True, "No se puede verificar ventana en Linux; la aplicación se ha intentado abrir."

            app_name = args[0] if args else ""
            time.sleep(2.5)  # más tiempo para que la ventana aparezca

            # Obtener todos los títulos de ventanas abiertas
            try:
                windows = gw.getAllTitles()
                titles_lower = [w.lower() for w in windows if w]
            except Exception as e:
                print(f"Error al listar ventanas: {e}")
                titles_lower = []

            # Limpiar nombre buscado
            expected = app_name.lower().replace("'", "").replace('"', '').strip()

            # Títulos posibles: nombre original, alias, y el comando resuelto
            keywords = [expected]
            target = self.APP_ALIASES.get(expected, expected)
            keywords.append(target)

            # Añadir variaciones comunes (traducciones, etc)
            if any(k in target for k in ["notepad", "bloc", "notas"]):
                keywords += ["notepad", "bloc de notas", "notas", "sin título", "untitled"]
            if any(k in target for k in ["browser", "chrome", "opera"]):
                keywords += ["google chrome", "opera", "navegador", "nueva pestaña", "new tab"]
            if any(k in target for k in ["explorer", "explorador"]):
                keywords += ["explorador de archivos", "file explorer", "equipo", "this pc", "inicio", "escritorio"]
            if any(k in target for k in ["calc", "calculadora"]):
                keywords += ["calc", "calculadora", "calculator"]
            if "spotify" in target:
                keywords += ["spotify"]

            found = any(any(kw in title for kw in keywords) for title in titles_lower)
            if found:
                return True, "Ventana detectada en la lista de aplicaciones abiertas."
            else:
                print(f"DEBUG: No se encontró {keywords}. Títulos abiertos: {titles_lower[:10]}")
                return False, f"No se detectó la ventana '{app_name}' abierta."

        elif action_name == "spotify_liked_songs":
            if platform.system() != "Windows":
                return True, "Spotify lanzado en Linux; no se verifica la ventana."
            time.sleep(2.0)
            try:
                windows = gw.getAllTitles()
                titles_lower = [w.lower() for w in windows if w]
            except Exception:
                titles_lower = []
            if any("spotify" in t for t in titles_lower):
                return True, "Ventana de Spotify detectada."
            return False, "Spotify no detectado como ventana activa en el escritorio."

        elif action_name == "move_mouse":
            try:
                x = int(args[0])
                y = int(args[1])
                pos = pyautogui.position()
                if abs(pos.x - x) <= 10 and abs(pos.y - y) <= 10:
                    return True, "Ratón en posición correcta."
                else:
                    return False, f"Ratón en ({pos.x},{pos.y}), esperado ({x},{y})."
            except:
                return False, "Error al verificar posición."

        elif action_name in ("type_text", "press_key"):
            # No podemos verificar fácilmente, asumiremos éxito si no hubo excepción
            return True, ""

        # Para el resto de acciones, por ahora damos por bueno si no hubo error
        return "Error" not in result_str, ""

    def copy_file(self, src, dst):
        """Copia archivo de src a dst. Si dst es carpeta, copia dentro."""
        try:
            shutil.copy2(src, dst)
            return f"Copiado {src} a {dst}"
        except Exception as e:
            return f"Error copiando: {e}"

    def move_file(self, src, dst):
        """Mueve archivo/carpeta de src a dst."""
        try:
            shutil.move(src, dst)
            return f"Movido {src} a {dst}"
        except Exception as e:
            return f"Error moviendo: {e}"

    def create_folder(self, path):
        """Crea una carpeta (y padres si hacen falta)."""
        try:
            os.makedirs(path, exist_ok=True)
            return f"Carpeta creada: {path}"
        except Exception as e:
            return f"Error creando carpeta: {e}"

    def list_folder(self, path):
        """Lista archivos/carpetas en path."""
        try:
            items = os.listdir(path)
            return f"Contenido de {path} ({len(items)} elementos): {', '.join(items[:20])}"
        except Exception as e:
            return f"Error listando: {e}"

    def drag_file(self, x1, y1, x2, y2, duration=1.0):
        """Arrastra desde (x1,y1) hasta (x2,y2)."""
        try:
            pyautogui.moveTo(int(x1), int(y1), duration=0.2)
            pyautogui.mouseDown()
            pyautogui.moveTo(int(x2), int(y2), duration=float(duration))
            pyautogui.mouseUp()
            return f"Arrastrado de ({x1},{y1}) a ({x2},{y2})"
        except Exception as e:
            return f"Error arrastrando: {e}"

    def write_file(self, filepath, content):
        """Crea o sobreescribe un archivo con el contenido indicado. Ej: write_file|ruta.txt,contenido"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Archivo {filepath} guardado correctamente."
        except Exception as e:
            return f"Error al escribir en {filepath}: {e}"
