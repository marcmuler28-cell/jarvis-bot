# JARVIS — Local-First AI Voice Assistant for Linux

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Linux-orange)
![LLM](https://img.shields.io/badge/LLM-Local%20(Qwen%20%2B%20llama.cpp)-green)
![UI](https://img.shields.io/badge/UI-Electron%20%2B%20React-purple)

A personal, fully local-first AI assistant inspired by Iron Man's JARVIS: you talk, it understands, and it *acts* — controlling the system, running skills, planning multi-step tasks and answering through voice. Built end-to-end as a self-taught project: **≈9,000 lines of Python**, running 24/7 on my own PC with **no paid APIs** for inference.

## Highlights

- 🎙️ **Complete voice loop** — speech-to-text with `faster-whisper`, responses via `edge-tts`, optional wake-word detection (`openwakeword`)
- ⚡ **ReAct agent with fast path** — a trained intent classifier answers common requests in **<0.1 s** without touching the LLM; anything complex falls through to the agent loop
- 🤖 **Local LLM** — Qwen 3B/7B served with llama.cpp / Ollama: private, offline, zero cost per token
- 📚 **RAG memory** — ChromaDB + Ollama embeddings so the assistant remembers past interactions and can cite them
- 🛠️ **60+ voice commands / skills** — weather, RSS, web search, notes, reminders, Taskwarrior, Spotify control, system info, app/game launching, screen automation (`pyautogui`), and more (`skills/`)
- 🗓️ **Recipe-based planner** — multi-step tasks defined as composable recipes, with undo support
- 📈 **Self-improving intent layer** — a scikit-learn `RandomForest` classifier with nightly retraining; failed conversations are logged to SQLite and exported as ChatML JSONL for a future **QLoRA fine-tune** (`finetune_db.py`)
- 👥 **Multi-user by voice** — speaker identification via voice embeddings, per-user PINs, roles and permission lists (`config_users.yaml.example`)
- 🖥️ **Desktop integration** — Electron + React HUD, KDE Plasma QML metrics widget, autostart scripts and a `systemd` service

## Architecture

```
        ┌────────────┐   ┌──────────────┐   ┌───────────────────┐
 mic ──▶│faster-     │──▶│ normalizer + │──▶│ intent classifier │
        │whisper STT │   │ context      │   │ (fast path <0.1s) │
        └────────────┘   └──────────────┘   └─────────┬─────────┘
                                                      │ complex intent
                                                      ▼
                                            ┌──────────────────┐
                                            │  ReAct agent     │◀── RAG (ChromaDB)
                                            │ (assistant.py)   │◀── MySQL / SQLite memory
                                            └────────┬─────────┘
                          ┌──────────────┬───────────┼──────────────┐
                          ▼              ▼           ▼              ▼
                     skills/tools   planner       system       Spotify/games
                                      (recipes)   control
                                                      │
                                                      ▼
                                       edge-tts ──▶ speakers / Electron HUD
```

## Key modules

| Module | What it does | ~Lines |
|---|---|---|
| `assistant.py` | Core ReAct agent, fast-path classifier, self-improvement loop, health monitor | 2,100+ |
| `server.py` / `server_linux.py` | SocketIO backend for the desktop UI | 445+ |
| `whatsapp_bot.py` | WhatsApp Cloud API bot with LLM order parsing (see below) | 418 |
| `agent.py` | Agent abstractions and tool dispatch | 365 |
| `planner.py` | Recipe planner for multi-step tasks (with undo) | 233 |
| `cibertec.py` | Playwright automation for the college platform (see below) | 196 |
| `rag.py` | ChromaDB retrieval-augmented memory | 83 |
| `skills/` | Tool implementations (weather, RSS, search, notes, reminders, system…) | — |
| `finetune_db.py` | Conversation logger + ChatML JSONL dataset builder for QLoRA | — |
| `voice_id.py` | Speaker identification from voice embeddings | — |
| `ui-electron/` | Electron + React HUD (chat, status, walkie-talkie button) | — |

## Companion bots in this repo

### 📦 WhatsApp Order Bot (`whatsapp_bot.py`)
A WhatsApp Business bot built on the **Meta Cloud API (v25)** with a Flask webhook. A local LLM (`qwen2.5-coder:7b` via Ollama) reads informal Spanish customer messages and extracts **structured JSON orders** — product, max budget, client, urgency, delivery method — applying strict business rules (self-corrections: *the last instruction always wins*). Every chat is logged, and a built-in dashboard (`/dashboard`) exposes APIs for tasks, chat logs and extracted entities.

### 🎓 Grades Notifier (`cibertec.py`)
Playwright automation that logs into my university platform (Microsoft SSO + MFA), scrapes courses and grades from Blackboard, and pushes notifications — credentials live only in `.env`.

## Getting started (Linux)

Prerequisites: Python 3.10+, Node.js, ffmpeg, portaudio, Ollama (or llama.cpp), MySQL (optional). Full setup guide (Spanish): [`docs/dev/REQUISITOS_Y_ARRANQUE.txt`](docs/dev/REQUISITOS_Y_ARRANQUE.txt).

```bash
git clone https://github.com/marcmuler28-cell/jarvis-bot.git
cd jarvis-bot
python -m venv venv_linux && source venv_linux/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your credentials
python main.py                # assistant entry point
python whatsapp_bot.py        # run the WhatsApp bot instead
```

The first run should enroll each user's voice (see the sample phrases in `config_users.yaml.example`).

## Security model

- All credentials are read from environment variables (`.env`, gitignored) — no secrets in code
- Voice embeddings and PINs live in `config_users.yaml` (gitignored; copy from the `.example`)
- Session state for the college automation is gitignored

## Documentation

- 📘 Full user manual (Spanish): [`docs/MANUAL_ES.txt`](docs/MANUAL_ES.txt)
- 🛠️ Design and refactor notes: [`docs/dev/`](docs/dev/)

## Screenshots

<!-- TODO: add HUD / dashboard screenshots -->

## Notes

This project taught me agent design (ReAct + tool routing), latency engineering (local fast-path classification before hitting an LLM), the tradeoffs of local vs. cloud inference, voice biometrics, and how to automate painful SSO flows with Playwright. It is under continuous development — next steps are the QLoRA fine-tune pipeline and a smarter planner.
