import os
import sys
import json
import time
import threading
import subprocess
import platform
import tempfile
import wave
import re

# Asegurar que el directorio del script está en sys.path,
# para que import spotify_manager funcione desde systemd o desde otro cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime
from datetime import datetime, date
import random
import glob
import urllib.parse
import shutil
import pyperclip
from pathlib import Path
from rag import RAGManager
from planner import RecipeLoader, ParamExtractor, PlanExecutor
from skills.taskwarrior_skill import TaskwarriorSkill
from context_collector import log_interaction, get_active_window_kde
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, tools):
        self.tools = tools
        self._debounce = {}

    def _should_log(self, path):
        now = time.time()
        if path in self._debounce and now - self._debounce[path] < 2:
            return False
        self._debounce[path] = now
        return True

    def on_created(self, event):
        if not event.is_directory and self._should_log(event.src_path):
            self.tools._log_file_event("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._should_log(event.src_path):
            self.tools._log_file_event("modified", event.src_path)

    def on_moved(self, event):
        if not event.is_directory and self._should_log(event.dest_path):
            self.tools._log_file_event("moved", event.dest_path, extra=f"origen: {event.src_path}")

def start_file_monitor(tools):
    paths = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    event_handler = FileChangeHandler(tools)
    observer = Observer()
    for p in paths:
        if os.path.exists(p):
            observer.schedule(event_handler, p, recursive=False)
    observer.start()
    return observer
import numpy as np
import sounddevice as sd

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import pygame
except Exception:
    pygame = None

try:
    from spotify_manager import play_playlist_by_name, play_liked_songs, open_playlists, play_track_by_name
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False
    print("⚠️ spotify_manager no encontrado. Comandos de Spotify desactivados.")

from faster_whisper import WhisperModel
from llama_cpp import Llama

pynput_mouse = None
pynput_keyboard = None

from openwakeword.model import Model

from config import TEXT_MODE, MODEL_FAST, MODEL_POWERFUL, CTX_SIZE, MAX_REACT_STEPS, PATHS, POWER_COMMANDS, SELF_IMPROVER_ENABLED, WHISPER_SIZE, LOG_LEVEL
from logger_config import logger
from normalizer import normalizar, extraer_nombre_app, corregir_nombre_app, levenshtein, buscar_mejor_coincidencia
import finetune_db
import logging
from agent import AgentCore
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
from database import MemoryManager
from utils import SystemTools
from skills.weather import WeatherSkill
from skills.reminders import RemindersSkill
from skills.notes import NotesSkill
from skills.system_info import SystemInfoSkill
from skills.web_search import WebSearchSkill
from skills.blackboard_skill import BlackboardSkill
from ui import VoiceInterface


def merge_linux_gui_launch_env(env_dict):
    """Rellena DISPLAY / WAYLAND / XDG_RUNTIME_DIR cuando el backend corre bajo systemd (sin sesión GUI en env)."""
    if platform.system() != "Linux":
        return dict(env_dict)
    out = dict(env_dict)
    uid = os.getuid()
    rt = out.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    out["XDG_RUNTIME_DIR"] = rt
    if out.get("PATH"):
        if "/usr/bin" not in out["PATH"]:
            out["PATH"] = f'{out["PATH"]}:/usr/local/bin:/usr/bin:/bin'
    else:
        out["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    if not out.get("DISPLAY"):
        try:
            xdir = "/tmp/.X11-unix"
            if os.path.isdir(xdir):
                lowest_num = None
                for name in sorted(os.listdir(xdir)):
                    if name.startswith("X") and name[1:].isdigit():
                        n = int(name[1:])
                        if lowest_num is None or n < lowest_num:
                            lowest_num = n
                if lowest_num is not None:
                    out["DISPLAY"] = f":{lowest_num}"
        except OSError:
            pass
    if not out.get("WAYLAND_DISPLAY"):
        for w in ("wayland-0", "wayland-1"):
            if os.path.exists(os.path.join(rt, w)):
                out["WAYLAND_DISPLAY"] = w
                break
    return out


class HealthMonitor:
    """Monitor de salud y metricas del asistente."""
    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "fast_path_hits": 0,
            "llm_calls": 0,
            "llm_total_time": 0.0,
            "parse_retries": 0,
            "actions_executed": 0,
            "actions_failed": 0,
        }
        self.start_time = time.time()

    def record_request(self, fast_path_hit=False):
        self.stats["total_requests"] += 1
        if fast_path_hit:
            self.stats["fast_path_hits"] += 1

    def record_llm_call(self, duration):
        self.stats["llm_calls"] += 1
        self.stats["llm_total_time"] += duration

    def record_parse_retry(self):
        self.stats["parse_retries"] += 1

    def record_action_result(self, success):
        self.stats["actions_executed"] += 1
        if not success:
            self.stats["actions_failed"] += 1

    def get_uptime(self):
        return time.time() - self.start_time

    def get_report(self):
        uptime = self.get_uptime()
        avg_llm = (self.stats["llm_total_time"] / self.stats["llm_calls"]
                    if self.stats["llm_calls"] > 0 else 0)
        return (
            f"Salud Jarvis (activo: {uptime/60:.1f} min)\n"
            f"Peticiones: {self.stats['total_requests']} "
            f"(fast: {self.stats['fast_path_hits']}, LLM: {self.stats['llm_calls']})\n"
            f"LLM promedio: {avg_llm:.2f}s | Reintentos parseo: {self.stats['parse_retries']}\n"
            f"Acciones: {self.stats['actions_executed']} "
            f"(fallos: {self.stats['actions_failed']})"
        )

class ReActAgent:
    SYSTEM_PROMPT_TEMPLATE = """Eres Jarvis, un asistente de escritorio inteligente.
Responde de forma concisa y directa. Si necesitas realizar acciones, usa el formato ReAct exactamente así:

Pensamiento: (tu razonamiento breve sobre qué hacer)
Acción: herramienta|argumento1,argumento2
Respuesta final: (tu mensaje final al usuario)

Herramientas disponibles: open_app, spotify_liked_songs, read_file, run_command, move_mouse, click, type_text, press_key, screenshot, copy_file, move_file, create_folder, list_folder, drag_file, list_processes, write_file, set_brightness, get_brightness, set_volume, get_volume, lock_session, system_status, pending_updates, service_status, kill_process.

Instrucciones de herramientas:
- spotify_liked_songs (sin argumentos) Abre Spotify en «Tus me gusta» e intenta reproducir música de esa lista. Usar una sola acción: spotify_liked_songs|
- Para comandos como "suscríbete", "suscribirme" o similares, usar spotify_liked_songs| para abrir Spotify.

- list_processes (Muestra los procesos activos en el PC)
- copy_file|ruta_origen,ruta_destino (Copia un archivo)
- move_file|origen,destino (Mueve o renombra archivo/carpeta)
- create_folder|ruta (Crea una carpeta nueva)
- list_folder|ruta (Lista archivos en una ruta)
- move_mouse|x,y (Mueve el ratón a coordenadas)
- drag_file|x1,y1,x2,y2 (Arrastra de un punto a otro)
- write_file|ruta,contenido (Crea o sobreescribe un archivo con texto)
- set_brightness|valor (Ajusta el brillo, ej: 50%, 200, 10%+ para subir 10%)
- get_brightness| (Obtiene el nivel de brillo actual)
- set_volume|valor (Ajusta el volumen, ej: 40%, 80, 10%+ para subir 10%)
- get_volume| (Obtiene el volumen actual)
- lock_session| (Bloquea la sesion del sistema)
- system_status| (Muestra CPU, RAM y disco)
- pending_updates| (Comprueba actualizaciones pendientes de pacman)
- service_status|nombre (Estado de un servicio systemd)
- kill_process|nombre_o_pid (Termina un proceso, requiere confirmacion)
- NUNCA uses run_command para abrir aplicaciones ni para manipular archivos; run_command es solo para comandos de terminal que necesiten su salida.

Memoria y contexto:
{lessons}
{history}
Usuario: {user_input}
Pensamiento:"""

    def __init__(self, fast_model_path, powerful_model_path, ctx_size=CTX_SIZE):
        self.powerful_model_path = powerful_model_path
        self.ctx_size = ctx_size
        try:
            logger.info("Cargando modelo rápido (Qwen 3B)...")
            self.llm_fast = Llama(
                model_path=fast_model_path,
                n_ctx=ctx_size,
                n_threads=4,
                n_batch=256,
                n_gpu_layers=0,
                seed=42,
                verbose=False
            )
            logger.info("Modelo rápido cargado.")
        except Exception as e:
            logger.error(f"Error cargando modelo rápido: {e}")
            raise
        self.llm_powerful = None
        self.current_llm = self.llm_fast
        self.tools = SystemTools()
        self.memory = MemoryManager()
        self.taskwarrior = TaskwarriorSkill()
        self.skills = {
            "weather": WeatherSkill(),
            "reminders": RemindersSkill(),
            "notes": NotesSkill(),
            "system_info": SystemInfoSkill(),
            "web_search": WebSearchSkill(),
            "blackboard": BlackboardSkill(self.memory)
        }
        self.rag = RAGManager()
        self.health = HealthMonitor()
        self.recipe_loader = RecipeLoader()
        self.plan_executor = PlanExecutor(self.tools, self.memory)
        self.file_observer = start_file_monitor(self.tools)
        self.context_clf = None
        self.le_action = None
        self.le_input = None
        self.le_day = None
        self.le_window = None
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

        # AgentCore: lógica de triggers, predicción contextual y fast_path
        self.agent = AgentCore(
            tools=self.tools,
            memory=self.memory,
            health=self.health,
            voice=None,                  # <--- CORREGIDO: ya no usa self.voice
            skills=self.skills,
            llm=self.current_llm
        )
        # Sincronizar el clasificador ya cargado
        self.agent.context_clf = self.context_clf
        self.agent.le_action = self.le_action
        self.agent.le_input = self.le_input
        self.agent.le_day = self.le_day
        self.agent.le_window = self.le_window

    def load_powerful_model(self):
        if self.llm_powerful is None:
            try:
                logger.info("Cargando modelo potente (Qwen 7B) bajo demanda...")
                self.llm_powerful = Llama(
                    model_path=self.powerful_model_path,
                    n_ctx=self.ctx_size,
                    n_threads=4,
                    n_batch=256,
                    n_gpu_layers=0,
                    seed=42,
                    verbose=False
                )
                logger.info("Modelo potente cargado.")
            except Exception as e:
                logger.error(f"Error cargando modelo potente: {e}")
                raise

    def is_complex_task(self, user_input: str) -> bool:
        text = user_input.lower()
        complex_keywords = [
            "analiza", "explica detalladamente", "código", "programa", "script",
            "depura", "debug", "error", "resuelve", "arquitectura", "diseña",
            "compara", "optimiza", "refactoriza", "documenta", "investiga"
        ]
        if any(kw in text for kw in complex_keywords):
            return True
        if len(user_input) > 100:
            return True
        return False

    def _expected_args_count_heuristic(self, func_name):
        expected = {
            "open_app": (1, 1),
            "read_file": (1, 1),
            "list_recent_files": (0, 2),
            "run_command": (1, 1),
            "move_mouse": (2, 3),
            "click": (0, 1),
            "double_click": (0, 0),
            "right_click": (0, 0),
            "type_text": (1, 2),
            "press_key": (1, 1),
            "screenshot": (0, 1),
            "locate_on_screen": (1, 2),
            "mouse": (0, 1),
            "spotify_liked_songs": (0, 0),
            "list_processes": (0, 2),
        }
        return expected.get(func_name, (0, 3))

    def _parse_response(self, text):
        thought = ""
        actions = []
        final_answer = None

        m = re.search(r'Pensamiento:\s*(.+?)(?=Acci\u00f3n:|Respuesta final:|Respuesta:|$)', text, re.DOTALL)
        if m:
            thought = m.group(1).strip()

        for m in re.finditer(r'Acci\u00f3n:\s*(.+?)(?:\n|$)', text, re.MULTILINE):
            action_str = m.group(1).strip()
            action_str = re.sub(r'[\[\]"\'\\\\]', '', action_str).strip()
            
            if action_str.count('|') > 1:
                logger.warning(f"Accion malformada con multiples pipes: {action_str}")
                continue
            
            if '|' in action_str:
                func_name, _, args_str = action_str.partition('|')
                func_name = func_name.strip()
                args = [a.strip() for a in args_str.split(',') if a.strip()]
            else:
                func_name = action_str.split()[0].strip() if action_str else ''
                args = []
            
            if not func_name:
                continue
            
            if func_name not in self.tools.actions:
                logger.warning(f"Herramienta desconocida: {func_name}")
                continue
            
            min_a, max_a = self._expected_args_count_heuristic(func_name)
            if min_a <= len(args) <= max_a:
                actions.append((func_name, args))
            else:
                logger.warning(f"Numero de argumentos invalido para {func_name}: {args} (esperado {min_a}-{max_a})")

        for trigger in ["Respuesta final:", "Respuesta:", "Respondiendo:", "Jarvis:"]:
            if trigger in text:
                idx = text.rfind(trigger)
                final_answer = text[idx + len(trigger):].strip()
                break

        if not final_answer and not actions and text.strip():
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                last = lines[-1]
                if "Pensamiento:" not in last and "Acci" not in last:
                    final_answer = last

        return thought, actions, final_answer


    def _execute_action(self, action):
        func_name, args = action
        if func_name in self.tools.actions:
            try:
                result = self.tools.actions[func_name](*args)
                result_str = str(result)
            except Exception as e:
                result_str = f"Error en acción {func_name}: {e}"
                return result_str, False, result_str

            ok, info = self.tools.verify_action(func_name, args, result_str)
            if not ok:
                conflict_desc = f"Fallo en {func_name} con {args}: {info}"
                self.memory.add_lesson(f"conflict_{datetime.now().timestamp()}", 
                                       json.dumps({"action": func_name, "args": args, "error": info}))
                
                repair_msg = self._autonomous_repair(action, info)
                return result_str + f" [CONFLICTO: {info}] [REPARACIÓN: {repair_msg}]", False, conflict_desc
            return result_str, True, ""
        else:
            return f"Acción desconocida: {func_name}", False, ""

    def _execute_with_retries(self, action, max_attempts=3):
        attempts = 0
        last_result = ""
        conflict_desc = ""
        while attempts < max_attempts:
            result_str, ok, conflict_desc = self._execute_action(action)
            if ok:
                return result_str, True, ""
            
            attempts += 1
            if attempts >= max_attempts:
                last_result = result_str
                break
            
            print(f"⚠️ Intento {attempts} fallido. Probando auto-reparación...")
            repair_msg = self._autonomous_repair(action, conflict_desc)
            print(f"🔧 Reparación: {repair_msg}")
            
            time.sleep(1.0)
            
        return last_result, False, f"Fallo tras {max_attempts} intentos. {conflict_desc}"

    def _autonomous_repair(self, action, error_desc):
        func_name, args = action
        if func_name == "move_mouse":
            try:
                screen_w, screen_h = pyautogui.size()
                safe_x, safe_y = screen_w//2, screen_h//2
                self.tools.move_mouse(safe_x, safe_y, 0.3)
                new_x = min(max(int(args[0]), 20), screen_w-20)
                new_y = min(max(int(args[1]), 20), screen_h-20)
                return self.tools.move_mouse(new_x, new_y, 0.3)
            except Exception as e:
                return f"No se pudo reparar movimiento: {e}"
        elif func_name == "type_text" and ("Error" in error_desc or "foco" in error_desc.lower()):
            try:
                self.tools.click("left")
                time.sleep(0.2)
                return self.tools.type_text(*args)
            except Exception as e:
                return f"No se pudo reparar escritura: {e}"
        
        if func_name != "open_app":
            return "No hay estrategia de reparación para esta herramienta."

        original_name = args[0]
        logger.debug(f"Iniciando auto-reparación para {original_name}...")
        
        prompt = f"Instrucción: Lista 3 nombres técnicos (ej: notepad, calc, chrome) para la aplicación '{original_name}'.\nRespuesta: "
        
        try:
            output = self.current_llm(
                prompt,
                max_tokens=50,
                stop=["\n", "Instrucción:"],
                temperature=0.2
            )
            text_alt = output["choices"][0]["text"].strip()
            text_alt = re.sub(r'[0-9]\.', '', text_alt)
            text_alt = text_alt.replace("\n", ",").replace(";", ",")
            
            alternatives = [a.strip().lower() for a in text_alt.split(",") if a.strip()]
            if len(alternatives) <= 1:
                alternatives = [a.strip().lower() for a in text_alt.split() if a.strip()]
            
            for alt in alternatives:
                if not alt or alt == original_name:
                    continue
                
                try:
                    res_str = self.tools.open_app(alt)
                    time.sleep(2.0)
                    ok, _ = self.tools.verify_action("open_app", [alt], res_str)
                    if ok:
                        signature = f"open_app|{original_name}"
                        self.memory.save_conflict_fix(signature, ("open_app", [alt]), True)
                        SystemTools.APP_ALIASES[original_name] = alt
                        return f"Aprendí que '{original_name}' se abre con '{alt}'."
                except:
                    continue
            
            logger.debug(f"LLM no ayudó. Buscando '{original_name}' en Program Files...")
            found_path = self.tools._find_executable_on_disk(original_name)
            if found_path:
                try:
                    res_str = self.tools.open_app(found_path)
                    time.sleep(1)
                    ok, _ = self.tools.verify_action("open_app", [found_path], res_str)
                    if ok:
                        self.memory.save_conflict_fix(f"open_app|{original_name}", ("open_app", [found_path]), True)
                        SystemTools.APP_ALIASES[original_name] = found_path
                        return f"Localicé la aplicación en el disco: {found_path}"
                except: pass

            return "No encontré una alternativa funcional."
        except Exception as e:
            return f"Error en auto-reparación: {e}"

    def _try_resolve_conflict(self, action, error_desc):
        func_name, args = action
        signature = f"{func_name}|{','.join(args) if args else ''}"
        
        past_fixes = self.memory.get_conflict_fixes(signature)
        for fix in past_fixes:
            if fix.get("success"):
                fix_action = fix["fix_action"]
                try:
                    fname, fargs = fix_action
                    result = self.tools.actions[fname](*fargs)
                    return f"Recuperado usando solución previa: {result}"
                except:
                    continue

        repair_msg = self._autonomous_repair(action, error_desc)
        if "Aprendí" in repair_msg:
            return repair_msg
            
        return "No se pudo resolver el conflicto automáticamente."

    # -----------------------------------------------------------------
    # Función auxiliar para detectar tareas con fecha
    # -----------------------------------------------------------------
    @staticmethod
    def es_tarea_con_fecha(texto: str) -> bool:
        """Detecta si la frase incluye palabras que sugieren una tarea con fecha/hora."""
        indicadores = [
            "clases", "mañana", "tarde", "noche", "lunes", "martes", "miércoles",
            "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo",
            "a las", "el día", "a la", "hora", "horas", "pm", "am",
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]
        return any(ind in texto.lower() for ind in indicadores)

    def _fast_path(self, user_input):
        text = normalizar(user_input)
        text_norm = normalizar(text)

        # --- Mostrar comandos disponibles ---
        if any(phrase in text_norm for phrase in [
            "dime los comandos",
            "di los comandos",
            "dime los comando",
            "di los comando",
            "muéstrame los comandos",
            "mostrar comandos",
            "qué comandos",
            "que comandos",
            "lista de comandos",
            "comandos alexa",
            "dime los comandos alexa",
        ]):
            response = (
                "Puedo abrir apps como Spotify, calculadora, navegador o el panel de métricas, "
                "cerrar apps como Spotify o el panel de Quickshell, "
                "mostrar métricas de programas y procesos, "
                "buscar en Google, crear recordatorios, "
                "y también apagar o reiniciar el equipo si dices 'apágate' o 'reinicia el equipo'."
            )
            self.memory.add_interaction(user_input, response, [{"action": "help", "args": [], "result": response}])
            return response, []

        # --- Spotify: Reproducir playlist por nombre ---
        if SPOTIFY_AVAILABLE:
            match = re.search(r'(?:reproduce|pon|poner|toca)\s+(?:la\s+)?playlist\s+(.+)', text)
            if match:
                playlist_name = match.group(1).strip()
                for stop in [" y ", " luego", " después"]:
                    if stop in playlist_name:
                        playlist_name = playlist_name.split(stop, 1)[0].strip()
                try:
                    result = play_playlist_by_name(playlist_name)
                    response = result
                    self.memory.add_interaction(user_input, response, [{"action": "play_playlist_by_name", "args": [playlist_name], "result": result}])
                    print(f"[⏱️ SPOTIFY] Playlist: {playlist_name} ejecutada en tiempo real", flush=True)
                    return response, []
                except Exception as e:
                    print(f"Error reproduciendo playlist: {e}", flush=True)
                    return f"Error reproduciendo playlist: {e}", []

        # --- Spotify: Reproducir "Tus me gusta" (frases completas) ---
        if SPOTIFY_AVAILABLE and any(phrase in text for phrase in [
            "me gusta", "megusta", "likes", "tus me gusta",
            "lista de me gusta", "mis me gusta", "canciones que me gustan"
        ]):
            try:
                result = play_liked_songs()
                response = result
                self.memory.add_interaction(user_input, response, [{"action": "play_liked_songs", "args": [], "result": result}])
                print(f"[⏱️ SPOTIFY] Me gusta reproduciendo", flush=True)
                return response, []
            except Exception as e:
                print(f"Error reproduciendo me gusta: {e}", flush=True)
                return f"Error reproduciendo me gusta: {e}", []

        # --- Spotify: Reproducir "Tus me gusta" (detección extra por errores de transcripción) ---
        if SPOTIFY_AVAILABLE:
            text_lower = text.lower()
            m_verb = re.search(r'(?:reproduce|pon|poner|toca)\s+(.+)', text_lower)
            if m_verb:
                rest = m_verb.group(1).strip().rstrip('.')
                # Si después del verbo solo hay una palabra y contiene "like" o "laik", es un "liked" mal transcrito
                if len(rest.split()) == 1 and any(p in rest for p in ["like", "laik", "liked"]):
                    try:
                        result = play_liked_songs()
                        response = result
                        self.memory.add_interaction(user_input, response, [{"action": "play_liked_songs", "args": [], "result": result}])
                        print(f"[⏱️ SPOTIFY] Me gusta (corregido de '{rest}')", flush=True)
                        return response, []
                    except Exception as e:
                        print(f"Error reproduciendo me gusta (corregido): {e}", flush=True)
                        return f"Error reproduciendo me gusta: {e}", []
                # --- Spotify / Música por voz (atajo rápido) ---
        if SPOTIFY_AVAILABLE and any(phrase in text for phrase in [
            "música", "musica", "pon música", "pon musica",
            "ponme música", "quiero música", "pon algo de música"
        ]):
            try:
                result = play_liked_songs()
                response = result
                self.memory.add_interaction(user_input, response, [{"action": "play_liked_songs", "args": [], "result": result}])
                print(f"[⏱️ SPOTIFY] Música rápida", flush=True)
                return response, []
            except Exception as e:
                print(f"Error reproduciendo música: {e}", flush=True)
                return f"Error reproduciendo música: {e}", []                
        # --- Spotify: Abrir "Mis playlists" ---
        if SPOTIFY_AVAILABLE and ("mis playlists" in text or "lista de playlist" in text or "mis playlist" in text):
            try:
                result = open_playlists()
                response = result
                self.memory.add_interaction(user_input, response, [{"action": "open_playlists", "args": [], "result": result}])
                print(f"[⏱️ SPOTIFY] Abriendo playlists del usuario", flush=True)
                return response, []
            except Exception as e:
                print(f"Error abriendo playlists: {e}", flush=True)
                return f"Error abriendo playlists: {e}", []

        # --- Spotify: Reproducir canción por nombre ---
        print("DEBUG: llegamos al bloque de canción", flush=True)
        if SPOTIFY_AVAILABLE:
            verbos = r'reproduc\w*|pon|poner|toca'
            patron = rf'(?:(?:puedes|puede|pueden)\s+)?(?:{verbos})\s+(?:la\s+)?(?:canción|cancion|tema|track|música|musica\s+)?(.+)'
            if "playlist" in text or "me gusta" in text or "megusta" in text or "likes" in text:
                match = None
            else:
                match = re.search(patron, text)

            if match:
                track_name = match.group(1).strip()
                for muletilla in [" y ", " luego", " después", " por favor", " ahora"]:
                    if track_name.endswith(muletilla):
                        track_name = track_name[:-len(muletilla)].strip()
                track_name = re.sub(r'\bque\s+de\b', 'quédate', track_name, flags=re.IGNORECASE)
                track_name = track_name.replace("contigo", "conmigo").replace("con tigo", "conmigo")

                if track_name:
                    try:
                        result = play_track_by_name(track_name)
                        self.memory.add_interaction(user_input, result, [{"action": "play_track_by_name", "args": [track_name], "result": result}])
                        print(f"[⏱️ SPOTIFY] Canción: {track_name} ejecutada en tiempo real", flush=True)
                        return result, []
                    except Exception as e:
                        print(f"Error reproduciendo canción: {e}", flush=True)
                        return f"Error reproduciendo canción: {e}", []

        # --- Función auxiliar para matching difuso ---
        def fuzzy_match(text, keywords):
            generic_prefixes = {
                "abre",
                "abrir",
                "busca",
                "buscar",
                "muestr",
                "mostr",
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

        # --- Procesos específicos: CPU / RAM por programa ---
        if any(word in text for word in ["nota", "horario", "blackboard", "tarea", "curso", "materia", "promedio", "intranet"]):
            pass
        elif any(word in text for word in ["proceso", "programa", "app", "aplicación", "aplicacion"]) and any(
            word in text for word in ["cpu", "memoria", "ram", "uso", "usa", "gasta", "consume"]
        ):
            if any(term in text for term in ["más cpu", "mas cpu", "top cpu", "mayor cpu", "cpu más", "uso cpu"]):
                cmd = "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -15"
                res = self.tools.run_command(cmd)
                response = "Procesos principales por uso de CPU:"
                self.memory.add_interaction(user_input, response, [{"action": "run_command", "args": [cmd], "result": res}])
                return response + "\n" + res, []

            if any(term in text for term in ["más memoria", "mas memoria", "top memoria", "mayor memoria", "ram", "uso memoria"]):
                cmd = "ps -eo pid,comm,%cpu,%mem --sort=-%mem | head -15"
                res = self.tools.run_command(cmd)
                response = "Procesos principales por uso de memoria:"
                self.memory.add_interaction(user_input, response, [{"action": "run_command", "args": [cmd], "result": res}])
                return response + "\n" + res, []

            specific = None
            match = re.search(r"uso.*de ([\w\s]+)", text)
            if match:
                specific = match.group(1).strip()
            elif "de " in text:
                candidate = text.split("de ", 1)[1].strip()
                if candidate:
                    specific = candidate
            if specific:
                specific = re.sub(r"\b(cpu|memoria|ram|proceso|programa|app|aplicación|aplicacion|que|qué|que)\b", "", specific).strip()
                specific = specific.split()[0:4]
                specific = " ".join(specific).strip()
                if specific:
                    cmd = f"ps -eo pid,comm,%cpu,%mem | grep -i '{specific}' | head -15"
                    res = self.tools.run_command(cmd)
                    response = f"Uso de CPU/RAM para procesos relacionados con '{specific}':"
                    self.memory.add_interaction(user_input, response, [{"action": "run_command", "args": [cmd], "result": res}])
                    return response + "\n" + res, []

        # --- Spotify: abrir Tus me gusta y reproducir ---
        if "spotify" in text and fuzzy_match(
            text,
            [
                "me gusta",
                "megusta",
                "liked",
                "likes",
                "gustan",
                "tus me gusta",
                "lista",
                "musica",
                "música",
                "reproduce",
                "canciones",
                "canción",
                "song",
                "shuffle",
                "mezcla",
            ],
        ):
            res = self.tools.spotify_liked_songs()
            actions_log = [{"action": "spotify_liked_songs", "args": [], "result": res}]
            self.memory.add_interaction(user_input, res, actions_log)
            self._maybe_extract_lesson(user_input, res)
            return res, actions_log

        # --- Navegador y Búsqueda ---
        if fuzzy_match(text, ["busca ", "buscar ", "buscas "]):
            query = ""
            for kw in ["busca sobre ", "buscar sobre ", "buscas sobre ", "busca ", "buscar ", "buscas "]:
                if kw in text:
                    query = text.split(kw, 1)[1].strip()
                    break
            
            if query:
                try:
                    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                    res = self.tools.run_command(f'xdg-open "{url}"')
                    response = f"Buscando '{query}' en el navegador."
                    self.memory.add_interaction(user_input, response, [{"action": "run_command", "args": [url], "result": res}])
                    self._maybe_extract_lesson(user_input, response)
                    return response, []
                except Exception as e:
                    return f"Error al buscar en el navegador: {e}", []

        if ("abre" in text or "abrir" in text or "open" in text) and ("cibertec" in text or "blackboard" in text or "plataforma" in text):
            try:
                response = "Actualizando Cibertec y Blackboard en segundo plano. Esto puede tardar un momento."
                actions_log = [{"action": "blackboard_fetch_all_data", "args": [], "result": "started"}]
                self.memory.add_interaction(user_input, response, actions_log)
                self._maybe_extract_lesson(user_input, response)
                self.skills["blackboard"].fetch_all_data()
                response = "Datos de Cibertec actualizados y guardados en la base de datos."
                actions_log = [{"action": "blackboard_fetch_all_data", "args": [], "result": "success"}]
                return response, actions_log
            except Exception as e:
                response = f"Error al actualizar Cibertec: {e}"
                self.memory.add_interaction(user_input, response, [])
                return response, []

        if ("nota" in text or "notas" in text) and not any(
            word in text for word in ["bloc", "blog", "block", "anota"]
        ):
            try:
                grades = self.skills["blackboard"].get_grades()
                if not grades:
                    print(f"[BLACKBOARD] No hay notas almacenadas. Actualizando datos...", flush=True)
                    response = "No tenía notas guardadas. Estoy actualizando los datos de Cibertec ahora mismo..."
                    self.memory.add_interaction(user_input, response, [{"action": "blackboard_fetch_all_data", "args": [], "result": "started"}])
                    self.skills["blackboard"].fetch_all_data()
                    grades = self.skills["blackboard"].get_grades()
                    if not grades:
                        response = "Se actualizaron los datos pero no encontré notas con evaluaciones (T1, T2, EF). Es posible que la página de Cibertec haya cambiado su estructura o que aún no hay evaluaciones registradas. Los horarios sí se extrajeron."
                        self.memory.add_interaction(user_input, response, [])
                        return response, []

                # ─── Resumen con LLM ───
                resumen = "\n".join(
                    f"{r['course']}: {r['name']} {r['grade']} (peso {r['weight']}%)"
                    for r in grades
                )

                prompt = f"""Eres Jarvis. Tienes estas notas de Cibertec:

{resumen}

Haz un resumen por curso indicando el rendimiento global (promedio) y un breve comentario alentador o de aviso según la nota.
Formato: curso - nota promedio - comentario.
No incluyas nada más. Respuesta final:"""

                output = self.current_llm(
                    prompt,
                    max_tokens=200,
                    temperature=0.3,
                    stop=["\n\n", "Ejemplo:"],
                )
                summary_text = output["choices"][0]["text"].strip()
                if not summary_text:
                    summary_text = "No pude generar el resumen. Aquí tienes los datos en crudo:\n" + resumen

                response = "Estas son tus notas de Cibertec:\n" + summary_text
                self.memory.add_interaction(user_input, response, [{"action": "get_grades", "args": [], "result": grades}])
                self._maybe_extract_lesson(user_input, response)
                return response, []

            except Exception as e:
                return f"Error al consultar notas de Cibertec: {e}", []
        
        if ("horario" in text or "horarios" in text or "clases" in text) and ("cibertec" in text or "blackboard" in text):
            try:
                course_name = None
                if " de " in text:
                    course_name = text.split(" de ", 1)[1].strip()
                schedules = self.skills["blackboard"].get_schedules(course_name) if course_name else self.skills["blackboard"].get_schedules()
                if not schedules:
                    print(f"[BLACKBOARD] No hay horarios almacenados. Actualizando datos...", flush=True)
                    response = "No tenía horarios guardados. Estoy actualizando los datos de Cibertec..."
                    self.memory.add_interaction(user_input, response, [{"action": "blackboard_fetch_all_data", "args": [], "result": "started"}])
                    self.skills["blackboard"].fetch_all_data()
                    schedules = self.skills["blackboard"].get_schedules(course_name) if course_name else self.skills["blackboard"].get_schedules()
                    if schedules:
                        lines_bb = [f"{r['course']} {r['day']} {r['start']}-{r['end']} en {r['classroom']}" for r in schedules]
                        response = "Datos actualizados. Estos son tus horarios:\n" + "\n".join(lines_bb[:8])
                    else:
                        response = "No pude obtener los horarios. Revisa tus credenciales."
                else:
                    lines_bb = [f"{r['course']} {r['day']} {r['start']}-{r['end']} en {r['classroom']}" for r in schedules]
                    response = "Estos son tus horarios:\n" + "\n".join(lines_bb[:8])
                self.memory.add_interaction(user_input, response, [])
                return response, []
            except Exception as e:
                return f"Error al consultar horarios: {e}", []
        
        if ("tarea" in text or "asignación" in text or "entrega" in text) and ("cibertec" in text or "blackboard" in text):
            try:
                assignments = self.skills["blackboard"].get_upcoming_assignments()
                if not assignments:
                    response = "No hay tareas próximas registradas en la base de datos."
                else:
                    lines = [f"{r['title']} (curso {r['course_id']}) vence el {r['due_date']}" for r in assignments]
                    response = "Estas son las próximas entregas en Cibertec:\n" + "\n".join(lines[:8])
                self.memory.add_interaction(user_input, response, [{"action": "get_upcoming_assignments", "args": [], "result": assignments}])
                self._maybe_extract_lesson(user_input, response)
                return response, []
            except Exception as e:
                return f"Error al consultar tareas de Cibertec: {e}", []

        if ("abre" in text or "abrir" in text or "open" in text) and ("explorador" in text or "explorer" in text):
            folder_path = os.path.expanduser("~")
            result_str = self.tools.run_command(f'xdg-open "{folder_path}"')
            response = f"Abriendo el gestor de archivos en tu carpeta personal."
            actions_log = [{"action": "run_command", "args": [folder_path], "result": result_str}]
            self.memory.add_interaction(user_input, response, actions_log)
            self._maybe_extract_lesson(user_input, response)
            return response, actions_log

        # --- Linux: abrir ventana Electron del asistente (menú/manual; sin autostart) ---
        if platform.system() == "Linux":
            gui_triggers = [
                "abre asistente",
                "abrir asistente",
                "abre el asistente",
                "abre jarvis",
                "abrir jarvis",
                "abrir interfaz",
                "abre interfaz",
                "abrir ui",
                "abre ui",
                "muestra jarvis",
                "mostrar jarvis",
                "mostrar interfaz",
                "mostrar interfaz jarvis",
                "mostrar ventana jarvis",
                "mostrar pantalla jarvis",
                "abre jarvis interfaz",
            ]
            if fuzzy_match(text, gui_triggers) and any(
                token in text for token in ["interfaz", "asistente", "jarvis", "ui"]
            ):
                desk = Path.home() / ".local/share/applications/jarvisbot.desktop"
                env = merge_linux_gui_launch_env(os.environ)
                try:
                    if desk.is_file():
                        gtk = shutil.which("gtk-launch") or shutil.which("gtk4-launch")
                        if gtk:
                            subprocess.Popen(
                                [gtk, desk.stem],
                                env=env,
                                cwd=str(Path.home()),
                                start_new_session=True,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        else:
                            subprocess.Popen(
                                ["xdg-open", str(desk)],
                                env=env,
                                start_new_session=True,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        response = "Abriendo la interfaz Jarvis desde el lanzador."
                    else:
                        response = (
                            f"No encuentro JarvisBot en ~/.local/share/applications/ "
                            "(ejecuta install_linux_integration.py install)."
                        )
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                except Exception as e:
                    err = f"No pude abrir la interfaz: {e}"
                    self.memory.add_interaction(user_input, err, [])
                    return err, []
         # --- Aprende lecciones (siempre se apaga al final) ---
        if any(phrase in text for phrase in [
            "aprende tus lecciones",
            "estudia tus lecciones",
            "repasa tus lecciones",
            "aprende lo que has aprendido"
        ]):
           #  self.voice.speak("Voy a repasar lo que he aprendido hoy. Buenas noches.")
            subprocess.Popen(
                [os.path.expanduser("~/.jarvis/retrain_models.sh")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return "Entrenando y apagando...", []
        # --- Apagar / reiniciar sistema Linux (CON CONFIRMACIÓN) ---
        if platform.system() == "Linux":
            power_off_phrases = [
                "apágate", "apagate", "apaga el equipo", "apaga la pc", "apaga el pc",
                "apaga la computadora", "apaga el computador", "apaga el sistema",
                "apaga el ordenador","apagar la computadora",
                "apara el ordenador","aparate", "apaga el servidor"
            ]
            reboot_phrases = [
                "reinicia el equipo", "reinicia la pc", "reinicia el pc",
                "reinicia la computadora", "reinicia el computador", "reinicia el sistema",
                "reinicia el ordenador", "reinicia el servidor",
                "reiniciar el equipo", "reiniciar la pc", "reiniciar el sistema",
                "reiniciar el ordenador"
            ]
            
            if any(phrase in text for phrase in power_off_phrases):
                response = "Apagando el sistema ahora."
                self.memory.add_interaction(user_input, response, [{"action": "poweroff", "args": [], "result": "initiated"}])
                try:
                    if shutil.which("systemctl"):
                        subprocess.run(["systemctl", "poweroff"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif shutil.which("shutdown"):
                        subprocess.run(["shutdown", "-h", "now"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        response = "No encontré un comando de apagado válido en el sistema."
                        self.memory.add_interaction(user_input, response, [])
                        return response, []
                except Exception as e:
                    response = f"No pude apagar el sistema: {e}. Ejecuta Jarvis como root o configura sudo sin contraseña."
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                return response, []
            
            if any(phrase in text for phrase in reboot_phrases):
                response = "Reiniciando el sistema ahora."
                self.memory.add_interaction(user_input, response, [{"action": "reboot", "args": [], "result": "initiated"}])
                try:
                    if shutil.which("systemctl"):
                        subprocess.run(["systemctl", "reboot"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif shutil.which("reboot"):
                        subprocess.run(["reboot"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        response = "No encontré un comando de reinicio válido en el sistema."
                        self.memory.add_interaction(user_input, response, [])
                        return response, []
                except Exception as e:
                    response = f"No pude reiniciar el sistema: {e}. Ejecuta Jarvis como root o configura sudo sin contraseña."
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                return response, []

        # --- Cerrar aplicaciones comunes por voz (Linux) ---
        if platform.system() == "Linux":
            close_app_keywords = ["cierra", "cerrar", "termina", "terminar", "apaga", "apagar"]
            app_names = [
                ("spotify", "Spotify"),
                ("calculadora", "calculadora"),
                ("calc", "calculadora"),
                ("terminal", "terminal"),
                ("explorador", "explorador"),
                ("firefox", "Firefox"),
                ("chrome", "Chrome"),
                ("brave", "Brave"),
            ]
            if any(term in text for term in close_app_keywords):
                for app_key, app_label in app_names:
                    if app_key in text and not any(
                        marker in text for marker in ["métricas", "metricas", "hud", "quickshell", "gpu", "panel", "rendimiento"]
                    ):
                        result_str = self.tools.close_app(app_key)
                        response = f"Cerrando {app_label}. {result_str}"
                        self.memory.add_interaction(user_input, response, [{"action": "close_app", "args": [app_key], "result": result_str}])
                        return response, []

        # --- Panel Quickshell: cerrar barra métricas (voz, Linux) ---
        if platform.system() == "Linux":
            close_metric_keywords = [
                "cierra las metricas",
                "cierra las métricas",
                "cerrar metricas",
                "cerrar métricas",
                "cierra metricas",
                "cierra métricas",
                "quita las metricas",
                "quita las métricas",
                "oculta metricas",
                "oculta métricas",
                "cerrar hud",
                "cierra hud",
                "cerrar panel de metricas",
                "cierra panel de metricas",
                "cerrar rendimiento",
                "cierra el panel",
                "quita metricas",
            ]
            if fuzzy_match(text, close_metric_keywords) or (
                ("cierra" in text or "cerrar" in text or "quita" in text or "oculta" in text)
                and (
                    ("métricas" in text or "metricas" in text)
                    or ("hud" in text and ("gpu" in text or "panel" in text or "rendimiento" in text))
                    or "quickshell" in text
                )
            ):
                try:
                    subprocess.run(
                        ["pkill", "-f", "quickshell -c gpu-jarvis"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["pkill", "-f", "gpu-jarvis-hud"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                    )
                    response = "Métricas cerradas si el proceso Quickshell estaba activo."
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                except Exception as e:
                    err = f"No pude cerrar el panel de métricas: {e}"
                    self.memory.add_interaction(user_input, err, [])
                    return err, []

        # --- Panel Quickshell (GPU / RAM / HUD): ~/.config/quickshell/gpu-jarvis + gpu-jarvis-hud ---
        if platform.system() == "Linux":
            hud_keywords = [
                "panel gpu",
                "panel de gpu",
                "hud gpu",
                "monitor gpu",
                "panel de rendimiento",
                "panel rendimiento",
                "monitor de sistema",
                "quickshell",
                "gpu jarvis",
                "panel jarvis",
                "barra de sistema",
                "panel quickshell",
                "monitor ram",
                "ver gpu",
                "muestra gpu",
                "muestra el panel",
                "activa el hud",
                "métricas",
                "metricas",
                "abre métricas",
                "abre metricas",
                "muestra métricas",
                "muestra metricas",
            ]
            wants_hud = fuzzy_match(text, hud_keywords) or (
                ("panel" in text or "hud" in text or "monitor" in text or "barra" in text)
                and (
                    "gpu" in text
                    or "ram" in text
                    or "rendimiento" in text
                    or "sistema" in text
                    or "quickshell" in text
                )
            )
            wants_process_metrics = (
                any(
                    phrase in text for phrase in [
                        "métricas de programas",
                        "metricas de programas",
                        "métricas de procesos",
                        "metricas de procesos",
                        "programas",
                        "procesos",
                        "apps",
                        "aplicaciones",
                    ]
                )
                and ("métrica" in text or "metric" in text or "uso" in text)
            )
            process_metrics_cmd = None
            if wants_process_metrics:
                specific = None
                match = re.search(r"(?:cpu|uso de cpu|memoria|ram|uso de memoria|uso de ram) (?:de|del)?\s*([\w\s]+)", text)
                if match:
                    specific = match.group(1).strip()
                elif "de " in text:
                    candidate = text.split("de ", 1)[1].strip()
                    if candidate:
                        specific = candidate
                if specific:
                    specific = re.sub(r"\b(cpu|memoria|ram|proceso|programa|aplicacion|aplicación|uso|que|qué|los|las|el|la|de)\b", "", specific).strip()
                    specific = specific.split()[0:4]
                    specific = " ".join(specific).strip()
                if specific:
                    quoted = shlex.quote(specific)
                    process_metrics_cmd = f"watch -n 2 'ps -eo pid,comm,%cpu,%mem | grep -i {quoted} | head -20'"
                else:
                    process_metrics_cmd = "watch -n 2 'ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -20'"
            if wants_hud or wants_process_metrics:
                try:
                    launcher = shutil.which("gpu-jarvis-hud")
                    if launcher:
                        subprocess.Popen(
                            [launcher],
                            start_new_session=True,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        response = "Abriendo el panel de rendimiento Quickshell."
                    else:
                        qs = shutil.which("quickshell")
                        if qs:
                            subprocess.Popen(
                                [qs, "-c", "gpu-jarvis"],
                                start_new_session=True,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            response = "Abriendo el panel Quickshell gpu-jarvis."
                        else:
                            hud_script = os.path.join(os.path.dirname(__file__), "abrir-panel-hud.sh")
                            if os.path.isfile(hud_script):
                                subprocess.Popen(
                                    ["/bin/bash", hud_script],
                                    start_new_session=True,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                                response = "Lanzando el panel con abrir-panel-hud.sh."
                            else:
                                response = (
                                    "No encontré quickshell ni gpu-jarvis-hud en el PATH. "
                                    "Instala Quickshell y ejecuta ~/.local/bin/gpu-jarvis-hud o el script abrir-panel-hud.sh en esta carpeta."
                                )
                    if process_metrics_cmd:
                        terminal_result = self.tools.open_terminal_command(process_metrics_cmd)
                        response = response + " " + terminal_result
                        self.memory.add_interaction(user_input, response, [{"action": "open_terminal_command", "args": [process_metrics_cmd], "result": terminal_result}])
                    else:
                        self.memory.add_interaction(user_input, response, [])
                    return response, []
                except Exception as e:
                    err = f"No pude abrir el panel: {e}"
                    self.memory.add_interaction(user_input, err, [])
                    return err, []

        # --- Gestión de Ventanas ---
        if fuzzy_match(text, ["minimizar", "minimiza ventana", "minimiza la ventana", "minimiza"]):
            response = "Gestión de ventanas no está soportada de forma confiable en Linux desde este asistente."
            self.memory.add_interaction(user_input, response, [])
            return response, []
            
        if fuzzy_match(text, ["maximizar", "maximiza ventana", "maximiza", "agranda"]):
            response = "Gestión de ventanas no está soportada de forma confiable en Linux desde este asistente."
            self.memory.add_interaction(user_input, response, [])
            return response, []
            
        if any(kw in text for kw in ["cierra ventana", "cerrar ventana", "cierra la ventana"]):
            response = "Cerrar ventanas por voz no está soportado directamente en Linux."
            self.memory.add_interaction(user_input, response, [])
            return response, []
            
        if any(kw in text for kw in ["cierra pestaña", "cerrar pestaña", "cierra la pestaña"]):
            response = "Cerrar pestañas por voz no está soportado directamente en Linux."
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Recordatorio: abrir notepad, escribir y guardar ---
        recordatorio_triggers = ["recordatorio", "recordar", "recuerda", "recuerd", "recordator",
                                 "recolent", "recorden", "record"]
        if any(t in text for t in recordatorio_triggers) and not self.es_tarea_con_fecha(text):
            tema = user_input.strip()
            for keyword in ["recordatorio sobre", "recordatorio de", "recordatorio",
                            "recordar sobre", "recordar de", "recordar",
                            "recuerda sobre", "recuerda de", "recuerda",
                            "crea un", "crear un", "escribe un", "escribir un",
                            "hazme un", "haz un", "sobre"]:
                if keyword in text:
                    tema = text.split(keyword, 1)[-1].strip()
                    for stop_word in [" y luego", " y guard", " luego ", " después"]:
                        if stop_word in tema.lower():
                            tema = tema.lower().split(stop_word, 1)[0].strip()
                    break
            if not tema:
                tema = "Recordatorio"
            try:
                home = os.path.expanduser("~")
                folder_path = os.path.join(home, "Downloads")
                if "documento" in text:
                    folder_path = os.path.join(home, "Documents")
                elif "escritorio" in text:
                    folder_path = os.path.join(home, "Desktop")
                os.makedirs(folder_path, exist_ok=True)

                filename = f"recordatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                full_path = os.path.join(folder_path, filename)
                texto_recordatorio = f"Recordatorio: {tema.capitalize()}\n"

                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(texto_recordatorio)

                response = f"He creado el recordatorio sobre {tema} y lo he guardado en {full_path}."
                actions_log = [{"action": "write_file", "args": [full_path, texto_recordatorio], "result": "OK"}]
                self.memory.add_interaction(user_input, response, actions_log)
                return response, actions_log
            except Exception as e:
                return f"Error al crear recordatorio: {e}", []

        # --- Guardar el archivo actual en una carpeta ---
        guardar_triggers = ["guarda", "guardar", "guárdalo", "guardalo", "guardan", "guárdal"]
        carpeta_triggers = {
            "downloads": ["descarga", "descargas", "las cargas", "carga", "download"],
            "documents": ["documento", "documentos", "document"],
            "desktop":   ["escritorio", "desktop", "escrito"],
        }

        if any(g in text for g in guardar_triggers):
            folder_key = None
            for fk, triggers in carpeta_triggers.items():
                if any(t in text for t in triggers):
                    folder_key = fk
                    break
            if not folder_key:
                folder_key = "downloads"

            lessons = self.memory.get_lessons()
            folder_lesson = lessons.get(f"folder_{folder_key}")
            folder_path = None
            if folder_lesson:
                try:
                    folder_path = json.loads(folder_lesson).get("path")
                except Exception:
                    pass

            if not folder_path:
                folder_map = {"downloads": "downloads", "documents": "documents", "desktop": "desktop"}
                folder_key_normalized = folder_map.get(folder_key, "downloads")
                folder_path = PATHS.get(folder_key_normalized, PATHS["downloads"])
                self.learn_explorer_map()

            filename = f"archivo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            full_path = os.path.join(folder_path, filename)

            try:
                os.makedirs(folder_path, exist_ok=True)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write("Archivo generado por el asistente.\n")
                response = f"Guardé un archivo de prueba en {full_path}."
                actions_log = [{"action": "write_file", "args": [full_path], "result": "OK"}]
                self.memory.add_interaction(user_input, response, actions_log)
                return response, actions_log
            except Exception as e:
                return f"Error al guardar: {e}", []

        # --- Escribir texto en la ventana activa ---
        escribe_triggers = ["escribe ", "escribir ", "escríbeme ", "escribeme ", "anota ", "anotar "]
        for t in escribe_triggers:
            if text.startswith(t):
                contenido = user_input[len(t):].strip()
                if contenido:
                    try:
                        self.tools.type_text(contenido, 0.03)
                        response = f"He escrito: {contenido}"
                        actions_log = [{"action": "type_text", "args": [contenido], "result": "OK"}]
                        self.memory.add_interaction(user_input, response, actions_log)
                        return response, actions_log
                    except Exception as e:
                        return f"Error al escribir: {e}", []

        # --- Abrir aplicaciones (Restaurado con aprendizaje) ---
        match = re.search(
            r'(?:abre|abrir|abri|abra|abrí|habre|abrè)\s+(?:el |la |los |las )?([\w\sáéíóúüñ]+)',
            text,
        )
        if match:
            app_raw = match.group(1).strip()
            for stop in [" y ", " para ", " luego ", " después ", " con ", " que "]:
                if stop in app_raw:
                    app_raw = app_raw.split(stop, 1)[0].strip()
                    break
            
            correcciones = {
                "expirador": "explorador",
                "esplorador": "explorador",
                "blog de notas": "notepad",
                "bloc de notas": "notepad",
                "calculo dora": "calculadora",
                "calcula dora": "calculadora",
            }
            app_raw = correcciones.get(app_raw, app_raw)
            
            action = ("open_app", [app_raw])
            result_str, ok, desc = self._execute_action(action)
            response = f"Abriendo {app_raw}. {result_str}"
            actions_log = [{"action": "open_app", "args": [app_raw], "result": result_str}]
            self.memory.add_interaction(user_input, response, actions_log)
            self._maybe_extract_lesson(user_input, response)
            return response, actions_log

        # --- Mover ratón a posiciones comunes (fast-path) ---
        if "ratón" in text or "mouse" in text:
            w, h = pyautogui.size()
            if "centro" in text or "al medio" in text:
                target_x, target_y = w//2, h//2
                self.tools.move_mouse(target_x, target_y, 0.5)
                res = f"Ratón movido al centro ({target_x}, {target_y})."
                self.memory.add_interaction(user_input, res, [("move_mouse", [str(target_x), str(target_y)])])
                return res, []
            if ("arriba" in text and "izquierda" in text) or ("superior izquierd" in text):
                self.tools.move_mouse(20, 20, 0.3)
                res = "Ratón en la esquina superior izquierda."
                self.memory.add_interaction(user_input, res, [("move_mouse", ["20","20"])])
                return res, []
            if ("abajo" in text and "derecha" in text) or ("inferior derech" in text):
                self.tools.move_mouse(w-20, h-20, 0.3)
                res = "Ratón en la esquina inferior derecha."
                self.memory.add_interaction(user_input, res, [("move_mouse", [str(w-20), str(h-20)])])
                return res, []

        # --- Navegación de carpetas (fast-path) ---
        if "abre la carpeta" in text or "abre carpeta" in text:
            carpeta = text.split("carpeta")[-1].strip()
            lessons = self.memory.get_lessons()
            folder_key = None
            for key in ["downloads", "documents", "desktop", "pictures", "music", "videos"]:
                if key in carpeta:
                    folder_key = key
                    break
            
            if not folder_key:
                folder_path = carpeta
            else:
                try:
                    data = json.loads(lessons.get(f"folder_{folder_key}", "{}"))
                    folder_path = data.get("path")
                except:
                    folder_path = None
                if not folder_path:
                    folder_path = os.path.join(os.path.expanduser("~"), folder_key.capitalize())
            
            subprocess.Popen(["xdg-open", folder_path])
            res = f"Abriendo carpeta {folder_path}"
            self.memory.add_interaction(user_input, res, [("open_folder", [folder_path])])
            return res, []
                    # --- Listar contenido de carpetas conocidas ---
        listar_triggers = ["lista de carpetas en", "lista las carpetas en", "carpetas en", "lista de archivos en"]
        if any(trigger in text for trigger in listar_triggers):
            # Extraer el nombre de la carpeta después del trigger
            carpeta_nombre = None
            for trigger in listar_triggers:
                if trigger in text:
                    carpeta_nombre = text.split(trigger, 1)[1].strip()
                    break
            if carpeta_nombre:
                # Mapear nombres comunes a rutas reales
                folder_map = {
                    "descargas": os.path.expanduser("~/Downloads"),
                    "downloads": os.path.expanduser("~/Downloads"),
                    "documentos": os.path.expanduser("~/Documents"),
                    "documents": os.path.expanduser("~/Documents"),
                    "escritorio": os.path.expanduser("~/Desktop"),
                    "desktop": os.path.expanduser("~/Desktop"),
                    "imágenes": os.path.expanduser("~/Pictures"),
                    "imagenes": os.path.expanduser("~/Pictures"),
                    "música": os.path.expanduser("~/Music"),
                    "musica": os.path.expanduser("~/Music"),
                    "vídeos": os.path.expanduser("~/Videos"),
                    "videos": os.path.expanduser("~/Videos"),
                }
                # Buscar coincidencia exacta o parcial
                ruta = None
                for key, path in folder_map.items():
                    if key in carpeta_nombre.lower():
                        ruta = path
                        break
                if not ruta:
                    # Si no coincide con ninguna, usar la carpeta tal cual (podría fallar)
                    ruta = carpeta_nombre

                # Ejecutar list_folder con la ruta
                try:
                    resultado = self.tools.list_folder(ruta)
                    response = f"Contenido de {ruta}:\n{resultado}"
                    self.memory.add_interaction(user_input, response, [{"action": "list_folder", "args": [ruta], "result": resultado}])
                    return response, []
                except Exception as e:
                    response = f"No pude listar la carpeta {ruta}: {e}"
                    self.memory.add_interaction(user_input, response, [])
                    return response, []

        # --- Selección de archivos (fast-path) ---
        if "selecciona el archivo" in text or "seleccionar archivo" in text:
            nombre = text.split("archivo")[-1].strip()
            self.tools.press_key("ctrl+e")
            time.sleep(0.2)
            self.tools.press_key("ctrl+a")
            self.tools.press_key("delete")
            self.tools.type_text(nombre, 0.02)
            time.sleep(0.5)
            self.tools.press_key("enter")
            res = f"Buscando y seleccionando '{nombre}'."
            self.memory.add_interaction(user_input, res, [])
            return res, []

        # --- Portapapeles (fast-path) ---
        if "copia" in text or "copiar" in text:
            self.tools.press_key("ctrl+c")
            res = "Elemento copiado al portapapeles."
            self.memory.add_interaction(user_input, res, [])
            return res, []
        if "corta" in text or "cortar" in text:
            self.tools.press_key("ctrl+x")
            res = "Elemento cortado al portapapeles."
            self.memory.add_interaction(user_input, res, [])
            return res, []
        if "pega" in text or "pegar" in text:
            self.tools.press_key("ctrl+v")
            res = "Elemento pegado."
            self.memory.add_interaction(user_input, res, [])
            return res, []

        # --- Brillo ---
        if "brillo" in text:
            if any(kw in text for kw in ["sube", "aumenta", "mas", "mas brillo"]):
                self.tools.set_brightness('10%+')
                response = "Subiendo el brillo un 10%."
                self.memory.add_interaction(user_input, response, [])
                return response, []
            elif any(kw in text for kw in ["baja", "reduce", "menos", "menos brillo"]):
                self.tools.set_brightness('10%-')
                response = "Bajando el brillo un 10%."
                self.memory.add_interaction(user_input, response, [])
                return response, []
            elif any(kw in text for kw in ["actual", "cuanto", "nivel", "como esta"]):
                response = self.tools.get_brightness()
                self.memory.add_interaction(user_input, response, [])
                return response, []

        # --- Volumen ---
        if "volumen" in text or "sonido" in text:
            if any(kw in text for kw in ["sube", "aumenta", "mas"]):
                self.tools.set_volume('10%+')
                response = "Subiendo el volumen un 10%."
                self.memory.add_interaction(user_input, response, [])
                return response, []
            elif any(kw in text for kw in ["baja", "reduce", "menos"]):
                self.tools.set_volume('10%-')
                response = "Bajando el volumen un 10%."
                self.memory.add_interaction(user_input, response, [])
                return response, []
            elif any(kw in text for kw in ["actual", "cuanto", "nivel"]):
                response = self.tools.get_volume()
                self.memory.add_interaction(user_input, response, [])
                return response, []

        # --- Estado del sistema (PRIMERO: más específico) ---
        if any(phrase in text for phrase in ["como esta el sistema", "estado del sistema", "uso de ram", "cuanta ram", "rendimiento"]):
            response = self.tools.system_status()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Salud / estado (DESPUÉS: más genérico) ---
        if any(kw in text for kw in ["como estas", "como esta", "salud", "metricas"]):
            response = self.health.get_report()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Actualizaciones pendientes ---
        if any(phrase in text for phrase in ["actualizaciones pendientes", "hay updates", "paquetes por actualizar", "actualizaciones disponibles"]):
            response = self.tools.pending_updates()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Servicios ---
        m = re.search(r'(?:estado|status) del servicio ([\w\s]+)', text)
        if m:
            service_name = m.group(1).strip()
            response = self.tools.service_status(service_name)
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Procesos top ---
        if any(phrase in text for phrase in ["procesos que mas consumen", "top memoria", "top cpu", "que esta tragando ram", "consumo de recursos"]):
            sort = 'memory' if 'memoria' in text or 'ram' in text else 'cpu'
            response = self.tools.list_processes(sort_by=sort, limit=10)
            self.memory.add_interaction(user_input, response, [])
            return response, []

    


        # --- Busqueda en historial de archivos ---
        if any(phrase in text for phrase in ["donde esta", "donde guarde", "busca archivo", "archivos de ayer", "que modifique", "archivos recientes"]):
            import json as _json, os as _os, time as _time
            hist_file = _os.path.expanduser("~/.jarvis/file_history.json")
            if not _os.path.exists(hist_file):
                response = "Aun no tengo historial de archivos. Empieza a abrir o crear archivos para que los recuerde."
            else:
                with open(hist_file, 'r') as f:
                    history = _json.load(f)
                if not history:
                    response = "No hay eventos registrados todavia."
                else:
                    recent = history[-50:]
                    summary_lines = []
                    for e in recent:
                        ts = _time.strftime('%Y-%m-%d %H:%M', _time.localtime(e['timestamp']))
                        extra = f" ({e['extra']})" if e.get('extra') else ""
                        summary_lines.append(f"- {ts}: {e['action']} {e['path']}{extra}")
                    summary = "Historial reciente de archivos:\n" + "\n".join(summary_lines)
                    self.load_powerful_model()
                    prompt = f"""Basandote en el siguiente historial de archivos, responde de forma concisa a la pregunta del usuario.\n\n{summary}\n\nPregunta: {user_input}\nRespuesta:"""
                    output = self.llm_powerful(prompt, max_tokens=150, temperature=0.1)
                    response = output["choices"][0]["text"].strip()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Matar proceso (SIN confirmación por voz) ---
        m = re.search(r'(?:mata|termina|elimina) (?:el |la |el proceso )?([\w\s]+)', text)
        if m:
            target = m.group(1).strip()
            response = self.tools.kill_process(target)
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Bloqueo de sesion ---
        if any(phrase in text for phrase in ["bloquea la sesion", "bloquear sesion", "bloquea el equipo", "bloquear equipo"]):
            response = self.tools.lock_session()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Prediccion contextual (para comandos ambiguos o sin match exacto) ---
        predicted = self.agent.predict_context_action(user_input)
        if predicted:
            if predicted in self.tools.actions:
                min_args, _ = self._expected_args_count_heuristic(predicted)
                if min_args == 0:  # Solo ejecutar acciones sin argumentos obligatorios
                    print(f"[CONTEXT] Predicción: {predicted}")
                    response = self.tools.actions[predicted]()
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                # Si requiere argumentos, se ignora la predicción y se sigue adelante
            elif hasattr(self, 'skills') and predicted in self.skills:
                print(f"[CONTEXT] Predicción (skill): {predicted}")
                response = str(self.skills[predicted])
                self.memory.add_interaction(user_input, response, [])
                return response, []

        # --- Tareas (Taskwarrior) ---
        if any(phrase in text for phrase in ["recuerdame", "anade tarea", "nueva tarea", "tengo que", "anyade tarea", "crea tarea", "agrega tarea", "recuerda que"]):
            response = self.taskwarrior.add_task(self.current_llm, user_input)
            self.memory.add_interaction(user_input, response, [])
            return response, []

        if any(phrase in text for phrase in ["lista tareas", "que tareas", "tareas pendientes", "mis tareas"]):
            response = self.taskwarrior.list_tasks()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        if any(phrase in text for phrase in ["completa tarea", "termina tarea", "marca como completada"]):
            m = re.search(r'(?:tarea|id)?\s*(\d+)', text)
            if m:
                response = self.taskwarrior.complete_task(m.group(1))
            else:
                response = "Necesito el numero de la tarea. Por ejemplo: 'completa tarea 3'."
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Planificador (recetas multi-paso) ---
        if any(phrase in text for phrase in ["organiza", "ordena", "clasifica", "limpia", "prepara"]):
            match = self.recipe_loader.find_recipe(text)
            if match:
                intent, recipe = match
                params = ParamExtractor.extract(intent, text, recipe)
                response, actions_log = self.plan_executor.execute(recipe, params)
                self.memory.add_interaction(user_input, response, actions_log)
                return response, actions_log

        if "deshaz lo ultimo" in text or "deshacer" in text:
            response = self.plan_executor.undo_last()
            self.memory.add_interaction(user_input, response, [])
            return response, []

        if "aprende nueva tarea" in text:
            response = self._learn_new_recipe(voice)
            self.memory.add_interaction(user_input, response, [])
            return response, []

        # --- Clasificador contextual (solo como fallback) ---
        if self.context_clf:
            try:
                active_window = get_active_window_kde()
                predicted = self.agent.predict_context_action(user_input)
                if predicted and predicted in self.tools.actions:
                    min_args, _ = self._expected_args_count_heuristic(predicted)
                    if min_args == 0:
                        result = self.tools.actions[predicted]()
                        self.memory.add_interaction(user_input, result, [])
                        return result, []
            except Exception as e:
                print(f"[CONTEXT] Error en clasificador: {e}")
        # --- Saludo matutino: leer briefing ---
        # IMPORTANTE: 'text' ya está normalizado (minúsculas, sin tildes)
        saludos_normalizados = ["buenos dias", "buen dia", "buenas", "como amanecio", "que tal el dia", "cómo amaneció", "qué tal el día"]
        # Imprimimos para depuración (luego puedes quitarlo)
        print(f"[BRIEFING] text recibido: '{text}'", flush=True)
        if any(s in text for s in saludos_normalizados):
            print("[BRIEFING] Saludo detectado, buscando briefing...", flush=True)
            import json as _json_lib
            from datetime import date as _date_lib
            briefing_path = os.path.join(os.path.expanduser("~"), ".jarvis", "briefing.json")
            if os.path.exists(briefing_path):
                with open(briefing_path, 'r', encoding='utf-8') as f:
                    data = _json_lib.load(f)
                if data.get("date") == str(_date_lib.today()):
                    print("[BRIEFING] Briefing de hoy encontrado.", flush=True)
                    return data["briefing"], []
                else:
                    print("[BRIEFING] Briefing no es de hoy.", flush=True)
                    return "El briefing de hoy aún no está listo. Puedes pedirme que lo genere ahora mismo.", []
            else:
                print("[BRIEFING] Archivo no existe.", flush=True)
                return "Buenos días, Marc. Aún no he preparado el briefing. Si quieres, puedo generarlo ahora mismo. ¿Te gustaría que lo haga?", []
        else:
            print("[BRIEFING] No se detectó saludo.", flush=True)
        return None

    def _learn_new_recipe(self, voice=None):
        def _ask(prompt, timeout=15):
            if voice:
                voice.speak(prompt)
                resp = voice.listen(timeout=timeout)
                if resp:
                    return resp.strip()
            return input(prompt + "\n> ").strip()

        intent = _ask("Di el nombre de la tarea, por ejemplo: organiza mi escritorio")
        if not intent:
            return "No se detecto ninguna tarea. Aprendizaje cancelado.", []

        steps = []
        paso_num = 1
        while True:
            step_desc = _ask(f"Paso {paso_num}: describe la accion a realizar. Di 'listo' si no hay mas pasos.")
            if not step_desc or 'listo' in step_desc.lower() or 'terminar' in step_desc.lower():
                break
            tool, args = self._parse_step_description(step_desc)
            if tool:
                steps.append({
                    "tool": tool,
                    "args": args,
                    "preconditions": [],
                    "inverse": "run_command" if tool == "run_command" else None
                })
                print(f"  -> Accion registrada: {tool}|{', '.join(args)}")
                paso_num += 1
            else:
                _ask("No entendi esa accion. Describe que herramienta usar. Por ejemplo: 'crea la carpeta Documentos'")

        if not steps:
            return "No se registraron pasos. Aprendizaje cancelado.", []

        pasos_str = "\n".join([f"  {i+1}. {s['tool']}|{', '.join(s['args'])}" for i, s in enumerate(steps)])
        confirm = _ask(f"La tarea '{intent}' tendra estos pasos:\n{pasos_str}\nConfirmar? Di 'si' para guardar.")
        if not confirm or not any(w in confirm.lower() for w in ["si", "sí", "yes", "ok", "claro"]):
            return "Receta no guardada. Aprendizaje cancelado.", []

        recipe = {
            "task": intent,
            "param_patterns": {},
            "steps": steps
        }
        self.recipe_loader.add_recipe(intent, recipe)
        return f"Receta '{intent}' guardada con {len(steps)} pasos.", []

    def _parse_step_description(self, text):
        text_lower = text.lower().strip()

        patterns = [
            (r'crea\s+(?:la\s+)?(?:carpeta|directorio|folder)\s+(.+)', 'create_folder', 1),
            (r'abre\s+(?:el|la|el\s+)?(.+)', 'open_app', 1),
            (r'mueve\s+(?:el\s+)?(?:mouse|raton)\s+a\s+(\d+)\s+(\d+)', 'move_mouse', 2),
            (r'(?:haz\s+)?clic\s+(?:izquierdo|left)?', 'click', 0),
            (r'(?:haz\s+)?clic\s+derecho', 'right_click', 0),
            (r'(?:escribe|typea|teclea)\s+(.+)', 'type_text', 1),
            (r'(?:presiona|pulsa)\s+(\w+(?:\+\w+)?)', 'press_key', 1),
            (r'(?:copia|copy)\s+(.+)\s+(?:a|en)\s+(.+)', 'copy_file', 2),
            (r'(?:mueve|move)\s+(.+)\s+(?:a|en)\s+(.+)', 'move_file', 2),
            (r'(?:captura|screenshot|pantallazo)', 'screenshot', 0),
            (r'(?:lista|listar?)\s+(?:el\s+)?(?:contenido\s+de\s+)?(.+)', 'list_folder', 1),
            (r'(?:ejecuta|corre|run)\s+(?:el\s+)?comando\s+(.+)', 'run_command', 1),
            (r'(?:escribe|write|guardar?)\s+(?:en\s+)?(.+)\s+(?:el\s+)?(?:contenido|texto)\s+(.+)', 'write_file', 2),
        ]

        for pattern, tool, n_args in patterns:
            match = re.search(pattern, text_lower)
            if match:
                args = list(match.groups())
                args = [a.strip().strip("'\"") for a in args if a.strip()]
                if tool in self.tools.actions:
                    return tool, args
                else:
                    print(f"Herramienta '{tool}' no disponible")
                    return None, None

        if 'comando' in text_lower or 'ejecuta' in text_lower:
            return 'run_command', [text_lower]
        if 'carpeta' in text_lower or 'directorio' in text_lower:
            return 'create_folder', [text_lower.replace('crea', '').replace('la', '').replace('carpeta', '').replace('directorio', '').strip()]
        if 'abre' in text_lower:
            return 'open_app', [text_lower.replace('abre', '').replace('el', '').replace('la', '').strip()]

        return None, None

    def _predict_context_action(self, user_input):
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

    def entrenar_apertura(self, app_name):
        print(f"Iniciando entrenamiento para abrir: {app_name}")
        aliases = list(SystemTools.APP_ALIASES.keys())
        app_norm = normalizar(app_name)
        fuzzy_names = []
        for alt in aliases:
            if levenshtein(app_norm, normalizar(alt)) <= 2:
                fuzzy_names.append(alt)
        test_names = [app_name] + fuzzy_names + [alt for alt in aliases if alt in app_name or app_name in alt] + aliases[:5]
        
        for name in test_names:
            action = ("open_app", [name])
            print(f"Probando alias: '{name}'")
            res_str, ok, desc = self._execute_action(action)
            if ok:
                signature = f"open_app|{app_name}"
                self.memory.save_conflict_fix(signature, action, True)
                return f"Éxito abriendo con el alias '{name}'."
            time.sleep(1)
        return "No se pudo encontrar un alias válido durante el entrenamiento."

    def process(self, user_input):
        self.health.record_request(fast_path_hit=False)

        # --- Sistema de triggers (horarios programados) ---
        try:
            trigger_result = self.agent.check_triggers()
            if trigger_result:
                print(f"[TRIGGER] Acción ejecutada: {trigger_result}")
        except Exception as e:
            print(f"[TRIGGER] Error checking triggers: {e}")

        t0 = time.time()
        fast = self._fast_path(user_input)
        t1 = time.time()
        print(f"[⏱️ FAST_PATH] {t1-t0:.2f}s", flush=True)
        if fast:
            self.health.record_request(fast_path_hit=True)
            return fast

        skill_triggers = {
            "weather": ["clima", "weather", "tiempo"],
            "reminders": ["recordatorio", "reminder", "recuerda"],
            "notes": ["nota", "note", "anota"],
            "system_info": ["info del sistema", "system info", "información del sistema"],
            "web_search": ["buscar en web", "web search", "busca en internet"]
        }
        for skill_name, triggers in skill_triggers.items():
            if any(trigger in user_input.lower() for trigger in triggers):
                response = self.skills[skill_name].execute(user_input)
                actions_log = []
                self.memory.add_interaction(user_input, response, actions_log)
                return response, actions_log

        t2 = time.time()
        print(f"[⏱️ SKILLS_CHECKS] {t2-t1:.2f}s", flush=True)

        if self.is_complex_task(user_input):
            self.load_powerful_model()
            self.current_llm = self.llm_powerful
            logger.debug("Usando modelo POTENTE para tarea compleja...")
        else:
            self.current_llm = self.llm_fast
            logger.debug("Usando modelo RÁPIDO para tarea simple...")

        t3 = time.time()
        print(f"[⏱️ MODEL_SELECTION] {t3-t2:.2f}s", flush=True)

        history = ""
        steps = 0
        actions_log = []
        final_answer = None

        while steps < MAX_REACT_STEPS:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lessons = self.memory.get_lessons()
            if lessons:
                practice_keys = [k for k in lessons.keys() if k.startswith("practica_")]
                compact_lessons = {k: v for k, v in lessons.items() 
                                   if not k.startswith(("practica_", "task_safe_", "practice_", "conflict_"))}
                
                lessons_list = []
                for k, v in compact_lessons.items():
                    try:
                        data = json.loads(v)
                        if "path" in data: v = data["path"]
                    except: pass
                    lessons_list.append(f"{k} es {v}")
                
                lessons_str = "\n".join(lessons_list)[:1000]
            else:
                lessons_str = "Vacía"
            
            all_lessons = self.memory.get_lessons()
            conflict_keys = sorted([k for k in all_lessons.keys() if k.startswith("conflict_")])
            recent_conflicts = []
            for ck in conflict_keys[-3:]:
                try:
                    data = json.loads(all_lessons[ck])
                    recent_conflicts.append(f"- Falló {data['action']} con {data['args']}: {data['error']}")
                except: pass
            
            conflict_str = "\n".join(recent_conflicts)
            if conflict_str:
                lessons_str += "\n\nConflictos recientes (evita repetir estos errores):\n" + conflict_str

            memory_ctx = self.memory.get_recent_context(limit=2)
            user_input = user_input[:180]

            try:
                rag_chunks = self.rag.query(user_input, n_results=3)
                if rag_chunks:
                    rag_context = "\n".join([f"- {chunk}" for chunk in rag_chunks])
                    lessons_str += "\n\nConocimiento relevante:\n" + rag_context
            except Exception as e:
                print(f"[RAG_ERROR] {e}")

            prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
                history=history,
                lessons=lessons_str,
                user_input=user_input
            )

            t4 = time.time()
            output = self.current_llm(
                prompt,
                max_tokens=150,
                stop=["Usuario:", "\n\n", "Ejemplo"],
                temperature=0.1,
                repeat_penalty=1.2
            )
            t5 = time.time()
            print(f"[⏱️ LLM_INFERENCE] {t5-t4:.2f}s (modelo: {'potente' if self.current_llm == self.llm_powerful else 'rápido'})", flush=True)
            self.health.record_llm_call(t5 - t4)
            response_text = output["choices"][0]["text"].strip()
            if not response_text.startswith("Pensamiento:"):
                response_text = "Pensamiento: " + response_text
            try:
                print(f"LLM ({t5-t4:.1f}s): {response_text}")
            except UnicodeEncodeError:
                print(f"LLM ({t5-t4:.1f}s): {response_text.encode('ascii', 'ignore').decode('ascii')}")

            if not response_text:
                response_text = (
                    "Pensamiento: No pude generar una respuesta adecuada. "
                    "Respuesta final: No entendí bien. ¿Puedes repetirlo de otra manera?"
                )

            thought, actions, final_answer = self._parse_response(response_text)

            max_parse_attempts = 3
            parse_attempt = 0
            while parse_attempt < max_parse_attempts:
                thought, actions, final_answer = self._parse_response(response_text)

                if actions:
                    break
                if final_answer:
                    break

                parse_attempt += 1
                if parse_attempt >= max_parse_attempts:
                    break

                error_msg = (
                    "Error: Tu respuesta no tiene el formato correcto. "
                    "Debes incluir 'Acción: herramienta|arg1,arg2' para ejecutar algo "
                    "o 'Respuesta final: ...' si no necesitas acción. "
                    "Corrige tu respuesta."
                )
                history += "\n" + error_msg
                prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
                    history=history,
                    lessons=lessons_str,
                    user_input=user_input
                )
                output = self.current_llm(
                    prompt,
                    max_tokens=150,
                    stop=["Usuario:", "\n\n", "Ejemplo"],
                    temperature=0.2,
                    repeat_penalty=1.2
                )
                response_text = output["choices"][0]["text"].strip()
                if not response_text.startswith("Pensamiento:"):
                    response_text = "Pensamiento: " + response_text
                self.health.record_parse_retry()
                print(f"[REINTENTO PARSEO #{parse_attempt}] {response_text[:120]}...")

            if len(actions) > 3:
                actions = actions[:3]
                print("Demasiadas acciones, se ejecutarán solo las 3 primeras.")

            if actions:
                observations = []
                all_ok = True
                for action in actions:
                    print(f"Ejecutando acción: {action}")
                    t_act0 = time.time()
                    observation, ok, conflict = self._execute_with_retries(action)
                    t_act = time.time() - t_act0
                    print(f"Acción ejecutada en {t_act:.2f}s")
                    observations.append(observation)
                    actions_log.append({"action": action[0], "args": action[1], "result": observation})
                    history += f"\nObservación: {observation}"
                    if not ok:
                        all_ok = False
                        resolution = self._try_resolve_conflict(action, conflict)
                        observations[-1] += f"\nResolución final intentada: {resolution}"
                        history += f"\nRecuperación: {resolution}"
                    self.health.record_action_result(ok)
                try:
                    action_str = action.get("tool", "unknown") if isinstance(action, dict) else str(action)
                    log_interaction(user_input, action_str, ok)
                except Exception as e:
                    print(f"[CONTEXT] Error en log_interaction: {e}")

                steps += 1
                if final_answer:
                    self.memory.add_interaction(user_input, final_answer, actions_log)
                    self._maybe_extract_lesson(user_input, final_answer)
                    return final_answer, actions_log
                else:
                    continue

            if final_answer:
                self.memory.add_interaction(user_input, final_answer, actions_log)
                self._maybe_extract_lesson(user_input, final_answer)
                return final_answer, actions_log

            if not actions and not final_answer:
                history += "\nError: No se generó respuesta válida tras varios intentos."
                steps += 1
                continue

        final_answer = "He completado las acciones solicitadas."
        self.memory.add_interaction(user_input, final_answer, actions_log)
        return final_answer, actions_log

    def _maybe_extract_lesson(self, user_input, assistant_response):
        user_lower = user_input.lower()
        if "abre" in user_lower or "abrir" in user_lower:
            apps = ["firefox", "chrome", "spotify", "calculadora", "terminal", "explorador", "bloc de notas"]
            for app in apps:
                if app in user_lower:
                    self.memory.add_lesson(
                        "preferencia_navegador" if app in ["firefox", "chrome"] else "ultima_app",
                        app
                    )
                    break

    def _fuzzy_match(self, text, keywords):
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

    def _extract_search_query(self, text):
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


# ─── EJECUCIÓN PRINCIPAL (si se llama directamente) ───
if __name__ == '__main__':
    import sys
    from config import MODEL_FAST, MODEL_POWERFUL, CTX_SIZE
    agent = ReActAgent(MODEL_FAST, MODEL_POWERFUL, CTX_SIZE)
    # Ejemplo de uso por texto
    if len(sys.argv) > 1:
        comando = ' '.join(sys.argv[1:])
        respuesta, _ = agent.process(comando)
        print(respuesta)
    else:
        print("Modo interactivo. Escribe 'salir' para terminar.")
        while True:
            try:
                user_input = input("Tú: ").strip()
                if user_input.lower() in ('salir', 'exit', 'quit'):
                    break
                respuesta, _ = agent.process(user_input)
                print(f"Jarvis: {respuesta}")
            except KeyboardInterrupt:
                break