#!/usr/bin/env python3
"""
Batch Store Scraper from CSV

CSV Format:
    store_name,store_locator_url

Usage:
    python scrape_from_csv.py stores.csv

Output:
    Creates JSON files in all_stores/raw/ directory with naming pattern:
    {brand_name_slug}.json
"""

import csv
import sys
import os
import re
import subprocess
from datetime import datetime

SCRAPERS = {
    'stockist': 'scripts/scrape_stockist_stores.py',
    'storepoint': 'scripts/scrape_storepoint_stores.py',
    'storerocket': 'scripts/scrape_storerocket_stores.py',
    'storemapper': 'scripts/scrape_storemapper_stores.py',
    'destini': 'scripts/scrape_destini_stores.py',
    'pearcommerce': 'scripts/scrape_pearcommerce_stores.py',
}


def slugify(text):
    text = text.lower()
    text = re.sub(r'[\s-]+', '_', text)
    text = re.sub(r'[^a-z0-9_]', '', text)
    text = text.strip('_')
    return text


def read_csv_file(csv_file):
    brands = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        sample = f.read(1024)
        f.seek(0)
        sniffer = csv.Sniffer()
        has_header = sniffer.has_header(sample)
        reader = csv.reader(f)

        if has_header:
            next(reader)

        for row in reader:
            if len(row) >= 2:
                brand_name = row[0].strip()
                url = row[1].strip()

                if brand_name and url:
                    brands.append((brand_name, url))
    return brands


def try_scraper(scraper_name, script_path, url, output_file):
    print(f"\n{'='*80}")
    print(f"Trying {scraper_name.upper()} scraper...")
    print(f"{'='*80}")

    try:
        result = subprocess.run(
            ['python3', script_path, url, output_file],
            capture_output=True,
            text=True,
            timeout=300
        )

        print(result.stdout)
        if result.stderr:
            print("Errors/Warnings:")
            print(result.stderr)

        if os.path.exists(output_file):
            import json
            with open(output_file, 'r') as f:
                data = json.load(f)
                store_count = data.get('total_stores', 0)
                if store_count > 0:
                    print(f"\n✓ {scraper_name.upper()} succeeded! Found {store_count} stores.")
                    return True
                else:
                    print(f"\n✗ {scraper_name.upper()} found 0 stores.")
                    os.remove(output_file)
                    return False
        else:
            print(f"\n✗ {scraper_name.upper()} failed (no output file created).")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n✗ {scraper_name.upper()} timed out after 5 minutes.")
        return False
    except Exception as e:
        print(f"\n✗ {scraper_name.upper()} error: {str(e)}")
        return False


def scrape_brand(brand_name, url, output_dir):
    print(f"\n{'#'*80}")
    print(f"# SCRAPING: {brand_name}")
    print(f"# URL: {url}")
    print(f"{'#'*80}")

    brand_slug = slugify(brand_name)
    output_file = os.path.join(output_dir, f"{brand_slug}.json")

    for scraper_name, script_path in SCRAPERS.items():
        if not os.path.exists(script_path):
            print(f"⚠ Warning: {script_path} not found, skipping {scraper_name}...")
            continue

        success = try_scraper(scraper_name, script_path, url, output_file)
        if success:
            return {
                'brand_name': brand_name,
                'url': url,
                'success': True,
                'scraper': scraper_name,
                'output_file': output_file
            }

    print(f"\n✗ All scrapers failed for {brand_name}")
    return {
        'brand_name': brand_name,
        'url': url,
        'success': False,
        'scraper': None,
        'output_file': None
    }


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scrape_from_csv.py <csv_file>")
        print("\nCSV Format:")
        print("  store_name,store_locator_url")
        print("  Brand Name,https://example.com/pages/store-locator")
        print("\nExample:")
        print("  python scrape_from_csv.py stores.csv")
        return 1

    csv_file = sys.argv[1]
    print("="*80)
    print("BATCH STORE SCRAPER FROM CSV")
    print("="*80)
    print(f"\nCSV file: {csv_file}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output_dir = "all_stores/raw"

    try:
        brands = read_csv_file(csv_file)
    except Exception as e:
        print(f"✗ Error reading CSV file: {str(e)}")
        return 1

    if not brands:
        print("✗ No valid brands found in CSV file")
        return 1

    print(f"Found {len(brands)} brands to scrape:\n")
    for i, (brand_name, url) in enumerate(brands, 1):
        print(f"  {i}. {brand_name} - {url}")

    results = []
    for i, (brand_name, url) in enumerate(brands, 1):
        print(f"\n{'='*80}")
        print(f"Processing {i}/{len(brands)}: {brand_name}")
        print(f"{'='*80}")

        result = scrape_brand(brand_name, url, output_dir)
        results.append(result)

    print(f"\n{'='*80}")
    print("SCRAPING SUMMARY")
    print(f"{'='*80}")
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total brands: {len(brands)}")
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}\n")

    if successful:
        print("Successful scrapes:")
        for r in successful:
            print(f"  ✓ {r['brand_name']} - {r['scraper']} scraper - {r['output_file']}")

    if failed:
        print("\nFailed scrapes:")
        for r in failed:
            print(f"  ✗ {r['brand_name']} - {r['url']}")

    print(f"\n{'='*80}")
    return 0 if not failed else 1


if __name__ == '__main__':
    exit(main())
