import os
import sys

# Configuración inicial del terminal
if sys.platform == "win32":
    os.system('chcp 65001 > nul')  # Configura terminal a UTF-8
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

# ---------- CONFIGURACIÓN ----------
TEXT_MODE = False  # MODO TEMPORAL: Cambia a False para volver a usar voz
MODEL_FAST = "models/qwen2.5-3b-instruct-q4_k_m.gguf"   # Rápido y ligero (~2.5 GB)
MODEL_POWERFUL = "models/Qwen2.5-7B-Instruct-1M-Q4_K_M.gguf"  # Potente y con 1M de contexto (~4.7 GB)
WHISPER_SIZE = "small"
CTX_SIZE = 4096  # Aumentamos contexto para el modelo grande (1M tokens requiere mucho, con 8192 basta)
MAX_REACT_STEPS = 5
SILENCE_THRESHOLD = 0.041
SILENCE_DURATION = 1.5
# Corte de seguridad para no esperar el timeout completo tras empezar a hablar
MAX_RECORDING_AFTER_SPEECH = 7.0
# Si no detecta voz al inicio, corta pronto para reintentar
MAX_WAIT_FOR_SPEECH = 5.0
# Índices de audio (pon enteros según `voice.list_audio_devices()`; usa None para automático)
AUDIO_INPUT_DEVICE = 12
AUDIO_OUTPUT_DEVICE = None

# ========== CONFIGURACIÓN DE RUTAS CENTRALIZADAS ==========
# Esto evita repetir os.path.expanduser("~") en 20+ lugares

from pathlib import Path

# Directorio home
HOME = os.path.expanduser("~")
HOME_PATH = Path(HOME)

# Diccionario centralizado de rutas del usuario
PATHS = {
    "home": HOME,
    "downloads": os.path.join(HOME, "Downloads"),
    "documents": os.path.join(HOME, "Documents"),
    "desktop": os.path.join(HOME, "Desktop"),
    "pictures": os.path.join(HOME, "Pictures"),
    "music": os.path.join(HOME, "Music"),
    "videos": os.path.join(HOME, "Videos"),
    "applications": os.path.join(HOME, ".local/share/applications"),
    "autostart": os.path.join(HOME, ".config/autostart"),
    "systemd_user": os.path.join(HOME, ".config/systemd/user"),
    "cache": os.path.join(HOME, ".cache"),
    "config": os.path.join(HOME, ".config"),
}

# Crear directorios si no existen
for dir_name, dir_path in PATHS.items():
    # Evitar crear rutas del sistema
    if not dir_path.startswith(("/proc", "/sys", "/dev")):
        try:
            os.makedirs(dir_path, exist_ok=True)
        except:
            pass  # Silenciar errores de creación de directorios

# ========== CONFIGURACIÓN DE COMANDOS CENTRALIZADOS ==========

# Aplicaciones estándar del sistema
APPS = {
    "firefox": "firefox",
    "chrome": "google-chrome",
    "spotify": "spotify",
    "calculator": "gnome-calculator",
    "file_manager": "xdg-open",
    "terminal": "gnome-terminal",
    "text_editor": "gedit",
}

# Comandos de potencia (Linux)
POWER_COMMANDS = {
    "poweroff": ["systemctl", "poweroff"],
    "reboot": ["systemctl", "reboot"],
}

# ========== PLUGIN CONFIGURATION ==========

# Habilitar/deshabilitar plugins opcionales
# SelfImprover SIEMPRE debe ser False en producción
SELF_IMPROVER_ENABLED = os.getenv("JARVIS_SELF_IMPROVER", "false").lower() == "true"

# ========== LOGGING CONFIGURATION ==========
# Nivel de logging (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL = os.getenv("JARVIS_LOG_LEVEL", "INFO")
WHISPER_LANGUAGE = "es"
