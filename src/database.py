import aiosqlite
import json
import logging
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    # Status constants for clarity
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    
    def __init__(self, db_path: str = "logeion.sqlite"):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Using sync SQLite for initialization since it's one-time
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS lemmas (
                    id INTEGER PRIMARY KEY,
                    lemma TEXT NOT NULL,
                    language TEXT NOT NULL,
                    details TEXT NOT NULL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(lemma, language)
                );

                CREATE TABLE IF NOT EXISTS scrape_queue (
                    id INTEGER PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    last_attempted TIMESTAMP,
                    processing_started TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma);
                CREATE INDEX IF NOT EXISTS idx_lemmas_source ON lemmas(source);
                CREATE INDEX IF NOT EXISTS idx_queue_status ON scrape_queue(status);
                CREATE INDEX IF NOT EXISTS idx_queue_retry ON scrape_queue(retry_count);
            ''')

    async def add_lexicon_entry(self, entry: Dict) -> bool:
        """Save a lexicon entry to database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO lemmas (lemma, language, details, source)
                    VALUES (?, ?, ?, ?)
                ''', (
                    entry['lemma'],
                    entry.get('language', 'greek'),
                    json.dumps(entry.get('details', {}), ensure_ascii=False),
                    entry.get('source', 'LSJ')  # Default to LSJ for MVP
                ))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving entry for {entry['lemma']}: {str(e)}")
            return False

    async def get_lexicon_entry(self, lemma: str) -> Optional[Dict]:
        """Retrieve a lexicon entry"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT lemma, language, details, source FROM lemmas WHERE lemma = ?',
                    (lemma,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'lemma': row[0],
                            'language': row[1],
                            'details': json.loads(row[2]),
                            'source': row[3]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error retrieving entry for {lemma}: {str(e)}")
            return None

    async def get_entries_by_source(self, source: str) -> List[Dict]:
        """Get all entries from a specific source"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT lemma, language, details FROM lemmas WHERE source = ?',
                    (source,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [{
                        'lemma': row[0],
                        'language': row[1],
                        'details': json.loads(row[2]),
                        'source': source
                    } for row in rows]
        except Exception as e:
            logger.error(f"Error getting entries for source {source}: {str(e)}")
            return []

    async def add_to_queue(self, url: str) -> bool:
        """Add URL to scraping queue if not exists"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO scrape_queue (url, status)
                    VALUES (?, ?)
                ''', (url, self.STATUS_PENDING))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding URL to queue {url}: {str(e)}")
            return False

    async def get_next_url(self) -> Optional[Tuple[str, int]]:
        """Get next pending URL to scrape and mark it as processing"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT url, retry_count FROM scrape_queue 
                    WHERE status = ? 
                    OR (status = ? AND retry_count < 3)
                    ORDER BY retry_count, created_at 
                    LIMIT 1
                ''', (self.STATUS_PENDING, self.STATUS_FAILED)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        url, retry_count = row
                        # Mark as processing
                        await db.execute('''
                            UPDATE scrape_queue 
                            SET status = ?, processing_started = CURRENT_TIMESTAMP
                            WHERE url = ?
                        ''', (self.STATUS_PROCESSING, url))
                        await db.commit()
                        return url, retry_count
                    return None
        except Exception as e:
            logger.error(f"Error getting next URL: {str(e)}")
            return None

    async def mark_url_failed(self, url: str, error: str) -> bool:
        """Mark a URL as failed with error message"""
        return await self.update_url_status(url, self.STATUS_FAILED, error)

    async def mark_url_completed(self, url: str) -> bool:
        """Mark a URL as completed"""
        return await self.update_url_status(url, self.STATUS_COMPLETED)

    async def update_url_status(self, url: str, status: str, error: str = None) -> bool:
        """Update URL status after processing"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE scrape_queue 
                    SET status = ?,
                        error = ?,
                        retry_count = CASE 
                            WHEN ? = ? THEN retry_count + 1 
                            ELSE retry_count 
                        END,
                        last_attempted = CURRENT_TIMESTAMP,
                        processing_started = CASE 
                            WHEN ? = ? THEN processing_started
                            ELSE NULL 
                        END
                    WHERE url = ?
                ''', (status, error, status, self.STATUS_FAILED, status, self.STATUS_PROCESSING, url))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating URL status {url}: {str(e)}")
            return False

    async def get_progress(self) -> Dict[str, int]:
        """Get detailed scraping progress"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed,
                        SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as processing
                    FROM scrape_queue
                ''', (self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_PENDING, self.STATUS_PROCESSING)) as cursor:
                    row = await cursor.fetchone()
                    return {
                        'total': row[0] or 0,
                        'completed': row[1] or 0,
                        'failed': row[2] or 0,
                        'pending': row[3] or 0,
                        'processing': row[4] or 0
                    }
        except Exception as e:
            logger.error(f"Error getting progress: {str(e)}")
            return {'total': 0, 'completed': 0, 'failed': 0, 'pending': 0, 'processing': 0}

    async def export_to_json(self, output_path: str) -> bool:
        """Export all completed entries to JSON"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT lemma, language, details, source FROM lemmas') as cursor:
                    entries = []
                    async for row in cursor:
                        entries.append({
                            'lemma': row[0],
                            'language': row[1],
                            'details': json.loads(row[2]),
                            'source': row[3]
                        })
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(entries, f, ensure_ascii=False, indent=2)
                    return True
        except Exception as e:
            logger.error(f"Error exporting to JSON: {str(e)}")
            return False

    async def reset_failed(self) -> int:
        """Reset all failed URLs to pending for retry"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    UPDATE scrape_queue 
                    SET status = ?, retry_count = 0, error = NULL 
                    WHERE status = ?
                ''', (self.STATUS_PENDING, self.STATUS_FAILED))
                await db.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error resetting failed URLs: {str(e)}")
            return 0 