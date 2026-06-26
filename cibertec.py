import os
import sys
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError, sync_playwright

# Cargar .env desde la raíz del proyecto JarvisBot de forma explícita.
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)
else:
    load_dotenv(override=True)

USER = os.getenv("USER")
PASS = os.getenv("PASS")
OPERA_PATH = os.getenv("OPERA_PATH")

EMAIL_INPUT = "#i0116"
EMAIL_NEXT_BTN = "#idSIButton9"
PASS_INPUT = "#i0118"
PASS_LOGIN_BTN = "#idSIButton9"
MFA_CODE_INPUT = "#idTxtBx_SAOTCC_OTC"
MFA_SUBMIT_BTN = "#idSubmit_SAOTCC_Continue"
KMSI_YES_BTN = "#idSIButton9"
COOKIE_ACCEPT_BTN = "#agree_button"
MFA_METHOD_SMS = 'div[data-value="OneWaySMS"]'


def extraer_contenido_curso_completo(page):
    """Extrae el árbol completo de contenido del curso desde Blackboard."""
    def procesar_items(contenedor_id=None):
        if contenedor_id:
            items = page.query_selector_all(f"#{contenedor_id} div.content-list-item")
        else:
            items = page.query_selector_all(
                "div.root.content-list-item:not(div.content-list-item div.content-list-item)"
            )
        resultados = []
        for item in items:
            icon = item.query_selector("[role='img']")
            tipo = icon.get_attribute("aria-label") if icon else ""

            titulo_elem = item.query_selector("[class*='contentItemTitle']")
            titulo = titulo_elem.inner_text().strip() if titulo_elem else ""
            enlace = ""
            if titulo_elem:
                es_enlace = titulo_elem.evaluate("el => el.tagName.toLowerCase() === 'a'")
                if es_enlace:
                    enlace = titulo_elem.get_attribute("href") or ""

            hijos = []
            if tipo in ("Módulo de aprendizaje", "Carpeta"):
                boton = item.query_selector("button[aria-expanded]")
                if boton:
                    expandido = boton.get_attribute("aria-expanded") == "true"
                    if not expandido:
                        boton.click()
                        page.wait_for_timeout(800)

                contenedor = None
                if tipo == "Módulo de aprendizaje":
                    contenedor = item.query_selector("[id*='learning-module-contents']")
                else:
                    contenedor = item.query_selector("[id*='folder-contents']")

                if contenedor:
                    id_contenedor = contenedor.get_attribute("id")
                    if id_contenedor:
                        hijos = procesar_items(id_contenedor)

            resultados.append({
                "tipo": tipo,
                "titulo": titulo,
                "enlace": enlace,
                "hijos": hijos,
            })
        return resultados

    return procesar_items()


def imprimir_arbol(elementos, nivel=0):
    prefijo = "  " * nivel
    for e in elementos:
        icono = (
            "📄" if "Documento" in e["tipo"] else
            "🔗" if e["tipo"] == "Enlace" else
            "📁" if "Carpeta" in e["tipo"] else
            "⋯"
        )
        print(f"{prefijo}{icono} [{e['tipo']}] {e['titulo']}")
        if e["enlace"]:
            print(f"{prefijo}   → {e['enlace']}")
        if e["hijos"]:
            imprimir_arbol(e["hijos"], nivel + 1)


def run():
    if not USER or not PASS:
        raise RuntimeError(
            "Faltan USER/PASS en el archivo .env de JarvisBot. "
            "Crea un .env en la raíz del proyecto con USER, PASS y OPERA_PATH."
        )

    with sync_playwright() as p:
        if OPERA_PATH and os.path.exists(OPERA_PATH):
            browser = p.chromium.launch(headless=False, executable_path=OPERA_PATH,
                                        args=["--disable-blink-features=AutomationControlled"])
        else:
            browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Navegando a Blackboard...")
        page.goto("https://cibertec.blackboard.com/webapps/login/")
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_selector(COOKIE_ACCEPT_BTN, timeout=10000)
            page.click(COOKIE_ACCEPT_BTN)
            page.wait_for_selector(".lb-overlay", state="hidden", timeout=10000)
        except TimeoutError:
            pass

        print("Clic en 'Estudiante | Docente'...")
        page.click("#btn-login")
        page.wait_for_url("**/login.microsoftonline.com/**", timeout=20000)

        print("Ingresando correo...")
        page.fill(EMAIL_INPUT, USER)
        page.click(EMAIL_NEXT_BTN)
        page.wait_for_selector(PASS_INPUT, timeout=15000)
        page.fill(PASS_INPUT, PASS)
        page.click(PASS_LOGIN_BTN)

        try:
            page.wait_for_selector(MFA_METHOD_SMS, timeout=10000)
            page.click(MFA_METHOD_SMS)
            page.wait_for_selector("#idSIButton9", state="visible", timeout=5000)
            page.click("#idSIButton9")
        except TimeoutError:
            pass

        try:
            page.wait_for_selector(MFA_CODE_INPUT, timeout=15000)
            code = input("Introduce el código recibido (SMS): ").strip()
            page.fill(MFA_CODE_INPUT, code)
            page.click(MFA_SUBMIT_BTN)
            page.wait_for_selector(MFA_CODE_INPUT, state="hidden", timeout=15000)
        except TimeoutError:
            pass

        try:
            page.wait_for_selector("#KmsiDescription", timeout=8000)
            page.click(KMSI_YES_BTN)
        except TimeoutError:
            pass

        print("Esperando dashboard...")
        page.wait_for_url("**/ultra/institution-page**", timeout=30000)
        page.wait_for_load_state("networkidle")
        print("Autenticación completada.")

        print("Navegando a lista de cursos...")
        page.goto("https://cibertec.blackboard.com/ultra/course")
        try:
            page.wait_for_selector("article.element-card", timeout=20000)
        except TimeoutError:
            print("No se encontraron cursos.")
            browser.close()
            return
        page.wait_for_timeout(4000)
        cursos = page.query_selector_all("article.course-element-card h4.js-course-title-element")
        print(f"Cursos encontrados: {len(cursos)}")
        for c in cursos:
            print(f"- {c.inner_text().strip()}")

        primer_curso = page.query_selector("article.course-element-card")
        if not primer_curso:
            print("No se pudo seleccionar el primer curso.")
            browser.close()
            return

        print("Entrando al primer curso...")
        primer_curso.click()
        page.wait_for_url("**/ultra/courses/**", timeout=15000)
        page.wait_for_load_state("networkidle")
        print("Dentro del curso.")

        contenido = extraer_contenido_curso_completo(page)
        print("\n📚 Árbol de contenido del curso:")
        imprimir_arbol(contenido)

        browser.close()


if __name__ == "__main__":
    run()
