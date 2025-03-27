import sqlite3
from pathlib import Path
import logging
from typing import Dict, Any, Optional

class Database:
    def __init__(self, db_path: str = "logeion.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Main table for lexicon entries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lexicon_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lemma TEXT NOT NULL,
                    lexicon_source TEXT NOT NULL,
                    definition TEXT,
                    url TEXT NOT NULL,
                    raw_html TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for tracking scraping progress
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scrape_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    last_attempt TIMESTAMP,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lemma ON lexicon_entries(lemma)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON scrape_queue(url)")
            
            conn.commit()

    def add_lexicon_entry(self, entry: Dict[str, Any]) -> int:
        """Add a new lexicon entry to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lexicon_entries 
                (lemma, lexicon_source, definition, url, raw_html)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entry['lemma'],
                entry['lexicon_source'],
                entry['definition'],
                entry['url'],
                entry.get('raw_html')
            ))
            return cursor.lastrowid

    def add_to_queue(self, url: str) -> bool:
        """Add a URL to the scraping queue if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO scrape_queue (url) VALUES (?)",
                    (url,)
                )
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"Error adding URL to queue: {e}")
            return False

    def get_next_url(self) -> Optional[str]:
        """Get the next URL to scrape from the queue."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url FROM scrape_queue 
                WHERE status = 'pending' 
                AND (retry_count < 3 OR retry_count IS NULL)
                ORDER BY id ASC LIMIT 1
            """)
            result = cursor.fetchone()
            return result[0] if result else None

    def update_url_status(self, url: str, status: str, error_message: str = None):
        """Update the status of a URL in the queue."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if status == 'error':
                cursor.execute("""
                    UPDATE scrape_queue 
                    SET status = ?, error_message = ?, 
                        retry_count = retry_count + 1,
                        last_attempt = CURRENT_TIMESTAMP
                    WHERE url = ?
                """, (status, error_message, url))
            else:
                cursor.execute("""
                    UPDATE scrape_queue 
                    SET status = ?, last_attempt = CURRENT_TIMESTAMP
                    WHERE url = ?
                """, (status, url))
            conn.commit()

    def get_progress(self) -> Dict[str, int]:
        """Get the current scraping progress."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as failed
                FROM scrape_queue
            """)
            result = cursor.fetchone()
            return {
                'total': result[0],
                'completed': result[1] or 0,
                'failed': result[2] or 0
            } 