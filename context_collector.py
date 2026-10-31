"""Colector de contexto de escritorio (habitos) - Hyprland/Wayland."""
import csv, json, os, subprocess
from datetime import datetime

CONTEXT_LOG = os.path.expanduser("~/.jarvis/logs/context_habits.csv")


def get_active_window_hyprland():
    """Titulo de la ventana activa via hyprctl (Wayland)."""
    try:
        r = subprocess.run(['hyprctl', '-j', 'activewindow'],
                           capture_output=True, text=True, timeout=3)
        s = r.stdout.strip()
        if r.returncode != 0 or not s or s == 'Invalid':
            return 'unknown'
        return json.loads(s).get('title', '') or 'unknown'
    except Exception as e:
        print(f"[CONTEXT] Error ventana activa: {e}")
        return 'unknown'


get_active_window_kde = get_active_window_hyprland  # alias compatibilidad


def log_interaction(user_input, action_taken, success):
    """Guarda una linea en el CSV de habitos."""
    os.makedirs(os.path.dirname(CONTEXT_LOG), exist_ok=True)
    now = datetime.now()
    fields = [now.strftime('%Y-%m-%d %H:%M:%S'), now.hour,
              now.strftime('%A'), get_active_window_hyprland(),
              user_input.replace(',', ';'), action_taken.replace(',', ';'),
              '1' if success else '0']
    with open(CONTEXT_LOG, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(fields)
