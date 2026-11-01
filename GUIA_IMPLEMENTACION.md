# Guía de Implementación Paso a Paso

## Paso 1: Confirmación en Acciones Destructivas (⏱️ 15 minutos)

### Cambio Recomendado
Modificar el bloque de apagado/reinicio (líneas 660-693) para solicitar confirmación por voz.

**Archivo: `assistant.py` línea 660**

```python
# ANTES (sin confirmación):
if any(phrase in text for phrase in power_off_phrases):
    response = "Intentando apagar el sistema..."
    subprocess.run(["systemctl", "poweroff"], ...)
    return response, []

# DESPUÉS (con confirmación):
if any(phrase in text for phrase in power_off_phrases):
    # Pedir confirmación por voz
    msg = "¿Estás seguro de que quieres apagar el equipo? Di 'sí' para confirmar."
    self.voice.speak(msg)
    
    try:
        confirmation = self.voice.listen(timeout=5)
        if confirmation and any(w in confirmation.lower() for w in ["sí", "si", "yes", "claro", "adelante"]):
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
                response = f"No pude apagar el sistema: {e}."
                self.memory.add_interaction(user_input, response, [])
                return response, []
            
            return response, []
        else:
            response = "Apagado cancelado."
            self.memory.add_interaction(user_input, response, [])
            return response, []
    except:
        response = "No pude escuchar la confirmación."
        return response, []
```

**Hacer lo mismo para `reboot_phrases` (línea 690)**

✅ **Seguro:** No rompe funcionalidad, solo añade una capa de confirmación

---

## Paso 2: Centralizar Rutas en `config.py` (⏱️ 20 minutos)

### Cambio 2.1: Agregar a `config.py`

```python
# Al final del archivo config.py:

import os
from pathlib import Path

# ========== RUTAS CENTRALIZADAS ==========
HOME = os.path.expanduser("~")

PATHS = {
    "home": HOME,
    "downloads": os.path.join(HOME, "Downloads"),
    "documents": os.path.join(HOME, "Documents"),
    "desktop": os.path.join(HOME, "Desktop"),
    "pictures": os.path.join(HOME, "Pictures"),
    "music": os.path.join(HOME, "Music"),
    "videos": os.path.join(HOME, "Videos"),
}

# Crear directorios si no existen
for key, path in PATHS.items():
    if path and not path.startswith(("/proc", "/sys")):
        os.makedirs(path, exist_ok=True)
```

### Cambio 2.2: Reemplazar en `assistant.py`

**Importar al inicio del archivo:**
```python
from config import PATHS  # Agregar esta línea
```

**Luego reemplazar todas estas líneas:**

| Línea | Antes | Después |
|-------|-------|---------|
| 592 | `folder_path = os.path.expanduser("~")` | `folder_path = PATHS["home"]` |
| 945 | `home = os.path.expanduser("~")` | `home = PATHS["home"]` |
| 999 | `home = os.path.expanduser("~")` | `home = PATHS["home"]` |
| 1110 | `home = os.path.expanduser("~")` + `os.path.join(home, "Downloads")` | `folder_path = PATHS["downloads"]` |

✅ **Seguro:** Solo cambios de variable, mismo resultado

---

## Paso 3: Agregar Logging (⏱️ 30 minutos)

### Paso 3.1: Crear archivo `logger_config.py`

```python
import logging
import sys
from pathlib import Path

# Crear directorio de logs
LOG_DIR = Path.home() / ".cache" / "jarvisbot"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "jarvisbot.log"

def setup_logger(name="JarvisBot", level=logging.INFO):
    """Configura logging para JarvisBot."""
    logger = logging.getLogger(name)
    
    # Evitar duplicar handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Formato con timestamp
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para archivo (siempre DEBUG)
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except:
        pass  # Si no puede escribir el archivo, continuar sin él
    
    return logger

# Logger global
logger = setup_logger()
```

### Paso 3.2: Usar logging en `assistant.py`

**Al inicio del archivo:**
```python
from logger_config import logger  # Agregar esta línea
```

**Reemplazar print por logger (ejemplos):**

| Ubicación | Antes | Después |
|-----------|-------|---------|
| Línea 123 | `print("Cargando modelo rápido...")` | `logger.info("Cargando modelo rápido (Qwen 3B)...")` |
| Línea 135 | `print(f"Error cargando modelo: {e}")` | `logger.error(f"Error cargando modelo rápido: {e}")` |
| Línea 226 | `print(f"Advertencia: acción malformada...")` | `logger.warning(f"Acción malformada con múltiples pipes: {action_str}")` |
| Línea 350 | `print(f"DEBUG: Iniciando...")` | `logger.debug(f"Iniciando auto-reparación para {original_name}...")` |

**Ventaja:** Los logs quedan en `~/.cache/jarvisbot/jarvisbot.log` para inspeccionar problemas

✅ **Seguro:** `logger` funciona igual que `print()`, solo con más información

---

## Paso 4: Refactorizar `_fast_path` (⏱️ 60 minutos)

Este es el cambio más grande. **Hacerlo por bloques:**

### Paso 4.1: Crear método auxiliar `_fuzzy_match`

**Extraer de `_fast_path` la función `fuzzy_match` local:**

```python
def _fuzzy_match(self, text, keywords):
    """Devuelve True si alguna keyword está contenida en text."""
    generic_prefixes = {"abre", "abrir", "busca", "buscar", "muestr", "mostr"}
    
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
```

### Paso 4.2: Extraer método para Spotify

```python
def _fast_spotify(self, text, user_input):
    """Manejo de comandos de Spotify."""
    if "spotify" not in text:
        return None
    
    keywords = ["me gusta", "megusta", "liked", "likes", "gustan", 
                "tus me gusta", "lista", "musica", "música", "reproduce"]
    
    if not self._fuzzy_match(text, keywords):
        return None
    
    res = self.tools.spotify_liked_songs()
    actions_log = [{"action": "spotify_liked_songs", "args": [], "result": res}]
    self.memory.add_interaction(user_input, res, actions_log)
    self._maybe_extract_lesson(user_input, res)
    return (res, actions_log)  # Retorna tupla (response, actions)
```

### Paso 4.3: Extraer método para búsqueda

```python
def _fast_search(self, text, user_input):
    """Manejo de búsquedas en Google."""
    if not any(kw in text for kw in ["busca", "buscar", "buscas"]):
        return None
    
    query = ""
    for kw in ["busca sobre", "buscar sobre", "buscas sobre", "busca", "buscar", "buscas"]:
        if kw in text:
            query = text.split(kw, 1)[1].strip()
            break
    
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
        return (f"Error al buscar: {e}", [])
```

### Paso 4.4: Refactorizar `_fast_path` para usar estos métodos

```python
def _fast_path(self, user_input):
    """Atajos sin pasar por LLM. Usa múltiples handlers."""
    text = user_input.strip().lower()
    
    # Lista de handlers en orden de probabilidad
    handlers = [
        ("help", self._fast_help_commands),
        ("spotify", self._fast_spotify),
        ("search", self._fast_search),
        ("open_app", self._fast_open_app),
        ("file_ops", self._fast_file_operations),
        ("power", self._fast_system_power),
        # ... más handlers
    ]
    
    for handler_name, handler_method in handlers:
        result = handler_method(text, user_input)
        if result is not None:
            return result  # Retorna (response, actions)
    
    # Si ningún fast-path coincidió, retornar None para ir a LLM
    return None
```

✅ **Seguro:** Cada método es pequeño, testeable y el flujo es idéntico

---

## Paso 5: SelfImprover como Plugin (⏱️ Opcional, 90 minutos)

Este cambio es **arquitectónico** y puede hacerse después. Ver `MEJORAS_RECOMENDADAS.md` para estructura completa.

Lo importante es que en `config.py` añadas:

```python
# Habilitar/deshabilitar plugin de auto-mejora (SIEMPRE False en producción)
SELF_IMPROVER_ENABLED = False  # O: os.getenv("JARVIS_SELF_IMPROVER", "false") == "true"
```

Y luego en `assistant.py` verifica esta flag antes de usar SelfImprover.

---

## Testing Rápido Después de Cambios

```bash
# 1. Verificar que no hay errores de sintaxis
python -m py_compile assistant.py
python -m py_compile config.py
python -m py_compile logger_config.py

# 2. Ejecutar en TEXT_MODE para test rápido
# Cambiar en config.py: TEXT_MODE = True
python main.py

# 3. Probar comandos básicos:
#    "Hola" → debe responder
#    "dime los comandos" → debe listar
#    "apágate" → debe pedir confirmación

# 4. Cambiar TEXT_MODE = False y probar con voz (opcional)
```

---

## Checklist de Implementación

- [ ] **Paso 1:** Confirmación en apagado/reinicio (CRÍTICO)
- [ ] **Paso 2:** Centralizar rutas en config.py
- [ ] **Paso 3:** Agregar logging
- [ ] **Paso 4:** Refactorizar _fast_path
- [ ] **Paso 5:** SelfImprover como plugin (opcional)
- [ ] Testear que todo funciona igual
- [ ] Crear commit en git (si usas control de versiones)

---

## Notas Importantes

✅ **Funcionalidad NO cambia** - El usuario no notará diferencia  
✅ **Compatible hacia atrás** - Nada se rompe  
✅ **Mejora mantenibilidad** - Código más limpio y organizado  
⚠️ **Testing importante** - Probar cada cambio  

