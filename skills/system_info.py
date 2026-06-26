# skills/system_info.py
import platform
import psutil

class SystemInfoSkill:
    def __init__(self):
        pass

    def execute(self, command):
        if "info del sistema" in command.lower():
            info = f"Sistema: {platform.system()}, Versión: {platform.version()}, CPU: {psutil.cpu_percent()}%, Memoria: {psutil.virtual_memory().percent}%"
            return info
        else:
            return "Comando de info del sistema no reconocido."