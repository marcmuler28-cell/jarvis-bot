import os
import sys
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

# Cargar .env
load_dotenv(override=True)
USER = os.getenv("USER")
PASS = os.getenv("PASS")

STORAGE_STATE = "blackboard_state.json"

def main():
    print("=== PRUEBA DE LOGIN BLACKBOARD / MICIBERTEC ===")
    print(f"Usuario: {USER}")
    print("Se abrirá Chromium headless. Si prefieres verlo, cambia headless=False en el código.")
    print("Asegúrate de tener tu teléfono a mano para el código SMS.\n")

    with sync_playwright() as p:
        # Cambia headless=False si quieres ver el navegador
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context()
        page = context.new_page()

        # --- Paso 1: Ir a Blackboard ---
        print("1. Navegando a Blackboard...")
        page.goto("https://cibertec.blackboard.com/webapps/login/", wait_until="networkidle", timeout=30000)

        # Aceptar cookies si aparece
        try:
            page.wait_for_selector("#agree_button", timeout=5000)
            page.click("#agree_button")
        except TimeoutError:
            pass

        # Clic en "Estudiante | Docente"
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

        # Manejar MFA: elegir SMS si es posible
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

        # Esperar llegar al dashboard de Blackboard
        print("6. Esperando dashboard de Blackboard...")
        page.wait_for_url("**/ultra/institution-page**", timeout=30000)
        page.wait_for_load_state("networkidle")
        print("   ¡Autenticación completada en Blackboard!")

        # --- Paso 2: Verificar acceso a MiCibertec ---
        print("7. Navegando a MiCibertec...")
        page.goto("https://estudiante.cibertec.edu.pe/lideres-cibertec", wait_until="networkidle", timeout=20000)
        # Si redirige a Microsoft, esperar a que vuelva automáticamente
        if "login.microsoftonline.com" in page.url:
            print("   Redirigiendo automáticamente (usando sesión existente)...")
            page.wait_for_url("**/lideres-cibertec**", timeout=30000)
        print("   ¡Acceso exitoso a MiCibertec!")

        # --- Paso 3: Guardar estado de sesión ---
        context.storage_state(path=STORAGE_STATE)
        print(f"\n8. Cookies guardadas en {STORAGE_STATE}")
        print("   A partir de ahora, las futuras ejecuciones usarán esta sesión mientras no caduque.")

        browser.close()

    print("\n=== PRUEBA COMPLETADA CON ÉXITO ===")
    print("Puedes ejecutar ahora la extracción de datos con la skill Blackboard sin necesidad de nuevo login.")

if __name__ == "__main__":
    main()