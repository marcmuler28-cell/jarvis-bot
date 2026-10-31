# whatsapp_bridge — WhatsApp de marc con SU propio número

Puente local entre el cerebro Python (`jarvis_whatsapp.py`) y WhatsApp,
usando **whatsapp-web.js + LocalAuth** (sesión de WhatsApp Web). Sin API de
Meta, sin tokens de Facebook, sin webhook ni ngrok.

```
cerebro (assistant.py fast-path)
   └─ jarvis_whatsapp.py ──HTTP 127.0.0.1:5015──> server.js (Node)
                                                    └─ whatsapp-web.js
                                                       sesión en .wwebjs_auth/
```

## Instalación (una sola vez)

```bash
cd ~/Proyectos/JarvisBot/whatsapp_bridge
./instalar.sh          # npm install (usa el chromium del sistema)
sudo pacman -S chromium   # solo si instalar.sh avisó que falta
```

## Primer arranque (escanear QR)

```bash
./iniciar.sh
```

- Te imprime un **token** la primera vez: añádelo a `~/Proyectos/JarvisBot/.env`:
  `JARVIS_WA_BRIDGE_TOKEN=<el que te dio>`
- Escanea el QR que aparece en la terminal **o** abre
  `http://127.0.0.1:5015/qr?t=<token>` en el navegador.
- A partir de aquí la sesión queda en `.wwebjs_auth/` y **ya no pide más QR**
  (mientras no cierres sesión desde el teléfono).

## Probar

```bash
python3 jarvis_whatsapp.py estado          # desde la raíz del proyecto
python3 jarvis_whatsapp.py guarda mama +51987654321
python3 jarvis_whatsapp.py enviar mama "prueba desde jarvis"
```

## Dejarlo siempre encendido (opcional)

```bash
systemd-run --user --unit=jarvis-whatsapp ./iniciar.sh
```

## Seguridad

- `server.js` escucha **solo en 127.0.0.1** y exige `X-Jarvis-Token`.
- `.wwebjs_auth/` equivale a tu sesión de WhatsApp: está en `.gitignore`
  y NUNCA debe subirse ni compartirse.
