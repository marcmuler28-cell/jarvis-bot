import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager
from skills.blackboard_skill import BlackboardSkill

def main():
    print("=== PRUEBA DE EXTRACCIÓN DE DATOS ===")
    print("Usando sesión guardada (blackboard_state.json).\n")

    # Inicializar base de datos (usa la misma que Jarvis)
    db = DatabaseManager()
    skill = BlackboardSkill(db_manager=db)

    try:
        print("1. Haciendo login con cookies guardadas...")
        skill.login()
        print("   Sesión reutilizada correctamente (o regenerada si era necesario).")

        print("2. Extrayendo mensajes de Blackboard...")
        skill._fetch_blackboard_messages()
        messages = db.query("SELECT course_name, remitente, cuerpo FROM bb_messages LIMIT 5")
        print(f"   Mensajes guardados: {len(messages)}")
        for m in messages:
            print(f"      - {m[0]}: {m[1]} -> {m[2][:50]}...")

        print("3. Cursos guardados:")
        courses = db.query("SELECT id, name FROM bb_courses")
        print(f"   Cursos encontrados: {len(courses)}")
        for c in courses:
            print(f"      - {c[1]} (ID: {c[0]})")

        print("4. Extrayendo horarios y notas de MiCibertec (unificado)...")
        skill._fetch_micibertec_all()
        schedules = db.query("SELECT course_name, schedule_date, day_of_week, start_time, end_time, classroom, status FROM bb_schedules")
        print(f"   Horarios guardados: {len(schedules)}")
        for s in schedules[:5]:
            print(f"      - {s[0]} | {s[2]} {s[1]} {s[3]}-{s[4]} | Aula: {s[5]} | Estado: {s[6]}")

        print("5. Notas guardadas:")
        grades = db.query("SELECT course_name, evaluation_name, grade, evaluation_type FROM bb_grades")
        print(f"   Notas guardadas: {len(grades)}")
        for g in grades:
            print(f"      - {g[0]}: {g[1]} = {g[2]} ({g[3]})")

        print("\n=== EXTRACCIÓN COMPLETADA CON ÉXITO ===")
        print("Los datos están en la base de datos SQLite de Jarvis.")

    except Exception as e:
        print(f"Error durante la extracción: {e}")
        import traceback
        traceback.print_exc()
    finally:
        skill.close()

if __name__ == "__main__":
    main()