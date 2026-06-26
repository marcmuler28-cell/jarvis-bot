"""
finetune_db.py - Base de datos SQLite para dataset de fine-tuning.

Separa el dataset de entrenamiento de la memoria principal (MySQL).
SQLite = un solo archivo, cero procesos en segundo plano, cero RAM en reposo.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finetune_dataset.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
#  failed_interactions - comandos que el asistente no supo resolver
# ---------------------------------------------------------------------------

def add_failed_interaction(user_input, expected_action=None, actual_error=None):
    """Guarda un comando que fallo para futuro fine-tuning."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO failed_interactions (user_input, expected_action, actual_error) VALUES (?, ?, ?)",
            (user_input, expected_action, actual_error)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[finetune_db] Error guardando failed_interaction: {e}")
        return False


def get_failed_interactions(limit=100):
    """Obtiene los ultimos comandos fallidos."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT user_input, expected_action, actual_error, timestamp "
            "FROM failed_interactions ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[finetune_db] Error obteniendo failed_interactions: {e}")
        return []


# ---------------------------------------------------------------------------
#  finetune_dataset - ejemplos ideales en formato ChatML
# ---------------------------------------------------------------------------

def add_example(user_input, ideal_response, actions_json=None, category=None):
    """Guarda un ejemplo ideal para fine-tuning (formato ChatML)."""
    try:
        conn = _get_conn()
        actions_str = json.dumps(actions_json) if actions_json else None
        conn.execute(
            "INSERT INTO finetune_dataset (user_input, ideal_response, actions_json, category) VALUES (?, ?, ?, ?)",
            (user_input, ideal_response, actions_str, category)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[finetune_db] Error guardando ejemplo: {e}")
        return False


def export_as_jsonl(limit=1000):
    """Exporta el dataset en formato JSONL (ChatML) para QLoRA/llama.cpp.
    
    Formato por linea:
    {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT user_input, ideal_response, actions_json, category "
            "FROM finetune_dataset ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        
        lines = []
        for r in rows:
            msg = {
                "messages": [
                    {"role": "user", "content": r["user_input"]},
                    {"role": "assistant", "content": r["ideal_response"]}
                ]
            }
            if r["actions_json"]:
                try:
                    msg["actions"] = json.loads(r["actions_json"])
                except:
                    pass
            if r["category"]:
                msg["category"] = r["category"]
            lines.append(json.dumps(msg, ensure_ascii=False))
        
        return "\n".join(lines)
    except Exception as e:
        print(f"[finetune_db] Error exportando dataset: {e}")
        return ""


def get_stats():
    """Estadisticas del dataset."""
    try:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM finetune_dataset").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM failed_interactions").fetchone()[0]
        cats = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM finetune_dataset "
            "WHERE category IS NOT NULL GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        conn.close()
        return {
            "total_examples": total,
            "failed_interactions": failed,
            "categories": {r["category"]: r["cnt"] for r in cats}
        }
    except Exception as e:
        print(f"[finetune_db] Error obteniendo stats: {e}")
        return {}


# ---------------------------------------------------------------------------
#  Auto-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== TEST finetune_db ===")
    
    # Agregar ejemplo
    add_example(
        "abre spotify",
        "Abriendo Spotify...",
        [{"action": "open_app", "args": ["spotify"], "result": "Spotify abierto"}],
        "open_app"
    )
    add_example(
        "reproduce musica relajante",
        "Reproduciendo musica relajante en Spotify...",
        [{"action": "play_playlist_by_name", "args": ["musica relajante"], "result": "OK"}],
        "spotify"
    )
    
    # Agregar fallo
    add_failed_interaction("abre spotifi", "open_app spotify", "No se encontro el alias")
    
    print(f"Stats: {get_stats()}")
    print(f"\nJSONL exportado:\n{export_as_jsonl()}")
