import sqlite3
import json
import logging
from typing import Dict, Optional, List, Set
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "logeion.sqlite"):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,
                    lemma TEXT NOT NULL UNIQUE,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS failed_lemmas (
                    id INTEGER PRIMARY KEY,
                    lemma TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_entries_lemma ON entries(lemma);
                CREATE INDEX IF NOT EXISTS idx_failed_lemmas_lemma ON failed_lemmas(lemma);
            ''')

    def store_entry(self, lemma: str, data: Dict) -> bool:
        """Store a lexicon entry in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO entries (lemma, data)
                    VALUES (?, ?)
                ''', (lemma, json.dumps(data, ensure_ascii=False)))
                return True
        except Exception as e:
            logger.error(f"Error storing entry for {lemma}: {str(e)}")
            return False

    def get_entry(self, lemma: str) -> Optional[Dict]:
        """Retrieve a lexicon entry from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT data FROM entries WHERE lemma = ?', (lemma,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return None
        except Exception as e:
            logger.error(f"Error retrieving entry for {lemma}: {str(e)}")
            return None

    def get_all_entries(self) -> Dict[str, Dict]:
        """Get all entries from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT lemma, data FROM entries')
                return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error retrieving all entries: {str(e)}")
            return {}

    def add_failed_lemma(self, lemma: str) -> bool:
        """Add a lemma to the failed lemmas table"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR IGNORE INTO failed_lemmas (lemma)
                    VALUES (?)
                ''', (lemma,))
                return True
        except Exception as e:
            logger.error(f"Error adding failed lemma {lemma}: {str(e)}")
            return False

    def remove_failed_lemma(self, lemma: str) -> bool:
        """Remove a lemma from the failed lemmas table"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM failed_lemmas WHERE lemma = ?', (lemma,))
                return True
        except Exception as e:
            logger.error(f"Error removing failed lemma {lemma}: {str(e)}")
            return False

    def get_failed_lemmas(self) -> Set[str]:
        """Get all failed lemmas"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT lemma FROM failed_lemmas')
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error retrieving failed lemmas: {str(e)}")
            return set()

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT 
                        (SELECT COUNT(*) FROM entries) as total_entries,
                        (SELECT COUNT(*) FROM failed_lemmas) as total_failed
                ''')
                row = cursor.fetchone()
                return {
                    'total_entries': row[0],
                    'total_failed': row[1]
                }
        except Exception as e:
            logger.error(f"Error getting database stats: {str(e)}")
            return {'total_entries': 0, 'total_failed': 0} 