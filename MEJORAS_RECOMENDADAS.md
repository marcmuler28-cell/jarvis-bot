# Sugerencias de Mejora para JarvisBot

## 1. Refactorizar `_fast_path` en Métodos Específicos

### Problema Actual
El método `_fast_path()` (línea 438) tiene más de 200 líneas con múltiples bloques `if/elif` anidados:
- Comandos de Spotify
- Búsqueda en navegador
- Abrir aplicaciones
- Recordatorios
- Apagar/reiniciar
- Gestión de ventanas
- Manejo de ratón
- Etc.

### Solución Propuesta
Separar en métodos temáticos más pequeños y reutilizables:

```python
def _fast_path(self, user_input):
    """Dispatcher de atajos sin pasar por LLM."""
    text = user_input.strip().lower()
    
    # Intentar cada fast-path en orden de probabilidad
    handlers = [
        self._fast_help_commands,
        self._fast_spotify,
        self._fast_search,
        self._fast_open_app,
        self._fast_file_operations,  # recordatorio, guardar archivo
        self._fast_system_power,      # apagar, reiniciar
        self._fast_window_management, # minimizar, maximizar, cerrar
        self._fast_mouse_control,     # mover ratón
        self._fast_folder_navigation, # abrir carpetas
    ]
    
    for handler in handlers:
        result = handler(text, user_input)
        if result is not None:
            response, actions = result
            return response, actions
    
    # Si ningún fast-path funcionó, retornar None para ir a LLM
    return None

# Nuevos métodos específicos:
def _fast_spotify(self, text, user_input):
    """Detecta y ejecuta comandos de Spotify."""
    if "spotify" not in text:
        return None
    keywords = ["me gusta", "megusta", "liked", "canciones", "música", "reproduce"]
    if not self._fuzzy_match(text, keywords):
        return None
    
    res = self.tools.spotify_liked_songs()
    actions = [{"action": "spotify_liked_songs", "args": [], "result": res}]
    self.memory.add_interaction(user_input, res, actions)
    self._maybe_extract_lesson(user_input, res)
    return res, actions

def _fast_search(self, text, user_input):
    """Detecta y ejecuta búsquedas en Google."""
    if not any(kw in text for kw in ["busca", "buscar", "buscas"]):
        return None
    
    query = self._extract_search_query(text)
    if not query:
        return None
    
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    res = self.tools.run_command(f'xdg-open "{url}"')
    response = f"Buscando '{query}' en el navegador."
    actions = [{"action": "run_command", "args": [url], "result": res}]
    self.memory.add_interaction(user_input, response, actions)
    self._maybe_extract_lesson(user_input, response)
    return response, actions

def _fast_system_power(self, text, user_input):
    """Detecta comandos de apagar/reiniciar CON confirmación por voz."""
    if platform.system() != "Linux":
        return None
    
    power_off_phrases = [
        "apágate", "apagate", "apaga el equipo", "apaga la pc",
        "apaga la computadora", "apaga el sistema"
    ]
    reboot_phrases = [
        "reinicia el equipo", "reinicia la pc", "reinicia el sistema",
        "reiniciar el equipo", "reiniciar el pc"
    ]
    
    if any(phrase in text for phrase in power_off_phrases):
        return self._confirm_and_poweroff(user_input)
    elif any(phrase in text for phrase in reboot_phrases):
        return self._confirm_and_reboot(user_input)
    
    return None

def _confirm_and_poweroff(self, user_input):
    """Solicita confirmación por voz antes de apagar."""
    msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
    self.voice.speak(msg)
    confirmation = self.voice.listen(timeout=5)
    
    if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante"]):
        response = "Apagando el sistema. Esto puede requerir permisos de administrador."
        self.memory.add_interaction(user_input, response, [{"action": "poweroff", "args": [], "result": "initiated"}])
        
        try:
            if shutil.which("systemctl"):
                subprocess.run(["systemctl", "poweroff"], stdin=subprocess.DEVNULL)
            elif shutil.which("shutdown"):
                subprocess.run(["shutdown", "-h", "now"], stdin=subprocess.DEVNULL)
            else:
                response = "No encontré comando de apagado válido."
        except Exception as e:
            response = f"Error al apagar: {e}"
            self.memory.add_interaction(user_input, response, [])
        
        return response, []
    else:
        response = "Apagado cancelado."
        self.memory.add_interaction(user_input, response, [])
        return response, []

def _confirm_and_reboot(self, user_input):
    """Solicita confirmación por voz antes de reiniciar."""
    msg = "¿Estás seguro de que quieres reiniciar? Di 'sí' para confirmar."
    self.voice.speak(msg)
    confirmation = self.voice.listen(timeout=5)
    
    if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante"]):
        response = "Reiniciando el sistema..."
        self.memory.add_interaction(user_input, response, [{"action": "reboot", "args": [], "result": "initiated"}])
        
        try:
            if shutil.which("systemctl"):
                subprocess.run(["systemctl", "reboot"], stdin=subprocess.DEVNULL)
            elif shutil.which("reboot"):
                subprocess.run(["reboot"], stdin=subprocess.DEVNULL)
            else:
                response = "No encontré comando de reinicio válido."
        except Exception as e:
            response = f"Error al reiniciar: {e}"
            self.memory.add_interaction(user_input, response, [])
        
        return response, []
    else:
        response = "Reinicio cancelado."
        self.memory.add_interaction(user_input, response, [])
        return response, []

# Más métodos específicos...
def _fast_help_commands(self, text, user_input):
    """Detecta solicitud de ayuda."""
    help_keywords = ["dime los comandos", "muéstrame los comandos", "qué comandos"]
    if not any(kw in text for kw in help_keywords):
        return None
    
    response = (
        "Puedo abrir apps como Spotify, calculadora, navegador o panel de métricas, "
        "cerrar apps como Spotify o el panel de Quickshell, "
        "mostrar métricas de programas y procesos, "
        "buscar en Google, crear recordatorios, "
        "y también apagar o reiniciar el equipo si dices 'apágate' o 'reinicia el equipo'."
    )
    self.memory.add_interaction(user_input, response, [{"action": "help", "args": [], "result": response}])
    return response, []
```

### Ventajas
- ✅ Métodos más pequeños y testables
- ✅ Más fácil agregar nuevos comandos
- ✅ Reutilización de código
- ✅ Separación de responsabilidades
- ✅ Mantenimiento simplificado

---

## 2. Centralizar Rutas y Comandos en `config.py`

### Problema Actual
`os.path.expanduser("~")` se repite **20+ veces** en `assistant.py`:
- Línea 592: `os.path.expanduser("~")`
- Línea 945, 999, 1110: Más repeticiones
- Caminos duplicados para Downloads, Documents, Desktop

### Solución Propuesta

**Agregar a `config.py`:**

```python
import os
from pathlib import Path

# ========== CONFIGURACIÓN DE RUTAS CENTRALIZADAS ==========

# Directorio home del usuario
HOME = os.path.expanduser("~")
HOME_PATH = Path(HOME)

# Directorios estándar del usuario
DIRS = {
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
for dir_name, dir_path in DIRS.items():
    if not dir_path.startswith("/proc") and not dir_path.startswith("/sys"):
        os.makedirs(dir_path, exist_ok=True)

# Rutas de archivos importante
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), "checkpoint.json")

# ========== COMANDOS DE SISTEMA CENTRALIZADOS ==========

SYSTEM_COMMANDS = {
    "firefox": "firefox",
    "chrome": "google-chrome",
    "spotify": "spotify",
    "calculator": "gnome-calculator",
    "file_manager": "xdg-open",
    "terminal": "gnome-terminal",
}

# Comandos de potencia (Linux)
POWER_COMMANDS = {
    "poweroff": ["systemctl", "poweroff"],
    "reboot": ["systemctl", "reboot"],
    "fallback_poweroff": ["shutdown", "-h", "now"],
    "fallback_reboot": ["reboot"],
}
```

**Luego en `assistant.py` usar:**

```python
from config import DIRS, SYSTEM_COMMANDS, POWER_COMMANDS

# Antes (repetido 20 veces):
# home = os.path.expanduser("~")
# folder_path = os.path.join(home, "Downloads")

# Ahora:
folder_path = DIRS["downloads"]
home = DIRS["home"]

# Para comandos:
# Antes:
# subprocess.run(["systemctl", "poweroff"], ...)

# Ahora:
subprocess.run(POWER_COMMANDS["poweroff"], ...)
```

### Ventajas
- ✅ Una fuente única de verdad (DRY)
- ✅ Fácil cambiar rutas en un único lugar
- ✅ Código más legible
- ✅ Facilita porting a Windows/macOS

---

## 3. Reemplazar `print()` con Logging

### Problema Actual
El código usa `print()` directamente (40+ veces):
- No hay niveles de severidad (DEBUG, INFO, WARNING, ERROR)
- Difícil filtrar mensajes en producción
- No hay timestamp
- Imposible redirigir a archivo

### Solución Propuesta

**Crear `logger_config.py`:**

```python
import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".cache" / "jarvisbot"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "jarvisbot.log"

def setup_logger(name=__name__, level=logging.INFO):
    """Configura logging con consola y archivo."""
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Formatter con timestamp
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para archivo
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # Archivo siempre DEBUG
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# Uso global en assistant.py:
logger = setup_logger('JarvisBot')
```

**En `assistant.py` reemplazar:**

```python
# Antes:
print("Cargando modelo rápido (Qwen 3B)...")
print(f"Modelo rápido cargado.")
print(f"Error cargando modelo rápido: {e}")

# Después:
logger.info("Cargando modelo rápido (Qwen 3B)...")
logger.info("Modelo rápido cargado.")
logger.error(f"Error cargando modelo rápido: {e}")

# Debug (solo en desarrollo):
logger.debug(f"Textoanalizado: '{text}'")

# Warnings (situaciones inesperadas):
logger.warning(f"Acción malformada con múltiples pipes: {action_str}")
```

### Ventajas
- ✅ Debugging más fácil en producción
- ✅ Historial de eventos persistente
- ✅ Niveles de severidad
- ✅ Compatible con herramientas de monitoreo

---

## 4. Proteger Acciones Destructivas con Confirmación por Voz

### Problema Actual
En líneas 663-693, apagar/reiniciar se ejecutan **sin confirmación**:

```python
# Actual (inseguro):
if any(phrase in text for phrase in power_off_phrases):
    response = "Intentando apagar..."
    # ¡Se apaga directamente!
    subprocess.run(["systemctl", "poweroff"], ...)
```

### Solución Propuesta
Ver **Sección 1** - El método `_confirm_and_poweroff()` incluye:

```python
def _confirm_and_poweroff(self, user_input):
    msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
    self.voice.speak(msg)
    confirmation = self.voice.listen(timeout=5)
    
    if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro"]):
        # OK, proceder
        subprocess.run(POWER_COMMANDS["poweroff"], ...)
    else:
        response = "Apagado cancelado."
        self.memory.add_interaction(user_input, response, [])
        return response, []
```

### Otras Acciones a Proteger
- Eliminar archivos (no está implementado, pero si lo haces)
- Cambiar configuración del sistema
- Reinstalar/actualizar software
- Formatear unidades

### Ventajas
- ✅ Evita apagados accidentales
- ✅ Confirmación natural por voz
- ✅ Coherente con UX del asistente
- ✅ Respeta UNIX safety principles

---

## 5. Separar SelfImprover en Plugin Opcional

### Problema Actual
`SelfImprover` (línea 1343) está integrado en el flujo principal:
- Se carga siempre en memoria
- No hay control de activación
- Código de 200+ líneas que puede no necesitarse

### Solución Propuesta

**Estructura de plugin:**

```
plugins/
  __init__.py
  plugin_base.py
  self_improver/
    __init__.py
    plugin.py
    strategies.py
    checkpoint_manager.py
```

**Crear `plugins/plugin_base.py`:**

```python
from abc import ABC, abstractmethod

class JarvisPlugin(ABC):
    """Clase base para todos los plugins de JarvisBot."""
    
    def __init__(self, voice, agent, config):
        self.voice = voice
        self.agent = agent
        self.config = config
        self.enabled = False
    
    @abstractmethod
    def initialize(self):
        """Se llama cuando se carga el plugin."""
        pass
    
    @abstractmethod
    def shutdown(self):
        """Se llama cuando se descarga el plugin."""
        pass
    
    @abstractmethod
    def on_command(self, user_input):
        """Se llama para cada comando (si el plugin se suscribió)."""
        pass
```

**Crear `plugins/self_improver/plugin.py`:**

```python
from ..plugin_base import JarvisPlugin

class SelfImproverPlugin(JarvisPlugin):
    def __init__(self, voice, agent, config):
        super().__init__(voice, agent, config)
        self.self_improver = None
    
    def initialize(self):
        """Se llama al iniciar JarvisBot si está habilitado."""
        if not self.config.get("SELF_IMPROVER_ENABLED", False):
            self.enabled = False
            return
        
        from .plugin import SelfImprover
        self.self_improver = SelfImprover(self.voice, self.agent)
        self.enabled = True
        self.voice.speak("Módulo de auto-mejora activado (EXPERIMENTAL).")
    
    def shutdown(self):
        """Se llama al apagar JarvisBot."""
        if self.self_improver:
            self.self_improver.cleanup()
    
    def on_command(self, user_input):
        """Intercepta comandos si está habilitado."""
        if not self.enabled:
            return None
        
        if "automejora" in user_input.lower() or "self-improve" in user_input.lower():
            return self.self_improver.start()
        
        return None
```

**En `config.py`:**

```python
# PLUGINS HABILITADOS
PLUGINS_ENABLED = {
    "self_improver": False,     # SIEMPRE False en producción
    "weather": True,
    "reminders": True,
    "web_search": True,
}

# O desde variable de entorno en producción:
import os
SELF_IMPROVER_ENABLED = os.getenv("JARVIS_SELF_IMPROVER", "false").lower() == "true"
```

**En `assistant.py` (inicialización):**

```python
from plugins.self_improver.plugin import SelfImproverPlugin

class ReActAgent:
    def __init__(self, ...):
        # ... código existente ...
        
        # Cargar plugins
        self.plugins = {}
        self._load_plugins()
    
    def _load_plugins(self):
        """Carga plugins según configuración."""
        if TEXT_MODE:
            return  # No cargar plugins en modo texto
        
        if SELF_IMPROVER_ENABLED or os.getenv("JARVIS_SELF_IMPROVER"):
            self.plugins["self_improver"] = SelfImproverPlugin(
                self.voice, 
                self, 
                {"SELF_IMPROVER_ENABLED": SELF_IMPROVER_ENABLED}
            )
            self.plugins["self_improver"].initialize()
    
    def shutdown(self):
        """Limpieza al apagar."""
        for plugin_name, plugin in self.plugins.items():
            plugin.shutdown()
        
        # Resto del shutdown existente
        self.memory.save()
```

### Ventajas
- ✅ `SelfImprover` nunca se ejecuta sin configuración explícita
- ✅ Fácil de deshabilitar en producción
- ✅ Más legible y mantenible
- ✅ Permite agregar más plugins en el futuro
- ✅ Bajo acoplamiento

---

## Resumen de Cambios

| Mejora | Prioridad | Complejidad | Impacto |
|--------|-----------|-------------|---------|
| 1. Refactorizar `_fast_path` | ALTA | MEDIA | Mantenibilidad |
| 2. Centralizar rutas en `config.py` | MEDIA | BAJA | Mantenibilidad |
| 3. Agregar logging | MEDIA | BAJA | Debugging |
| 4. Confirmación en acciones destructivas | ALTA | BAJA | Seguridad |
| 5. SelfImprover como plugin | BAJA | MEDIA | Arquitectura |

## Orden Recomendado de Implementación

1. **Primero:** Confirmación en acciones destructivas (rápido, crítico)
2. **Segundo:** Centralizar rutas en `config.py` (refactorización de base)
3. **Tercero:** Reemplazar `print()` con logging (depuración)
4. **Cuarto:** Refactorizar `_fast_path` (mejora mayor)
5. **Quinto:** SelfImprover como plugin (arquitectura)

---

## Testing

Para cada cambio, verificar que **no se rompa funcionalidad**:

```bash
# Test de commands básicos
python main.py  # Verificar que los comandos se ejecutan igual

# Test de apagar/reiniciar (en VM o test machine)
# Decir: "apágate" → debe pedir confirmación
# Decir: "sí" → debe apagar
# Decir: "no" → debe cancelar

# Test de búsqueda, spotify, abrir apps
# Que todos funcionen igual que antes
```
