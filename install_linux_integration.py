#!/usr/bin/env python3
import os
import pathlib
import shutil
import stat
import sys
import textwrap

APP_NAME = "JarvisBot"
DESKTOP_FILE = "jarvisbot.desktop"
APPLICATIONS_DIR = os.path.expanduser("~/.local/share/applications")
AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
SERVICE_FILE = "jarvisbot.service"


def get_repo_root():
    return pathlib.Path(__file__).resolve().parent


def build_exec_command(root_path, skip_backend=False):
    ui_dir = root_path / "ui-electron"
    if skip_backend:
        return (
            f"/usr/bin/env bash -lc 'cd \"{ui_dir}\" && "
            f"JARVIS_SKIP_BACKEND=1 npm run electron'"
        )
    return f"/usr/bin/env bash -lc 'cd \"{ui_dir}\" && npm run electron'"


def build_desktop_entry(exec_command, icon_path=None, autostart=False):
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_NAME}",
        "Comment=Inicia el asistente JarvisBot en Linux",
        f"Exec={exec_command}",
        "Terminal=false",
        "Categories=Utility;AudioVideo;Development;",
        "StartupNotify=true",
        "StartupWMClass=JarvisBot",
    ]
    if icon_path:
        lines.append(f"Icon={icon_path}")
    if autostart:
        lines.append("X-GNOME-Autostart-enabled=true")
    return "\n".join(lines) + "\n"


def write_desktop_file(target_path, content):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    os.chmod(target_path, 0o644)
    # Si ejecutaste este script con sudo, devuelve el .desktop al usuario correcto (autostart lo exige).
    sudou = os.environ.get("SUDO_UID")
    if sudou:
        try:
            os.chown(target_path, int(sudou), int(os.environ.get("SUDO_GID", sudou)))
        except (OSError, ValueError):
            pass
    try:
        if target_path.stat().st_uid == 0:
            print(
                f"Aviso: {target_path} es propiedad de root; el escritorio suele ignorar ese autostart. "
                'Ejecuta: sudo chown "$USER:$USER" "' + str(target_path) + '"'
            )
    except OSError:
        pass
    print(f"Escrito: {target_path}")


def build_service_file(root_path):
    # Script que fija XDG_RUNTIME_DIR/DISPLAY para PipeWire + Electron vía orden de voz
    launcher = root_path / "jarvisbot-server.sh"
    if not launcher.exists():
        raise FileNotFoundError(
            "Falta jarvisbot-server.sh en la carpeta del proyecto (debe estar en el repo)."
        )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # Use server.py for the Linux voice/UI backend and wake-word integration
    server_path = root_path / "server.py"
    if not server_path.exists():
        server_path = root_path / "server_linux.py"
    if not server_path.exists():
        raise FileNotFoundError("No se encuentra server.py ni server_linux.py.")
    service_lines = [
        "[Unit]",
        "Description=JarvisBot UI Backend",
        "# Red “online” útil para edge-tts, APIs, etc. (requiere network-online bien configurado)",
        "Wants=network-online.target",
        "After=network-online.target network.target sound.target",
        "# Audio de sesión: esperar socket de PipeWire (nombre estándar en systemd --user)",
        "After=graphical-session-pre.target graphical-session.target",
        "Wants=pipewire.socket",
        "After=pipewire.socket",
        "",
        "[Service]",
        "# PassEnvironment suele llegar vacío: el script fuerza valores típicos de sesión gráfica",
        f"ExecStart={launcher}",
        f"WorkingDirectory={root_path}",
        "Restart=always",
        "RestartSec=5",
        "Environment=PYTHONUNBUFFERED=1",
        "# Respaldo explícito (el script también lo hace)",
        "Environment=XDG_RUNTIME_DIR=/run/user/%U",
        "PassEnvironment=WAYLAND_DISPLAY DISPLAY XDG_RUNTIME_DIR",
        "",
        "[Install]",
        "WantedBy=default.target",
    ]
    return "\n".join(service_lines) + "\n"


def install(autostart=False, service=False):
    root_path = get_repo_root()
    icon_path = None

    # Prefer icon if está en ui-electron/public/icon.png
    candidate_icon = root_path / "ui-electron" / "public" / "icon.png"
    if candidate_icon.exists():
        icon_path = str(candidate_icon)

    # Con --service: systemd ejecuta server.py; la entrada de menú y autostart no deben lanzar otro server.py
    skip_backend = bool(service)
    exec_command = build_exec_command(root_path, skip_backend=skip_backend)
    desktop_content = build_desktop_entry(exec_command, icon_path=icon_path, autostart=autostart)
    app_target = pathlib.Path(APPLICATIONS_DIR) / DESKTOP_FILE
    write_desktop_file(app_target, desktop_content)

    if autostart:
        autostart_target = pathlib.Path(AUTOSTART_DIR) / DESKTOP_FILE
        write_desktop_file(autostart_target, desktop_content)
        print("Autostart configurado: se iniciará JarvisBot al iniciar sesión.")
        if skip_backend:
            print("  (JARVIS_SKIP_BACKEND=1: solo la ventana Electron; el backend es jarvisbot.service.)")
    else:
        print("Integración de escritorio instalada. Busca JarvisBot en tu menú de aplicaciones.")

    if service:
        service_content = build_service_file(root_path)
        service_target = pathlib.Path(SYSTEMD_DIR) / SERVICE_FILE
        write_desktop_file(service_target, service_content)
        print("Servicio systemd instalado: jarvisbot.service")
        print("Para activar el servicio, ejecuta:")
        print("  systemctl --user daemon-reload")
        print("  systemctl --user enable --now jarvisbot.service")
        if not autostart:
            print("Nota: sin --autostart solo tendrás el servidor en segundo plano; abre la UI desde el menú.")


def uninstall(remove_autostart=False, remove_service=False):
    app_target = pathlib.Path(APPLICATIONS_DIR) / DESKTOP_FILE
    if app_target.exists():
        app_target.unlink()
        print(f"Eliminado: {app_target}")
    if remove_autostart:
        autostart_target = pathlib.Path(AUTOSTART_DIR) / DESKTOP_FILE
        if autostart_target.exists():
            autostart_target.unlink()
            print(f"Eliminado autostart: {autostart_target}")
    if remove_service:
        service_target = pathlib.Path(SYSTEMD_DIR) / SERVICE_FILE
        if service_target.exists():
            service_target.unlink()
            print(f"Eliminado servicio: {service_target}")


def usage():
    print(textwrap.dedent(
        """
        Uso:
          python install_linux_integration.py install [--autostart] [--service]
          python install_linux_integration.py uninstall [--autostart] [--service]

        Opciones:
          --autostart    Crea ~/.config/autostart para abrir la ventana al iniciar sesión.
          --service      Instala ~/.config/systemd/user/jarvisbot.service (server.py: API + voz).
                         Si usas --service, las entradas .desktop usan JARVIS_SKIP_BACKEND
                         para no lanzar un segundo server.py cuando systemd ya lo ejecuta.

        Atajo (recomendado en Linux desde tu usuario en la carpeta del proyecto):
          ./activar-autostart-linux.sh
        """
    ).strip())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    action = sys.argv[1].lower()
    autostart = "--autostart" in sys.argv
    service = "--service" in sys.argv

    if action == "install":
        install(autostart=autostart, service=service)
    elif action == "uninstall":
        uninstall(remove_autostart=autostart, remove_service=service)
    else:
        usage()
        sys.exit(1)
