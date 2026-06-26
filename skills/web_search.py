# skills/web_search.py
import requests

class WebSearchSkill:
    def __init__(self):
        pass

    def execute(self, command):
        if "buscar en web" in command.lower():
            query = command.split("buscar en web", 1)[1].strip()
            # Simple search, perhaps use a API
            return f"Resultado de búsqueda para '{query}': (funcionalidad básica, implementar API)"
        else:
            return "Comando de búsqueda web no reconocido."