import asyncio
from scraper import LogeionScraper
import json

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

if __name__ == "__main__":
    asyncio.run(main()) 