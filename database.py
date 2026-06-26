import os
import mysql.connector
import re
import json
from datetime import datetime
from logger_config import logger

class MemoryManager:
    def __init__(self):
        self.conn = mysql.connector.connect(
            host="localhost",
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database="jarvisbot"
        )
        self.conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        """Crea las tablas necesarias si no existen."""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_input TEXT,
                response TEXT,
                actions_log TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_key VARCHAR(255) PRIMARY KEY,
                lesson_value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conflict_fixes (
                signature VARCHAR(255),
                fix_action TEXT,
                success BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_signature (signature)
            )
        """)
        # Tabla para entidades extraídas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS extracted_entities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message_id VARCHAR(100),
                sender VARCHAR(50),
                extracted_json JSON,
                producto VARCHAR(255),
                precio_max DECIMAL(10,2),
                cliente VARCHAR(100),
                dni VARCHAR(20),
                urgencia VARCHAR(20),
                fecha_recojo VARCHAR(100),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Otras tablas que usa whatsapp_bot.py
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME,
                sender VARCHAR(50),
                message TEXT,
                response TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id VARCHAR(100) PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tareas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender VARCHAR(50),
                tipo VARCHAR(30),
                descripcion TEXT,
                fecha_hora VARCHAR(50),
                responsable VARCHAR(100),
                prioridad VARCHAR(20)
            )
        """)
        self.conn.commit()
        logger.info("Tablas de memoria inicializadas correctamente.")

    def execute(self, sql, params=None):
        sql = re.sub(r'\?', '%s', sql)
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        self.conn.commit()
        return cur

    def query(self, sql, params=None):
        sql = re.sub(r'\?', '%s', sql)
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchall()

    def query_one(self, sql, params=None):
        sql = re.sub(r'\?', '%s', sql)
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchone()

    def add_interaction(self, user_input, response, actions_log=None):
        try:
            actions_json = json.dumps(actions_log) if actions_log else "[]"
            self.execute(
                "INSERT INTO interactions (user_input, response, actions_log) VALUES (?, ?, ?)",
                (user_input, response, actions_json)
            )
        except Exception as e:
            logger.error(f"Error guardando interacción: {e}")

    def get_recent_context(self, limit=10):
        try:
            rows = self.query(
                "SELECT user_input, response FROM interactions ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,)
            )
            rows.reverse()
            context = []
            for user_input, response in rows:
                context.append({"role": "user", "content": user_input})
                context.append({"role": "assistant", "content": response})
            return context
        except Exception as e:
            logger.error(f"Error obteniendo contexto: {e}")
            return []

    def add_lesson(self, lesson_key, lesson_value):
        try:
            self.execute(
                "INSERT INTO lessons (lesson_key, lesson_value) VALUES (?, ?) "
                "ON DUPLICATE KEY UPDATE lesson_value = VALUES(lesson_value), updated_at = CURRENT_TIMESTAMP",
                (lesson_key, lesson_value)
            )
        except Exception as e:
            logger.error(f"Error guardando lección: {e}")

    def get_lessons(self):
        try:
            rows = self.query("SELECT lesson_key, lesson_value FROM lessons")
            return {k: v for k, v in rows}
        except Exception as e:
            logger.error(f"Error obteniendo lecciones: {e}")
            return {}

    def save_conflict_fix(self, signature, fix_action, success=True):
        try:
            self.execute(
                "INSERT INTO conflict_fixes (signature, fix_action, success) VALUES (?, ?, ?)",
                (signature, json.dumps(fix_action), success)
            )
        except Exception as e:
            logger.error(f"Error guardando fix de conflicto: {e}")

    def get_conflict_fixes(self, signature):
        try:
            rows = self.query(
                "SELECT fix_action, success FROM conflict_fixes WHERE signature = ? ORDER BY created_at DESC",
                (signature,)
            )
            fixes = []
            for fix_action, success in rows:
                try:
                    action = json.loads(fix_action)
                except:
                    action = fix_action
                fixes.append({"fix_action": action, "success": bool(success)})
            return fixes
        except Exception as e:
            logger.error(f"Error obteniendo fixes: {e}")
            return []

    def save_extracted_entities(self, sender, message_id, data):
        """Guarda las entidades extraídas por la IA en la tabla extracted_entities."""
        sql = """
            INSERT INTO extracted_entities 
            (message_id, sender, extracted_json, producto, precio_max, cliente, dni, urgencia, fecha_recojo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            message_id,
            sender,
            json.dumps(data),
            data.get("producto"),
            data.get("precio_max"),
            data.get("cliente"),
            data.get("dni"),
            data.get("urgencia"),
            data.get("fecha_recojo")
        )
        try:
            self.execute(sql, params)
        except Exception as e:
            logger.error(f"Error guardando entidades extraídas: {e}")


class DatabaseManager(MemoryManager):
    pass