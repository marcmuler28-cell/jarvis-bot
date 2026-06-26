#!/bin/bash
cd /home/marc/Descargas/JarvisBot/ui-electron

echo "[JARVIS] Esperando al backend..."
# Esperar hasta 90 segundos a que el backend responda
for i in {1..90}; do
  if curl -s http://127.0.0.1:5000/ > /dev/null 2>&1; then
    echo "[JARVIS] ✅ Backend listo tras $i segundos"
    break
  fi
  sleep 1
done

JARVIS_SKIP_BACKEND=1 JARVIS_UI_MODE=wallpaper npx electron . --no-sandbox --disable-gpu --disable-dev-shm-usage --ozone-platform=x11
