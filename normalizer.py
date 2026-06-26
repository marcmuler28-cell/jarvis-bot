"""
normalizer.py - Normalizacion y fuzzy matching para comandos de voz.

Caracteristicas:
- Normalizador: elimina articulos, tildes, ruido de transcripcion
- Distancia Levenshtein: umbral 2 para errores de pronunciacion
- Fuzzy match de comandos contra lista de alias/conocidos
"""

import re
import unicodedata

# ──────────────────────────────────────────────
#  NORMALIZADOR
# ──────────────────────────────────────────────

# Articulos y palabras a eliminar al inicio/final
CORRECCIONES_VOZ = {
    "aparate": "apágate",
    "apara": "apaga",
    "apagarme": "apágame",
    "aparame": "apágame",
    # Añade más según veas en los logs
}

ARTICULOS = ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas "]
PREFIJOS_NOISE = ["por favor", "quiero que", "necesito que", "puedes", "podrias", "podrias", "podria ", "podrias "]

def quitar_tildes(texto: str) -> str:
    """Convierte 'cancion' -> 'cancion', 'ultimo' -> 'ultimo'"""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def normalizar(texto: str) -> str:
    """
    Normaliza un texto para matching:
    1. Quita tildes
    2. Minusculas
    3. Quita puntuacion
    4. Quita articulos al inicio
    5. Quita prefijos de cortesia
    6. Quita espacios extra
    """
    t = texto.lower().strip()
    t = quitar_tildes(t)
    # Quitar puntuacion basica (deja letras, numeros y espacios)
    t = re.sub(r'[^\w\s]', ' ', t)
    # Quitar espacios multiples
    t = re.sub(r'\s+', ' ', t).strip()
        # Aplicar correcciones de voz conocidas
    for mal, bien in CORRECCIONES_VOZ.items():
        if mal in t:
            t = t.replace(mal, bien)
    # Quitar prefijos de cortesia
    for pref in PREFIJOS_NOISE:
        if t.startswith(pref):
            t = t[len(pref):].strip()
    # Quitar articulos al inicio
    for art in ARTICULOS:
        if t.startswith(art):
            t = t[len(art):].strip()
            break
    return t


def extraer_nombre_app(texto_original: str) -> str:
    """
    De un comando como "abre spotify" extrae "spotify".
    Tambien maneja "abre el navegador" -> "navegador"
    """
    t = normalizar(texto_original)
    # Quitar verbo "abre", "abrir", "pon", "poner", "reproduce", "reproducir"
    for verbo in ["abre ", "abrir ", "pon ", "poner ", "reproduce ", "reproducir ", 
                  "abrime ", "abrirme ", "ponme ", "ponerme ", 
                  "abras ", "abra ", "abrirme ", "abrime "]:
        if t.startswith(verbo):
            t = t[len(verbo):].strip()
            break
    # Quitar articulos nuevamente (por si "abre el spotify")
    for art in ARTICULOS:
        if t.startswith(art):
            t = t[len(art):].strip()
            break
    return t


# ──────────────────────────────────────────────
#  DISTANCIA LEVENSHTEIN
# ──────────────────────────────────────────────

def levenshtein(s1: str, s2: str) -> int:
    """
    Distancia de Levenshtein entre dos strings.
    Cuenta inserciones, eliminaciones y sustituciones.
    """
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Inserciones, eliminaciones, sustituciones
            insert = prev_row[j + 1] + 1
            delete = curr_row[j] + 1
            replace = prev_row[j] + (c1 != c2)
            curr_row.append(min(insert, delete, replace))
        prev_row = curr_row
    
    return prev_row[-1]


def fuzzy_match(texto: str, conocido: str, umbral: int = 2) -> bool:
    """
    Retorna True si 'texto' coincide con 'conocido' 
    dentro del umbral de distancia Levenshtein.
    """
    return levenshtein(texto, conocido) <= umbral


def buscar_mejor_coincidencia(texto: str, lista_conocidos: list, umbral: int = 2):
    """
    Busca el elemento mas cercano en 'lista_conocidos' usando Levenshtein.
    Retorna (mejor_coincidencia, distancia) o (None, None) si no encuentra.
    """
    mejor = None
    menor_dist = float('inf')
    for conocido in lista_conocidos:
        dist = levenshtein(texto, conocido)
        if dist < menor_dist:
            menor_dist = dist
            mejor = conocido
    if mejor and menor_dist <= umbral:
        return mejor, menor_dist
    return None, None


# ──────────────────────────────────────────────
#  FUNCION COMBINADA: normalizar + fuzzy match
# ──────────────────────────────────────────────

def match_comando(texto_original: str, comando_conocido: str, umbral: int = 2) -> bool:
    """
    Normaliza ambos textos y aplica fuzzy match.
    Util para comparar "reprodusir spotifi" con "reproducir spotify".
    """
    a = normalizar(texto_original)
    b = normalizar(comando_conocido)
    return fuzzy_match(a, b, umbral)


def corregir_nombre_app(texto_original: str, alias_dict: dict, umbral: int = 2) -> str:
    """
    Dado un nombre de app (ej: "spotifi", "spotufy", "calcudadora"),
    busca el alias mas cercano en APP_ALIASES usando Levenshtein.
    Retorna el valor real (ej: "spotify") o el original si no encuentra.
    """
    nombre = extraer_nombre_app(texto_original)
    conocido, dist = buscar_mejor_coincidencia(nombre, list(alias_dict.keys()), umbral)
    if conocido:
        return conocido
    return nombre


# ──────────────────────────────────────────────
#  EJEMPLO DE USO (descomentar para probar)
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # Pruebas
    print("=== NORMALIZADOR ===")
    tests = [
        "Abreme Spotify por favor",
        "Abre el bloc de notas",
        "REPRODUCE CANCION",
        "Quiero que abras la calculadora",
        "Pon musica relajante",
        "Abre el explorador de archivos",
    ]
    for t in tests:
        print(f"  '{t}' -> '{normalizar(t)}'")
    
    print("\n=== EXTRAER NOMBRE APP ===")
    for t in tests:
        print(f"  '{t}' -> '{extraer_nombre_app(t)}'")
    
    print("\n=== FUZZY MATCH (umbral=2) ===")
    ALIASES_PRUEBA = ["spotify", "reproducir", "calculadora", "navegador", "explorador", "terminal"]
    tests2 = ["spotifi", "abre spotify", "reprodusir", "calcudadora", "navegador", "explolador", "terminal"]
    for t in tests2:
        ok, dist = buscar_mejor_coincidencia(t, ALIASES_PRUEBA)
        print(f"  '{t}' -> mejor: {ok} (dist: {dist})")
