# skills/reminders.py
class RemindersSkill:
    def __init__(self):
        self.reminders = []

    def execute(self, command):
        if "agregar recordatorio" in command.lower():
            # Extract reminder
            reminder = command.split("agregar recordatorio", 1)[1].strip()
            self.reminders.append(reminder)
            return f"Recordatorio agregado: {reminder}"
        elif "ver recordatorios" in command.lower():
            return "Recordatorios: " + ", ".join(self.reminders) if self.reminders else "No hay recordatorios."
        else:
            return "Comando de recordatorios no reconocido."