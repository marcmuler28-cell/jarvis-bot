#!/usr/bin/env python3
"""test_cibertec.py — pruebas de cibertec_bridge.py v2 sin MySQL ni red.

Igual que test_ventanas.py: autocontenido, con una FakeDB in-memory.
Corre con:  python3 test_cibertec.py
"""
import sys
import unittest

import cibertec_bridge as cb


# ─────────────────────────────────────────────────────────────
# FakeDB: responde por nombre de tabla; aplica LIKE sobre la 1.ª columna
# ─────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, **tablas):
        self.tablas = tablas  # {"bb_grades": [filas], ...}

    def query(self, sql, params=None):
        sql_l = sql.lower()
        for tabla, filas in self.tablas.items():
            if f"from {tabla}" in sql_l:
                if params and " like " in sql_l:
                    aguja = str(params[0]).strip("%").lower()
                    return [f for f in filas if aguja in str(f[0]).lower()]
                return list(filas)
        return []

    def execute(self, sql, params=None):  # pragma: no cover (solo sync)
        return None


class DBRoto:
    def query(self, *a, **k):
        raise RuntimeError("mysql down")

    def execute(self, *a, **k):
        raise RuntimeError("mysql down")


class DBNone:
    def query(self, *a, **k):
        return []

    def execute(self, *a, **k):
        return None


GRADES = [
    # curso, tipo, nombre, peso, nota
    ("DESARROLLO WEB", "T1", "Parcial 1", 30, 15),
    ("DESARROLLO WEB", "T2", "Parcial 2", 30, 16),
    ("DESARROLLO WEB", "EF", "Final", 40, 18),
    ("BASE DE DATOS", "T1", "Avance 1", 0, 14),
    ("BASE DE DATOS", "T2", "Avance 2", 0, 16),
]
COURSES = [("c0", "BASE DE DATOS", None), ("c1", "DESARROLLO WEB", None)]
MESSAGES = [
    ("DESARROLLO WEB", "profe", "hace 2 h", "Recuerden la entrega", 1),
    ("DESARROLLO WEB", "profe", "ayer", "Sala de clases", 0),
    ("BASE DE DATOS", "profe", "ayer", "Buen trabajo", 0),
]
SCHEDULES = [
    ("DESARROLLO WEB", "22/05", "Viernes", "07:00 PM", "08:29 PM", "Asistió"),
    ("BASE DE DATOS", "10/03", "Martes", "06:00 PM", "07:29 PM", "Pendiente"),
]

TODO = dict(bb_grades=GRADES, bb_courses=COURSES,
            bb_messages=MESSAGES, bb_schedules=SCHEDULES)
VACIO = dict(bb_grades=[], bb_courses=[], bb_messages=[], bb_schedules=[])


def setUpModule():
    cb.set_db(FakeDB(**TODO))


def tearDownModule():
    cb.set_db(None)


# ─────────────────────────────────────────────────────────────
# Parser: qué entra al dominio y qué no
# ─────────────────────────────────────────────────────────────

class TestParser(unittest.TestCase):
    def test_frases_validas(self):
        for frase in ("mis notas", "ver notas", "mis calificaciones",
                      "mis cursos", "que cursos llevo este ciclo",
                      "mensajes del aula", "bandeja cibertec",
                      "calendario del aula", "mis evaluaciones"):
            self.assertIsNotNone(cb.intentar(frase), frase)

    def test_frases_ajenas_devuelven_none(self):
        for frase in ("hola que tal", "manda un whatsapp a mama",
                      "trae spotify aqui", "pon music aletoria",
                      "organiza mis descargas", "que hora es"):
            self.assertIsNone(cb.intentar(frase), frase)

    def test_guardas_notas_ajenas(self):
        # «notas» que NO son del aula: bloc de notas / anotar
        for frase in ("abre el bloc de notas", "anota que mañana hay examen",
                      "escribe en mi blog sobre python"):
            self.assertIsNone(cb.intentar(frase), frase)

    def test_hint_de_curso(self):
        self.assertEqual(cb._curso_hint("notas de desarrollo web"), "desarrollo web")
        self.assertIsNone(cb._curso_hint("mis notas"))
        self.assertIsNone(cb._curso_hint("notas del aula"))  # palabra vacía

    def test_filtro_por_curso(self):
        r = cb.intentar("notas de desarrollo web")
        self.assertIn("DESARROLLO WEB", r)
        self.assertNotIn("BASE DE DATOS", r)


# ─────────────────────────────────────────────────────────────
# Formateo
# ─────────────────────────────────────────────────────────────

class TestFormatos(unittest.TestCase):
    def test_promedio_ponderado(self):
        # T1 30% =15, T2 30% =16, EF 40% =18 -> (450+480+720)/100 = 16.5
        r = cb.fmt_notas(GRADES)
        self.assertIn("16.5/20", r)
        # general = (16.5 + 15.0) / 2 = 15.8
        self.assertIn("Promedio general: 15.8/20", r)

    def test_promedio_simple_sin_pesos(self):
        r = cb.fmt_notas([("CURSO", "T1", "A", 0, 14), ("CURSO", "T2", "B", 0, 16)])
        self.assertIn("15.0/20", r)

    def test_curso_sin_notas_calificadas(self):
        filas = GRADES + [("REDES", "T1", "Examen", 30, 0)]
        r = cb.fmt_notas(filas)
        self.assertIn("REDES: sin notas aún", r)
        self.assertIn("1 evaluaciones registradas", r)

    def test_vacio_devuelve_none(self):
        self.assertIsNone(cb.fmt_notas([]))
        self.assertIsNone(cb.fmt_cursos([]))
        self.assertIsNone(cb.fmt_mensajes([]))
        self.assertIsNone(cb.fmt_calendario([]))

    def test_mensajes_agrupa_sin_leer(self):
        r = cb.fmt_mensajes(MESSAGES)
        self.assertIn("1 mensajes sin leer", r)  # total global
        self.assertIn("🔔 DESARROLLO WEB: 1 sin leer de 2", r)
        self.assertIn("✅ BASE DE DATOS: 0 sin leer de 1", r)

    def test_calendario_orden_y_formato(self):
        r = cb.fmt_calendario(SCHEDULES)
        # ambos meses ya pasaron (hoy: octubre) -> quedan "próximo ciclo",
        # orden por mes: marzo antes que mayo
        self.assertLess(r.index("10/03"), r.index("22/05"))
        self.assertIn("Martes 10/03 06:00 PM-07:29 PM", r)
        self.assertIn("(Pendiente)", r)

    def test_calendario_fila_sin_fecha_al_final(self):
        filas = SCHEDULES + [("X", "sin fecha", "Lunes", "", "", "")]
        r = cb.fmt_calendario(filas)
        self.assertIn("(sin fecha)", r)
        self.assertGreater(r.index("(sin fecha)"), r.index("10/03"))


# ─────────────────────────────────────────────────────────────
# BD caída / vacía
# ─────────────────────────────────────────────────────────────

class TestBD(unittest.TestCase):
    def test_db_caida_mensaje_honesto(self):
        cb.set_db(None)
        original = cb._DB
        try:
            # BD que revienta al consultar: intentar() NUNCA debe propagar
            cb.set_db(DBRoto())
            for frase in ("mis notas", "mensajes del aula",
                          "calendario del aula", "mis cursos"):
                r = cb.intentar(frase)
                self.assertIn("MySQL", r, frase)
        finally:
            cb.set_db(original)

    def test_tablas_vacias_piden_sincronizar(self):
        cb.set_db(FakeDB(**VACIO))
        try:
            for frase in ("mis notas", "mis cursos", "mensajes del aula",
                          "calendario del aula"):
                r = cb.intentar(frase)
                self.assertIn("abre cibertec", r, frase)
        finally:
            cb.set_db(FakeDB(**TODO))

    def test_cursos_respaldo_desde_grades_y_schedules(self):
        # bb_courses vacía pero con datos en grades/schedules
        cb.set_db(FakeDB(bb_courses=[], bb_grades=GRADES,
                         bb_schedules=SCHEDULES, bb_messages=[]))
        try:
            r = cb.intentar("mis cursos")
            self.assertIn("BASE DE DATOS", r)
            self.assertIn("DESARROLLO WEB", r)
        finally:
            cb.set_db(FakeDB(**TODO))


# ─────────────────────────────────────────────────────────────
# Herramientas para el LLM
# ─────────────────────────────────────────────────────────────

class TestTools(unittest.TestCase):
    def test_registrar_expone_tres(self):
        herramientas = cb.registrar()
        self.assertEqual(set(herramientas),
                         {"cibertec_notas", "cibertec_cursos", "cibertec_mensajes"})
        for h in herramientas.values():
            self.assertTrue(callable(h))

    def test_tools_devuelven_texto(self):
        herramientas = cb.registrar()
        for nombre, h in herramientas.items():
            self.assertIsInstance(h(), str, nombre)


if __name__ == "__main__":
    unittest.main(verbosity=2)
