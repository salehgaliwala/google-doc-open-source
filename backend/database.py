import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "/data/db/wordcraft.db")
STORAGE_DIR = os.getenv("STORAGE_DIR", "/data/documents")

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Documents table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        format TEXT NOT NULL,
        filename TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        is_public INTEGER DEFAULT 0,
        share_mode TEXT DEFAULT 'private', -- 'private', 'link', 'public'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Migration check for existing DBs
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN share_mode TEXT DEFAULT 'private'")
    except Exception:
        pass

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
