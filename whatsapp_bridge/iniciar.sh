#!/usr/bin/env bash
# whatsapp_bridge/iniciar.sh — arranca el puente con el token del .env del proyecto.
# La sesión de WhatsApp queda guardada en ./.wwebjs_auth (no se vuelve a pedir QR).
set -euo pipefail
cd "$(dirname "$0")"

# 1) Carga el .env del proyecto (para reutilizar JARVIS_WA_BRIDGE_TOKEN)
if [ -f ../.env ]; then
  set -a; . ../.env 2>/dev/null || true; set +a
fi

# 2) Si no hay token, genera uno y te lo muestra para copiarlo al .env
if [ -z "${JARVIS_WA_BRIDGE_TOKEN:-}" ]; then
  JARVIS_WA_BRIDGE_TOKEN="$(node -e "console.log(require('crypto').randomBytes(16).toString('hex'))")"
  echo ""
  echo "──────────────────────────────────────────────────────────────"
  echo " Token NUEVO para el puente:  $JARVIS_WA_BRIDGE_TOKEN"
  echo " Añádelo a ~/Proyectos/JarvisBot/.env:"
  echo "   JARVIS_WA_BRIDGE_TOKEN=$JARVIS_WA_BRIDGE_TOKEN"
  echo " (así el cerebro Python y este puente se autentican entre sí)"
  echo "──────────────────────────────────────────────────────────────"
  echo ""
fi
export JARVIS_WA_BRIDGE_TOKEN

# 3) Chromium del sistema
for c in /usr/bin/chromium /usr/bin/chromium-browser /usr/bin/google-chrome-stable; do
  if [ -x "$c" ]; then export CHROME_PATH="$c"; break; fi
done

# 3b) Limpieza de restos: si quedó un puente viejo en el puerto o un
#     chromium huérfano del puente anterior, el nuevo arranca sin sesión
#     («The browser is already running» / EADDRINUSE). fuser mata al que
#     escucha el puerto; pkill wwebjs_auth mata SOLO al chromium cuyo
#     perfil es el de este puente (no toca tu navegador normal).
fuser -k "${JARVIS_WA_BRIDGE_PORT:-5015}/tcp" 2>/dev/null || true
pkill -f "wwebjs_auth" 2>/dev/null || true
sleep 2

# 4) Escucha de TU chat propio: te escribes desde el celular y Jarvis responde
#    («mis notas», «ayuda»...). Log en ~/.jarvis/wa_escucha.log
#    IMPORTANTE: correr con el python del VENV (tiene mysql-connector y
#    python-dotenv); con el python del sistema el aula responde «sin datos».
if command -v python3 >/dev/null 2>&1; then
  RAIZ="$(cd .. && pwd)"
  PY="$RAIZ/venv_linux/bin/python"
  [ -x "$PY" ] || PY="$(command -v python3)"
  pkill -f "jarvis_whatsapp.py escuchar" 2>/dev/null || true
  sleep 1   # dale un segundo al viejo para soltar el cerrojo del oyente
  mkdir -p "$HOME/.jarvis"
  (cd .. && nohup "$PY" jarvis_whatsapp.py escuchar >> "$HOME/.jarvis/wa_escucha.log" 2>&1 & disown) || true
  echo "👂 Escucha de tu chat propio lanzada con $(basename "$PY") (log: ~/.jarvis/wa_escucha.log)"
fi

echo "▶ Puente de WhatsApp escuchando en 127.0.0.1:5015  (Ctrl+C para parar)"
exec node server.js
