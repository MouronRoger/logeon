# LSJ Greek Dictionary Scraper - User Guide

This guide covers how to use the LSJ (Liddell-Scott-Jones) Greek Dictionary scraper to extract entries from the Perseus Digital Library.

## Quick Start

```bash
# Clone the repository and navigate to it
git clone https://github.com/yourusername/perseus-scraper
cd perseus-scraper

# Set up the virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the scraper with limits (recommended for first run)
python run_lsj_scraper.py --limit-letters 3 --limit-groups 5
```

## Understanding the Data

The scraper extracts data from the Perseus LSJ dictionary and stores it in:

1. **SQLite database**: `lsj_entries.sqlite` (primary storage)
2. **JSON export**: `lsj_entries_export.json` (for easy viewing/sharing)

Each entry contains:
- Greek letter
- Dictionary entry content (both text and HTML)
- Source URL
- Associated metadata

## Advanced Usage

### Full Dictionary Extraction

**Warning**: This will make many requests to the Perseus server and may take several hours.

```bash
python run_lsj_scraper.py --force
```

### Custom Parameters

```bash
# Custom delay between requests (in seconds)
python run_lsj_scraper.py --delay 2.0 --limit-letters 2

# Custom output JSON file
python run_lsj_scraper.py --limit-letters 2 --output my_lsj_data.json
```

## Accessing Stored Data

### From SQLite Database

```python
import sqlite3
import json

# Connect to the database
conn = sqlite3.connect('lsj_entries.sqlite')
cursor = conn.cursor()

# Get all entries
cursor.execute('SELECT lemma, data FROM entries')
entries = {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

# Get a specific entry
cursor.execute('SELECT data FROM entries WHERE lemma = ?', ('Α_complete',))
alpha_data = json.loads(cursor.fetchone()[0])

conn.close()
```

### From JSON Export

```python
import json

# Load the entire dataset
with open('lsj_entries_export.json', 'r', encoding='utf-8') as f:
    entries = json.load(f)

# Access a specific entry
alpha_entry = entries.get('Α_complete')
```

## Troubleshooting

1. **Rate limiting**: If you encounter 429 errors, increase the delay parameter
2. **Failed requests**: The scraper automatically retries failed requests
3. **Database issues**: Ensure SQLite is properly installed on your system

## Limitations

- The Perseus Betacode system for Greek characters can be complex
- Not all entries may be properly parsed due to HTML structure variations
- The scraper focuses on letter entries and common words by default

## Next Steps

To extend the functionality:
1. Add more common Greek words in `direct_lsj_entry_scraper.py`
2. Implement a more complete Betacode converter
3. Create a viewer application for the extracted data 