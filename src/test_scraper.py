import asyncio
from scraper import LogeionScraper
import json
import pytest
import aiosqlite

async def test_single_entry():
    """Test fetching a single lexicon entry."""
    scraper = LogeionScraper()
    lemma = "ἀγαθός"
    
    print(f"\nTesting lexicon entry for '{lemma}':")
    entry = await scraper.get_lexicon_entry(lemma)
    if entry:
        print(f"Language: {entry['language']}")
        print("Details preview:")
        print(json.dumps(entry['details'], indent=2, ensure_ascii=False)[:500] + "...")
    else:
        print("Failed to fetch entry")

async def test_lemma_discovery():
    """Test discovering lemmas starting with a letter."""
    scraper = LogeionScraper()
    letter = "α"
    
    print(f"\nTesting lemma discovery for letter '{letter}':")
    lemmas = await scraper.discover_lemmas(letter)
    print(f"Found {len(lemmas)} lemmas")
    if lemmas:
        print("Sample lemmas:")
        for lemma in sorted(list(lemmas))[:5]:
            print(f"- {lemma}")
            # Test getting an entry for this lemma
            entry = await scraper.get_lexicon_entry(lemma)
            if entry:
                print(f"  Language: {entry['language']}")
                print(f"  Has details: {'details' in entry and bool(entry['details'])}")

async def test_corpus_site():
    """Test getting corpus site URL for a lemma."""
    scraper = LogeionScraper()
    lemma = "ἀγαθός"
    
    print(f"\nTesting corpus site for '{lemma}':")
    url = await scraper.get_corpus_site(lemma)
    if url:
        print(f"Corpus site URL: {url}")
    else:
        print("Failed to get corpus site URL")

async def main():
    """Run all tests."""
    print("Testing Logeion Scraper...")
    
    await test_single_entry()
    await test_lemma_discovery()
    await test_corpus_site()

@pytest.mark.asyncio
async def test_get_lexicon_entry():
    """Canary test: Verify we can fetch a basic Greek lemma entry"""
    scraper = LogeionScraper()
    result = await scraper.get_lexicon_entry('λόγος')
    
    assert result is not None
    assert result['lemma'] == 'λόγος'
    assert result['language'] == 'greek'
    assert 'details' in result
    
@pytest.mark.asyncio
async def test_db_insert():
    """Canary test: Verify basic database operations work"""
    async with aiosqlite.connect(':memory:') as db:
        # Create test table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS lemmas (
                id INTEGER PRIMARY KEY,
                lemma TEXT NOT NULL,
                language TEXT NOT NULL,
                details TEXT NOT NULL
            )
        ''')
        
        # Insert test data
        test_data = {
            'lemma': 'λόγος',
            'language': 'greek',
            'details': '{"test": "data"}'
        }
        
        await db.execute(
            'INSERT INTO lemmas (lemma, language, details) VALUES (?, ?, ?)',
            (test_data['lemma'], test_data['language'], test_data['details'])
        )
        await db.commit()
        
        # Verify insertion
        async with db.execute('SELECT * FROM lemmas WHERE lemma = ?', (test_data['lemma'],)) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[1] == test_data['lemma']
            assert row[2] == test_data['language']
            assert row[3] == test_data['details']

if __name__ == "__main__":
    asyncio.run(main()) 