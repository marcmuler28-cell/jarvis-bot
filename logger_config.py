"""
Configuración centralizada de logging para JarvisBot.
Los logs se guardan en ~/.cache/jarvisbot/jarvisbot.log
"""

import logging
import sys
from pathlib import Path

# Crear directorio de logs si no existe
LOG_DIR = Path.home() / ".cache" / "jarvisbot"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "jarvisbot.log"

def setup_logger(name="JarvisBot", level=logging.INFO):
    """
    Configura logging para JarvisBot con console y archivo.
    
    Args:
        name: Nombre del logger
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    
    # Evitar duplicar handlers si se llama múltiples veces
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Formato con timestamp, nombre del logger, nivel y mensaje
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # ==== Handler para Consola ====
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # ==== Handler para Archivo ====
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        # Archivo siempre en DEBUG para tener más información
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"⚠️ No se pudo abrir archivo de log: {e}")
        # Continuar sin archivo de log si hay error
    
    return logger

# Crear logger global que se usa en todo el programa
logger = setup_logger()
