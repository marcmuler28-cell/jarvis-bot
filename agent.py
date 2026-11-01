"""
agent.py - Lógica central de triggers, hábitos y predicción contextual.
Separa de assistant.py toda la lógica de _fast_path y clasificador contextual.

Uso:
    from agent import AgentCore
    agent = AgentCore(tools, memory, health, voice, skills, llm)
    resultado = agent.fast_path(user_input)
"""

import os
import re
import json
import time
import subprocess
import shutil
from datetime import datetime, timedelta

from context_collector import get_active_window_kde


class AgentCore:
    """
    Núcleo de agentes: triggers, predicción contextual, fast_path.
    No depende del LLM directamente; recibe las dependencias por inyección.
    """

    def __init__(self, tools, memory, health, voice, skills, llm=None):
        self.tools = tools
        self.memory = memory
        self.health = health
        self.voice = voice
        self.skills = skills if skills else {}
        self.llm = llm  # Opcional, para funciones que necesiten LLM

        # Clasificador contextual
        self.context_clf = None
        self.le_action = None
        self.le_input = None
        self.le_day = None
        self.le_window = None
        self._load_classifier()

        # Triggers
        self.triggers = []
        self._load_triggers()

    # ──────────────────────────────────────────────
    # CLASIFICADOR CONTEXTUAL
    # ──────────────────────────────────────────────

    def _load_classifier(self):
        """Carga el clasificador contextual desde ~/.jarvis/models/context_classifier.pkl"""
        classifier_path = os.path.expanduser("~/.jarvis/models/context_classifier.pkl")
        if os.path.exists(classifier_path):
            try:
                import pickle
                with open(classifier_path, 'rb') as f:
                    (self.context_clf, self.le_action, self.le_input,
                     self.le_day, self.le_window) = pickle.load(f)
                print("[CONTEXT] Clasificador contextual cargado.")
            except Exception as e:
                print(f"[CONTEXT] Error cargando clasificador: {e}")

    def predict_context_action(self, user_input):
        """
        Predice la accion mas probable segun el contexto actual.
        Maneja valores desconocidos (ventanas/inputs nuevos) sin romperse.
        """
        if not self.context_clf:
            return None
        try:
            now = datetime.now()
            active_window = get_active_window_kde()

            def safe_transform(le, values):
                try:
                    return le.transform(values)
                except ValueError:
                    return [-1]

            input_enc = safe_transform(self.le_input, [user_input])[0]
            day_enc = safe_transform(self.le_day, [now.strftime('%A')])[0]
            window_enc = safe_transform(self.le_window, [active_window])[0]

            if day_enc == -1:
                return None

            features = [[now.hour, day_enc, window_enc, input_enc]]
            action_enc = self.context_clf.predict(features)[0]
            action_name = self.le_action.inverse_transform([action_enc])[0]
            return action_name
        except Exception as e:
            return None

    # ──────────────────────────────────────────────
    # TRIGGERS
    # ──────────────────────────────────────────────

    def _load_triggers(self):
        """Carga las reglas de triggers desde ~/.jarvis/triggers.json"""
        path = os.path.expanduser("~/.jarvis/triggers.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.triggers = json.load(f)
                print(f"[TRIGGERS] {len(self.triggers)} reglas cargadas.")
            except Exception as e:
                print(f"[TRIGGERS] Error cargando triggers: {e}")
                self.triggers = []
        else:
            self.triggers = []

    def add_trigger(self, intent, action, args, condition):
        """
        Añade una nueva regla ECA al sistema de triggers.
        intent: descripción legible (ej: 'Abrir Firefox a las 9')
        action: nombre de la herramienta (ej: 'open_app')
        args: argumentos de la herramienta (ej: ['firefox'])
        condition: dict con 'hour', 'minute', 'days' (ej: {'hour':9, 'minute':0, 'days':['Monday','Tuesday',...]})
        """
        new_trigger = {
            "intent": intent,
            "event": "time",
            "action": action,
            "args": args,
            "condition": condition,
            "accepted": True,
            "last_triggered": None
        }
        self.triggers.append(new_trigger)
        self._save_triggers()
        return new_trigger

    def check_triggers(self):
        """
        Evalúa las condiciones de los triggers y ejecuta los que correspondan.
        Se llama periódicamente (ej: desde un timer o al inicio de process()).
        """
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.strftime('%A')

        for trigger in self.triggers:
            if trigger.get('accepted') is not True:
                continue  # Solo triggers aceptados

            if trigger.get('event') == 'time':
                cond = trigger.get('condition', {})
                if (cond.get('hour') == current_hour and
                    cond.get('minute') == current_minute and
                    current_day in cond.get('days', [])):

                    action = trigger.get('action')
                    args = trigger.get('args', [])
                    print(f"[TRIGGER] Ejecutando: {action}({args})")

                    if action in self.tools.actions:
                        try:
                            result = self.tools.actions[action](*args)
                            trigger['last_triggered'] = now.isoformat()
                            self._save_triggers()
                            return result
                        except Exception as e:
                            print(f"[TRIGGER] Error ejecutando {action}: {e}")
        return None

    def _save_triggers(self):
        """Guarda el estado actual de los triggers."""
        path = os.path.expanduser("~/.jarvis/triggers.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.triggers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TRIGGERS] Error guardando: {e}")

    # ──────────────────────────────────────────────
    # DETECCIÓN DE HÁBITOS Y PROPUESTAS
    # ──────────────────────────────────────────────

    def analyze_habits_and_propose(self):
        """
        Analiza los hábitos guardados en context_habits.csv y propone
        automatizaciones si detecta patrones repetitivos.
        Debe llamarse después del entrenamiento nocturno o periódicamente.
        """
        try:
            from habit_clustering import analizar_habitos
            rutinas = analizar_habitos()  # Devuelve lista de dicts con 'hora', 'accion', 'frecuencia'
        except ImportError:
            print("[HABITS] Módulo habit_clustering no encontrado.")
            return
        except Exception as e:
            print(f"[HABITS] Error analizando hábitos: {e}")
            return

        # Filtrar rutinas que no estén ya en triggers
        propuestas = []
        for r in rutinas:
            hora = r.get('hora')
            accion = r.get('accion')
            frecuencia = r.get('frecuencia', 0)

            if not hora or not accion or frecuencia < 3:
                continue

            # Verificar si ya existe un trigger similar
            ya_existe = any(
                t.get('event') == 'time' and
                t.get('condition', {}).get('hour') == hora and
                t.get('action') == accion
                for t in self.triggers
            )
            if not ya_existe:
                propuestas.append(r)

        for prop in propuestas:
            self.propose_automation(prop)

    def propose_automation(self, rutina):
        """
        Propone verbalmente una automatización detectada.
        Si el usuario acepta, guarda el trigger.
        """
        hora = rutina.get('hora')
        accion = rutina.get('accion')
        args = rutina.get('args', [])

        # Construir mensaje
        intent = f"He notado que a las {hora}:00 sueles usar '{accion}'."
        if args:
            intent += f" con los argumentos {args}."
        intent += " ¿Quieres que lo haga automáticamente a esa hora?"

        print(f"[HABITS] Propuesta: {intent}")
        if self.voice:
            self.voice.speak(intent)

            # Escuchar respuesta
            try:
                respuesta = self.voice.listen(timeout=5)
                if respuesta and any(w in respuesta.lower() for w in ["sí", "si", "yes", "claro", "ok", "vale", "dale"]):
                    # Determinar días (asumimos día laborable por defecto, se puede afinar)
                    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
                    trigger = self.add_trigger(
                        intent=intent,
                        action=accion,
                        args=args,
                        condition={"hour": hora, "minute": 0, "days": days}
                    )
                    print(f"[HABITS] Trigger creado: {trigger}")
                    if self.voice:
                        self.voice.speak("Perfecto, lo haré automáticamente a partir de ahora.")
                else:
                    if self.voice:
                        self.voice.speak("De acuerdo, no lo automatizaré.")
            except Exception as e:
                print(f"[HABITS] Error escuchando respuesta: {e}")

    # ──────────────────────────────────────────────
    # MÉTODOS AUXILIARES
    # ──────────────────────────────────────────────

    def fuzzy_match(self, text, keywords):
        """
        Devuelve True si alguna keyword está contenida en text.
        Tolera errores de Whisper con matching parcial.
        """
        generic_prefixes = {
            "abre", "abrir", "busca", "buscar", "muestr", "mostr",
        }

        for kw in keywords:
            if kw in text:
                return True

            if len(kw) >= 5:
                prefix = kw[:5].strip()
                if not prefix or prefix in generic_prefixes:
                    continue
                prefix = re.escape(prefix)
                if re.search(r"\b" + prefix, text):
                    return True

        return False

    def extract_search_query(self, text):
        """
        Extrae la consulta de búsqueda del texto.
        Ejemplo: "busca sobre python" → "python"
        """
        keywords = ["busca sobre", "buscar sobre", "buscas sobre", "busca", "buscar", "buscas"]

        for kw in keywords:
            if kw in text:
                query = text.split(kw, 1)[1].strip()
                for stop in [" y ", " pero ", " luego ", " después"]:
                    if stop in query:
                        query = query.split(stop, 1)[0].strip()
                        break
                return query if query else None

        return None

    # ──────────────────────────────────────────────
    # CONFIRMACIÓN DE APAGADO / REINICIO
    # ──────────────────────────────────────────────

    def confirm_and_poweroff(self, user_input):
        """Solicita confirmación por voz antes de apagar."""
        msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
        if self.voice:
            self.voice.speak(msg)
        else:
            print(msg)

        confirmation = None
        if self.voice:
            confirmation = self.voice.listen(timeout=5)

        if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante", "ok", "okei"]):
            response = "Apagando el sistema. Esto puede requerir permisos de administrador."
            self.memory.add_interaction(user_input, response, [{"action": "poweroff", "args": [], "result": "initiated"}])
            try:
                if shutil.which("systemctl"):
                    subprocess.run(["systemctl", "poweroff"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("shutdown"):
                    subprocess.run(["shutdown", "-h", "now"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    response = "No encontré un comando de apagado válido en el sistema."
            except Exception as e:
                response = f"No pude apagar el sistema: {e}. Ejecuta Jarvis como root o configura sudo sin contraseña."
            return response, []
        else:
            response = "Apagado cancelado."
            return response, []

    def confirm_and_reboot(self, user_input):
        """Solicita confirmación por voz antes de reiniciar."""
        msg = "¿Estás seguro de que quieres reiniciar el equipo? Di 'sí' para confirmar."
        if self.voice:
            self.voice.speak(msg)
        else:
            print(msg)

        confirmation = None
        if self.voice:
            confirmation = self.voice.listen(timeout=5)

        if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante", "ok", "okei"]):
            response = "Reiniciando el sistema. Esto puede requerir permisos de administrador."
            self.memory.add_interaction(user_input, response, [{"action": "reboot", "args": [], "result": "initiated"}])
            try:
                if shutil.which("systemctl"):
                    subprocess.run(["systemctl", "reboot"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("shutdown"):
                    subprocess.run(["shutdown", "-r", "now"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    response = "No encontré un comando de reinicio válido en el sistema."
            except Exception as e:
                response = f"No pude reiniciar el sistema: {e}. Ejecuta Jarvis como root o configura sudo sin contraseña."
            return response, []
        else:
            response = "Reinicio cancelado."
            return response, []