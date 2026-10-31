"""
jarvis_windows.py v3 — Conciencia de ventanas para Hyprland.
=============================================================
Hace que Jarvis VEA las ventanas y las maneje por su nombre:

  - listar()          → "qué ventanas hay abiertas" (por workspace, con foco marcado)
  - mover(app, ws)    → "mueve firefox al 3" / "al escritorio de juegos" / "al siguiente"
  - traer(app)        → "trae spotify" (lo trae al workspace actual y enfoca)
  - enfocar(app)      → "enfoca kitty"
  - cerrar(app)       → "cierra la ventana de spotify" (solo la ventana, no el proceso)
  - minimizar/maximizar/pantalla_completa(app)
  - parse_mover(txt)  → parser universal de frases (mover / mover el ratón guard / pásalo al 3)

Solo usa stdlib + hyprctl. Sin dependencias nuevas.
Diseñado para probarse sin Hyprland (mock de hyprctl por PATH).
"""

import difflib
import json
import re
import subprocess
import unicodedata

# ─────────────────────────────────────────────────────────────
# Normalización (mismas reglas que normalizer.py: minúsculas, sin tildes)
# ─────────────────────────────────────────────────────────────

def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in nfkd if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s\+\.\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _compact(t: str) -> str:
    return re.sub(r"[\s\-\_\.]", "", t or "")


# ─────────────────────────────────────────────────────────────
# Parser universal de «mover ventana»
# ─────────────────────────────────────────────────────────────

# Verbos de movimiento (forma base; se aceptan pronombres pegados: pásalo, llévala…)
_VERBOS_MOVER = {
    "mueve", "mueves", "mueva", "muevan", "mueven", "mover", "move",
    "manda", "mandas", "mandan", "mandar", "send",
    "pasa", "pasas", "pasan", "pasar",
    "lleva", "llevas", "llevan", "llevar",
    "traslada", "trasladas", "trasladan", "trasladar",
    "envia", "envias", "envian", "enviar",
    "devuelve", "devuelves", "devuelven", "devolver",
    "regresa", "regresas", "regresan", "regresar",
}
_VERBOS_TRAER = {
    "trae", "traes", "traen", "traer", "traeme", "bring", "ven",
}
_NUMEROS = {
    "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12,
}
# Frases donde el verbo NO es de ventana (protección contra colisiones)
_GUARDAS = ("mouse", "raton", "cursor", "volumen", "brillo",
            "pantalla completa", "captura", "foto")
# Objetos que jamás son ventanas
_APP_INVALIDA = {
    "volumen", "brillo", "pantalla", "cancion", "musica", "playlist",
    "mensaje", "correo", "notificacion", "pestaña", "pestana",
}
_RE_PREPOSICION = re.compile(
    r"(?:^|\s+)(?:al|a\s+el|a\s+la|hacia(?:\s+(?:el|la))?|para(?:\s+(?:el|la))?|to)\s+"
)
# keyword de workspace + opcional "numero/n" + opcional "de"
_RE_KEYWORD_WS = re.compile(
    r"^(?:workspaces?|escritorios?|wss?|desktops?|espacios?)\s*"
    r"(?:num(?:ero)?|n)?\s*(?:de\s+)?(?P<valor>.+)$"
)
_RE_DESTINO = re.compile(r"^(?P<dest>\d{1,2}|siguiente|anterior|next|prev|[a-z][a-z0-9\-_]{2,})\b")
_RE_SUFIJO_LUGAR = re.compile(
    r"\s+(?:hasta\s+)?(?:aqui|aca|conmigo|para\s+aca|siguiendo|y\s+ve|ve\s+tu)$"
)
_RE_TITULO_CONTENEDOR = re.compile(
    r"^(?:ventanas?|apps?|aplicaciones?|programas?)\s+(?:de\s+|del\s+)?"
)


def parse_mover(texto):
    """
    Interpreta frases de movimiento de ventanas. Entrada: texto ya normalizado
    (minúsculas, sin tildes) pero tolera cualquier entrada.

    Devuelve dict {'accion': 'mover'|'traer', 'app': str, 'ws': str|None,
                   'follow': bool}  o None si no es un comando de ventana.
    """
    t = _norm(texto)
    if not t or len(t) < 6:
        return None
    for g in _GUARDAS:
        if g in t:
            return None

    palabras = t.split()
    v = palabras[0]
    if v.endswith(("lo", "la", "me")) and v[:-2] in (_VERBOS_MOVER | _VERBOS_TRAER):
        v = v[:-2]
    if v in _VERBOS_TRAER:
        accion = "traer"
    elif v in _VERBOS_MOVER:
        accion = "mover"
    else:
        return None

    cuerpo = " ".join(palabras[1:])
    # artículos y contenedores ("la ventana de firefox" → "firefox")
    cuerpo = re.sub(r"^(?:el|la|los|las|un|una)\s+", "", cuerpo)
    cuerpo = _RE_TITULO_CONTENEDOR.sub("", cuerpo).strip()
    # sufijos de lugar ("trae firefox aquí")
    cuerpo = _RE_SUFIJO_LUGAR.sub("", cuerpo).strip()

    # separar app / destino
    app = cuerpo
    ws = None
    kw_presente = False
    m = _RE_PREPOSICION.search(cuerpo)
    if m:
        destino = cuerpo[m.end():].strip()
        app = cuerpo[:m.start()].strip()
        mk = _RE_KEYWORD_WS.match(destino)
        if mk:
            kw_presente = True
            destino_val = (mk.group("valor") or "").strip()
        else:
            destino_val = destino
        md = _RE_DESTINO.match(destino_val)
        if not md:
            return None
        dest = md.group("dest")
        if re.fullmatch(r"\d{1,2}", dest):
            ws = dest
        elif dest in _NUMEROS:
            ws = str(_NUMEROS[dest])
        elif dest in ("siguiente", "next"):
            ws = "e+1"
        elif dest in ("anterior", "prev"):
            ws = "e-1"
        elif kw_presente and len(dest) >= 3:
            ws = dest          # workspace con nombre: «al escritorio de juegos»
        else:
            return None        # «mueve spotify al chat» → no es un ws válido

    # limpiar app
    app = re.sub(r"^(?:el|la|los|las|un|una)\s+", "", app).strip()
    if app in _APP_INVALIDA or len(app) < 2:
        return None
    if "conmigo" in t or "siguiendo" in t or "sigueme" in t:
        follow = True
    else:
        follow = False

    if accion == "traer":
        # «trae firefox al 3» → mover al ws 3 y quedarse allí; «trae firefox» → traer aquí
        if ws:
            return {"accion": "mover", "app": app, "ws": ws, "follow": True}
        return {"accion": "traer", "app": app, "ws": None, "follow": True}

    if not ws:
        return None            # «mueve spotify» sin destino → ambiguo, no forzar
    return {"accion": "mover", "app": app, "ws": ws, "follow": follow}


# ─────────────────────────────────────────────────────────────
# Clase Ventanas (wrapper sobre hyprctl)
# ─────────────────────────────────────────────────────────────

_NOMBRES_ACTIVAS = ("activa", "actual", "esta", "esta ventana", "ventana activa",
                    "ventana actual", "la activa", "enfoque", "foco")


class Ventanas:
    """Operaciones de ventana en Hyprland vía hyprctl."""

    def __init__(self, timeout=3.0):
        self.timeout = timeout

    # ---------- infraestructura ----------

    def _hyprctl(self, *args):
        """Ejecuta hyprctl y devuelve stdout, o None si falla."""
        try:
            r = subprocess.run(["hyprctl", *args],
                               capture_output=True, text=True, timeout=self.timeout)
            return r.stdout or ""
        except Exception:
            return None

    def _hyprctl_json(self, *args):
        raw = self._hyprctl("-j", *args)
        if raw is None:
            return None
        try:
            return json.loads(raw or "null")
        except Exception:
            return None

    def _clientes(self):
        return [c for c in (self._hyprctl_json("clients") or []) if c.get("mapped")]

    def _ws_actual(self):
        data = self._hyprctl_json("activeworkspace")
        if isinstance(data, dict):
            return {"id": data.get("id"), "name": data.get("name") or ""}
        return {"id": None, "name": ""}

    def _activa(self):
        return self._hyprctl_json("activewindow") or None

    # ---------- resolución por nombre ----------

    def resolver(self, nombre):
        """Devuelve el cliente de Hyprland que mejor coincide con el nombre."""
        q = _norm(nombre).strip(" '\"")
        q = re.sub(r"^(?:el|la|los|las|un|una)\s+", "", q)
        q = _RE_TITULO_CONTENEDOR.sub("", q).strip()
        if not q:
            return None
        if q in _NOMBRES_ACTIVAS:
            return self._activa()

        clientes = self._clientes()
        if not clientes:
            return None
        try:
            actual = self._ws_actual().get("id")
        except Exception:
            actual = None

        q_pc = _compact(q)
        tokens = [tk for tk in q.split() if len(tk) >= 3]
        mejor, mejor_score = None, 0
        for c in clientes:
            clase = _norm(c.get("class") or "")
            ini = _norm(c.get("initialClass") or "")
            tit = _norm(c.get("title") or "")
            clase_pc, ini_pc, tit_pc = _compact(clase), _compact(ini), _compact(tit)
            ws = c.get("workspace") or {}
            s = 0
            if clase and q == clase:
                s = max(s, 100)
            if ini and q == ini:
                s = max(s, 97)
            if clase_pc and q_pc == clase_pc:
                s = max(s, 95)
            if ini_pc and q_pc == ini_pc:
                s = max(s, 93)
            if tit and q == tit:
                s = max(s, 92)
            if clase and (clase.startswith(q) or q.startswith(clase)):
                s = max(s, 84)
            if ini and (ini.startswith(q) or q.startswith(ini)):
                s = max(s, 82)
            if len(q) >= 3:
                if clase and q in clase:
                    s = max(s, 78)
                if ini and q in ini:
                    s = max(s, 75)
                if clase_pc and q_pc in clase_pc:
                    s = max(s, 76)
                if ini_pc and q_pc in ini_pc:
                    s = max(s, 73)
                if q in tit:
                    s = max(s, 62)
                if q_pc and q_pc in tit_pc:
                    s = max(s, 60)
            if tokens and all(
                tk in clase or tk in ini or tk in tit for tk in tokens
            ):
                s = max(s, 66)
            if len(q) >= 4:
                for cand in (clase, ini):
                    if cand and difflib.SequenceMatcher(None, q, cand).ratio() >= 0.82:
                        s = max(s, 70)
            if not s:
                continue
            if actual is not None and ws.get("id") == actual:
                s += 4
            if c.get("focused"):
                s += 3
            if s > mejor_score:
                mejor, mejor_score = c, s
        return mejor if mejor_score >= 55 else None

    # ---------- formato de ayudas ----------

    def _no_encontrada(self, nombre):
        cs = self._clientes()
        if not cs:
            return "No veo ninguna ventana abierta ahora mismo."
        abiertas = ", ".join(sorted({(c.get("class") or "?") for c in cs}))
        return (f"No encontré ninguna ventana que se parezca a «{nombre}». "
                f"Abiertas: {abiertas}. Di «ventanas abiertas» para verlas con detalle.")

    # ---------- acciones ----------

    def listar(self):
        cs = sorted(self._clientes(),
                    key=lambda c: ((c.get("workspace") or {}).get("id") or 0,
                                   c.get("class") or ""))
        if not cs:
            return "No veo ninguna ventana abierta ahora mismo."
        actual = self._ws_actual().get("id")
        lineas = [f"Veo {len(cs)} ventana(s):"]
        ultimo_ws = None
        for c in cs:
            ws = c.get("workspace") or {}
            wid = ws.get("id")
            wname = ws.get("name") or ""
            if wid != ultimo_ws:
                marca = "  ← donde estás" if wid == actual else ""
                nombre_ws = f"Workspace {wid}" if wid is not None else "Workspace ?"
                if wname and not str(wname).isdigit() and str(wname) != str(wid):
                    nombre_ws += f" · {wname}"
                lineas.append(f"▸ {nombre_ws}{marca}")
                ultimo_ws = wid
            clase = c.get("class") or "?"
            tit = (c.get("title") or "").strip()
            foco = "  ●foco" if c.get("focused") else ""
            lineas.append(f"   {clase} — {tit}{foco}" if tit else f"   {clase}{foco}")
        lineas.append("Puedo mover/traer/cerrar cualquiera por su nombre: "
                      "«mueve kitty al 2», «trae firefox», «cierra spotify».")
        return "\n".join(lineas)

    def mover(self, nombre, ws, follow=False):
        nombre = (nombre or "").strip().strip("'\"")
        ws = str(ws or "").strip().lower()
        if not nombre:
            return "¿Qué ventana muevo? Dime su nombre o di «ventanas abiertas»."
        if not ws:
            return "¿A qué workspace la muevo? Ej: «mueve firefox al 2»."
        ws = {"siguiente": "e+1", "next": "e+1",
              "anterior": "e-1", "prev": "e-1"}.get(ws, ws)
        cliente = self.resolver(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre)
        addr = cliente["address"]
        disp = "movetoworkspace" if follow else "movetoworkspacesilent"
        r = self._hyprctl("dispatch", disp, f"{ws},address:{addr}")
        if r is None or "ok" not in r.lower():
            return (f"Hyprland rechazó mover «{nombre}» al workspace {ws}: "
                    f"{(r or 'sin respuesta').strip()}")
        titulo = cliente.get("title") or cliente.get("class") or nombre
        extra = " y me quedo contigo" if follow else ""
        return f"«{titulo}» movida al workspace {ws}{extra}."

    def traer(self, nombre):
        nombre = (nombre or "").strip().strip("'\"")
        if not nombre:
            return "¿Qué ventana te traigo? Dime su nombre."
        cliente = self.resolver(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre)
        addr = cliente["address"]
        cur = self._ws_actual().get("id")
        if cur is None:
            return "No pude saber en qué workspace estás."
        r1 = self._hyprctl("dispatch", "movetoworkspacesilent", f"{cur},address:{addr}")
        r2 = self._hyprctl("dispatch", "focuswindow", f"address:{addr}")
        if (r1 is None or "ok" not in r1.lower()) or (r2 is None or "ok" not in r2.lower()):
            return f"Hyprland no pudo traer «{nombre}» al workspace {cur}."
        titulo = cliente.get("title") or cliente.get("class") or nombre
        return f"Traje «{titulo}» aquí (workspace {cur}) y la puse en foco."

    def enfocar(self, nombre):
        nombre = (nombre or "").strip().strip("'\"")
        if not nombre:
            return "¿A qué ventana pongo el foco?"
        cliente = self.resolver(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre)
        r = self._hyprctl("dispatch", "focuswindow", f"address:{cliente['address']}")
        if r is None or "ok" not in r.lower():
            return f"No pude enfocar «{nombre}»."
        titulo = cliente.get("title") or cliente.get("class") or nombre
        return f"Foco en «{titulo}»."

    def cerrar(self, nombre):
        """Cierra UNA ventana por nombre (no mata el proceso como pkill)."""
        nombre = (nombre or "").strip().strip("'\"")
        if not nombre:
            return "¿Qué ventana cierro? Dime su nombre."
        cliente = self.resolver(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre)
        r = self._hyprctl("dispatch", "closewindow", f"address:{cliente['address']}")
        if r is None or "ok" not in r.lower():
            return f"No pude cerrar «{nombre}»."
        titulo = cliente.get("title") or cliente.get("class") or nombre
        return f"Cerré la ventana «{titulo}»."

    def _aplicar_a(self, nombre):
        """Resuelve el cliente objetivo o usa la activa si no dan nombre."""
        if nombre and _norm(nombre) not in _NOMBRES_ACTIVAS:
            return self.resolver(nombre)
        return self._activa()

    def minimizar(self, nombre=None):
        cliente = self._aplicar_a(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre or "la ventana activa")
        self._hyprctl("dispatch", "focuswindow", f"address:{cliente['address']}")
        r = self._hyprctl("dispatch", "minimize")
        if r is None or "ok" not in r.lower():
            return ("Tu Hyprland no aceptó el dispatcher «minimize» "
                    "(actualiza Hyprland o usa otro atajo).")
        titulo = cliente.get("title") or cliente.get("class") or ""
        return f"Minimizé «{titulo}»."

    def maximizar(self, nombre=None):
        cliente = self._aplicar_a(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre or "la ventana activa")
        self._hyprctl("dispatch", "focuswindow", f"address:{cliente['address']}")
        r = self._hyprctl("dispatch", "fullscreen", "1")
        if r is None or "ok" not in r.lower():
            return f"No pude maximizar «{nombre or 'la ventana activa'}»."
        titulo = cliente.get("title") or cliente.get("class") or ""
        return f"Maximicé «{titulo}»."

    def pantalla_completa(self, nombre=None):
        cliente = self._aplicar_a(nombre)
        if not cliente or not cliente.get("address"):
            return self._no_encontrada(nombre or "la ventana activa")
        self._hyprctl("dispatch", "focuswindow", f"address:{cliente['address']}")
        r = self._hyprctl("dispatch", "fullscreen", "0")
        if r is None or "ok" not in r.lower():
            return f"No pude poner pantalla completa a «{nombre or 'la ventana activa'}»."
        titulo = cliente.get("title") or cliente.get("class") or ""
        return f"«{titulo}» a pantalla completa."
