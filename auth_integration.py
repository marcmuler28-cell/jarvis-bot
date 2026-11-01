#!/usr/bin/env python3
"""
auth_integration.py - Módulo de integración de autenticación por voz

Actúa como "pegamento" entre voice_id, user_permissions, user_session,
game_monitor y el código existente de JarvisBot.

NO modifica los archivos existentes. Solo proporciona funciones que
server.py y assistant.py pueden llamar.
"""

import os
import sys
import threading
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from user_permissions import PermissionManager
from user_session import SessionManager


def detect_action_from_input(user_input: str) -> str:
    """Detecta qué tipo de acción quiere ejecutar el usuario."""
    text = user_input.lower().strip()

    ACTION_KEYWORDS = {
        "open_app": [
            "abre", "abrir", "inicia", "lanza", "ejecuta",
            "firefox", "chrome", "spotify", "opera", "calculadora", "terminal",
            "notas", "editor"
        ],
        "close_app": ["cierra", "cerrar", "finaliza"],
        "open_terminal": ["abre terminal", "abrir terminal", "abre una terminal"],
        "open_calculator": ["calculadora"],
        "file_operations": [
            "crea carpeta", "copia archivo", "mueve archivo",
            "lista carpeta", "escribe archivo", "lee archivo",
            "crea archivo", "borra archivo"
        ],
        "create_folder": ["crea carpeta", "crea directorio"],
        "copy_file": ["copia", "copiar"],
        "move_file": ["mueve", "mover"],
        "spotify": ["spotify", "play", "pon música", "reproduce", "playlist"],
        "play_media": ["reproduce", "pon", "play"],
        "volume": ["volumen", "sube el volumen", "baja el volumen", "silencio"],
        "browser": ["navegador", "firefox", "chrome", "busca en internet"],
        "web_search": ["busca", "buscar", "google", "internet"],
        "poweroff": ["apágate", "apagar", "apaga la pc", "apaga la computadora", "shutdown"],
        "reboot": ["reinicia", "reiniciar", "reboot", "restart"],
        "lock_session": ["bloquea", "bloquear", "lock"],
        "system_status": ["cómo está el sistema", "estado del sistema", "cpu", "ram", "disco"],
        "kill_process": ["mata", "matar", "termina proceso", "kill"],
        "pending_updates": ["actualizaciones", "updates", "pacman"],
        "play_game": ["juego", "jugar", "steam", "minecraft", "gaming"],
        "notes": ["nota", "anota", "registrar nota"],
        "reminders": ["recuérdame", "recordatorio", "recuerda"],
        "tasks": ["tarea", "taskwarrior", "añade tarea"],
        "calendar": ["calendario", "cita", "evento"],
        "weather": ["clima", "tiempo", "weather", "lluvia", "sol"],
        "time": ["hora", "qué hora"],
        "date": ["fecha", "día es", "qué día"],
        "ask_llm": [],
        "blackboard": ["blackboard", "cibertec", "notas", "horarios"],
        "grades": ["notas de", "promedio de"],
        "schedule": ["horarios", "horario"],
        "mouse_control": ["mueve mouse", "clic", "doble clic", "arrastra"],
        "keyboard_control": ["escribe", "presiona", "tecla"],
        "screenshot": ["captura", "screenshot"],
    }

    for action, keywords in ACTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return action
    return "ask_llm"


_pm_instance = None

def get_permission_manager() -> PermissionManager:
    global _pm_instance
    if _pm_instance is None:
        _pm_instance = PermissionManager()
    return _pm_instance


def check_action_permission(user_id: Optional[str], action: str) -> Tuple[bool, str]:
    """Verifica si un usuario puede ejecutar una acción."""
    pm = get_permission_manager()

    if not user_id:
        if pm.unknown_can_chat():
            if action == "ask_llm":
                return True, ""
            return False, "No te reconozco. Debes identificarte primero para ejecutar comandos."
        else:
            return False, "Usuario no autenticado."

    if user_id == "guest":
        return False, "Los invitados no pueden ejecutar comandos."

    if pm.can_execute(user_id, action):
        return True, ""
    else:
        display = pm.get_display_name(user_id)
        return False, f"Lo siento {display}, no tienes permiso para ejecutar '{action}'."


class AuthIntegration:
    """Integra voice_id, session, permissions y game_monitor."""

    def __init__(self):
        self.pm = get_permission_manager()
        self.session = SessionManager(timeout_minutes=self.pm.get_session_timeout())
        self.voice_id = None
        self.game_monitor = None
        self._initialized = False
        self._lock = threading.Lock()

    def initialize(self, enable_voice_id: bool = False, enable_game_monitor: bool = True):
        if self._initialized:
            return
        print("[AUTH] Inicializando sistema de autenticación...")

        if enable_voice_id:
            try:
                from voice_id import VoiceIdentifier
                self.voice_id = VoiceIdentifier(
                    min_confidence=self.pm.get_min_confidence()
                )
                self.voice_id.load_profiles()
                if not self.voice_id.has_profiles():
                    print("[AUTH] ⚠️  No hay perfiles de voz cargados.")
                    print("[AUTH]    Registra usuarios con: python enroll_user.py --user marc")
                else:
                    users = self.voice_id.list_profiles()
                    print(f"[AUTH] ✅ Voice ID listo ({len(users)} perfiles: {', '.join(users)})")
            except Exception as e:
                print(f"[AUTH] ❌ Error cargando voice_id: {e}")
                self.voice_id = None

        if enable_game_monitor:
            try:
                from game_monitor import GameMonitor
                self.game_monitor = GameMonitor()
                print("[AUTH] ✅ Game monitor listo")
            except Exception as e:
                print(f"[AUTH] ❌ Error cargando game_monitor: {e}")
                self.game_monitor = None

        self._initialized = True
        print("[AUTH] 🎉 Sistema de autenticación inicializado")


    def login_with_pin(self, pin: str) -> Tuple[bool, str]:
        """Inicia sesión usando un PIN."""
        user_id = self.pm.validate_pin(pin)
        if user_id:
            self.session.set_current_user(user_id, confidence=1.0)
            display = self.pm.get_display_name(user_id)
            return True, f"Sesión iniciada como {display}"
        return False, "PIN incorrecto"

    def identify_user(self, wav_path: str) -> Optional[str]:
        if not self.voice_id or not self.voice_id.has_profiles():
            return None
        try:
            user_id, confidence = self.voice_id.identify_speaker(wav_path)
            if user_id:
                self.session.set_current_user(user_id, confidence)
                return user_id
            return None
        except Exception as e:
            print(f"[AUTH] Error identificando usuario: {e}")
            return None

    def get_current_user(self) -> Optional[str]:
        return self.session.get_current_user()

    def clear_session(self):
        self.session.clear_session()

    def check_permission(self, user_id: Optional[str], action: str) -> Tuple[bool, str]:
        return check_action_permission(user_id, action)

    def get_user_display(self, user_id: Optional[str]) -> str:
        if not user_id:
            return "Desconocido"
        return self.pm.get_display_name(user_id)

    def start_game_session(self, user_id: str):
        if self.game_monitor:
            self.game_monitor.start_session(user_id)

    def stop_game_session(self, user_id: str):
        if self.game_monitor:
            self.game_monitor.stop_session(user_id)

    def check_game_limits(self, broadcast_callback=None):
        if self.game_monitor:
            return self.game_monitor.check_limits(broadcast_callback)
        return []

    def start_auto_monitor(self, interval_seconds: int = 60, broadcast_callback=None):
        if self.game_monitor:
            self.game_monitor.start_auto_monitor(interval_seconds, broadcast_callback)

    def get_game_stats(self, user_id: str) -> Optional[dict]:
        if self.game_monitor:
            return self.game_monitor.get_user_stats(user_id)
        return None

    def get_session_info(self) -> Optional[dict]:
        return self.session.get_session_info()


_auth_instance = None

def get_auth() -> AuthIntegration:
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = AuthIntegration()
    return _auth_instance


if __name__ == '__main__':
    print("=== Test detect_action_from_input ===")
    tests = [
        "abre firefox",
        "apaga la computadora",
        "reinicia el equipo",
        "pon música en spotify",
        "sube el volumen",
        "crea carpeta /tmp/test",
        "qué hora es",
        "cuál es el clima",
        "mata proceso firefox",
        "bloquea la sesión",
        "hola jarvis cómo estás",
    ]
    for t in tests:
        action = detect_action_from_input(t)
        print(f"  '{t}' → {action}")

    print("\n=== Test check_action_permission ===")
    for user_id in ["marc", "jefferson", "guest", None]:
        print(f"\nUsuario: {user_id or 'None'}")
        for action in ["poweroff", "open_app", "play_game", "ask_llm", "kill_process"]:
            allowed, msg = check_action_permission(user_id, action)
            emoji = "✅" if allowed else "❌"
            print(f"  {emoji} {action}: {'OK' if allowed else msg}")
