#!/usr/bin/env bash
# Instala el config de Quickshell para métricas movibles con barras y animación

set -euo pipefail

CONFIG_DIR="$HOME/.config/quickshell/gpu-jarvis"
REPO_DIR="$(dirname "$0")/quickshell-config"

echo "Instalando config de Quickshell en $CONFIG_DIR..."

# Crear directorio si no existe
mkdir -p "$CONFIG_DIR"

# Copiar archivos
cp "$REPO_DIR/main.qml" "$CONFIG_DIR/"
cp "$REPO_DIR/SystemMetricsService.qml" "$CONFIG_DIR/"
# Renombrar main.qml a shell.qml
mv "$CONFIG_DIR/main.qml" "$CONFIG_DIR/shell.qml"

echo "Config instalado. Para probar: quickshell -c gpu-jarvis"
echo "O usa el comando de voz: 'abre quickshell'"