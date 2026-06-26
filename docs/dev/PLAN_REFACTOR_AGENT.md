# Plan de Refactorización: Extraer agent.py desde assistant.py

## Objetivo
Mover la lógica de triggers, hábitos y predicción contextual desde `assistant.py` (~2100 líneas) a `agent.py`, dejando `assistant.py` solo con el loop ReAct.

## Estructura final

```
agent.py                  ← Lógica de triggers, _fast_path, clasificador contextual
assistant.py              ← Solo ReActAgent (process, _parse_response, _execute_action)
~/.jarvis/triggers.json   ← Reglas de triggers persistidas
skills/                   ← Skills individuales (weather, rss, etc.)
```

## Fases

### Fase 1: Preparación (sin riesgo)
- [ ] Crear clase `AgentCore` en `agent.py`
- [ ] Copiar a `agent.py` los métodos que NO dependen de `self.current_llm`:
  - `_predict_context_action` + `safe_transform`
  - `_fuzzy_match`
  - `_extract_search_query`
  - Carga de `triggers.json`
- [ ] Verificar que `agent.py` importa todo lo necesario (datetime, subprocess, etc.)
- [ ] Test: `python3 -c "from agent import AgentCore; print('OK')"`

### Fase 2: Mover _fast_path (riesgo medio)
- [ ] Copiar `_fast_path` completo a `AgentCore._fast_path`
- [ ] Identificar dependencias de `_fast_path` hacia `self` (ReActAgent):
  - `self.voice.speak()` → pasar como callback
  - `self.tools.actions` → `self.tools` ya se pasa en __init__
  - `self.memory.add_interaction()` → pasar como callback
  - `self.health.get_report()` → `self.health` se pasa en __init__
  - `self.current_llm` → solo en `_learn_new_recipe` y `_parse_step_description`
  - `self.skills` → se pasa en __init__
- [ ] Crear `AgentCore.__init__(self, tools, memory, health, voice, skills, llm)`
- [ ] En `assistant.py`, `ReActAgent.__init__` crea `self.agent = AgentCore(...)`
- [ ] Test: ejecutar comandos básicos ("cómo estás", "abre firefox")

### Fase 3: Delegar desde assistant.py (riesgo bajo)
- [ ] En `ReActAgent.process()`, llamar primero a `self.agent.fast_path(user_input)`
- [ ] Si retorna algo, usarlo; si no, continuar con LLM
- [ ] Mover métodos de confirmación:
  - `_confirm_and_poweroff`
  - `_confirm_and_reboot`
  - `_confirm_and_execute`

### Fase 4: Sistema de triggers desde agent.py
- [ ] `AgentCore` carga `~/.jarvis/triggers.json` al iniciar
- [ ] Método `check_triggers(hour, minute, weekday)` que evalúa condiciones
- [ ] Si un trigger cumple condición y `accepted == true`, ejecuta la acción
- [ ] Triggers con `proposed: true, accepted: false` se sugieren al usuario

## Dependencias por método

| Método | Dependencias externas |
|--------|----------------------|
| `_predict_context_action` | `self.context_clf`, `self.le_*`, `get_active_window_kde()` |
| `_fast_path` | `self.tools`, `self.memory`, `self.voice`, `self.health`, `self.skills`, `self.current_llm` |
| `_fuzzy_match` | solo `re` |
| `_extract_search_query` | nada |
| `_confirm_and_poweroff` | `self.voice`, `self.memory` |

## Riesgos y mitigaciones

1. **Que _fast_path use `self.current_llm`** → Pasar el LLM como dependencia
2. **Que _fast_path acceda a atributos de ReActAgent** → Identificarlos en Fase 2
3. **Romper imports cíclicos** → `agent.py` no importa `assistant.py`, solo al revés
4. **Perder estado** → `AgentCore` se crea una vez en `__init__` y vive todo el ciclo

## Rollback
Si algo falla: `git checkout assistant.py` y se revierte cualquier cambio.
