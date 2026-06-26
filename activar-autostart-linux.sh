#!/usr/bin/env bash
# Instala/autualiza JarvisBot: autostart (ventana Electron) + servicio (voz/servidor).
# Ejecuta esto desde tu usuario normal (sin sudo salvo donde se pida por propietarios root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${ROOT}/install_linux_integration.py" install --autostart --service

for f in "${HOME}/.config/autostart/jarvisbot.desktop" "${HOME}/.local/share/applications/jarvisbot.desktop"; do
  if [[ -f "${f}" ]]; then
    uid="$(stat -c %u "${f}" 2>/dev/null)" || uid=""
    if [[ "${uid:-}" == 0 ]]; then
      echo "Corrigiendo propietario root del archivo..."
      sudo chown "${USER}:${USER}" "${f}"
    fi
  fi
done

systemctl --user daemon-reload
systemctl --user enable jarvisbot.service
systemctl --user restart jarvisbot.service || systemctl --user start jarvisbot.service

echo ""
echo "--- jarvisbot.service ---"
systemctl --user status jarvisbot.service --no-pager || true
echo ""
echo "Hecho. La ventana Electron debería abrirse solo al iniciar sesión;"
echo "el backend de voz queda como servicio systemd de usuario."
