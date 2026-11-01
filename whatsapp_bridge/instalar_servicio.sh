#!/usr/bin/env bash
# whatsapp_bridge/instalar_servicio.sh — instala el puente de WhatsApp como
# SERVICIO de systemd del usuario: arranca al encender la PC y se apaga al
# apagarla. Ya no necesitas ./iniciar.sh ni dejar terminales abiertas.
set -euo pipefail
cd "$(dirname "$0")"

echo "📦 Instalando servicio de usuario jarvis-wa.service…"
mkdir -p "$HOME/.config/systemd/user"
cp -v jarvis-wa.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload

echo "🔌 Activando y arrancando el servicio…"
echo "   (si tenías ./iniciar.sh en una terminal, el nuevo puente toma el"
echo "    puerto 5015 y mata al viejo automáticamente — puedes cerrarla)"
systemctl --user enable --now jarvis-wa.service

echo ""
echo "✅ Servicio instalado y arrancado."
echo ""
echo "⭐ PARA QUE ARRANQUE AL ENCENDER LA PC (sin abrir sesión):"
echo "      sudo loginctl enable-linger $USER"
echo "   (pídelo una sola vez; sin esto, arranca al abrir tu sesión)"
echo ""
echo "Comandos útiles desde ahora:"
echo "   systemctl --user status jarvis-wa     # ver estado"
echo "   systemctl --user restart jarvis-wa    # reiniciar el puente"
echo "   systemctl --user stop jarvis-wa       # pararlo"
echo "   journalctl --user -u jarvis-wa -f     # log del puente (node)"
echo "   tail -f ~/.jarvis/wa_escucha.log      # log del oyente"
echo ""
echo "⚠️  YA NO uses ./iniciar.sh a mano: ahora lo gestiona systemd."
echo ""
sleep 3
systemctl --user --no-pager --lines=8 status jarvis-wa.service || true
