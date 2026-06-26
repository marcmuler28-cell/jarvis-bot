#!/usr/bin/env bash
# Launcher para server.py bajo systemd --user
# Las variables WAYLAND_DISPLAY, DISPLAY, XAUTHORITY ya vienen importadas
# desde ~/.config/plasma-workspace/env/sync-wayland-to-systemd.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

UID_NUM="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${UID_NUM}}"
export PATH="${PATH:-/usr/local/bin:/usr/bin:/bin}"

# Si no hay WAYLAND_DISPLAY, buscarlo en XDG_RUNTIME_DIR
if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
  for w in wayland-0 wayland-1; do
    if [[ -S "${XDG_RUNTIME_DIR}/${w}" ]]; then
      export WAYLAND_DISPLAY="$w"
      break
    fi
  done
fi

# Si no hay DISPLAY, usar :0 (XWayland)
export DISPLAY="${DISPLAY:-:0}"

# XAUTHORITY: buscar dinámicamente
if [[ -z "${XAUTHORITY:-}" || ! -f "${XAUTHORITY:-}" ]]; then
  XAUTH_FOUND=$(ls -t /run/user/${UID_NUM}/xauth_* 2>/dev/null | head -1)
  if [[ -n "$XAUTH_FOUND" ]]; then
    export XAUTHORITY="$XAUTH_FOUND"
  fi
fi

# D-Bus de usuario
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "${XDG_RUNTIME_DIR}/bus" ]]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi

# PulseAudio/PipeWire
PN="${XDG_RUNTIME_DIR}/pulse/native"
if [[ -S "$PN" ]]; then
  export PULSE_SERVER="unix:${PN}"
fi

echo "[JARVIS-LAUNCHER] WAYLAND=$WAYLAND_DISPLAY DISPLAY=$DISPLAY XAUTH=$XAUTHORITY"

# Buscar Python del venv
PY="${ROOT}/venv_linux/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${ROOT}/venv/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

sleep 2
# Construir cache de apps (si no existe o es viejo)
"$PY" "${ROOT}/build_app_cache.py" 2>/dev/null || true

exec "$PY" "${ROOT}/server.py"
