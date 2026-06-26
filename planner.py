import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Intentamos importar fuzzywuzzy; si no esta, usamos coincidencia exacta
try:
    from fuzzywuzzy import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# Rutas por defecto
JARVIS_DIR = os.path.expanduser("~/.jarvis")
RECIPES_FILE = os.path.join(JARVIS_DIR, "recipes.json")
ARCHIVE_FILE = os.path.join(JARVIS_DIR, "recipes.archive.json")
LOG_DIR = os.path.join(JARVIS_DIR, "logs")
PLANNER_LOG = os.path.join(LOG_DIR, "planner.log")
UNDO_FILE = os.path.join(JARVIS_DIR, "tmp", "undo_stack.json")

# Asegurar que existen las carpetas
for d in [JARVIS_DIR, LOG_DIR, os.path.dirname(UNDO_FILE)]:
    os.makedirs(d, exist_ok=True)


class RecipeLoader:
    """Carga, guarda y busca recetas en disco."""

    def __init__(self):
        self.recipes: Dict[str, dict] = {}
        self.load()

    def load(self):
        if os.path.exists(RECIPES_FILE):
            with open(RECIPES_FILE, 'r', encoding='utf-8') as f:
                self.recipes = json.load(f)

    def save(self):
        with open(RECIPES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.recipes, f, indent=2, ensure_ascii=False)

    def find_recipe(self, user_input: str) -> Optional[Tuple[str, dict]]:
        """Busca la receta por intent, primero exacto y luego difuso."""
        text = user_input.lower().strip()
        # 1. Coincidencia exacta
        for intent, recipe in self.recipes.items():
            if intent.lower() in text:
                return intent, recipe
        # 2. Busqueda difusa (si esta disponible)
        if FUZZY_AVAILABLE:
            best_score = 0
            best_intent = None
            for intent in self.recipes:
                score = fuzz.partial_ratio(text, intent.lower())
                if score > best_score:
                    best_score = score
                    best_intent = intent
            if best_score >= 70 and best_intent:
                return best_intent, self.recipes[best_intent]
        return None

    def add_recipe(self, intent: str, recipe: dict):
        self.recipes[intent] = recipe
        self.save()

    def archive_unused(self, days_threshold=30):
        now = datetime.now()
        to_archive = {}
        active = {}
        for intent, recipe in self.recipes.items():
            last_used = recipe.get("last_used")
            if last_used:
                last_dt = datetime.fromisoformat(last_used)
                if (now - last_dt).days > days_threshold:
                    to_archive[intent] = recipe
                    continue
            active[intent] = recipe
        if to_archive:
            archive = {}
            if os.path.exists(ARCHIVE_FILE):
                with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                    archive = json.load(f)
            archive.update(to_archive)
            with open(ARCHIVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(archive, f, indent=2, ensure_ascii=False)
            self.recipes = active
            self.save()
        return len(to_archive)


class ParamExtractor:
    """Extrae parametros del lenguaje natural usando regex por receta."""

    @staticmethod
    def extract(intent: str, user_input: str, recipe: dict) -> dict:
        params = {}
        if "param_patterns" in recipe:
            for param_name, pattern in recipe["param_patterns"].items():
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    params[param_name] = match.group(1).strip()
        return params


class PlanExecutor:
    """Ejecuta un plan paso a paso, con precondiciones, recuperacion y deshacer."""

    def __init__(self, tools, memory):
        self.tools = tools
        self.memory = memory
        self.undo_stack = []
        # Cargar pila de deshacer persistente
        if os.path.exists(UNDO_FILE):
            try:
                with open(UNDO_FILE, 'r', encoding='utf-8') as f:
                    self.undo_stack = json.load(f)
            except Exception:
                self.undo_stack = []

    def execute(self, plan: dict, params: dict, voice=None) -> Tuple[str, List[dict]]:
        """
        Ejecuta un plan.
        Devuelve (respuesta_final, actions_log).
        """
        steps = plan.get("steps", [])
        results = []
        actions_log = []

        for i, step in enumerate(steps):
            tool = step["tool"]
            args = self._resolve_args(step.get("args", []), params)
            precond = step.get("preconditions", [])
            recovery = step.get("recovery")

            # 1. Verificar precondiciones
            if not self._check_preconditions(precond):
                if "create_folder" in str(precond):
                    try:
                        folder = self._resolve_arg(precond[0], params)
                        self.tools.create_folder(folder)
                        results.append(f"Precondicion resuelta: creada carpeta {folder}")
                    except Exception as e:
                        results.append(f"No se pudo crear la carpeta: {e}")
                        continue
                else:
                    results.append(f"Precondicion fallida en paso {i+1}")
                    continue

            # 2. Ejecutar la accion
            try:
                func = self.tools.actions[tool]
                result = func(*args) if args else func()
                ok, info = self.tools.verify_action(tool, args, str(result))
                if ok:
                    results.append(f"Paso {i+1}: {result}")
                    actions_log.append({"action": tool, "args": args, "result": str(result)})
                    self._record_undo(step, args)
                else:
                    raise RuntimeError(info)
            except Exception as e:
                error_msg = f"Paso {i+1} fallo ({tool}): {e}"
                results.append(error_msg)
                actions_log.append({"action": tool, "args": args, "result": error_msg})
                if recovery:
                    try:
                        rec_tool = recovery["tool"]
                        rec_args = self._resolve_args(recovery.get("args", []), params)
                        func = self.tools.actions[rec_tool]
                        rec_result = func(*rec_args) if rec_args else func()
                        results.append(f"Recuperacion: {rec_result}")
                        actions_log.append({"action": rec_tool, "args": rec_args, "result": str(rec_result)})
                    except Exception as e2:
                        results.append(f"No se pudo recuperar: {e2}")
                        final = f"No se completo la tarea. {error_msg}"
                        return final, actions_log

        # Marcar la receta como usada
        plan["last_used"] = datetime.now().isoformat()
        final = f"Plan completado: {plan.get('task', 'plan')}. Resultados:\n" + "\n".join(results)
        return final, actions_log

    def _resolve_args(self, args: list, params: dict) -> list:
        """Reemplaza marcadores {param} en los argumentos."""
        resolved = []
        for arg in args:
            if isinstance(arg, str) and '{' in arg:
                for k, v in params.items():
                    arg = arg.replace(f'{{{k}}}', v)
            resolved.append(arg)
        return resolved

    def _resolve_arg(self, arg: str, params: dict) -> str:
        return self._resolve_args([arg], params)[0]

    def _check_preconditions(self, preconditions: list) -> bool:
        """Verifica precondiciones simples (ej. que una carpeta exista)."""
        for cond in preconditions:
            if cond.startswith("exists:"):
                path = cond[7:]
                if not os.path.exists(path):
                    return False
        return True

    def _record_undo(self, step: dict, args: list):
        """Guarda accion inversa en la pila de deshacer."""
        tool = step["tool"]
        inverse = step.get("inverse")
        if inverse:
            self.undo_stack.append({
                "tool": inverse,
                "args": args,
                "timestamp": datetime.now().isoformat()
            })
            with open(UNDO_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.undo_stack, f, indent=2)

    def undo_last(self) -> str:
        """Deshace la ultima accion ejecutada."""
        if not self.undo_stack:
            return "No hay nada que deshacer."
        action = self.undo_stack.pop()
        try:
            func = self.tools.actions[action["tool"]]
            result = func(*action["args"])
            with open(UNDO_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.undo_stack, f, indent=2)
            return f"Deshecho: {result}"
        except Exception as e:
            return f"No se pudo deshacer: {e}"
