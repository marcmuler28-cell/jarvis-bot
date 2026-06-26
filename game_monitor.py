#!/usr/bin/env python3
"""
game_monitor.py - Monitor de tiempo de juego para control parental

Rastrea cuánto tiempo pasa cada usuario jugando y toma acciones cuando
excede su límite:
1. Aviso cuando quedan 30 minutos
2. Cerrar juegos suavemente (SIGTERM) al exceder el límite
3. Esperar 30 segundos
4. Apagar la PC (shutdown suave)

Uso:
    from game_monitor import GameMonitor
    gm = GameMonitor()
    gm.start_session("jefferson")
    gm.check_limits(broadcast_callback)
"""

import os
import sys
import time
import json
import subprocess
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from user_permissions import PermissionManager


JARVIS_DIR = os.path.expanduser("~/.jarvis")
USAGE_FILE = os.path.join(JARVIS_DIR, "game_usage.json")

GAME_PROCESSES = [
    "steam", "csgo", "dota2", "hl2", "tf2",
    "epicgameslauncher", "origin", "upc",
    "wine", "lutris", "heroic",
    "minecraft", "0ad", "xonotic", "supertuxkart",
]

GAME_WINDOW_KEYWORDS = [
    "steam", "minecraft", "league of legends", "fortnite",
    "valorant", "csgo", "counter-strike", "dota",
    "genshin impact", "epic games", "origin", "battle.net",
    "riot client", "riot games",
]


class GameMonitor:
    """Monitor de tiempo de juego con control parental."""

    def __init__(self, config_path: str = None):
        self.pm = PermissionManager(config_path)
        os.makedirs(JARVIS_DIR, exist_ok=True)
        self.usage_data = self._load_usage()
        self._active_sessions: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._shutdown_in_progress = False
        self._monitor_thread = None
        self._stop_monitor = threading.Event()

    def _load_usage(self) -> dict:
        if not os.path.exists(USAGE_FILE):
            return {'users': {}, 'last_updated': None}
        try:
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[GAME_MONITOR] Error cargando uso: {e}")
            return {'users': {}, 'last_updated': None}

    def _save_usage(self):
        self.usage_data['last_updated'] = datetime.now().isoformat()
        try:
            with open(USAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[GAME_MONITOR] Error guardando uso: {e}")

    def start_session(self, user_id: str):
        with self._lock:
            if user_id in self._active_sessions:
                print(f"[GAME_MONITOR] {user_id} ya tiene sesión activa")
                return
            self._active_sessions[user_id] = time.time()
            print(f"[GAME_MONITOR] ▶️  {user_id} empezó a jugar")

    def stop_session(self, user_id: str):
        with self._lock:
            if user_id not in self._active_sessions:
                return
            start = self._active_sessions.pop(user_id)
            elapsed = time.time() - start
            today = date.today().isoformat()
            if user_id not in self.usage_data['users']:
                self.usage_data['users'][user_id] = {}
            if today not in self.usage_data['users'][user_id]:
                self.usage_data['users'][user_id][today] = 0
            self.usage_data['users'][user_id][today] += elapsed
            self._save_usage()
            minutes = elapsed / 60
            print(f"[GAME_MONITOR] ⏹️  {user_id} dejó de jugar ({minutes:.1f} min esta sesión)")

    def get_today_usage(self, user_id: str) -> float:
        today = date.today().isoformat()
        user_data = self.usage_data['users'].get(user_id, {})
        seconds_today = user_data.get(today, 0)
        with self._lock:
            if user_id in self._active_sessions:
                seconds_today += time.time() - self._active_sessions[user_id]
        return seconds_today / 60

    def get_remaining_time(self, user_id: str) -> Optional[float]:
        limit = self.pm.get_game_time_limit(user_id)
        if limit is None:
            return None
        used = self.get_today_usage(user_id)
        remaining = limit - used
        return max(0, remaining)

    def check_limits(self, broadcast_callback=None) -> List[dict]:
        actions = []
        if self._shutdown_in_progress:
            return actions
        for user_id in list(self._active_sessions.keys()):
            limit = self.pm.get_game_time_limit(user_id)
            if limit is None:
                continue
            remaining = self.get_remaining_time(user_id)
            if remaining is None:
                continue
            warn_at = self.pm.get_game_overload_protection(user_id).get(
                'warn_at_remaining_minutes', 30
            )
            warned_key = f"{user_id}_warned_{date.today().isoformat()}"
            if remaining <= warn_at and remaining > 0:
                if not self.usage_data.get(warned_key):
                    msg = (f"⚠️ {user_id.title()}, te quedan {int(remaining)} minutos de juego. "
                           f"Guarda tu progreso.")
                    print(f"[GAME_MONITOR] {msg}")
                    if broadcast_callback:
                        broadcast_callback('assistant', msg)
                    self.usage_data[warned_key] = True
                    self._save_usage()
                    actions.append({'user': user_id, 'action': 'warn', 'message': msg})
            elif remaining <= 0:
                exceeded_key = f"{user_id}_exceeded_{date.today().isoformat()}"
                if not self.usage_data.get(exceeded_key):
                    msg = (f"🛑 {user_id.title()}, has excedido tu límite de juego diario "
                           f"({limit} minutos). Cerrando juegos...")
                    print(f"[GAME_MONITOR] {msg}")
                    if broadcast_callback:
                        broadcast_callback('assistant', msg)
                    self.usage_data[exceeded_key] = True
                    self._save_usage()
                    threading.Thread(
                        target=self._enforce_game_shutdown,
                        args=(user_id, broadcast_callback),
                        daemon=True
                    ).start()
                    actions.append({'user': user_id, 'action': 'shutdown_games', 'message': msg})
        return actions

    def _enforce_game_shutdown(self, user_id: str, broadcast_callback=None):
        if self._shutdown_in_progress:
            return
        self._shutdown_in_progress = True
        try:
            config = self.pm.get_game_overload_protection(user_id)
            wait_seconds = config.get('wait_before_shutdown_seconds', 30)
            do_shutdown = config.get('shutdown_after_close', True)
            close_gracefully = config.get('close_games_gracefully', True)
            if close_gracefully:
                msg = "Cerrando procesos de juego..."
                print(f"[GAME_MONITOR] {msg}")
                if broadcast_callback:
                    broadcast_callback('assistant', msg)
                self._close_game_processes()
            msg = f"Esperando {wait_seconds} segundos antes de apagar..."
            print(f"[GAME_MONITOR] {msg}")
            if broadcast_callback:
                broadcast_callback('assistant', msg)
            for i in range(wait_seconds, 0, -1):
                if broadcast_callback and i % 10 == 0:
                    broadcast_callback('assistant', f"Apagando en {i} segundos...")
                time.sleep(1)
            self.stop_session(user_id)
            if do_shutdown:
                msg = "Apagando el equipo. Hasta pronto."
                print(f"[GAME_MONITOR] {msg}")
                if broadcast_callback:
                    broadcast_callback('assistant', msg)
                self._shutdown_system()
        except Exception as e:
            print(f"[GAME_MONITOR] ❌ Error en enforce_game_shutdown: {e}")
        finally:
            self._shutdown_in_progress = False

    def _close_game_processes(self):
        for proc_name in GAME_PROCESSES:
            try:
                result = subprocess.run(
                    ['pkill', '-TERM', '-f', proc_name],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    print(f"[GAME_MONITOR] Proceso cerrado: {proc_name}")
            except Exception as e:
                print(f"[GAME_MONITOR] Error cerrando {proc_name}: {e}")

    def _shutdown_system(self):
        try:
            subprocess.run(['systemctl', 'poweroff'], check=False, timeout=10)
        except Exception as e:
            print(f"[GAME_MONITOR] Error apagando: {e}")
            try:
                subprocess.run(['shutdown', '-h', 'now'], check=False, timeout=5)
            except:
                pass

    def detect_running_games(self) -> List[str]:
        running = []
        try:
            result = subprocess.run(
                ['ps', 'aux'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                line_lower = line.lower()
                for game_proc in GAME_PROCESSES:
                    if game_proc in line_lower:
                        parts = line.split()
                        if len(parts) > 10:
                            proc_name = parts[10].split('/')[-1]
                            if proc_name and proc_name not in running:
                                running.append(proc_name)
        except Exception as e:
            print(f"[GAME_MONITOR] Error detectando juegos: {e}")
        return running

    def start_auto_monitor(self, interval_seconds: int = 60, broadcast_callback=None):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        def _monitor_loop():
            while not self._stop_monitor.is_set():
                try:
                    running_games = self.detect_running_games()
                    for user_id in list(self._active_sessions.keys()):
                        is_playing = len(running_games) > 0
                        if not is_playing:
                            self.stop_session(user_id)
                    self.check_limits(broadcast_callback)
                except Exception as e:
                    print(f"[GAME_MONITOR] Error en loop: {e}")
                self._stop_monitor.wait(interval_seconds)

        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        print(f"[GAME_MONITOR] 🔍 Auto-monitor iniciado (cada {interval_seconds}s)")

    def stop_auto_monitor(self):
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
        print("[GAME_MONITOR] 🔍 Auto-monitor detenido")

    def get_user_stats(self, user_id: str) -> dict:
        limit = self.pm.get_game_time_limit(user_id)
        used_today = self.get_today_usage(user_id)
        remaining = self.get_remaining_time(user_id)
        return {
            'user_id': user_id,
            'limit_minutes': limit,
            'used_today_minutes': round(used_today, 1),
            'remaining_minutes': round(remaining, 1) if remaining is not None else None,
            'is_currently_playing': user_id in self._active_sessions,
            'has_exceeded_limit': remaining is not None and remaining <= 0,
        }

    def get_weekly_report(self, user_id: str) -> dict:
        from datetime import timedelta
        report = {}
        today = date.today()
        for i in range(7):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            seconds = self.usage_data.get('users', {}).get(user_id, {}).get(day_str, 0)
            report[day_str] = round(seconds / 60, 1)
        return report


if __name__ == '__main__':
    gm = GameMonitor()
    print("=== GameMonitor ===")
    print(f"Juegos detectados corriendo: {gm.detect_running_games()}")
    print()
    print("=== Estados de usuarios ===")
    for user_id in ['marc', 'jefferson']:
        stats = gm.get_user_stats(user_id)
        print(f"\n{user_id}:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        weekly = gm.get_weekly_report(user_id)
        print(f"  Uso semanal (minutos): {weekly}")
