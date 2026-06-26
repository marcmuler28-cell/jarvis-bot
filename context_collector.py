"""Colector de contexto de escritorio para entrenar modelos de hábitos."""

import csv
import os
import time
import shutil
import subprocess
from datetime import datetime

CONTEXT_LOG = os.path.expanduser("~/.jarvis/logs/context_habits.csv")


def get_active_window_kde():
    """
    Devuelve el título de la ventana activa.
    Usa kdotool (más fiable en KDE) o xdotool como fallback.
    """
    try:
        if shutil.which('kdotool'):
            res = subprocess.run(
                ['kdotool', 'getactivewindow', 'getwindowname'],
                capture_output=True, text=True
            )
            return res.stdout.strip() or 'unknown'
        elif shutil.which('xdotool'):
            res = subprocess.run(
                ['xdotool', 'getactivewindow', 'getwindowname'],
                capture_output=True, text=True
            )
            return res.stdout.strip() or 'unknown'
        else:
            return 'unknown'
    except Exception as e:
        print(f"[CONTEXT] Error obteniendo ventana activa: {e}")
        return 'unknown'


def log_interaction(user_input, action_taken, success):
    """Guarda una línea en el CSV de hábitos."""
    os.makedirs(os.path.dirname(CONTEXT_LOG), exist_ok=True)
    now = datetime.now()
    fields = [
        now.strftime('%Y-%m-%d %H:%M:%S'),
        now.hour,
        now.strftime('%A'),
        get_active_window_kde(),
        user_input.replace(',', ';'),
        action_taken.replace(',', ';'),
        '1' if success else '0'
    ]
    with open(CONTEXT_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(fields)