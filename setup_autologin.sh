#!/usr/bin/env bash
# ============================================================
# setup_autologin.sh - Configura auto-login en KDE Plasma (SDDM)
# ============================================================
# Esto hace que la PC encienda directamente al escritorio sin pedir
# contraseña. JarvisBot se encargará de la autenticación por voz.
#
# ⚠️  ADVERTENCIA DE SEGURIDAD:
# Esto reduce la seguridad física. Cualquiera con acceso físico a la
# PC puede entrar sin contraseña. Solo recomendado si vives solo o
# confías en quienes tienen acceso físico.
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   JARVISBOT - Configuración de Auto-Login (SDDM)     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ $EUID -ne 0 ]]; then
    echo -e "${YELLOW}⚠️  Este script necesita permisos de root (sudo).${NC}"
    echo -e "Ejecútalo así:"
    echo ""
    echo -e "  ${CYAN}sudo $0${NC}"
    echo ""
    exit 1
fi

CURRENT_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
if [[ "$CURRENT_USER" == "root" ]]; then
    echo -e "${RED}❌ No se pudo determinar el usuario actual.${NC}"
    echo "Ejecuta este script con sudo desde tu usuario normal."
    exit 1
fi

echo -e "${GREEN}✅ Usuario objetivo: ${CURRENT_USER}${NC}"
echo ""

echo -e "${YELLOW}⚠️  ADVERTENCIA DE SEGURIDAD:${NC}"
echo ""
echo "  Este script configurará auto-login en SDDM para que la PC encienda"
echo "  directamente al escritorio SIN pedir contraseña."
echo ""
echo "  Esto significa que:"
echo "    ✅ La PC encenderá sola y entrará al escritorio"
echo "    ✅ JarvisBot arrancará automáticamente (autostart)"
echo "    ✅ JarvisBot pedirá identificación por voz para autorizar comandos"
echo ""
echo "    ⚠️  Cualquiera con acceso FÍSICO a la PC puede entrar sin contraseña"
echo "    ⚠️  JarvisBot NO es una barrera de seguridad del SO, solo de comandos"
echo ""
echo "  Si alguien robara la PC, tendría acceso a todos tus archivos."
echo "  JarvisBot solo controla qué comandos de voz se ejecutan, NO protege"
echo "  el sistema operativo en sí."
echo ""
read -p "¿Estás seguro de continuar? (escribe SI para confirmar): " CONFIRM
if [[ "$CONFIRM" != "SI" ]]; then
    echo -e "${YELLOW}Operación cancelada. No se hicieron cambios.${NC}"
    exit 0
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Configurando SDDM...${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"

SDDM_CONF=""
for conf in /etc/sddm.conf /etc/sddm.conf.d/autologin.conf /etc/sddm.conf.d/sddm.conf; do
    if [[ -f "$conf" ]] || [[ -d "$(dirname "$conf")" ]]; then
        SDDM_CONF="$conf"
        break
    fi
done

if [[ -z "$SDDM_CONF" ]]; then
    SDDM_CONF="/etc/sddm.conf.d/autologin.conf"
    mkdir -p /etc/sddm.conf.d
fi

echo -e "Usando archivo de configuración: ${CYAN}${SDDM_CONF}${NC}"

if [[ -f "$SDDM_CONF" ]]; then
    BACKUP="${SDDM_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$SDDM_CONF" "$BACKUP"
    echo -e "${GREEN}✅ Backup creado: ${BACKUP}${NC}"
fi

DESKTOP_SESSION=""
for session_path in \
    "/var/lib/AccountsService/users/${CURRENT_USER}" \
    "/home/${CURRENT_USER}/.dmrc"; do
    if [[ -f "$session_path" ]]; then
        SESSION_LINE=$(grep -i "^Session=" "$session_path" 2>/dev/null | head -1 || true)
        if [[ -n "$SESSION_LINE" ]]; then
            DESKTOP_SESSION="${SESSION_LINE#Session=}"
            break
        fi
    fi
done

if [[ -z "$DESKTOP_SESSION" ]]; then
    for xsess in /usr/share/xsessions/plasma*.desktop; do
        if [[ -f "$xsess" ]]; then
            DESKTOP_SESSION=$(basename "$xsess" .desktop)
            break
        fi
    done
    if [[ -z "$DESKTOP_SESSION" ]]; then
        for wsess in /usr/share/wayland-sessions/plasma*.desktop; do
            if [[ -f "$wsess" ]]; then
                DESKTOP_SESSION=$(basename "$wsess" .desktop)
                break
            fi
        done
    fi
fi

if [[ -z "$DESKTOP_SESSION" ]]; then
    echo -e "${YELLOW}⚠️  No se pudo detectar la sesión automáticamente.${NC}"
    echo "Sesiones disponibles en /usr/share/xsessions:"
    ls /usr/share/xsessions/ 2>/dev/null || echo "  (no hay)"
    echo "Sesiones disponibles en /usr/share/wayland-sessions:"
    ls /usr/share/wayland-sessions/ 2>/dev/null || echo "  (no hay)"
    echo ""
    read -p "Escribe el nombre de tu sesión (ej: plasma, plasmawayland): " DESKTOP_SESSION
fi

echo -e "Sesión detectada: ${CYAN}${DESKTOP_SESSION}${NC}"

if [[ "$SDDM_CONF" == *.conf.d/autologin.conf ]]; then
    cat > "$SDDM_CONF" << INNER_EOF
# Configuración de auto-login para JarvisBot
# Creado por setup_autologin.sh el $(date)
# Advertencia: esto reduce la seguridad física del equipo

[Autologin]
User=${CURRENT_USER}
Session=${DESKTOP_SESSION}
INNER_EOF
else
    if grep -q "^\[Autologin\]" "$SDDM_CONF" 2>/dev/null; then
        sed -i "/^\[Autologin\]/,/^\[/ s/^User=.*/User=${CURRENT_USER}/" "$SDDM_CONF"
        sed -i "/^\[Autologin\]/,/^\[/ s/^Session=.*/Session=${DESKTOP_SESSION}/" "$SDDM_CONF"
    else
        echo "" >> "$SDDM_CONF"
        echo "[Autologin]" >> "$SDDM_CONF"
        echo "User=${CURRENT_USER}" >> "$SDDM_CONF"
        echo "Session=${DESKTOP_SESSION}" >> "$SDDM_CONF"
    fi
fi

chmod 644 "$SDDM_CONF"

echo -e "${GREEN}✅ Auto-login configurado para ${CURRENT_USER} con sesión ${DESKTOP_SESSION}${NC}"
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Verificación${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Contenido de ${CYAN}${SDDM_CONF}${NC}:"
echo -e "${GREEN}─────────────────────────────────────────${NC}"
cat "$SDDM_CONF"
echo -e "${GREEN}─────────────────────────────────────────${NC}"
echo ""

if systemctl is-enabled sddm.service >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Servicio SDDM está habilitado${NC}"
else
    echo -e "${YELLOW}⚠️  SDDM no parece estar habilitado como display manager.${NC}"
    echo "   Si usas otro DM (gdm, lightdm), necesitarás configurarlo manualmente."
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 ¡Auto-login configurado!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Próximos pasos:"
echo ""
echo "  1. Reinicia la PC para probar:"
echo -e "     ${CYAN}sudo reboot${NC}"
echo ""
echo "  2. Después de reiniciar:"
echo "     - La PC entrará directo al escritorio (sin contraseña)"
echo "     - JarvisBot arrancará automáticamente (autostart + sleep 30)"
echo "     - JarvisBot pedirá identificación por voz para autorizar comandos"
echo ""
echo "  3. Para DESHACER el auto-login (si te arrepientes):"
echo -e "     ${CYAN}sudo rm ${SDDM_CONF}${NC}"
echo "     Y restaurar el backup si lo hiciste"
echo ""
echo -e "${YELLOW}⚠️  Recuerda: JarvisBot NO es una barrera de seguridad del SO.${NC}"
echo -e "${YELLOW}    Es solo una capa de autorización para comandos de voz.${NC}"
