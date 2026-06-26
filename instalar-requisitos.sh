#!/usr/bin/env bash
# Instala paquetes de sistema y deja JarvisBot listo. Requiere sudo para pacman.
set -euo pipefail
cd "$(dirname "$0")"
echo "==> Paquetes Arch (sudo)"
sudo pacman -S --needed python npm ffmpeg portaudio quickshell qt6-svg qt6-imageformats

echo "==> Node (ui-electron)"
pushd ui-electron >/dev/null
npm install
npm run build
popd >/dev/null

echo "==> Venv Python (crea venv_linux si no existe)"
if [[ ! -d venv_linux ]]; then
  python -m venv venv_linux
fi
# shellcheck source=/dev/null
source venv_linux/bin/activate
pip install --upgrade pip
pip install flask flask-socketio pyperclip sounddevice numpy faster-whisper llama-cpp-python openwakeword pygame edge-tts requests beautifulsoup4 pyautogui 2>/dev/null || pip install flask flask-socketio pyperclip sounddevice numpy

echo "==> Listo. Lee REQUISITOS_Y_ARRANQUE.txt para autostart / systemd."
echo "    Opción simple:  python install_linux_integration.py install --autostart"
echo "    systemd+UI:     python install_linux_integration.py install --autostart --service"
echo "                    systemctl --user daemon-reload && systemctl --user enable --now jarvisbot.service"
