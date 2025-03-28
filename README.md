# Perseus Greek Dictionary Scraper

A Python-based scraper for extracting lexicon entries from the Perseus Digital Library's Greek dictionaries, particularly the Liddell-Scott-Jones (LSJ) Greek-English Lexicon.

## Features

- Direct URL access to dictionary entries without browser automation
- SQLite database storage with efficient retrieval
- Extracts both the main letter entries and specific word entries
- Preserves both plain text and HTML formatting
- Configurable scraping with rate limiting and retry logic

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/perseus-scraper
cd perseus-scraper
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the LSJ scraper with default settings:
```bash
python run_lsj_scraper.py
```

With limits (recommended for testing):
```bash
python run_lsj_scraper.py --limit-letters 3 --limit-groups 5
```

### Command Line Options

- `--limit-letters` - Limit the number of letters to process
- `--limit-groups` - Limit the number of entry groups per letter
- `--delay` - Delay between requests in seconds (default: 1.2)
- `--output` - Output JSON file path
- `--force` - Force running without limits

## Database Schema

The scraped data is stored in an SQLite database with the following structure:

### entries
- `id`: Primary key
- `lemma`: Greek word/entry key
- `data`: JSON-encoded entry data
- `created_at`: Timestamp

### Data Format

Each entry in the database contains:
- `letter`: The Greek letter (Α, Β, etc.)
- `group`: The word or entry group
- `url`: Source URL
- `content`: Content object with text and HTML

## Understanding Perseus URLs

The Perseus LSJ URLs follow this pattern:

```
# For a letter
https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:alphabetic%20letter=*a

# For a specific entry
https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:entry=a)a/atos
```

Where `1999.04.0057` is the document ID for the LSJ lexicon.

## License

MIT License 