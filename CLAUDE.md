# Store Scraper

Python-based web scraping and data enrichment pipeline for independent grocery store locations.

## Project Structure

- `scrape_all_stores.py` — Main batch scraper (auto-detects store locator platform)
- `combine_all_stores.py` — Combines enriched data into single JSON
- `manual_store_scraper.py` — Handles non-standard scrapers
- `batch_enrich_*.py` — Batch enrichment scripts (Geoapify, Google, Foursquare, OpenAI)
- `scripts/` — Platform-specific scrapers and enrichment modules
- `all_stores/` — Data pipeline: raw → places_enriched → website_enriched → combined
- `index.html` — Standalone Notion-style store viewer
- `supabase/` — Database schema and edge functions for Instagram DM tracking

## Setup

```bash
pip install -r requirements.txt
```

Requires `.env` with API keys for: Geoapify, OpenAI, Foursquare, Cloudflare R2.

## Workflow

```bash
python scrape_all_stores.py stores.csv    # 1. Scrape stores
python batch_enrich_geoapify.py           # 2. Enrich with geo data
python batch_enrich_websites.py           # 3. Enrich with website data (OpenAI)
python combine_all_stores.py              # 4. Combine into final JSON
bash start_viewer.sh                      # 5. View at localhost:8000
```

## Key Details

- Python 3.7+, no build step for frontend
- Scraper auto-detects platform: Stockist, Storepoint, StoreRocket, StoreMaper, Destini, PearCommerce, GoToAisle, Dathic
- Filters to USA-only locations, excludes military bases and major chains
- Deployed via GitHub Pages (`.github/workflows/static.yml`)
