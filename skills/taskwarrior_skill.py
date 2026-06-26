"""Conector de Taskwarrior con parseo LLM para lenguaje natural."""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta

TASK_BIN = shutil.which("task") or "task"


class LLMTaskParser:
    """Usa el modelo LLM para extraer descripcion y fecha de vencimiento."""

    @staticmethod
    def parse(llm, user_input: str) -> dict:
        """Devuelve {"descripcion": str, "vencimiento": str (ISO opcional)}."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = (
            f"Hoy es {now}. Extrae la tarea y la fecha de vencimiento "
            "en formato JSON exacto: {\"descripcion\": \"...\", \"vencimiento\": \"YYYY-MM-DD HH:MM\"} "
            "(si no hay fecha, omite el campo vencimiento). "
            "Responde SOLO el JSON, nada mas.\n"
            f"Frase: \"{user_input}\""
        )
        try:
            output = llm(prompt, max_tokens=100, temperature=0.0, stop=["\n\n"])
            text = output["choices"][0]["text"].strip()
            # Limpiar posibles ruidos
            text = re.sub(r'^.*?(\{.*\}).*$', r'\1', text, flags=re.DOTALL)
            data = json.loads(text)
            result = {"descripcion": data.get("descripcion", user_input)}
            if "vencimiento" in data:
                result["vencimiento"] = data["vencimiento"]
            return result
        except Exception as e:
            print(f"[TASK_LLM] Error parseando: {e}")
            return {"descripcion": user_input}


class TaskwarriorSkill:
    """Gestion de tareas via Taskwarrior CLI."""

    def __init__(self):
        self.parser = LLMTaskParser()

    def add_task(self, llm, user_input: str) -> str:
        """Anade una tarea desde lenguaje natural usando el LLM."""
        parsed = self.parser.parse(llm, user_input)
        desc = parsed.get("descripcion", user_input)
        venc = parsed.get("vencimiento")

        # Escapar comillas en la descripcion
        desc_esc = desc.replace('"', '\\"')

        cmd = [TASK_BIN, "add", desc_esc]
        if venc:
            cmd.append(f"due:{venc}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                msg = f"Tarea anadida: {desc}"
                if venc:
                    msg += f" (vence: {venc})"
                return msg
            else:
                return f"Error al anadir tarea: {result.stderr.strip()}"
        except Exception as e:
            return f"Error ejecutando task: {e}"

    def list_tasks(self, filter_str: str = "pending") -> str:
        """Lista tareas pendientes."""
        try:
            result = subprocess.run(
                [TASK_BIN, filter_str, "minimal"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    return f"Tareas ({filter_str}):\n{output}"
                return "No hay tareas pendientes."
            return f"Error: {result.stderr.strip()}"
        except Exception as e:
            return f"Error listando tareas: {e}"

    def complete_task(self, task_id: str) -> str:
        """Marca tarea como completada."""
        try:
            result = subprocess.run(
                [TASK_BIN, "done", task_id],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return f"Tarea {task_id} completada."
            return f"Error: {result.stderr.strip()}"
        except Exception as e:
            return f"Error completando tarea: {e}"
