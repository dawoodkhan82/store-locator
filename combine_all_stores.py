#!/usr/bin/env python3
"""
Combine All Store Data

This script combines:
1. All JSON files from all_stores/website_enriched/
2. All JSON files from all_stores/raw/ (except alice, bjorn, rooted_fare, yolele)

Output: all_stores/combined/combined.json
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Directories
WEBSITE_ENRICHED_DIR = 'all_stores/website_enriched'
RAW_DIR = 'all_stores/raw'
OUTPUT_DIR = 'all_stores/combined'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'combined.json')

# Files to exclude from raw (already in website_enriched)
EXCLUDE_FROM_RAW = [
    'alice_mushrooms.json',
    'bjorn_qorn.json',
    'rooted_fare.json',
    'yolele.json'
]


def load_json_file(file_path):
    """Load a JSON file and return its data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"  ✗ Error loading {file_path}: {e}")
        return None


def extract_stores(data, source_file):
    """Extract stores array from JSON data and add source brand."""
    # Handle different formats
    if isinstance(data, dict):
        # Try common keys
        stores = data.get('stores') or data.get('places') or []
    elif isinstance(data, list):
        stores = data
    else:
        stores = []

    # Extract brand name from filename
    # e.g., "alice_mushrooms_website_enriched.json" -> "alice_mushrooms"
    brand_name = source_file.replace('_website_enriched.json', '')
    brand_name = brand_name.replace('_google.json', '')
    brand_name = brand_name.replace('.json', '')

    # Add brand to each store
    for store in stores:
        if not store.get('brand'):
            store['brand'] = brand_name
        if not store.get('source'):
            store['source'] = brand_name

    print(f"  → {len(stores)} stores from {source_file} (brand: {brand_name})")
    return stores


def normalize_address(address):
    """Normalize address for comparison."""
    if not address:
        return ""
    # Remove common variations, convert to lowercase, remove extra spaces
    normalized = address.lower().strip()
    normalized = normalized.replace(',', ' ')
    normalized = ' '.join(normalized.split())  # Remove extra whitespace
    return normalized


def get_store_key(store):
    """Generate a unique key for a store based on location."""
    # Try different address fields
    address = (
        store.get('formattedAddress') or
        store.get('address_line_1') or
        store.get('address') or
        ''
    )

    # Use coordinates if available for better matching
    lat = None
    lng = None

    if 'location' in store and store['location']:
        lat = store['location'].get('latitude')
        lng = store['location'].get('longitude')
    elif 'lat' in store and 'lng' in store:
        lat = store.get('lat')
        lng = store.get('lng')

    # If we have precise coordinates, use those
    if lat and lng:
        # Convert to float and round to 5 decimal places (~1 meter precision)
        try:
            lat_float = float(lat)
            lng_float = float(lng)
            return f"coord_{round(lat_float, 5)}_{round(lng_float, 5)}"
        except (ValueError, TypeError):
            pass  # Fall through to address-based key

    # Otherwise use normalized address
    normalized = normalize_address(address)
    if normalized:
        return f"addr_{normalized}"

    # Fallback: use store name + partial address
    name = store.get('displayName', {}).get('text') or store.get('name') or 'unknown'
    return f"name_{name.lower()}_{normalized[:50]}"


def merge_stores(existing_store, new_store):
    """Merge two stores at the same location, combining brands."""
    # Get brands from both stores
    existing_brands = set()
    new_brands = set()

    # Extract brand from existing store
    if existing_store.get('brand'):
        existing_brands.add(existing_store['brand'])
    if existing_store.get('source'):
        existing_brands.add(existing_store['source'])

    # Extract brand from new store
    if new_store.get('brand'):
        new_brands.add(new_store['brand'])
    if new_store.get('source'):
        new_brands.add(new_store['source'])

    # Combine all brands
    all_brands = existing_brands | new_brands

    # Keep the store with more data (prefer enriched over raw)
    base_store = existing_store.copy()

    # Update with better data if new store has it
    if not base_store.get('websiteUri') and new_store.get('websiteUri'):
        base_store['websiteUri'] = new_store['websiteUri']

    if not base_store.get('internationalPhoneNumber') and new_store.get('internationalPhoneNumber'):
        base_store['internationalPhoneNumber'] = new_store['internationalPhoneNumber']

    # Merge enrichment data
    if 'enrichment' in new_store:
        if 'enrichment' not in base_store:
            base_store['enrichment'] = {}

        # Merge categories
        existing_cats = set(base_store['enrichment'].get('productCategories', []))
        new_cats = set(new_store['enrichment'].get('productCategories', []))
        if existing_cats or new_cats:
            base_store['enrichment']['productCategories'] = list(existing_cats | new_cats)

        # Merge specialties
        existing_specs = set(base_store['enrichment'].get('specialties', []))
        new_specs = set(new_store['enrichment'].get('specialties', []))
        if existing_specs or new_specs:
            base_store['enrichment']['specialties'] = list(existing_specs | new_specs)

        # Merge social links (prefer existing, add new if missing)
        if 'socialLinks' in new_store['enrichment']:
            if 'socialLinks' not in base_store['enrichment']:
                base_store['enrichment']['socialLinks'] = {}
            for platform, link in new_store['enrichment']['socialLinks'].items():
                if platform not in base_store['enrichment']['socialLinks']:
                    base_store['enrichment']['socialLinks'][platform] = link

    # Set combined brands
    base_store['brands'] = sorted(list(all_brands))

    # Keep most specific brand/source
    if len(all_brands) > 0:
        base_store['brand'] = sorted(list(all_brands))[0]  # Alphabetically first

    return base_store


def main():
    print("="*80)
    print("COMBINING ALL STORE DATA")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_stores = []
    store_map = {}  # Key: location identifier, Value: merged store
    stats = {
        'website_enriched': 0,
        'raw': 0,
        'total': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'duplicates_merged': 0,
        'unique_locations': 0
    }

    # Process website enriched files
    print("1. Processing website enriched stores...")
    print("-" * 80)

    if os.path.exists(WEBSITE_ENRICHED_DIR):
        enriched_files = sorted([f for f in os.listdir(WEBSITE_ENRICHED_DIR) if f.endswith('.json')])

        for filename in enriched_files:
            file_path = os.path.join(WEBSITE_ENRICHED_DIR, filename)
            print(f"\nProcessing: {filename}")

            data = load_json_file(file_path)
            if data:
                stores = extract_stores(data, filename)

                # Add each store to the map, merging if duplicate location
                for store in stores:
                    key = get_store_key(store)

                    if key in store_map:
                        # Merge with existing store
                        store_map[key] = merge_stores(store_map[key], store)
                        stats['duplicates_merged'] += 1
                    else:
                        # New unique location
                        store_map[key] = store

                stats['website_enriched'] += len(stores)
                stats['files_processed'] += 1
    else:
        print(f"  ⚠ Directory not found: {WEBSITE_ENRICHED_DIR}")

    print(f"\n✓ Website enriched: {stats['website_enriched']} stores from {stats['files_processed']} files")

    # Process raw files (excluding already enriched ones)
    print("\n2. Processing raw stores (excluding duplicates)...")
    print("-" * 80)

    if os.path.exists(RAW_DIR):
        raw_files = sorted([f for f in os.listdir(RAW_DIR) if f.endswith('.json')])

        for filename in raw_files:
            if filename in EXCLUDE_FROM_RAW:
                print(f"\n✗ Skipping (already enriched): {filename}")
                stats['files_skipped'] += 1
                continue

            file_path = os.path.join(RAW_DIR, filename)
            print(f"\nProcessing: {filename}")

            data = load_json_file(file_path)
            if data:
                stores = extract_stores(data, filename)

                # Add each store to the map, merging if duplicate location
                for store in stores:
                    key = get_store_key(store)

                    if key in store_map:
                        # Merge with existing store
                        store_map[key] = merge_stores(store_map[key], store)
                        stats['duplicates_merged'] += 1
                    else:
                        # New unique location
                        store_map[key] = store

                stats['raw'] += len(stores)
                stats['files_processed'] += 1
    else:
        print(f"  ⚠ Directory not found: {RAW_DIR}")

    print(f"\n✓ Raw stores: {stats['raw']} stores from {stats['files_processed'] - len([f for f in os.listdir(WEBSITE_ENRICHED_DIR) if f.endswith('.json')]) if os.path.exists(WEBSITE_ENRICHED_DIR) else stats['files_processed']} files")

    # Convert map to list
    all_stores = list(store_map.values())
    stats['unique_locations'] = len(all_stores)
    stats['total'] = len(all_stores)

    # Create output directory if needed
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save combined data
    print("\n3. Saving combined data...")
    print("-" * 80)

    combined_data = {
        'metadata': {
            'combined_at': datetime.now().isoformat(),
            'total_stores': stats['total'],
            'website_enriched_stores': stats['website_enriched'],
            'raw_stores': stats['raw'],
            'files_processed': stats['files_processed'],
            'files_skipped': stats['files_skipped'],
            'sources': {
                'website_enriched_dir': WEBSITE_ENRICHED_DIR,
                'raw_dir': RAW_DIR,
                'excluded_from_raw': EXCLUDE_FROM_RAW
            }
        },
        'stores': all_stores
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved to: {OUTPUT_FILE}")

    # Get file size
    file_size = os.path.getsize(OUTPUT_FILE)
    file_size_mb = file_size / (1024 * 1024)

    print(f"  File size: {file_size_mb:.2f} MB")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Website enriched stores:     {stats['website_enriched']:,}")
    print(f"Raw stores:                  {stats['raw']:,}")
    print(f"{'─'*80}")
    print(f"Total stores loaded:         {stats['website_enriched'] + stats['raw']:,}")
    print(f"Duplicates merged:           {stats['duplicates_merged']:,}")
    print(f"{'─'*80}")
    print(f"Unique locations:            {stats['unique_locations']:,}")
    print(f"\nFiles processed:             {stats['files_processed']}")
    print(f"Files skipped:               {stats['files_skipped']}")
    print(f"\nOutput:                      {OUTPUT_FILE}")
    print(f"File size:                   {file_size_mb:.2f} MB")
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)


if __name__ == '__main__':
    main()
