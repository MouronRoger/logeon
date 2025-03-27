import asyncio
from scraper import LogeionScraper

async def test_single_page():
    """Test scraping a single lemma page."""
    scraper = LogeionScraper()
    test_url = "https://logeion.uchicago.edu/ἀγαθός"
    
    async with scraper:
        # Test page fetching
        content = await scraper.get_page_content(test_url)
        if content:
            print("✓ Successfully fetched page content")
        else:
            print("✗ Failed to fetch page content")
            return

        # Test parsing
        entries = await scraper.parse_lexicon_entry(content, test_url)
        if entries:
            print(f"✓ Successfully parsed {len(entries)} dictionary entries")
            for entry in entries:
                print(f"\nSource: {entry['lexicon_source']}")
                print(f"Lemma: {entry['lemma']}")
                print(f"Definition preview: {entry['definition'][:100]}...")
        else:
            print("✗ Failed to parse entries")

async def test_lemma_discovery():
    """Test discovering lemma links from an index page."""
    scraper = LogeionScraper()
    test_url = "https://logeion.uchicago.edu/α"
    
    async with scraper:
        lemma_urls = await scraper.discover_lemmas(test_url)
        if lemma_urls:
            print(f"\n✓ Successfully discovered {len(lemma_urls)} lemma links")
            print("Sample URLs:")
            for url in lemma_urls[:5]:
                print(f"  - {url}")
        else:
            print("\n✗ Failed to discover lemma links")

async def main():
    print("Testing Logeion Scraper...")
    print("\n1. Testing single page scraping:")
    await test_single_page()
    
    print("\n2. Testing lemma discovery:")
    await test_lemma_discovery()

if __name__ == "__main__":
    asyncio.run(main()) 