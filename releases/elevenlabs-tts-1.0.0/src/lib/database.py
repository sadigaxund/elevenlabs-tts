#!/usr/bin/env python3
"""SQLite database module for ElevenLabs TTS."""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# XDG paths
DATA_DIR = Path.home() / ".local/share/com.elevenlabs.tts"
CONFIG_DIR = Path.home() / ".config/com.elevenlabs.tts"
CACHE_DIR = Path.home() / ".cache/com.elevenlabs.tts"
DB_FILE = DATA_DIR / "tts.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_db_path():
    """Get database file path."""
    return DB_FILE


@contextmanager
def get_connection():
    """Get database connection context manager."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        logger.error(f"Database error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema - ALWAYS runs full initialization."""
    with get_connection() as conn:
        # Create tables with IF NOT EXISTS
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                api_key TEXT NOT NULL,
                character_count INTEGER DEFAULT 0,
                character_limit INTEGER DEFAULT 10000,
                exhausted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_preview TEXT,
                full_text TEXT,
                audio_file TEXT,
                voice_name TEXT,
                model_id TEXT,
                text_hash TEXT,
                thumbnail_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS playback_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        
        # Insert default playback state if not exists
        conn.execute("INSERT OR IGNORE INTO playback_state (key, value) VALUES ('current_index', '0')")
        
        # Create indexes
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_history_created 
            ON history(created_at DESC);
            
            CREATE INDEX IF NOT EXISTS idx_history_hash 
            ON history(text_hash);
        """)
        
        # Check if we need to migrate from old schema
        try:
            # Check for thumbnail_url
            conn.execute("SELECT thumbnail_url FROM history LIMIT 1")
        except sqlite3.OperationalError:
            try:
                conn.execute("ALTER TABLE history ADD COLUMN thumbnail_url TEXT")
            except: pass
            
        try:
            conn.execute("SELECT 1 FROM playback_state LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playback_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO playback_state (key, value) VALUES ('current_index', '0')")



# Config functions
def get_config(key, default=None):
    """Get a config value."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row["value"])
            return default
    except Exception as e:
        logger.error(f"Error getting config {key}: {e}")
        return default


def set_config(key, value):
    """Set a config value."""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
    except Exception as e:
        logger.error(f"Error setting config {key}: {e}")


def get_all_config():
    """Get all config as a dict."""
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {row["key"]: json.loads(row["value"]) for row in rows}
    except Exception as e:
        logger.error(f"Error getting all config: {e}")
        return {}


# API Keys functions (unchanged)
def get_api_keys():
    """Get all API keys."""
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, label, api_key, character_count, character_limit, exhausted
                FROM api_keys ORDER BY id
            """).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting API keys: {e}")
        return []


def add_api_key(label, api_key):
    """Add a new API key."""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO api_keys (label, api_key) VALUES (?, ?)",
                (label, api_key)
            )
    except Exception as e:
        logger.error(f"Error adding API key: {e}")


def update_api_key_label(key_id, new_label):
    """Update API key label."""
    try:
        with get_connection() as conn:
            conn.execute("UPDATE api_keys SET label = ? WHERE id = ?", (new_label, key_id))
    except Exception as e:
        logger.error(f"Error updating API key label {key_id}: {e}")


def delete_api_key(key_id):
    """Delete an API key by ID."""
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    except Exception as e:
        logger.error(f"Error deleting API key {key_id}: {e}")


def update_api_key_quota(key_id, character_count, character_limit, exhausted):
    """Update API key quota info."""
    try:
        with get_connection() as conn:
            conn.execute("""
                UPDATE api_keys 
                SET character_count = ?, character_limit = ?, exhausted = ?
                WHERE id = ?
            """, (character_count, character_limit, 1 if exhausted else 0, key_id))
    except Exception as e:
        logger.error(f"Error updating API key quota {key_id}: {e}")


def get_active_api_key():
    """Get the current active API key."""
    try:
        keys = get_api_keys()
        if not keys:
            return None
        
        active_idx = get_config("active_key_index", 0)
        
        # Find first non-exhausted key starting from active_idx
        for i in range(len(keys)):
            idx = (active_idx + i) % len(keys)
            if not keys[idx]["exhausted"]:
                if idx != active_idx:
                    set_config("active_key_index", idx)
                return keys[idx]
        
        # All exhausted, return first one anyway
        return keys[0] if keys else None
    except Exception as e:
        logger.error(f"Error getting active API key: {e}")
        return None


# History functions (unchanged)
def add_history(text, audio_file, voice_name, model_id, text_hash, thumbnail_url=""):
    """Add a history entry."""
    try:
        preview = text[:100] + ("..." if len(text) > 100 else "")
        
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO history (text_preview, full_text, audio_file, 
                                   voice_name, model_id, text_hash, thumbnail_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (preview, text, audio_file, voice_name, model_id, text_hash, thumbnail_url))
            
            # Cleanup old entries if not unlimited
            if not get_config("cache_unlimited", False):
                max_history = get_config("max_history", 10)
                conn.execute("""
                    DELETE FROM history WHERE id NOT IN (
                        SELECT id FROM history ORDER BY created_at DESC LIMIT ?
                    )
                """, (max_history,))
    except Exception as e:
        logger.error(f"Error adding history: {e}")


def get_history(limit=None):
    """Get history entries, newest first."""
    try:
        with get_connection() as conn:
            if limit:
                rows = conn.execute(
                    "SELECT * FROM history ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM history ORDER BY created_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return []


def get_history_by_hash(text_hash):
    """Get a history entry by text hash (for cache lookup)."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM history WHERE text_hash = ? ORDER BY created_at DESC LIMIT 1",
                (text_hash,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error getting history by hash: {e}")
        return None


def clear_history():
    """Clear all history."""
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM history")
    except Exception as e:
        logger.error(f"Error clearing history: {e}")


def get_cache_size():
    """Get total cache size in bytes."""
    try:
        total = 0
        for item in get_history():
            audio_file = item.get("audio_file", "")
            if audio_file and Path(audio_file).exists():
                total += Path(audio_file).stat().st_size
        return total
    except Exception as e:
        logger.error(f"Error getting cache size: {e}")
        return 0


# Playback State functions - FIXED with fallback
def get_playback_state(key, default=None):
    """Get playback state with schema fallback."""
    try:
        # First ensure DB is initialized
        init_db()
        
        with get_connection() as conn:
            row = conn.execute("SELECT value FROM playback_state WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
    except sqlite3.OperationalError as e:
        # Table might not exist yet, create it
        logger.warning(f"Playback state table missing, creating: {e}")
        init_db()  # This should create the table
        return default
    except Exception as e:
        logger.error(f"Error getting playback state {key}: {e}")
        return default


def set_playback_state(key, value):
    """Set playback state with schema fallback."""
    try:
        # First ensure DB is initialized
        init_db()
        
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO playback_state (key, value) VALUES (?, ?)", (key, str(value)))
    except sqlite3.OperationalError as e:
        # Table might not exist yet, create it
        logger.warning(f"Playback state table missing, creating: {e}")
        init_db()
        # Try again
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO playback_state (key, value) VALUES (?, ?)", (key, str(value)))
    except Exception as e:
        logger.error(f"Error setting playback state {key}: {e}")


# Initialize database on import
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    # Try to create DB if it doesn't exist
    if not DB_FILE.exists():
        try:
            init_db()
        except:
            logger.critical("Could not initialize database!")


def cleanup_orphaned_history():
    """Remove history entries where the audio file no longer exists."""
    try:
        with get_connection() as conn:
            # Get all history entries
            rows = conn.execute("SELECT id, audio_file FROM history").fetchall()
            deleted_count = 0
            
            for row in rows:
                audio_file = row["audio_file"]
                if audio_file and not Path(audio_file).exists():
                    conn.execute("DELETE FROM history WHERE id = ?", (row["id"],))
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} orphaned history entries.")
            
            return deleted_count
    except Exception as e:
        logger.error(f"Error during history cleanup: {e}")
        return 0