#!/usr/bin/env bash
# Abre el panel Quickshell (GPU, RAM, carga, J.A.R.V.I.S.) creado en ~/.config/quickshell/gpu-jarvis
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
if command -v gpu-jarvis-hud >/dev/null 2>&1; then
  exec gpu-jarvis-hud "$@"
fi
if command -v quickshell >/dev/null 2>&1; then
  exec quickshell -c gpu-jarvis "$@"
fi
echo "Error: no está instalado quickshell o falta ~/.local/bin/gpu-jarvis-hud." >&2
echo "Instala Quickshell (tu distro) y deja la config en ~/.config/quickshell/gpu-jarvis/" >&2
exit 1
