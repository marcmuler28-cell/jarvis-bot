#!/usr/bin/env python3
"""
sync_aula.py — sincroniza el aula (Blackboard + MiCibertec) a la BD local MySQL.

Extrae mensajes, horarios, notas y cursos a las tablas bb_*; después
«mis notas» / «mis mensajes» / «mi horario» funcionan sin abrir el navegador.

Uso (NO hace falta activar el venv, usa el python del venv directamente):
    ~/Proyectos/JarvisBot/venv_linux/bin/python ~/Proyectos/JarvisBot/sync_aula.py

Si la sesión del aula caducó, corre antes:  python3 login_unificado.py
(pide el código SMS una sola vez; las cookies quedan en blackboard_state.json)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        from database import DatabaseManager
        from skills.blackboard_skill import BlackboardSkill
    except ModuleNotFoundError as e:
        print(f"❌ Falta el módulo {e.name}. Instálalo en el venv del proyecto:")
        print("    source ~/Proyectos/JarvisBot/venv_linux/bin/activate")
        print("    pip install playwright python-dotenv mysql-connector-python")
        return 1

    print("📚 Sincronizando el aula CIBERTEC a MySQL…")
    try:
        s = BlackboardSkill(DatabaseManager())
    except Exception as e:
        print(f"❌ No pude conectar con MySQL: {e}")
        print("   ¿Está corriendo? → systemctl status mysqld")
        return 1

    try:
        s.fetch_all_data()
        print("✅ Sincronización terminada. Contenido REAL por tabla:")
        vacias = []
        for tabla in ("bb_courses", "bb_grades", "bb_schedules", "bb_messages"):
            try:
                n = s.db.query(f"SELECT COUNT(*) FROM {tabla}")[0][0]
                print(f"   • {tabla + ':':14}{n} filas")
                if not n:
                    vacias.append(tabla)
            except Exception:
                print(f"   • {tabla + ':':14}no existe")
        if vacias:
            print(f"⚠️  Tablas VACÍAS: {', '.join(vacias)}. Eso que preguntas por "
                  "WhatsApp seguirá diciendo «sin datos» hasta que el sync las "
                  "llene (revisa los warnings de arriba).")
        else:
            print("   Ahora pregunta por WhatsApp: «mis notas», «mis mensajes», «mi horario».")
        return 0
    except Exception as e:
        print(f"❌ Error durante la sincronización: {e}")
        print("   Si la sesión caducó: python3 login_unificado.py (código SMS una vez).")
        return 1
    finally:
        try:
            s.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
