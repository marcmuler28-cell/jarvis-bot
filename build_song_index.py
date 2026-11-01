#!/usr/bin/env python3
"""
Construye un índice semántico de canciones en ChromaDB usando búsquedas públicas.
No requiere token de Spotify. Usa spotapi y Ollama (nomic-embed-text).
"""
import os
import chromadb
from chromadb.utils import embedding_functions
# [PATCH_VOICE_GLOBAL]
try:
    from spotapi.public import Public
except Exception:
    pass
import time

COLLECTION_NAME = "spotify_songs"
OLLAMA_MODEL = "nomic-embed-text"

# Términos de búsqueda para recopilar canciones populares variadas
SEARCH_QUERIES = [
    "top hits", "pop", "rock", "hip hop", "reggaeton", "sertanejo",
    "brasil", "portuguese", "funk", "k-pop",
    "electronic", "r&b", "dance", "romantic", "sad", "happy",
    "party", "chill", "workout", "classical",
    "funk brasileiro",
    "montagem",
    "coração",
    "Cumbia",
    "Peru",
    "direção",
    "el egoismo",
    "funk 2025",
    "funk 2026",
    "funk bh",
    "mc's",
]

def get_tracks_from_search(query, limit=10):
    """Obtiene canciones de una búsqueda pública usando spotapi."""
    tracks = []
    try:
        for page in Public.song_search(query):
            if not page:
                continue
            # Asegurar que page sea iterable (a veces la API puede devolver un dict suelto)
            items = page if isinstance(page, list) else [page]
            for item in items:
                if not isinstance(item, dict):
                    continue   # ignora elementos que no son dict (ej. strings)
                wrapper = item.get("item") if isinstance(item, dict) else None
                if not isinstance(wrapper, dict):
                    continue
                data = wrapper.get("data") if isinstance(wrapper, dict) else None
                if not isinstance(data, dict):
                    continue
                uri = data.get("uri")
                name = data.get("name")
                artists = [a.get("name", "") for a in (data.get("artists", {}).get("items", []))]
                artist = ", ".join(artists) if artists else "Unknown"
                if uri and name and uri.startswith("spotify:track:"):
                    tracks.append({
                        "uri": uri,
                        "name": name,
                        "artist": artist
                    })
                    if len(tracks) >= limit:
                        break
            break  # solo primera página para cada búsqueda
    except Exception as e:
        print(f"Error en búsqueda '{query}': {e}")
    return tracks

def build_index():
    """Construye el índice en ChromaDB."""
    client = chromadb.PersistentClient(path=os.path.expanduser("~/.jarvis/chroma_songs"))

    # Eliminar colección anterior si existe para reindexar limpio
    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass

    embedding_fn = embedding_functions.OllamaEmbeddingFunction(
        model_name=OLLAMA_MODEL,
        url="http://localhost:11434/api/embeddings"
    )

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "Índice de canciones de Spotify (búsqueda pública)"}
    )

    all_tracks = []
    for q in SEARCH_QUERIES:
        print(f"Buscando '{q}'...")
        tracks = get_tracks_from_search(q, limit=10)
        all_tracks.extend(tracks)
        time.sleep(1)  # ser amable con la API pública

    # Eliminar duplicados (misma URI)
    unique = {}
    for t in all_tracks:
        unique[t['uri']] = t
    tracks = list(unique.values())
    print(f"Total canciones únicas: {len(tracks)}")

    if not tracks:
        print("No se obtuvo ninguna canción. Verifica la conexión a Internet o la API.")
        return

    ids = []
    documents = []
    metadatas = []
    for i, t in enumerate(tracks):
        ids.append(str(i))
        documents.append(f"{t['name']} - {t['artist']}")
        metadatas.append({"uri": t['uri'], "name": t['name'], "artist": t['artist']})

    batch_size = 100
    for i in range(0, len(ids), batch_size):
        end = i + batch_size
        collection.add(
            ids=ids[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end]
        )
        print(f"Progreso: {end}/{len(ids)}")

    print("Índice construido con éxito.")

if __name__ == "__main__":
    build_index()