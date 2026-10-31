import os
import re
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError
from database import DatabaseManager
from logger_config import logger

try:
    logger.setLevel(logging.INFO)
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, "..", ".env")
if os.path.exists(DOTENV_PATH):
    load_dotenv(DOTENV_PATH, override=True)

USER = os.getenv("USER")
PASS = os.getenv("PASS")

BLACKBOARD_LOGIN = "https://cibertec.blackboard.com/webapps/login/"
BLACKBOARD_COURSES = "https://cibertec.blackboard.com/ultra/course"
BLACKBOARD_MESSAGES = "https://cibertec.blackboard.com/ultra/messages"

SELECTORS = {
    "cookie_accept": "#agree_button",
    "login_btn": "#btn-login",
    "email_input": "#i0116",
    "email_next": "#idSIButton9",
    "pass_input": "#i0118",
    "pass_login": "#idSIButton9",
    "mfa_sms": 'div[data-value="OneWaySMS"]',
    "mfa_code_input": "#idTxtBx_SAOTCC_OTC",
    "mfa_submit": "#idSubmit_SAOTCC_Continue",
    "kmsi_yes": "#idSIButton9",
    "course_card": "article.course-element-card",
    "course_title": "h4.js-course-title-element",
    "content_list_item": "div.content-list-item",
    "content_item_title": "[class*='contentItemTitle']",
}

class BlackboardSkill:
    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager()
        self.storage_state_path = os.path.join(
            os.path.dirname(__file__), "..", "blackboard_state.json"
        )
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._ensure_tables()

    def _ensure_tables(self):
        """Crea las tablas bb_* si no existen (MySQL).

        Antes esto era un no-op que asumía que DatabaseManager las creaba,
        y «mis notas» reventaba con 1146 (42S02): Table 'jarvisbot.bb_grades'
        doesn't exist. Los tipos siguen EXACTAMENTE lo que insertan los
        métodos _fetch_* (fecha es texto porque Blackboard da "hace 2 h").
        """
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS bb_courses (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(255),
                last_updated DATETIME
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bb_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                course_id VARCHAR(64),
                course_name VARCHAR(255),
                remitente VARCHAR(255),
                fecha VARCHAR(64),
                destinatarios TEXT,
                cuerpo TEXT,
                unread TINYINT DEFAULT 0,
                last_updated DATETIME,
                INDEX idx_bb_msg_curso (course_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bb_schedules (
                id INT AUTO_INCREMENT PRIMARY KEY,
                course_name VARCHAR(255),
                schedule_date VARCHAR(64),
                day_of_week VARCHAR(20),
                start_time VARCHAR(20),
                end_time VARCHAR(20),
                classroom VARCHAR(255),
                status VARCHAR(64),
                last_updated DATETIME,
                INDEX idx_bb_sch_curso (course_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bb_grades (
                id INT AUTO_INCREMENT PRIMARY KEY,
                course_name VARCHAR(255),
                evaluation_type VARCHAR(20),
                evaluation_name VARCHAR(255),
                weight FLOAT DEFAULT 0,
                grade FLOAT DEFAULT 0,
                last_updated DATETIME,
                INDEX idx_bb_gr_curso (course_name)
            )
            """,
        ]
        try:
            for sql in ddl:
                self.db.execute(sql)
            logger.info("Tablas bb_* verificadas/creadas correctamente.")
        except Exception as e:
            # Si MySQL no está disponible, no tumbamos el cerebro: solo avisamos.
            logger.warning(f"No pude crear/verificar las tablas bb_*: {e}")

    # ─── LOGIN ────────────────────────────────────────────
    def login(self, force_manual=False):
        logger.info("Iniciando sesión en Blackboard/MiCibertec...")
        if not USER or not PASS:
            raise RuntimeError("Faltan USER/PASS en el archivo .env o las variables de entorno.")
        self._launch_browser()
        if not force_manual and os.path.exists(self.storage_state_path):
            self.context = self.browser.new_context(storage_state=self.storage_state_path)
            self.page = self.context.new_page()
            try:
                self.page.goto(BLACKBOARD_LOGIN, wait_until="domcontentloaded", timeout=15000)
                if "login.microsoftonline.com" not in self.page.url:
                    logger.info("Sesión reutilizada correctamente.")
                    return True
            except Exception:
                logger.warning("La sesión guardada ha caducado, forzando login manual.")
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None
                self.page = None

        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.goto(BLACKBOARD_LOGIN, wait_until="domcontentloaded", timeout=30000)

        try:
            self.page.wait_for_selector(SELECTORS["cookie_accept"], timeout=5000)
            self.page.click(SELECTORS["cookie_accept"])
        except TimeoutError:
            pass

        self.page.click(SELECTORS["login_btn"])
        self.page.wait_for_url("**/login.microsoftonline.com/**", timeout=20000)
        self.page.fill(SELECTORS["email_input"], USER)
        self.page.click(SELECTORS["email_next"])
        self.page.wait_for_selector(SELECTORS["pass_input"], timeout=15000)
        self.page.fill(SELECTORS["pass_input"], PASS)
        self.page.click(SELECTORS["pass_login"])

        try:
            self.page.wait_for_selector(SELECTORS["mfa_sms"], timeout=10000)
            self.page.click(SELECTORS["mfa_sms"])
            self.page.wait_for_selector("#idSIButton9", state="visible", timeout=5000)
            self.page.click("#idSIButton9")
        except TimeoutError:
            pass

        try:
            self.page.wait_for_selector(SELECTORS["mfa_code_input"], timeout=15000)
            code = input("Introduce el código recibido (SMS): ").strip()
            self.page.fill(SELECTORS["mfa_code_input"], code)
            self.page.click(SELECTORS["mfa_submit"])
            self.page.wait_for_selector(SELECTORS["mfa_code_input"], state="hidden", timeout=15000)
        except TimeoutError:
            pass

        try:
            self.page.wait_for_selector("#KmsiDescription", timeout=8000)
            self.page.click(SELECTORS["kmsi_yes"])
        except TimeoutError:
            pass

        self.page.wait_for_url("**/ultra/institution-page**", timeout=30000)
        self.page.wait_for_timeout(5000)  # Espera suficiente para el dashboard
        logger.info("Autenticación completada.")
        self.context.storage_state(path=self.storage_state_path)
        logger.info(f"Cookies guardadas en {self.storage_state_path}")
        return True

    def _launch_browser(self):
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

    def close(self):
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

    def fetch_all_data(self):
        self.login()
        try:
            self._fetch_blackboard_messages()
            self._fetch_micibertec_all()
            logger.info("Datos extraídos y guardados exitosamente.")
        finally:
            self.close()

    def _fetch_blackboard_messages(self):
        logger.info("Extrayendo mensajes de Blackboard...")
        self.page.goto(BLACKBOARD_MESSAGES, wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_load_state("networkidle", timeout=30000)

        # Bucle de espera activa
        cursos = []
        for _ in range(15):
            cursos = self.page.query_selector_all("[data-course-id]")
            if cursos:
                break
            self.page.wait_for_timeout(2000)

        if not cursos:
            logger.warning("No se encontraron cursos en la página de mensajes.")
            return

        total_cursos = len(cursos)
        logger.info(f"Cursos con mensajes: {total_cursos}")
        self.db.execute('DELETE FROM bb_messages')

        for idx in range(total_cursos):
            # Volver a la lista de mensajes (excepto primera vez)
            if idx > 0:
                self.page.goto(BLACKBOARD_MESSAGES, wait_until="domcontentloaded", timeout=30000)
                # Reobtener cursos después de volver
                cursos = []
                for _ in range(15):
                    cursos = self.page.query_selector_all("[data-course-id]")
                    if cursos:
                        break
                    self.page.wait_for_timeout(2000)
                if not cursos:
                    logger.warning("No se pudieron recargar los cursos.")
                    break

            curso = cursos[idx]
            course_id = curso.get_attribute("data-course-id") or ""
            nombre_curso = ""
            titulo_elem = curso.query_selector(".title a, .content-title")
            if titulo_elem:
                # Limpiar saltos de línea y badges
                nombre_curso = titulo_elem.inner_text().strip().split('\n')[0].strip()
            else:
                nombre_curso = course_id

            logger.info(f"[{idx+1}/{total_cursos}] Abriendo mensajes de: {nombre_curso}")

            click_target = curso.query_selector(".messages-header") or curso
            click_target.click()
            self.page.wait_for_timeout(3000)

            mensajes = []
            for _ in range(10):
                mensajes = self.page.query_selector_all("li.message-card")
                if mensajes:
                    break
                self.page.wait_for_timeout(1000)

            if not mensajes:
                logger.info(f"Sin mensajes en {nombre_curso}")
                continue

            for msg in mensajes:
                remitente = ""
                fecha = ""
                destinatarios = ""
                cuerpo = ""
                unread = 1 if "unread" in msg.get_attribute("class") else 0

                r_elem = msg.query_selector("bb-ui-username bdi")
                if r_elem:
                    remitente = r_elem.inner_text().strip()
                f_elem = msg.query_selector(".timestamp bdi, .js-duration-ago")
                if f_elem:
                    fecha = f_elem.inner_text().strip()
                d_elem = msg.query_selector(".recipients bb-usernames, .recipients bb-translate")
                if d_elem:
                    destinatarios = d_elem.inner_text().strip()
                c_elem = msg.query_selector(".latest-message .ellipse, .message-body")
                if c_elem:
                    cuerpo = c_elem.inner_text().strip()

                self.db.execute('''
                    INSERT INTO bb_messages (course_id, course_name, remitente, fecha, destinatarios, cuerpo, unread, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (course_id, nombre_curso, remitente, fecha, destinatarios, cuerpo, unread, datetime.now()))

        logger.info(f"Mensajes extraídos: {total_cursos} cursos procesados.")

    # ─── MICIBERTEC ───────────────────────────────────────
    def _acceder_a_micibertec(self):
        self.page.goto("https://estudiante.cibertec.edu.pe/", wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(2000)

        # Si la barra lateral ya está visible, sesión activa
        if self.page.query_selector(".lau-core-sidebar__desktop"):
            logger.info("Barra lateral ya visible. Sesión activa.")
            return True

        logger.info("Buscando botón 'Ingresa al portal del estudiante'...")
        try:
            self.page.wait_for_selector(
                "button[aria-label='Abrir portal de login de la Intranet Cibertec en una nueva ventana']",
                timeout=10000
            )
            self.page.click("button[aria-label='Abrir portal de login de la Intranet Cibertec en una nueva ventana']")
        except TimeoutError:
            logger.warning("No se encontró el botón con aria-label. Intentando con texto...")
            try:
                self.page.click("button:has-text('Ingresa al portal del estudiante')")
            except:
                logger.error("No se pudo hacer clic en ningún botón de login.")
                return False

        # Esperar a que la barra lateral aparezca (sin esperar URL concreta)
        for intento in range(6):  # 6 intentos de 5s = 30s máximo
            if self.page.query_selector(".lau-core-sidebar__desktop"):
                logger.info("Barra lateral detectada tras el login.")
                self.page.wait_for_timeout(2000)
                return True
            logger.info(f"Esperando barra lateral (intento {intento+1}/6)...")
            self.page.wait_for_timeout(5000)

        # Si no apareció, intentar una recarga y reintento
        logger.warning("Barra lateral no apareció. Recargando e intentando de nuevo...")
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_timeout(5000)
        if self.page.query_selector(".lau-core-sidebar__desktop"):
            logger.info("Barra lateral detectada tras recarga.")
            return True

        logger.warning("No se pudo acceder a MiCibertec tras múltiples intentos.")
        return False

    def _fetch_micibertec_all(self):
        if not self._acceder_a_micibertec():
            return
        self.page.goto("https://estudiante.cibertec.edu.pe/cursos", wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(5000)
        cursos = []
        enlaces = self.page.query_selector_all("a[href*='/cursos/detail?course=']")
        for enlace in enlaces:
            nombre_elem = enlace.query_selector("span[id^='card']")
            if not nombre_elem:
                continue
            course_name = nombre_elem.inner_text().strip()
            href = enlace.get_attribute("href")
            cursos.append((course_name, href))
        if not cursos:
            logger.warning("No se encontraron enlaces a detalle de curso en /cursos")
            return

        # Limpiar tablas antes de insertar nuevos datos
        self.db.execute('DELETE FROM bb_grades')
        self.db.execute('DELETE FROM bb_schedules')
        self.db.execute('DELETE FROM bb_courses')
        # Catálogo de cursos del ciclo (antes «mis cursos» no tenía fuente)
        for i, (course_name, _href) in enumerate(cursos):
            self.db.execute(
                'INSERT INTO bb_courses (id, name, last_updated) VALUES (?, ?, ?)',
                (f"c{i:02d}", course_name, datetime.now()))

        for course_name, href in cursos:
            logger.info(f"Navegando a detalle de {course_name}: {href}")
            self.page.goto(f"https://estudiante.cibertec.edu.pe{href}", wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(5000)

            # --- HORARIOS ---
            # La tabla de horarios tiene columnas "Fecha", "Hora", "Estado"
            tabla_horarios = self.page.query_selector(
                'table:has(th:has-text("Fecha")):has(th:has-text("Hora"))'
            )
            if tabla_horarios:
                filas = tabla_horarios.query_selector_all('tbody tr') or tabla_horarios.query_selector_all('tr')
                # Saltar la fila de encabezado
                for fila in filas[1:]:
                    celdas = fila.query_selector_all('td, th')
                    if len(celdas) < 3:
                        continue
                    fecha_hora = celdas[0].inner_text().strip()  # Ej: "Viernes 22/05"
                    hora_rango = celdas[1].inner_text().strip()  # Ej: "07:00 PM - 08:29 PM"
                    estado = celdas[2].inner_text().strip()

                    # Dividir día y fecha
                    partes_fecha = fecha_hora.split()
                    dia_semana = partes_fecha[0] if partes_fecha else ""
                    fecha = partes_fecha[1] if len(partes_fecha) > 1 else ""

                    # Dividir hora inicio y fin
                    horas = hora_rango.split(" - ")
                    start_time = horas[0].strip() if len(horas) > 0 else ""
                    end_time = horas[1].strip() if len(horas) > 1 else ""

                    self.db.execute('''
                        INSERT INTO bb_schedules (course_name, schedule_date, day_of_week, start_time, end_time, classroom, status, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (course_name, fecha, dia_semana, start_time, end_time, "", estado, datetime.now()))
                logger.info(f"Horarios extraídos para {course_name}")
            else:
                # Fallback: buscar filas que cumplan con el patrón de horario
                dias_semana = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
                filas = self.page.query_selector_all("tr, div.flex")
                for fila in filas:
                    celdas = fila.query_selector_all("td, span, div")
                    textos = [c.inner_text().strip() for c in celdas if c.inner_text().strip()]
                    if len(textos) < 2:
                        continue
                    primera = textos[0].split('\n')[0].strip()
                    if not any(primera.startswith(d) for d in dias_semana):
                        continue
                    segunda = textos[1].split('\n')[0].strip()
                    if " - " not in segunda:
                        continue

                    dia_semana = primera.split()[0]
                    fecha = primera.split()[1] if len(primera.split()) > 1 else ""
                    horas = segunda.split(" - ")
                    start_time = horas[0].strip()
                    end_time = horas[1].strip() if len(horas) > 1 else ""
                    estado = textos[2].split('\n')[0].strip() if len(textos) > 2 else ""

                    self.db.execute('''
                        INSERT INTO bb_schedules (course_name, schedule_date, day_of_week, start_time, end_time, classroom, status, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (course_name, fecha, dia_semana, start_time, end_time, "", estado, datetime.now()))
                logger.info(f"Horarios extraídos (método alternativo) para {course_name}")

            # --- EVALUACIONES (CORREGIDO) ---
            # Buscar la tabla de notas con encabezados "Tipo", "Evaluación", "Peso", "Nota"
            tabla_notas = self.page.query_selector(
                'table:has(th:has-text("Tipo")):has(th:has-text("Evaluación"))'
            )
            if not tabla_notas:
                # Alternativa: buscar tabla que contenga una celda con "T1"
                tabla_notas = self.page.query_selector('table:has(td:text-is("T1"))')

            if tabla_notas:
                # Obtener filas (tbody o tr directamente)
                filas = tabla_notas.query_selector_all('tbody tr')
                if not filas:
                    filas = tabla_notas.query_selector_all('tr')
                for fila in filas:
                    celdas = fila.query_selector_all('td, th')
                    if len(celdas) < 4:
                        continue
                    tipo = celdas[0].inner_text().strip()
                    # Solo procesar tipos de evaluación conocidos
                    if tipo not in ("T1", "T2", "EF", "RE"):
                        continue
                    nombre = celdas[1].inner_text().strip()
                    peso_str = celdas[2].inner_text().strip()
                    nota_str = celdas[3].inner_text().strip()

                    # Parsear numéricos
                    try:
                        peso = float(peso_str.replace('%', '').replace(',', '.'))
                    except ValueError:
                        peso = 0.0
                    try:
                        nota = float(nota_str)
                    except ValueError:
                        nota = 0.0

                    self.db.execute('''
                        INSERT INTO bb_grades (course_name, evaluation_type, evaluation_name, weight, grade, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (course_name, tipo, nombre, peso, nota, datetime.now()))
                logger.info(f"Evaluaciones extraídas correctamente para {course_name}")
            else:
                logger.warning(f"No se encontró la tabla de notas para {course_name}")

        logger.info("Horarios y evaluaciones extraídos correctamente.")

    # ─── CONSULTAS ────────────────────────────────────────
    def get_messages(self, course_name=None):
        if course_name:
            rows = self.db.query(
                "SELECT course_name, remitente, fecha, cuerpo, unread FROM bb_messages WHERE course_name LIKE ?",
                (f"%{course_name}%",),
            )
        else:
            rows = self.db.query(
                "SELECT course_name, remitente, fecha, cuerpo, unread FROM bb_messages"
            )
        return [
            {"course": r[0], "remitente": r[1], "fecha": r[2], "cuerpo": r[3], "unread": r[4]}
            for r in rows
        ]

    def get_schedules(self, course_name=None):
        if course_name:
            rows = self.db.query(
                "SELECT course_name, schedule_date, day_of_week, start_time, end_time, classroom, status FROM bb_schedules WHERE course_name LIKE ?",
                (f"%{course_name}%",),
            )
        else:
            rows = self.db.query(
                "SELECT course_name, schedule_date, day_of_week, start_time, end_time, classroom, status FROM bb_schedules"
            )
        return [
            {"course": r[0], "date": r[1], "day": r[2], "start": r[3], "end": r[4], "classroom": r[5], "status": r[6]}
            for r in rows
        ]

    def get_grades(self, course_name=None):
        if course_name:
            rows = self.db.query(
                "SELECT course_name, evaluation_type, evaluation_name, weight, grade FROM bb_grades WHERE course_name LIKE ?",
                (f"%{course_name}%",),
            )
        else:
            rows = self.db.query(
                "SELECT course_name, evaluation_type, evaluation_name, weight, grade FROM bb_grades"
            )
        return [
            {"course": r[0], "type": r[1], "name": r[2], "weight": r[3], "grade": r[4]}
            for r in rows
            
        ]
         