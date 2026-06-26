#!/usr/bin/env python3
"""user_permissions.py - Sistema de permisos por usuario para JarvisBot"""
import os
import yaml
from typing import Optional, List
from pathlib import Path


class PermissionManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            project_root = Path(__file__).resolve().parent
            config_path = project_root / "config_users.yaml"
        self.config_path = str(config_path)
        self.config = self._load_config()
        self.users = self.config.get('users', {})
        self.general = self.config.get('general', {})

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"[PERMISSIONS] ⚠️  No se encontró {self.config_path}")
            return {'users': {}, 'general': {}}
        except yaml.YAMLError as e:
            print(f"[PERMISSIONS] ❌ Error parseando YAML: {e}")
            return {'users': {}, 'general': {}}

    def reload(self):
        self.config = self._load_config()
        self.users = self.config.get('users', {})
        self.general = self.config.get('general', {})

    def user_exists(self, user_id: str) -> bool:
        return user_id in self.users

    def get_user(self, user_id: str) -> Optional[dict]:
        return self.users.get(user_id)

    def get_display_name(self, user_id: str) -> str:
        user = self.users.get(user_id)
        if user:
            return user.get('display_name', user.get('name', user_id))
        return user_id

    def get_role(self, user_id: str) -> str:
        user = self.users.get(user_id)
        return user.get('role', 'guest') if user else 'guest'

    def can_execute(self, user_id: str, action: str) -> bool:
        if not self.user_exists(user_id):
            return False
        user = self.users[user_id]
        permissions = user.get('permissions', [])
        denied = user.get('denied_actions', [])
        if '*' in denied:
            return False
        if action in denied:
            return False
        if '*' in permissions:
            return True
        if action in permissions:
            return True
        return False

    def list_allowed_actions(self, user_id: str) -> List[str]:
        if not self.user_exists(user_id):
            return []
        user = self.users[user_id]
        permissions = user.get('permissions', [])
        denied = user.get('denied_actions', [])
        if '*' in permissions:
            return ['* (todo excepto: ' + ', '.join(denied) + ')']
        if '*' in denied:
            return []
        return [p for p in permissions if p not in denied]

    def get_game_time_limit(self, user_id: str) -> Optional[int]:
        user = self.users.get(user_id)
        if not user:
            return 0
        return user.get('game_time_limit_minutes')

    def get_game_overload_protection(self, user_id: str) -> dict:
        user = self.users.get(user_id)
        if not user:
            return {}
        return user.get('game_overload_protection', {})


    def validate_pin(self, pin: str) -> Optional[str]:
        """Valida el PIN y retorna el user_id si es correcto."""
        for user_id, user_data in self.users.items():
            if user_data.get('pin') == pin:
                return user_id
        return None

    def get_enrollment_phrases(self) -> List[str]:
        return self.general.get('enrollment_phrases', [
            "Hola Jarvis, soy yo, mi voz es mi identificación"
        ])

    def get_min_confidence(self) -> float:
        return self.general.get('min_confidence', 0.75)

    def get_session_timeout(self) -> int:
        return self.general.get('session_timeout_minutes', 30)

    def unknown_can_chat(self) -> bool:
        return self.general.get('unknown_user_can_chat', True)

    def get_all_users(self) -> List[str]:
        return list(self.users.keys())

    def describe_user(self, user_id: str) -> str:
        if not self.user_exists(user_id):
            return f"Usuario '{user_id}' no registrado"
        user = self.users[user_id]
        name = user.get('display_name', user.get('name', user_id))
        role = user.get('role', 'unknown')
        perms = user.get('permissions', [])
        denied = user.get('denied_actions', [])
        game_limit = user.get('game_time_limit_minutes')
        lines = [
            f"👤 {name} (rol: {role})",
            f"   ✅ Permisos: {', '.join(perms) if perms else 'ninguno'}",
            f"   ❌ Denegado: {', '.join(denied) if denied else 'nada'}",
        ]
        if game_limit is not None:
            lines.append(f"   🎮 Límite de juego: {game_limit} min/día")
        else:
            lines.append(f"   🎮 Límite de juego: sin límite")
        return '\n'.join(lines)


KNOWN_ACTIONS = [
    "open_app", "close_app", "open_terminal", "open_calculator",
    "file_operations", "create_folder", "copy_file", "move_file",
    "spotify", "play_media", "volume",
    "browser", "web_search",
    "poweroff", "reboot", "lock_session", "system_status", "kill_process",
    "pending_updates", "play_game",
    "notes", "reminders", "tasks", "calendar",
    "weather", "time", "date",
    "blackboard", "grades", "schedule",
    "mouse_control", "keyboard_control", "screenshot",
    "ask_llm",
]


if __name__ == '__main__':
    pm = PermissionManager()
    print("=== Usuarios registrados ===")
    for uid in pm.get_all_users():
        print(pm.describe_user(uid))
        print()
    print("=== Tests de permisos ===")
    tests = [
        ("marc", "poweroff"),
        ("jefferson", "poweroff"),
        ("jefferson", "open_app"),
        ("jefferson", "play_game"),
        ("guest", "open_app"),
        ("unknown", "open_app"),
    ]
    for user, action in tests:
        can = pm.can_execute(user, action)
        emoji = "✅" if can else "❌"
        print(f"  {emoji} {user} → {action}: {'PERMITIDO' if can else 'DENEGADO'}")
