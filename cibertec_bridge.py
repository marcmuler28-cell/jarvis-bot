#!/usr/bin/env python3
"""cibertec_bridge.py v1 — Aula virtual (Blackboard Ultra) + Mi Cibertec dentro del cerebro.

Ejecuta ./consultar.py (Playwright + APIs /learn/api/v1 del aula) con la sesión
de ./blackboard_state.json y devuelve respuestas CORTAS para el chat.

Verbos del fast-path (a través de intentar()):
  «mis notas» «ver notas» «calificaciones»     -> notas por curso + promedios
  «mis cursos» «que cursos llevo»              -> matriculados este ciclo
  «mensajes del aula» «bandeja cibertec»       -> sin leer por curso
  «calendario del aula» «mis evaluaciones»     -> eventos próximos

Regla 2 del proyecto: si la sesión caducó, NO se loguea solo (el SMS exige
humano) -> remite a `python login_unificado.py` en terminal interactiva.

Solo stdlib. Este módulo JAMÁS lee ni imprime blackboard_state.json (solo lo
recibe consultar.py vía Playwright) y NUNCA debe subirse a un repo.
"""
import json
import os
import re
import subprocess
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
CONSULTAR = os.environ.get("JARVIS_CONSULTAR", os.path.join(AQUI, "consultar.py"))

MSG_SESION = ("🔒 Tu sesión del aula caducó. En una terminal del proyecto JarvisBot: "
              "`python login_unificado.py` (te pedirá el código SMS) y me vuelves a preguntar.")


def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ─────────────────────────────────────────────────────────────
# Ejecución de consultar.py
# ─────────────────────────────────────────────────────────────

def _disponible():
    return os.path.isfile(CONSULTAR)


def _correr(consulta, extra=(), timeout=120):
    """Corre consultar.py en el proyecto; devuelve (json_dict|None, error_str|None)."""
    if not _disponible():
        return None, "No encuentro `consultar.py` en la raíz del proyecto JarvisBot."
    try:
        r = subprocess.run(
            [sys.executable, CONSULTAR, consulta, *extra],
            capture_output=True, text=True, timeout=timeout,
            cwd=AQUI, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"El aula tardó más de {timeout}s — prueba otra vez en un rato."
    except Exception as e:
        return None, f"No pude ejecutar consultar.py: {e}"

    out = (r.stdout or "")
    if r.returncode == 2 or "SESIÓN EXPIRADA" in out:
        return None, MSG_SESION
    # el bloque JSON va al final tras la línea "--- JSON ---"
    if "--- JSON ---" in out:
        blob = out.rsplit("--- JSON ---", 1)[1].strip()
        try:
            return json.loads(blob), None
        except Exception:
            pass
    err = (r.stderr or "").strip().splitlines()
    return None, (err[-1][:160] if err else "El aula respondió vacío.")


# ─────────────────────────────────────────────────────────────
# Formateo (respuestas cortas para el chat)
# ─────────────────────────────────────────────────────────────

_RC_CODIGO = re.compile(r"^[A-Z]{3,5}\d{4,5}\s+")
_RC_FILA_TOTAL = re.compile(
    r"^(total|calificaci[oó]n general|total ponderado|promedio|nota final)\b", re.I)


def _curso_corto(nombre):
    return _RC_CODIGO.sub("", nombre or "").strip() or (nombre or "?")


def _a_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fmt_notas(datos):
    notas = datos.get("notas") or []
    nombres = {c.get("course_id"): c.get("nombre", "?") for c in (datos.get("cursos") or [])}
    por_curso, orden = {}, []
    for n in notas:
        cid = n.get("course_id")
        if cid not in por_curso:
            por_curso[cid] = []
            orden.append(cid)
        por_curso[cid].append(n)

    lineas = []
    promedios = []
    for cid in orden:
        filas = [f for f in por_curso[cid]
                 if f.get("item") and not _RC_FILA_TOTAL.match(f.get("item", ""))]
        if not filas:
            continue
        nombre = _curso_corto(nombres.get(cid) or "")
        calif = []
        for f in filas:
            pt, pos = _a_float(f.get("puntaje")), _a_float(f.get("puntos_posibles"))
            if pt is None or not pos:
                continue
            calif.append(pt / pos * 20.0)
        if calif:
            prom = sum(calif) / len(calif)
            promedios.append(prom)
            lineas.append(f"• {nombre}: promedio {prom:.1f}/20 ({len(calif)} notas)")
        sin_calificar = [f for f in filas if f.get("status") != "GRADED"]
        if sin_calificar:
            lineas.append(f"   ↳ {len(sin_calificar)} sin calificar (última: "
                          f"{sin_calificar[-1].get('item', '')[:40]})")
    if not lineas:
        return "No encontré notas registradas en el aula."
    resumen = "📚 NOTAS DEL AULA\n" + "\n".join(lineas[:14])
    if len(lineas) > 14:
        resumen += f"\n… y {len(lineas) - 14} más (detalle en jarvisbot.db)"
    if promedios:
        resumen += f"\n🎯 Promedio general: {sum(promedios) / len(promedios):.1f}/20"
    return resumen


def fmt_cursos(datos):
    cursos = [c for c in (datos.get("cursos") or [])]
    if not cursos:
        return "No vi cursos matriculados en el aula."
    vivos = [c for c in cursos if c.get("disponible")]
    lineas = [f"{i}. {_curso_corto(c.get('nombre', '?'))}"
              for i, c in enumerate(vivos, 1)]
    extra = len(cursos) - len(vivos)
    texto = f"🎓 CURSOS ({len(vivos)} activos)\n" + "\n".join(lineas[:12])
    if extra:
        texto += f"\n(+{extra} de ciclos pasados)"
    return texto


def fmt_mensajes(datos):
    convs = datos.get("conversaciones") or []
    resumen = datos.get("resumen_mensajes") or []
    nombres = {c.get("course_id"): c.get("nombre", "?") for c in (datos.get("cursos") or [])}
    if not convs and not resumen:
        return "No vi conversaciones en el aula."
    filas = convs if convs else resumen
    # agrupar por curso (el aula separa por conversación)
    agg = {}
    for c in filas:
        cid = c.get("course_id") or c.get("curso") or "?"
        a = agg.setdefault(cid, {"sl": 0, "tot": 0})
        a["sl"] += c.get("sin_leer") or 0
        a["tot"] += c.get("total") or 0
    orden = sorted(agg.items(), key=lambda kv: (-kv[1]["sl"], -kv[1]["tot"]))
    lineas = []
    for cid, a in orden[:10]:
        nombre = _curso_corto(nombres.get(cid) or (cid if cid != "?" else "?"))
        marca = "🔔" if a["sl"] else "✅"
        lineas.append(f"{marca} {nombre}: {a['sl']} sin leer de {a['tot']}")
    total_sl = sum(a["sl"] for _, a in agg.items())
    return f"✉️ AULA — {total_sl} mensajes sin leer\n" + "\n".join(lineas)


_MESES = ("ene feb mar abr may jun jul ago sep oct nov dic").split()


def fmt_calendario(datos):
    evs = datos.get("calendario") or []
    if not evs:
        return "No vi eventos en el calendario del aula."
    evs = sorted(evs, key=lambda e: e.get("inicio") or "")
    lineas, vistos = [], set()
    for e in evs:
        clave = (e.get("titulo"), e.get("inicio"))
        if clave in vistos:
            continue
        vistos.add(clave)
        ini = (e.get("inicio") or "")[:16].replace("T", " ")
        dia = ini[:10]
        try:
            y, m, d = dia.split("-")
            bonito = f"{d} {_MESES[int(m) - 1]}"
        except Exception:
            bonito = dia
        hora = ini[11:16] if len(ini) >= 16 else ""
        lineas.append(f"• {bonito}{' ' + hora if hora else ''} — {e.get('titulo', '?')}")
    return "🗓️ CALENDARIO DEL AULA\n" + "\n".join(lineas[:10])


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


def intentar(texto):
    """Devuelve la respuesta del aula si la frase es del dominio, o None."""
    t = _norm(texto)
    if not t:
        return None

    consulta, formateador, timeout = None, None, 120
    if _RE_NOTAS.search(t):
        consulta, formateador, timeout = "notas", fmt_notas, 240
    elif _RE_MENSAJES.search(t):
        consulta, formateador, timeout = "mensajes", fmt_mensajes, 150
    elif _RE_CALENDARIO.search(t):
        consulta, formateador, timeout = "calendario", fmt_calendario, 120
    elif _RE_CURSOS.search(t) and ("cibertec" in t or "aula" in t or "blackboard" in t
                                   or "universidad" in t or t.startswith(("mis cursos", "cursos", "que cursos"))):
        consulta, formateador, timeout = "cursos", fmt_cursos, 120

    if consulta is None:
        return None

    datos, error = _correr(consulta, extra=["--json"], timeout=timeout)
    if error:
        return error
    if datos is None:
        return "El aula respondió algo que no entendí (mira la terminal del gateway)."
    try:
        return formateador(datos)
    except Exception as e:
        return f"Extraje los datos del aula pero falló el resumen: {e}"


# ─────────────────────────────────────────────────────────────
# Herramientas para el LLM (ReAct)
# ─────────────────────────────────────────────────────────────

def _tool_notas(*_a):
    datos, err = _correr("notas", extra=["--json"], timeout=240)
    return fmt_notas(datos) if datos else (err or "Sin datos del aula.")


def _tool_cursos(*_a):
    datos, err = _correr("cursos", extra=["--json"], timeout=120)
    return fmt_cursos(datos) if datos else (err or "Sin datos del aula.")


def _tool_mensajes(*_a):
    datos, err = _correr("mensajes", extra=["--json"], timeout=150)
    return fmt_mensajes(datos) if datos else (err or "Sin datos del aula.")


def registrar():
    """Dict de herramientas extra para SystemTools.actions."""
    return {
        "cibertec_notas": _tool_notas,
        "cibertec_cursos": _tool_cursos,
        "cibertec_mensajes": _tool_mensajes,
    }
