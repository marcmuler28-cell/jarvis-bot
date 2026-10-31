#!/usr/bin/env python3
"""cibertec_bridge.py v2 — Aula Cibertec/Blackboard dentro del cerebro (via MySQL).

v1 dependia de un `consultar.py` que nunca existio; v2 lee las tablas bb_*
de MySQL (bb_grades, bb_courses, bb_messages, bb_schedules) que llena el
sincronizador `skills/blackboard_skill.py` con Playwright. Es la MISMA base
de datos del resto del Jarvis, asi que:

  - «mis notas» responde al instante, sin abrir navegador.
  - Si no hay datos sincronizados todavia, te dice como sincronizarlos
    («abre cibertec») en vez de reventar con 1146 (42S02).
  - Si MySQL no esta corriendo, avisa y el cerebro sigue vivo.

Verbos del fast-path (a traves de intentar()):
  «mis notas» «ver notas» «calificaciones»   -> notas por curso + promedios
  «mis cursos» «que cursos llevo»            -> matriculados este ciclo
  «mensajes del aula» «bandeja cibertec»     -> sin leer por curso
  «calendario del aula» «mis evaluaciones»   -> proximas sesiones/horarios

Regla 2 del proyecto: nada de aqui se loguea solo (el SMS exige humano).
Para refrescar los datos: «abre cibertec» con la sesion vigente, o
`python3 login_unificado.py` en terminal y luego «abre cibertec».

Importa solo stdlib al cargar; DatabaseManager (mysql) se abre de forma
perezoza y es inyectable (set_db) para los tests.
"""
import datetime as _dt
import re
import unicodedata

# ─────────────────────────────────────────────────────────────
# Acceso a datos (perezozo + inyectable para tests)
# ─────────────────────────────────────────────────────────────

_DB = None


def set_db(db):
    """Inyecta un gestor de BD (para tests). None vuelve al modo automatico."""
    global _DB
    _DB = db


def _db():
    """Devuelve el gestor de BD o None si no hay forma de conectar."""
    global _DB
    if _DB is not None:
        return _DB
    try:
        from database import DatabaseManager  # se resuelve al primer uso
        _DB = DatabaseManager()
        return _DB
    except Exception:
        return None


MSG_SIN_DB = ("🗄️ No pude hablar con la base de datos local (MySQL). "
              "Revísala con `systemctl status mysqld` y me vuelves a preguntar.")

MSG_SIN_DATOS = ("🗄️ Todavía no sincronicé datos del aula. Dime «abre cibertec» "
                 "(con la sesión vigente); si te pide código SMS, primero corre "
                 "`python3 login_unificado.py` en una terminal y reintenta.")


def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ─────────────────────────────────────────────────────────────
# Formateo (respuestas cortas para el chat)
# ─────────────────────────────────────────────────────────────

def _a_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def fmt_notas(filas):
    """filas: (course_name, evaluation_type, evaluation_name, weight, grade).

    Promedio PONDERADO cuando las evaluaciones traen peso (T1 30%, T2 30%,
    EF 40%); si no hay pesos, promedio simple. Escala vigesimal /20.
    Devuelve None si no hay filas (señal de «sin sincronizar»).
    """
    if not filas:
        return None
    por_curso = {}
    for curso, tipo, nombre, peso, nota in filas:
        por_curso.setdefault(curso or "?", []).append(
            ((tipo or "").strip(), _a_float(peso), _a_float(nota)))

    lineas, promedios = [], []
    for curso, evs in por_curso.items():
        calificadas = [(t, w, g) for t, w, g in evs if g > 0]
        if not calificadas:
            lineas.append(f"• {curso}: sin notas aún ({len(evs)} evaluaciones registradas)")
            continue
        peso_total = sum(w for _, w, _ in calificadas)
        if peso_total > 0:
            prom = sum(g * w for _, w, g in calificadas) / peso_total
        else:
            prom = sum(g for _, _, g in calificadas) / len(calificadas)
        promedios.append(prom)
        detalle = ", ".join(f"{t} {g:g}" for t, _, g in calificadas if t)
        linea = f"• {curso}: promedio {prom:.1f}/20"
        if detalle:
            linea += f"  ({detalle})"
        lineas.append(linea)

    if not promedios:
        return "📚 El aula todavía no tiene notas calificadas (solo evaluaciones registradas)."
    texto = "📚 NOTAS DEL AULA\n" + "\n".join(lineas[:14])
    if len(lineas) > 14:
        texto += f"\n… y {len(lineas) - 14} cursos más"
    texto += f"\n🎯 Promedio general: {sum(promedios) / len(promedios):.1f}/20"
    return texto


def fmt_cursos(nombres):
    if not nombres:
        return None
    lineas = [f"{i}. {n}" for i, n in enumerate(nombres, 1)]
    return f"🎓 CURSOS ({len(nombres)})\n" + "\n".join(lineas[:12])


def fmt_mensajes(filas):
    """filas: (course_name, remitente, fecha, cuerpo, unread)."""
    if not filas:
        return None
    agg = {}
    for curso, _remitente, _fecha, _cuerpo, unread in filas:
        a = agg.setdefault(curso or "?", {"sl": 0, "tot": 0})
        a["tot"] += 1
        if unread:
            a["sl"] += 1
    orden = sorted(agg.items(), key=lambda kv: (-kv[1]["sl"], -kv[1]["tot"]))
    lineas = [f"{'🔔' if a['sl'] else '✅'} {c}: {a['sl']} sin leer de {a['tot']}"
              for c, a in orden[:10]]
    total_sl = sum(a["sl"] for a in agg.values())
    return f"✉️ AULA — {total_sl} mensajes sin leer\n" + "\n".join(lineas)


_MESES = ("ene feb mar abr may jun jul ago sep oct nov dic").split()
_RE_FECHA = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def fmt_calendario(filas):
    """filas: (course_name, schedule_date, day_of_week, start_time, end_time, status).

    schedule_date viene como «22/05» (sin año): las fechas que ya pasaron
    este año se asumen del próximo ciclo y quedan al final.
    """
    if not filas:
        return None
    hoy = _dt.date.today()

    def clave(fecha):
        m = _RE_FECHA.match((fecha or "").strip())
        if not m:
            return (2, 99, 99)  # sin fecha parseable -> al final
        dia, mes = int(m.group(1)), int(m.group(2))
        pasado = 1 if (mes, dia) < (hoy.month, hoy.day) else 0
        return (pasado, mes, dia)

    lineas = []
    for curso, fecha, dia_sem, inicio, fin, estado in sorted(
            filas, key=lambda f: clave(f[1])):
        fecha_ok = bool(_RE_FECHA.match((fecha or "").strip()))
        cuando = " ".join(x for x in ((dia_sem or "").strip(), (fecha or "").strip()) if x)
        hora = f"{inicio}-{fin}" if (inicio or fin) else ""
        trozos = [f"• {cuando or '(sin fecha)'}"]
        if not fecha_ok:
            trozos.append("(sin fecha)")
        if hora:
            trozos.append(hora)
        trozos.append(curso or "?")
        if estado:
            trozos.append(f"({estado})")
        lineas.append(" ".join(trozos))
    return "🗓️ PRÓXIMAS SESIONES DEL AULA\n" + "\n".join(lineas[:10])


# ─────────────────────────────────────────────────────────────
# Interpretación de verbos
# ─────────────────────────────────────────────────────────────

_RE_NOTAS = re.compile(r"\b(notas|calificaciones|gradebook|promedios?)\b")
_RE_CURSOS = re.compile(r"\b(cursos|matricula|matriculado|matriculados)\b")
_RE_MENSAJES = re.compile(
    r"\b(mensajes|bandeja|conversaciones)\b.*(aula|cibertec|blackboard|universidad|profes?)\b")
_RE_CALENDARIO = re.compile(
    r"\b(calendario|agenda|evaluaciones?|examenes?|practicas?)\b"
    r".*(aula|cibertec|blackboard|universidad|este ciclo)\b|\b(calendario|evaluaciones|examenes)\b")

# Palabras que marcan que «notas» NO es del aula (bloc de notas, anotar...)
_GUARDAS_NOTAS = ("bloc", "blog", "block", "anota")

_STOP_CURSO = {"aula", "cibertec", "blackboard", "universidad", "ciclo",
               "este ciclo", "el aula", "mi", "mis", "aula virtual"}


def _curso_hint(t):
    """«notas de desarrollo web» -> 'desarrollo web' (o None si no aplica)."""
    m = re.search(r"\bde\s+([\w ]{3,60})$", t)
    if not m:
        return None
    candidato = m.group(1).strip()
    return None if candidato in _STOP_CURSO else candidato


def _q(db, sql, params=None):
    return db.query(sql, params) if params else db.query(sql)


def intentar(texto):
    """Devuelve la respuesta del aula si la frase es del dominio, o None."""
    t = _norm(texto)
    if not t:
        return None
    if any(g in t for g in _GUARDAS_NOTAS):
        return None  # «abre el bloc de notas», «anota que...» -> no son del aula

    hint = _curso_hint(t)
    db = _db()

    if _RE_NOTAS.search(t):
        if db is None:
            return MSG_SIN_DB
        try:
            if hint:
                filas = _q(db, "SELECT course_name, evaluation_type, evaluation_name, "
                               "weight, grade FROM bb_grades WHERE course_name LIKE ?",
                           (f"%{hint}%",))
            else:
                filas = _q(db, "SELECT course_name, evaluation_type, evaluation_name, "
                               "weight, grade FROM bb_grades")
            return fmt_notas(filas) or MSG_SIN_DATOS
        except Exception:
            return MSG_SIN_DB

    if _RE_MENSAJES.search(t):
        if db is None:
            return MSG_SIN_DB
        try:
            filas = _q(db, "SELECT course_name, remitente, fecha, cuerpo, unread FROM bb_messages")
            return fmt_mensajes(filas) or MSG_SIN_DATOS
        except Exception:
            return MSG_SIN_DB

    if _RE_CALENDARIO.search(t):
        if db is None:
            return MSG_SIN_DB
        try:
            filas = _q(db, "SELECT course_name, schedule_date, day_of_week, "
                           "start_time, end_time, status FROM bb_schedules")
            return fmt_calendario(filas) or MSG_SIN_DATOS
        except Exception:
            return MSG_SIN_DB

    if _RE_CURSOS.search(t) and ("cibertec" in t or "aula" in t or "blackboard" in t
                                 or "universidad" in t
                                 or t.startswith(("mis cursos", "cursos", "que cursos"))):
        if db is None:
            return MSG_SIN_DB
        try:
            nombres = [r[0] for r in _q(db, "SELECT name FROM bb_courses ORDER BY name") if r[0]]
            if not nombres:  # respaldo: derivar cursos de notas y horarios
                vistos = [r[0] for r in _q(db, "SELECT DISTINCT course_name FROM bb_grades")]
                vistos += [r[0] for r in _q(db, "SELECT DISTINCT course_name FROM bb_schedules")]
                nombres = sorted({v for v in vistos if v})
            return fmt_cursos(nombres) or MSG_SIN_DATOS
        except Exception:
            return MSG_SIN_DB

    return None


# ─────────────────────────────────────────────────────────────
# Herramientas para el LLM (ReAct)
# ─────────────────────────────────────────────────────────────

def _tool_notas(*_a):
    r = intentar("mis notas")
    return r if r is not None else "Sin datos del aula."


def _tool_cursos(*_a):
    r = intentar("mis cursos")
    return r if r is not None else "Sin datos del aula."


def _tool_mensajes(*_a):
    r = intentar("mensajes del aula")
    return r if r is not None else "Sin datos del aula."


def registrar():
    """Dict de herramientas extra para SystemTools.actions."""
    return {
        "cibertec_notas": _tool_notas,
        "cibertec_cursos": _tool_cursos,
        "cibertec_mensajes": _tool_mensajes,
    }
