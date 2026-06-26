# skills/notes.py
class NotesSkill:
    def __init__(self):
        self.notes = []

    def execute(self, command):
        if "agregar nota" in command.lower():
            note = command.split("agregar nota", 1)[1].strip()
            self.notes.append(note)
            return f"Nota agregada: {note}"
        elif "ver notas" in command.lower():
            return "Notas: " + ", ".join(self.notes) if self.notes else "No hay notas."
        else:
            return "Comando de notas no reconocido."