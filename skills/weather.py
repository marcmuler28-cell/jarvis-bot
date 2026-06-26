import requests
import time

class WeatherSkill:
    """
    Obtiene el clima actual y pronóstico usando wttr.in (con fallback a Open-Meteo).
    """
    def __init__(self, city="Lima", lang="es"):
        self.city = city
        self.lang = lang
        # Coordenadas por defecto para Lima, Perú
        self.lat = -12.06
        self.lon = -77.03

    def _fetch_wttr(self, endpoint, retries=2, timeout=20):
        """Intenta obtener datos de wttr.in con reintentos."""
        url = f"https://wttr.in/{self.city}?{endpoint}&lang={self.lang}"
        last_exc = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp.text.strip()
            except requests.exceptions.Timeout as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(2)  # esperar un poco antes de reintentar
                    continue
            except requests.exceptions.RequestException as e:
                last_exc = e
                # Si es un error 5xx, reintentamos
                if getattr(e.response, 'status_code', 500) >= 500 and attempt < retries:
                    time.sleep(2)
                    continue
                break
        raise last_exc if last_exc else Exception("Error desconocido en wttr.in")

    def _fetch_openmeteo(self):
        """Obtiene clima actual desde Open-Meteo (fallback)."""
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={self.lat}&longitude={self.lon}"
            f"&current_weather=true"
        )
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            cw = data.get("current_weather", {})
            temp = cw.get("temperature")
            code = cw.get("weathercode")
            # Mapeo básico de códigos WMO a descripción
            wmo_desc = {
                0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado",
                3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
                51: "Llovizna ligera", 53: "Llovizna moderada", 55: "Llovizna densa",
                61: "Lluvia ligera", 63: "Lluvia moderada", 65: "Lluvia intensa",
                71: "Nieve ligera", 73: "Nieve moderada", 75: "Nieve intensa",
                80: "Chubascos ligeros", 81: "Chubascos moderados", 82: "Chubascos fuertes",
                95: "Tormenta", 96: "Tormenta con granizo ligero", 99: "Tormenta con granizo intenso"
            }
            desc = wmo_desc.get(code, f"Código {code}")
            # Emulamos el formato de wttr.in: "Ciudad: +temp°C, descripción"
            return f"{self.city}: +{temp}°C, {desc}"
        except Exception as e:
            return f"No se pudo obtener el clima (fallback): {e}"

    def _fetch(self, endpoint):
        """Intenta wttr.in y, si falla, usa Open-Meteo como plan B."""
        try:
            return self._fetch_wttr(endpoint)
        except Exception as e:
            # Si es un error irrecuperable, usar fallback
            return self._fetch_openmeteo()

    def current(self):
        """Clima actual en formato compacto."""
        return self._fetch("format=3")

    def forecast_today(self):
        """Pronóstico para el día de hoy (resumido)."""
        return self._fetch("format=2")

    def full_report(self):
        """Texto combinado para el briefing."""
        actual = self.current()
        pronostico = self.forecast_today()
        return f"{actual}. Pronóstico: {pronostico}"

    def execute(self, command):
        """Interfaz antigua para comandos de voz."""
        return self.full_report()