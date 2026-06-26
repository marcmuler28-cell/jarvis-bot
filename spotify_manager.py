import subprocess
import time
import re
import os

from spotapi.public import Public
from fuzzywuzzy import fuzz

# ChromaDB para búsqueda semántica local
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# ========== CONFIGURACIÓN ==========
MARKET = "US"

# ========== LIMPIADOR MUSICAL INTERNO ==========
def _normalize_music_query(text):
    """Limpia una consulta musical para búsqueda."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(
        r'\b(reproduce|pon|poner|ponme|ponte|quiero escuchar|música de|la canción|el tema|la rola|el track|play|pon la)\b',
        '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    replacements = {
        'nait': 'night',
        'blaindin': 'blinding',
        'laikd': 'liked',
        'laikt': 'liked',
        'laik': 'like',
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text

# ========== BÚSQUEDA DE PLAYLISTS ==========
def search_playlist(query):
    """Busca una playlist por nombre (no implementado)."""
    return None

# ========== BÚSQUEDA DE CANCIONES ==========
def search_track(query):
    """Busca una canción por nombre y devuelve (nombre, uri) de la primera coincidencia."""
    try:
        for page in Public.song_search(query):
            if not page:
                continue
            for item in page:
                data = item.get("item", {}).get("data") if isinstance(item, dict) else None
                if not data:
                    continue
                uri = data.get("uri")
                name = data.get("name")
                if uri and name and uri.startswith("spotify:track:"):
                    return name, uri
    except Exception as e:
        print(f"Error en búsqueda de canción: {e}")
    return None

def search_track_fuzzy(query, threshold=70):
    """Busca una canción con fuzzy matching sobre los resultados de la API pública."""
    clean = _normalize_music_query(query)
    candidates = []
    try:
        for page in Public.song_search(clean):
            if not page:
                continue
            for item in page:
                data = item.get("item", {}).get("data") if isinstance(item, dict) else None
                if not data:
                    continue
                uri = data.get("uri")
                name = data.get("name")
                if uri and name and uri.startswith("spotify:track:"):
                    candidates.append((name, uri))
            break
    except Exception as e:
        print(f"Error en búsqueda difusa: {e}")
        return None

    if not candidates:
        return None

    best = max(candidates, key=lambda x: fuzz.token_sort_ratio(clean, x[0].lower()))
    best_score = fuzz.token_sort_ratio(clean, best[0].lower())

    if best_score >= threshold:
        return best
    else:
        return candidates[0]

def search_track_chromadb(query):
    """
    Busca la canción más cercana en el índice local de ChromaDB.
    Devuelve (nombre, uri) o None si no hay coincidencia suficiente.
    """
    if not CHROMADB_AVAILABLE:
        return None

    try:
        # Ruta persistente (relativa al directorio de trabajo del servicio)
        chroma_path = os.path.expanduser("~/.jarvis/chroma_songs")
        client = chromadb.PersistentClient(path=chroma_path)
        embedding_fn = embedding_functions.OllamaEmbeddingFunction(
            model_name="nomic-embed-text",
            url="http://localhost:11434/api/embeddings"
        )
        collection = client.get_collection("spotify_songs", embedding_function=embedding_fn)

        clean = _normalize_music_query(query)
        results = collection.query(query_texts=[clean], n_results=1)

        if results['ids'][0]:
            metadata = results['metadatas'][0][0]
            distance = results['distances'][0][0] if 'distances' in results else 0
            # Distancia: mientras más baja, más similar. Umbral ajustable.
            if distance < 0.6:
                return metadata['name'], metadata['uri']
    except Exception as e:
        print(f"Error en búsqueda ChromaDB: {e}")
    return None

# ========== REPRODUCCIÓN DE CANCIONES (sin mover el ratón) ==========
def play_track_uri(uri):
    """
    Reproduce una canción (track) sin mover el ratón.
    Solo abre la URI con kde-open5 y espera; si es necesario, intenta playerctl.
    """
    subprocess.run(["kde-open5", uri], check=False)
    time.sleep(2)
    try:
        subprocess.run(["playerctl", "--player=spotify", "play"],
                       capture_output=True, timeout=3)
    except:
        pass
    return f"Reproduciendo {uri}"

def play_track_by_name(name):
    """Busca y reproduce una canción por nombre (índice local + fuzzy)."""
    # 1. Intento con el índice semántico
    result = search_track_chromadb(name)
    if result:
        track_name, uri = result
        msg = play_track_uri(uri)
        return f"Reproduciendo '{track_name}' (índice local): {msg}"

    # 2. Fallback a búsqueda fuzzy normal
    result = search_track_fuzzy(name)
    if result is None:
        return f"No encontré la canción '{name}'."
    track_name, uri = result
    msg = play_track_uri(uri)
    return f"Reproduciendo '{track_name}': {msg}"

# ========== REPRODUCCIÓN DE COLECCIONES (clic necesario) ==========
def play_collection_uri(uri):
    """
    Abre una colección (playlist, Tus me gusta) y fuerza la reproducción
    haciendo clic en el botón ▶️ (coordenadas 480,460).
    """
    subprocess.run(["kde-open5", uri], check=False)
    time.sleep(2.5)
    subprocess.run(["xdotool", "mousemove", "480", "460", "click", "1"], check=False)
    return f"Reproduciendo {uri}"

def play_liked_songs():
    """Reproduce 'Tus me gusta' usando el clic forzado."""
    return play_collection_uri("spotify:user:spotify:collection")

def play_playlist_by_name(name):
    """Busca una playlist por nombre y la reproduce (con clic)."""
    result = search_playlist(name)
    if result is None:
        return f"No encontré la playlist '{name}'."
    playlist_name, uri = result
    return play_collection_uri(uri)

def open_playlists():
    """Abre la vista de playlists del usuario en la app de Spotify."""
    try:
        subprocess.Popen(
            ["xdg-open", "spotify:playlists"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return "Abriendo tus playlists en Spotify."
    except Exception as e:
        print(f"Error abriendo playlists: {e}")
        return "No se pudo abrir playlists."