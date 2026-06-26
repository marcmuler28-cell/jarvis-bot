import chromadb
from chromadb.utils import embedding_functions
import subprocess
import json
import os

# Configuración (podrías moverla a config.py más adelante)
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_rag_db")
COLLECTION_NAME = "knowledge_base"
EMBED_MODEL = "nomic-embed-text"  # Asegúrate de tenerlo en Ollama (ollama pull nomic-embed-text)
SIMILARITY_THRESHOLD = 0.6
MAX_CONTEXT_TOKENS_ESTIMATE = 1500  # tokens máximos para el contexto de Qwen

class RAGManager:
    def __init__(self):
        # Asegurar que Ollama está corriendo (puedes levantarlo con systemd o manual)
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        # Usamos OllamaEmbeddingFunction de ChromaDB
        self.embed_fn = embedding_functions.OllamaEmbeddingFunction(
            model_name=EMBED_MODEL,
            url="http://localhost:11434/api/embeddings"
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embed_fn
        )

    def add_documents(self, texts, metadatas=None, ids=None):
        """Añade fragmentos de texto a la base de conocimiento."""
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(texts))]
        self.collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
        print(f"[RAG] {len(texts)} documentos indexados.")

    def query(self, query_text, n_results=3):
        """
        Busca los fragmentos más relevantes.
        Retorna una lista de textos solo si la similitud máxima supera el umbral.
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        # results['distances'] es una lista de listas; la distancia de ChromaDB es 1 - similitud coseno
        distances = results.get('distances', [[0]])[0]  # primera query
        documents = results.get('documents', [[]])[0]
        
        if not documents or not distances:
            return []

        # Filtrar por umbral de similitud (1 - distance)
        relevant_chunks = []
        for dist, doc in zip(distances, documents):
            similarity = 1 - dist
            if similarity >= SIMILARITY_THRESHOLD:
                # Truncamos cada chunk para no exceder el contexto total
                relevant_chunks.append(doc[:500])  # cada chunk máximo 500 caracteres (~125 tokens)
        
        # Limitar tokens totales
        total_chars = sum(len(c) for c in relevant_chunks)
        while total_chars > MAX_CONTEXT_TOKENS_ESTIMATE * 4:  # 1 token ≈ 4 chars en español
            if not relevant_chunks:
                break
            relevant_chunks.pop()  # quita el último (el menos similar)
            total_chars = sum(len(c) for c in relevant_chunks)
        
        return relevant_chunks

    # Opcional: indexar un directorio de archivos .txt o .md
    def index_folder(self, folder_path, extensions=(".txt", ".md")):
        import glob
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
        for filepath in files:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # Dividir en fragmentos de ~500 caracteres
            chunks = [content[i:i+500] for i in range(0, len(content), 500)]
            self.add_documents(chunks, metadatas=[{"source": filepath}]*len(chunks))