import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

# Cargar variables de entorno
load_dotenv(override=True)
# Credenciales: JARVIS_BB_USER/JARVIS_BB_PASS primero (getenv("USER") en Linux
# devuelve el usuario del sistema, p.ej. "marc", no tu correo institucional).
_USER_LEGACY = os.getenv("USER") or ""
USER = os.getenv("JARVIS_BB_USER") or (_USER_LEGACY if "@" in _USER_LEGACY else None)
PASS = os.getenv("JARVIS_BB_PASS") or os.getenv("PASS")

STORAGE_STATE = "blackboard_state.json"  # Ahora guardará las cookies de ambos dominios

# Chromium del SISTEMA (evita descargar el navegador de playwright, ~170 MB).
# Si no hay ninguno, Playwright usará el suyo (requiere: python -m playwright install chromium).
_CHROME = (os.environ.get("JARVIS_CHROME_PATH")
           or next((p for p in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                                "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome")
                    if os.path.exists(p)), None))

def main():
    print("=== LOGIN UNIFICADO BLACKBOARD + MICIBERTEC ===")
    print(f"Usuario: {USER}")
    print("Se abrirá Chromium headless. Ten tu teléfono a mano para el código SMS.\n")

    if not USER or not PASS:
        print("ERROR: Faltan JARVIS_BB_USER / JARVIS_BB_PASS en el archivo .env")
        return

    with sync_playwright() as p:
        # Lanzar navegador
        browser = p.chromium.launch(
            headless=True,
            executable_path=_CHROME,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            # ==========================================
            # 1. LOGIN EN BLACKBOARD
            # ==========================================
            print("1. Navegando a Blackboard...")
            page.goto("https://cibertec.blackboard.com/webapps/login/", wait_until="networkidle", timeout=30000)

            # Aceptar cookies si aparece
            try:
                page.wait_for_selector("#agree_button", timeout=5000)
                page.click("#agree_button")
            except TimeoutError:
                pass

            # Hacer clic en "Estudiante | Docente"
            print("2. Clic en Estudiante | Docente...")
            page.click("#btn-login")
            page.wait_for_url("**/login.microsoftonline.com/**", timeout=20000)

            # Ingresar correo
            print("3. Ingresando correo...")
            page.fill("#i0116", USER)
            page.click("#idSIButton9")
            page.wait_for_selector("#i0118", timeout=15000)

            # Ingresar contraseña
            print("4. Ingresando contraseña...")
            page.fill("#i0118", PASS)
            page.click("#idSIButton9")

            # MFA: elegir SMS si es posible
            try:
                page.wait_for_selector('div[data-value="OneWaySMS"]', timeout=10000)
                page.click('div[data-value="OneWaySMS"]')
                page.wait_for_selector("#idSIButton9", state="visible", timeout=5000)
                page.click("#idSIButton9")
            except TimeoutError:
                pass

            # Pedir código SMS
            try:
                page.wait_for_selector("#idTxtBx_SAOTCC_OTC", timeout=15000)
                code = input("5. Introduce el código SMS recibido: ").strip()
                page.fill("#idTxtBx_SAOTCC_OTC", code)
                page.click("#idSubmit_SAOTCC_Continue")
                page.wait_for_selector("#idTxtBx_SAOTCC_OTC", state="hidden", timeout=15000)
                print("   Código enviado.")
            except TimeoutError:
                pass

            # Mantener sesión iniciada
            try:
                page.wait_for_selector("#KmsiDescription", timeout=8000)
                page.click("#idSIButton9")
            except TimeoutError:
                pass

            # Esperar dashboard de Blackboard
            print("6. Esperando dashboard de Blackboard...")
            page.wait_for_url("**/ultra/institution-page**", timeout=30000)
            page.wait_for_load_state("networkidle")
            print("   ✅ Login en Blackboard exitoso!")

            # ==========================================
            # 2. LOGIN EN MICIBERTEC (APROVECHANDO LA SESIÓN DE MICROSOFT)
            # ==========================================
            print("7. Navegando a MiCibertec...")
            page.goto("https://estudiante.cibertec.edu.pe/lideres-cibertec", wait_until="domcontentloaded", timeout=30000)

            # Aquí ocurre la redirección a Microsoft.
            # Como ya tenemos la sesión iniciada, debería redirigirnos automáticamente de vuelta a MiCibertec.
            # A veces se muestra un botón "Enviar" o similar para confirmar.
            try:
                # Esperar un posible botón de confirmación de Microsoft
                page.wait_for_selector("#idSIButton9", timeout=10000)
                page.click("#idSIButton9")
                print("   Confirmación automática de Microsoft...")
            except TimeoutError:
                pass
            
            # Esperar a que la URL sea la de MiCibertec
            try:
                page.wait_for_url("**/lideres-cibertec**", timeout=30000)
                print("   ✅ Login en MiCibertec exitoso!")
            except TimeoutError:
                print("   ⚠️ No se detectó la URL de MiCibertec. Revisa si el proceso de login requiere un paso manual adicional.")
                # Opcional: Puedes hacer una pausa aquí para ver qué pasó
                input("Presiona Enter para continuar...")

            # ==========================================
            # 3. GUARDAR ESTADO COMBINADO
            # ==========================================
            context.storage_state(path=STORAGE_STATE)
            print(f"\n8. Estado combinado guardado en {STORAGE_STATE}")
            print("   Ahora puedes ejecutar la extracción de datos sin problemas.")

        except Exception as e:
            print(f"\n❌ Error durante el proceso: {e}")
        finally:
            browser.close()

    print("\n=== LOGIN UNIFICADO COMPLETADO ===")

if __name__ == "__main__":
    main()
