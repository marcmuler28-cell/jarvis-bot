#!/usr/bin/env bash
# whatsapp_bridge/instalar.sh — deja listo el puente de WhatsApp en Arch/EndeavourOS.
set -euo pipefail
cd "$(dirname "$0")"

command -v node >/dev/null 2>&1 || {
  echo "✖ Falta Node.js (>=18). En Arch:  sudo pacman -S nodejs npm"; exit 1; }
echo "✔ Node $(node -v)"

if ! command -v chromium >/dev/null 2>&1 \
   && ! command -v google-chrome-stable >/dev/null 2>&1; then
  echo "⚠  No veo chromium ni google-chrome: whatsapp-web.js necesita un navegador."
  echo "   Instálalo con:  sudo pacman -S chromium"
fi

# Usamos el chromium del sistema; no descargamos el Chrome de puppeteer (pesa ~150MB)
export PUPPETEER_SKIP_DOWNLOAD=1
export PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=1
npm install

chmod +x iniciar.sh server.js 2>/dev/null || true
echo ""
echo "✔ Instalado. Arranca con:  ./iniciar.sh"
echo "  (la primera vez imprime un QR para vincular TU WhatsApp)"
