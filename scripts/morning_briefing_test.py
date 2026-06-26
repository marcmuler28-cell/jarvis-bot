#!/usr/bin/env python3
"""
Genera el briefing matutino y lo guarda en ~/.jarvis/briefing.json.
Se ejecuta desde systemd o manualmente.
"""
import os
import sys
import json
import subprocess
from datetime import date
import importlib.util

# Asegurar que el directorio del proyecto esté en el path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

from config import MODEL_FAST, HOME  # Usamos las rutas centralizadas

# Definir ruta para el archivo de briefing
JARVIS_DIR = os.path.join(HOME, ".jarvis")
os.makedirs(JARVIS_DIR, exist_ok=True)
BRIEFING_FILE = os.path.join(JARVIS_DIR, "briefing.json")

# ------------------------------------------------------------
# Carga directa de skills (evita importar database.py y MySQL)
# ------------------------------------------------------------
# WeatherSkill
weather_spec = importlib.util.spec_from_file_location(
    "weather", os.path.join(PROJECT_DIR, "skills", "weather.py")
)
weather_module = importlib.util.module_from_spec(weather_spec)
weather_spec.loader.exec_module(weather_module)
WeatherSkill = weather_module.WeatherSkill

# RSSReader
rss_spec = importlib.util.spec_from_file_location(
    "rss", os.path.join(PROJECT_DIR, "skills", "external", "rss.py")
)
rss_module = importlib.util.module_from_spec(rss_spec)
rss_spec.loader.exec_module(rss_module)
RSSReader = rss_module.RSSReader

# ------------------------------------------------------------
def get_tasks():
    """
    Obtiene las tareas pendientes de Taskwarrior.
    Intenta usar la librería 'taskw', si no, ejecuta 'task export'.
    """
    try:
        from taskw import TaskWarrior
        w = TaskWarrior()
        tasks = w.load_tasks()
        pending = [t for t in tasks['pending']]
        if not pending:
            return "No tienes tareas pendientes para hoy."
        # Ordenar por urgencia (si existe campo 'urgency')
        pending.sort(key=lambda t: t.get('urgency', 0), reverse=True)
        lines = []
        for i, t in enumerate(pending[:5], 1):  # máximo 5 tareas
            desc = t.get('description', 'Sin descripción')
            due = t.get('due', None)
            due_str = f" (vence: {due})" if due else ""
            lines.append(f"{i}. {desc}{due_str}")
        return "\n".join(lines)
    except ImportError:
        # Fallback con línea de comandos
        try:
            result = subprocess.run(
                ["task", "export"],
                capture_output=True, text=True, check=True
            )
            tasks = json.loads(result.stdout)
            pending = [t for t in tasks if t.get('status') == 'pending']
            if not pending:
                return "No tienes tareas pendientes para hoy."
            # Ordenar por urgencia manual (aproximado)
            pending.sort(key=lambda t: t.get('urgency', 0), reverse=True)
            lines = []
            for i, t in enumerate(pending[:5], 1):
                desc = t.get('description', 'Sin descripción')
                due = t.get('due', None)
                due_str = f" (vence: {due})" if due else ""
                lines.append(f"{i}. {desc}{due_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"No se pudieron obtener las tareas: {e}"

def generate_briefing_text(weather_report, tasks_text, headlines_text):
    """Usa el modelo rápido para crear un resumen agradable."""
    prompt = f"""Eres Jarvis, un asistente personal amable y conciso. Redacta un breve resumen matutino para tu usuario, Marc, basándote en los siguientes datos. Usa un tono cálido, motivador y natural, como si le dieras los buenos días. Incluye toda la información, pero no te extiendas demasiado.

Información:
- Clima: {weather_report}
- Tareas pendientes: {tasks_text}
- Noticias del día: {headlines_text}

Responde únicamente con el texto del briefing, sin notas adicionales."""

    # Cargar el modelo ligero
    from llama_cpp import Llama
    model_path = os.path.join(PROJECT_DIR, MODEL_FAST)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo no encontrado en {model_path}")

    llm = Llama(
        model_path=model_path,
        n_ctx=2048,            # contexto pequeño suficiente
        n_threads=4,           # ajusta según tu CPU
        verbose=False
    )

    try:
        output = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
            stop=["\n\n", "---"],
        )
        generated = output['choices'][0]['message']['content'].strip()
        return generated
    finally:
        del llm  # liberar memoria

def main():
    print("🌤️  Recopilando clima...")
    weather = WeatherSkill()
    weather_report = weather.full_report()

    print("📋  Consultando tareas...")
    tasks_text = get_tasks()

    print("📰  Obteniendo noticias...")
    rss = RSSReader()
    headlines_text = rss.headlines_text()

    print("🧠  Generando resumen con IA...")
    try:
        briefing = generate_briefing_text(weather_report, tasks_text, headlines_text)
    except Exception as e:
        # Fallback manual si el modelo falla
        briefing = (
            f"Buenos días, Marc. Aquí tienes tu resumen matutino.\n\n"
            f"🌡️ Clima: {weather_report}\n"
            f"📋 Tareas: {tasks_text}\n"
            f"📰 Noticias: {headlines_text}\n"
        )

    # Guardar en JSON
    data = {
        "date": str(date.today()),
        "briefing": briefing
    }
    with open(BRIEFING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Briefing guardado en {BRIEFING_FILE}")

if __name__ == "__main__":
    main()