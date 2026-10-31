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

## Arranque

```bash
python3 api_gateway.py          # gateway en 127.0.0.1:5001 (solo local, nunca exponer)
python3 test_ventanas.py        # suite de pruebas de ventanas + skills
```
