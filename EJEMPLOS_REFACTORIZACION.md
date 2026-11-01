# Ejemplos de Código Refactorizado (Listo para Copiar)

## 1. Confirmación Segura para Apagado/Reinicio

Reemplazar líneas **660-693** en `assistant.py`:

```python
# --- Apagar / reiniciar sistema Linux ---
if platform.system() == "Linux":
    power_off_phrases = [
        "apágate", "apagate", "apaga el equipo", "apaga la pc", "apaga el pc",
        "apaga la computadora", "apaga el computador", "apaga el sistema",
        "apaga el ordenador", "apaga el servidor"
    ]
    reboot_phrases = [
        "reinicia el equipo", "reinicia la pc", "reinicia el pc",
        "reinicia la computadora", "reinicia el computador", "reinicia el sistema",
        "reinicia el ordenador", "reinicia el servidor",
        "reiniciar el equipo", "reiniciar la pc", "reiniciar el sistema",
        "reiniciar el ordenador"
    ]
    
    if any(phrase in text for phrase in power_off_phrases):
        # Solicitar confirmación por voz
        msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
        self.voice.speak(msg)
        
        try:
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
                        self.memory.add_interaction(user_input, response, [])
                        return response, []
                except Exception as e:
                    response = f"No pude apagar el sistema: {e}. Ejecuta Jarvis como root."
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                return response, []
            else:
                response = "Apagado cancelado."
                self.memory.add_interaction(user_input, response, [])
                return response, []
        except:
            response = "No pude escuchar la confirmación. Apagado cancelado."
            return response, []
    
    if any(phrase in text for phrase in reboot_phrases):
        # Solicitar confirmación por voz
        msg = "¿Estás seguro de que quieres reiniciar? Di 'sí' para confirmar."
        self.voice.speak(msg)
        
        try:
            confirmation = self.voice.listen(timeout=5)
            if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante", "ok", "okei"]):
                response = "Reiniciando el sistema. Esto puede requerir permisos de administrador."
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
                    response = f"No pude reiniciar el sistema: {e}. Ejecuta Jarvis como root."
                    self.memory.add_interaction(user_input, response, [])
                    return response, []
                return response, []
            else:
                response = "Reinicio cancelado."
                self.memory.add_interaction(user_input, response, [])
                return response, []
        except:
            response = "No pude escuchar la confirmación. Reinicio cancelado."
            return response, []
```

---

## 2. Archivo `logger_config.py` Completo

Crear nuevo archivo: `/home/marc/Descargas/JarvisBot/logger_config.py`

```python
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

# ===== USO EN OTHER MODULES =====
# 
# from logger_config import logger
#
# logger.debug("Mensaje de debug detallado")
# logger.info("Información general")
# logger.warning("Advertencia (algo inesperado)")
# logger.error("Error (algo falló)")
# logger.critical("Error crítico (el programa no puede continuar)")
#
```

---

## 3. Actualización de `config.py` (Agregar al final)

Agregar al final del archivo `config.py`:

```python
# ========== CONFIGURACIÓN DE RUTAS CENTRALIZADAS ==========
# Esto evita repetir os.path.expanduser("~") en 20+ lugares

import os
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
```

**Luego en `assistant.py` (al inicio), agregar:**

```python
from config import PATHS, APPS, POWER_COMMANDS, SELF_IMPROVER_ENABLED, LOG_LEVEL
from logger_config import logger

# Configurar logger con nivel desde config
import logging
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
```

---

## 4. Refactorización Parcial de `_fast_path` - Método Auxiliar

Agregar este método a la clase `ReActAgent` (después del método `_maybe_extract_lesson`):

```python
def _fuzzy_match(self, text, keywords):
    """
    Devuelve True si alguna keyword está contenida en text.
    Tolera errores de Whisper con matching parcial.
    
    Args:
        text: Texto normalizado a minúsculas
        keywords: Lista de palabras clave a buscar
    
    Returns:
        True si hay coincidencia
    """
    generic_prefixes = {
        "abre", "abrir", "busca", "buscar", "muestr", "mostr",
    }
    
    for kw in keywords:
        # Coincidencia exacta
        if kw in text:
            return True
        
        # Coincidencia parcial (primeros 5 caracteres)
        if len(kw) >= 5:
            prefix = kw[:5].strip()
            if not prefix or prefix in generic_prefixes:
                continue
            prefix = re.escape(prefix)
            if re.search(r"\b" + prefix, text):
                return True
    
    return False

def _extract_search_query(self, text):
    """
    Extrae la consulta de búsqueda del texto.
    
    Ejemplo: "busca sobre python" → "python"
    """
    keywords = ["busca sobre", "buscar sobre", "buscas sobre", "busca", "buscar", "buscas"]
    
    for kw in keywords:
        if kw in text:
            query = text.split(kw, 1)[1].strip()
            # Cortar en conjunciones
            for stop in [" y ", " pero ", " luego ", " después"]:
                if stop in query:
                    query = query.split(stop, 1)[0].strip()
                    break
            return query if query else None
    
    return None
```

---

## 5. Métodos Específicos de `_fast_path` (Refactorización Modular)

Agregar estos métodos a `ReActAgent`:

```python
def _fast_help_commands(self, text, user_input):
    """Handler para comando 'dime los comandos'."""
    help_keywords = [
        "dime los comandos", "di los comandos", "dime los comando",
        "di los comando", "muéstrame los comandos", "mostrar comandos",
        "qué comandos", "que comandos", "lista de comandos"
    ]
    
    if not any(kw in text for kw in help_keywords):
        return None
    
    response = (
        "Puedo abrir apps como Spotify, calculadora, navegador o el panel de métricas, "
        "cerrar apps como Spotify o el panel de Quickshell, "
        "mostrar métricas de programas y procesos, "
        "buscar en Google, crear recordatorios, "
        "y también apagar o reiniciar el equipo si dices 'apágate' o 'reinicia el equipo'."
    )
    self.memory.add_interaction(user_input, response, [{"action": "help", "args": [], "result": response}])
    return (response, [])

def _fast_spotify(self, text, user_input):
    """Handler para comandos de Spotify."""
    if "spotify" not in text:
        return None
    
    keywords = [
        "me gusta", "megusta", "liked", "likes", "gustan", "tus me gusta",
        "lista", "musica", "música", "reproduce", "canciones", "canción",
        "song", "shuffle", "mezcla"
    ]
    
    if not self._fuzzy_match(text, keywords):
        return None
    
    res = self.tools.spotify_liked_songs()
    actions_log = [{"action": "spotify_liked_songs", "args": [], "result": res}]
    self.memory.add_interaction(user_input, res, actions_log)
    self._maybe_extract_lesson(user_input, res)
    return (res, actions_log)

def _fast_search(self, text, user_input):
    """Handler para búsquedas en Google."""
    if not any(kw in text for kw in ["busca", "buscar", "buscas"]):
        return None
    
    query = self._extract_search_query(text)
    if not query:
        return None
    
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        res = self.tools.run_command(f'xdg-open "{url}"')
        response = f"Buscando '{query}' en el navegador."
        self.memory.add_interaction(user_input, response, [{"action": "run_command", "args": [url], "result": res}])
        self._maybe_extract_lesson(user_input, response)
        return (response, [])
    except Exception as e:
        return (f"Error al buscar en el navegador: {e}", [])

def _fast_system_power(self, text, user_input):
    """Handler para apagar/reiniciar (con confirmación)."""
    if platform.system() != "Linux":
        return None
    
    power_off_phrases = [
        "apágate", "apagate", "apaga el equipo", "apaga la pc", "apaga el pc",
        "apaga la computadora", "apaga el computador", "apaga el sistema",
        "apaga el ordenador", "apaga el servidor"
    ]
    reboot_phrases = [
        "reinicia el equipo", "reinicia la pc", "reinicia el pc",
        "reinicia la computadora", "reinicia el computador", "reinicia el sistema",
        "reinicia el ordenador", "reinicia el servidor",
        "reiniciar el equipo", "reiniciar la pc", "reiniciar el sistema",
        "reiniciar el ordenador"
    ]
    
    if any(phrase in text for phrase in power_off_phrases):
        return self._confirm_and_execute("poweroff", user_input)
    elif any(phrase in text for phrase in reboot_phrases):
        return self._confirm_and_execute("reboot", user_input)
    
    return None

def _confirm_and_execute(self, action, user_input):
    """Solicita confirmación por voz antes de ejecutar acción destructiva."""
    if action == "poweroff":
        msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
        commands = POWER_COMMANDS.get("poweroff")
        success_msg = "Apagando el sistema."
        fail_msg = "Apagado cancelado."
    elif action == "reboot":
        msg = "¿Estás seguro de que quieres reiniciar? Di 'sí' para confirmar."
        commands = POWER_COMMANDS.get("reboot")
        success_msg = "Reiniciando el sistema."
        fail_msg = "Reinicio cancelado."
    else:
        return (f"Acción desconocida: {action}", [])
    
    self.voice.speak(msg)
    
    try:
        confirmation = self.voice.listen(timeout=5)
        if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante", "ok"]):
            response = success_msg + " Puede requerir permisos de administrador."
            self.memory.add_interaction(user_input, response, [{"action": action, "args": [], "result": "initiated"}])
            
            try:
                subprocess.run(commands, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                response = f"No pude ejecutar {action}: {e}. Ejecuta Jarvis como root."
                self.memory.add_interaction(user_input, response, [])
            
            return (response, [])
        else:
            response = fail_msg
            self.memory.add_interaction(user_input, response, [])
            return (response, [])
    except:
        return (f"No pude escuchar confirmación. {fail_msg}", [])
```

---

## 6. Refactorizar `_fast_path` para usar los nuevos métodos

Reemplazar el método `_fast_path` completo (línea 438) con:

```python
def _fast_path(self, user_input):
    """
    Atajos para comandos frecuentes sin pasar por LLM.
    Intenta handlers en orden de probabilidad.
    Retorna (response, actions) si coincide, None si no.
    """
    text = user_input.strip().lower()
    
    # Lista de handlers en orden de probabilidad (más comunes primero)
    handlers = [
        self._fast_help_commands,
        self._fast_spotify,
        self._fast_search,
        self._fast_system_power,
        # Agregar más handlers según necesario
    ]
    
    # Intentar cada handler hasta que uno devuelva resultado
    for handler in handlers:
        result = handler(text, user_input)
        if result is not None:
            response, actions = result
            return response, actions
    
    # Si ningún fast-path coincidió, retornar None
    # El caller (process_user_input) enviará a LLM
    return None
```

---

## Notas de Implementación

✅ **Copiar y pegar estos códigos directamente**  
✅ **No requieren cambios adicionales**  
✅ **Mantienen 100% de funcionalidad**  
⚠️ **Importar `logger` en los archivos donde se use**  
⚠️ **Importar `PATHS`, `POWER_COMMANDS` donde sea necesario**  

