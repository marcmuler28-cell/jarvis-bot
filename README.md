# JarvisBot — cerebro de JARVIS (local-first)

Cerebro del asistente personal de marc: agente ReAct local + gateway API
(`127.0.0.1:5001/api/chat`) que habla con el widget de Quickshell
(repo hermano: `hyprland-config`) y con los skills CLI
(`jarvis-organizador.sh`, `jarvis-peli`, `jarvis-buscar`).

## Novedades de la rama `cerebro-v3`

**Conciencia de ventanas Hyprland** (`jarvis_windows.py`, integrada en
`assistant.py` como fast-path + herramientas ReAct):

| Le dices al chat… | Jarvis… |
|---|---|
| «ver mis ventanas», «¿qué tengo abierto?» | lista clientes activos por escritorio |
| «trae spotify», «traeme el firefox» | trae la ventana al escritorio actual |
| «mueve discord al escritorio 3» | la manda al escritorio 3 |
| «manda el juego al siguiente escritorio» | workspace siguiente |
| «pasa spotify al escritorio de juegos» | workspace nombrado |
| «…al escritorio 1 y ve con él» | mueve Y te sigue (follow) |
| «cierra la ventana de discord» | cierra por nombre (con erratas fuzzy) |

- Parser universal `parse_mover()`: entiende mueve/mover/mueva/manda/pasa/lleva/envía/devuelve/trae…,
  ignora «mueve el ratón», «sube el volumen», «pantalla completa».
- Resolución de app por clase/título con tolerancia a erratas.
- **Puente a skills** (`jarvis_skills_bridge.py`): «organiza», «¿dónde está X?»,
  «estado de pelis», «transcribe/quema/prompt…» resuelven LOCALES, sin gastar
  la IA; lo demás cae al LLM como siempre.
- `api_gateway.py` v2: códigos HTTP reales, JSON `{response, acciones}`.
- `database.py` saneado: credenciales MySQL por `.env` (nunca en el código).
- **27/27 tests** (`test_ventanas.py`) verificados.

## Configuración

En el `.env` del proyecto (NO se sube al repo):

```
JARVIS_DB_HOST=localhost
JARVIS_DB_USER=root
JARVIS_DB_PASSWORD=tu_password_mysql
JARVIS_DB_NAME=jarvisbot
```

## Aula virtual (Blackboard Ultra / Mi Cibertec) — `cibertec_bridge.py`

Verbos locales que corren `consultar.py` (Playwright + APIs `/learn/api/v1`)
con la sesión de `blackboard_state.json`:

| Le dices al chat… | Jarvis… |
|---|---|
| «mis notas», «calificaciones» | promedio por curso + promedio general |
| «mis cursos» | matriculados activos |
| «mensajes del aula» | sin leer por curso |
| «mis evaluaciones», «calendario del aula» | eventos próximos |

Reglas respetadas: si la sesión caducó **no se loguea solo** (el SMS exige
humano) → te remite a `python login_unificado.py`; `blackboard_state.json` y
`sms_code.txt` están en `.gitignore` y **NUNCA** van al repo.

## WhatsApp con tu propio número — `jarvis_whatsapp.py` + `whatsapp_bridge/`

Sin API de Meta, sin tokens de Facebook, sin webhook: un puente local Node
(`whatsapp-web.js` + LocalAuth) abre **tu propia sesión de WhatsApp** y el
cerebro le habla por HTTP en `127.0.0.1:5015`.

| Le dices al chat… | Jarvis… |
|---|---|
| «manda un whatsapp a mamá diciendo que ya llegué» | envía con tu número (el mensaje conserva tildes y ñ) |
| «envíale un wsp a luis que mañana hay examen» | ídem, separador «que/dile/k» |
| «whatsapp a mama: no te preocupes» | ídem, separador «:» |
| «estado de whatsapp» | ¿el puente está conectado? |
| «mis contactos» | lista `~/.jarvis/contactos.json` |
| «guarda contacto papa +51987000123» | añade el apodo a la agenda |

Instalación y primer QR: ver `whatsapp_bridge/README.md`. Resumen:

```bash
cd ~/Proyectos/JarvisBot/whatsapp_bridge
./instalar.sh          # npm install (usa el chromium del sistema)
./iniciar.sh           # primera vez: imprime token + QR para vincular
```

- Agenda: `~/.jarvis/contactos.json` (apodo → número con código de país).
- `server.js` escucha SOLO en `127.0.0.1` y exige `X-Jarvis-Token`
  (`JARVIS_WA_BRIDGE_TOKEN` en el `.env` y en el entorno del puente).
- La sesión queda en `whatsapp_bridge/.wwebjs_auth/` → en `.gitignore`,
  **equivale a tu teléfono: nunca subirla ni compartirla**.
- `whatsapp_bot.py` (Cloud API vieja) quedó saneado: sus credenciales ahora
  van por `.env` (`JARVIS_WA_PHONE_ID` / `JARVIS_WA_TOKEN` / `JARVIS_WA_VERIFY`).
  El token que estaba hardcodeado en el repo público hay que **revocarlo** en
  developers.facebook.com.

## Arranque

```bash
python3 api_gateway.py          # gateway en 127.0.0.1:5001 (solo local, nunca exponer)
python3 test_ventanas.py        # suite de pruebas de ventanas + skills
python3 test_whatsapp.py        # suite de WhatsApp (sin Node, sin red)
```
