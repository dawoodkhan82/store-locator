#!/usr/bin/env python3
"""
Combine All Store Data

This script combines store data with the following priority:
1. Use website_enriched files (OpenAI enriched) if available
2. Fall back to places_enriched files (Geoapify/Google Places enriched)

Each store gets a 'data_enriched' field tracking which sources were used:
- 'geoapify' - enriched with Geoapify Places API
- 'google_places' - enriched with Google Places API
- 'openai' - website scraped and analyzed with OpenAI

Output: all_stores/combined/combined.json
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Directories
WEBSITE_ENRICHED_DIR = Path('all_stores/website_enriched')
PLACES_ENRICHED_DIR = Path('all_stores/places_enriched')
OUTPUT_DIR = Path('all_stores/combined')
OUTPUT_FILE = OUTPUT_DIR / 'combined.json'


def get_brand_name(filename):
    """Extract brand name from filename (remove suffixes)."""
    name = filename.replace('.json', '')
    suffixes = ['_website_enriched', '_geoapify', '_google', '_places', '_enriched']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name


def load_json_file(file_path):
    """Load a JSON file and return its data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"  ✗ Error loading {file_path}: {e}")
        return None


def detect_enrichment_sources(store, filename):
    """
    Detect which enrichment sources were used for this store.

    Returns a list of enrichment source names.
    """
    sources = []

    # Check for Geoapify enrichment
    if store.get('geoapify'):
        sources.append('geoapify')

    # Check for Google Places enrichment
    if store.get('google_places'):
        sources.append('google_places')

    # Check for OpenAI website enrichment (has 'enrichment' key with actual data)
    enrichment = store.get('enrichment', {})
    if enrichment:
        # Only count as OpenAI enriched if there's actual content
        has_content = (
            enrichment.get('productCategories') or
            enrichment.get('aboutText') or
            enrichment.get('specialties') or
            enrichment.get('socialLinks')
        )
        if has_content:
            sources.append('openai')

    return sources


def extract_country_state(store):
    """
    Extract country and state from store data.

    Returns tuple of (country, state_code)
    """
    country = None
    state = None

    # From geoapify geocoding
    geoapify = store.get('geoapify', {}).get('geocoding', {})
    if geoapify.get('country'):
        country = geoapify['country']
        state = geoapify.get('state_code')
    elif geoapify.get('country_code'):
        country = geoapify['country_code'].upper()
        state = geoapify.get('state_code')

    # From google_places address
    if not country and store.get('google_places', {}).get('formattedAddress'):
        addr = store['google_places']['formattedAddress']
        if ', USA' in addr or 'United States' in addr:
            country = 'United States'
        elif 'Canada' in addr:
            country = 'Canada'
        elif 'United Kingdom' in addr or ', UK' in addr:
            country = 'United Kingdom'

    # From raw state field (assume US if 2-letter state code)
    if not country and store.get('state'):
        if len(store['state']) == 2:
            country = 'United States'
            state = store['state'].upper()

    # From address parsing
    if not country:
        addr = store.get('formattedAddress', '') or store.get('address_line_1', '') or ''
        if addr:
            if 'USA' in addr or 'United States' in addr:
                country = 'United States'
            elif 'Canada' in addr:
                country = 'Canada'
            elif 'UK' in addr or 'United Kingdom' in addr:
                country = 'United Kingdom'

    # Normalize country names
    country_map = {
        'us': 'United States',
        'US': 'United States',
        'USA': 'United States',
        'ca': 'Canada',
        'CA': 'Canada',
        'gb': 'United Kingdom',
        'GB': 'United Kingdom',
        'UK': 'United Kingdom',
    }
    if country in country_map:
        country = country_map[country]

    return country, state


def extract_stores(data, source_file):
    """Extract stores array from JSON data and add source brand and enrichment info."""
    # Handle different formats
    if isinstance(data, dict):
        stores = data.get('stores') or data.get('places') or []
    elif isinstance(data, list):
        stores = data
    else:
        stores = []

    # Extract brand name from filename
    brand_name = get_brand_name(source_file)

    # Add brand and enrichment info to each store
    for store in stores:
        if not store.get('brand'):
            store['brand'] = brand_name
        if not store.get('source'):
            store['source'] = brand_name

        # Detect and add enrichment sources
        enrichment_sources = detect_enrichment_sources(store, source_file)
        store['data_enriched'] = enrichment_sources

        # Extract and add country/state
        country, state_code = extract_country_state(store)
        if country:
            store['country'] = country
        if state_code:
            store['state_code'] = state_code

    print(f"  → {len(stores)} stores from {source_file} (brand: {brand_name})")
    return stores


def normalize_address(address):
    """Normalize address for comparison."""
    if not address:
        return ""
    normalized = address.lower().strip()
    normalized = normalized.replace(',', ' ')
    normalized = ' '.join(normalized.split())
    return normalized


def get_store_key(store):
    """Generate a unique key for a store based on location."""
    address = (
        store.get('formattedAddress') or
        store.get('address_line_1') or
        store.get('address') or
        ''
    )

    lat = None
    lng = None

    if 'location' in store and store['location']:
        lat = store['location'].get('latitude')
        lng = store['location'].get('longitude')
    elif 'lat' in store and 'lng' in store:
        lat = store.get('lat')
        lng = store.get('lng')
    elif 'latitude' in store and 'longitude' in store:
        lat = store.get('latitude')
        lng = store.get('longitude')

    if lat and lng:
        try:
            lat_float = float(lat)
            lng_float = float(lng)
            return f"coord_{round(lat_float, 4)}_{round(lng_float, 4)}"
        except (ValueError, TypeError):
            pass

    normalized = normalize_address(address)
    if normalized:
        return f"addr_{normalized}"

    name = store.get('displayName', {}).get('text') or store.get('name') or 'unknown'
    return f"name_{name.lower()}_{normalized[:50]}"


def merge_stores(existing_store, new_store):
    """Merge two stores at the same location, combining brands and enrichment sources."""
    # Get brands from both stores
    existing_brands = set()
    new_brands = set()

    if existing_store.get('brand'):
        existing_brands.add(existing_store['brand'])
    if existing_store.get('source'):
        existing_brands.add(existing_store['source'])

    if new_store.get('brand'):
        new_brands.add(new_store['brand'])
    if new_store.get('source'):
        new_brands.add(new_store['source'])

    all_brands = existing_brands | new_brands

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

        existing_cats = set(base_store['enrichment'].get('productCategories', []))
        new_cats = set(new_store['enrichment'].get('productCategories', []))
        if existing_cats or new_cats:
            base_store['enrichment']['productCategories'] = list(existing_cats | new_cats)

        existing_specs = set(base_store['enrichment'].get('specialties', []))
        new_specs = set(new_store['enrichment'].get('specialties', []))
        if existing_specs or new_specs:
            base_store['enrichment']['specialties'] = list(existing_specs | new_specs)

        if 'socialLinks' in new_store['enrichment']:
            if 'socialLinks' not in base_store['enrichment']:
                base_store['enrichment']['socialLinks'] = {}
            for platform, link in new_store['enrichment']['socialLinks'].items():
                if platform not in base_store['enrichment']['socialLinks']:
                    base_store['enrichment']['socialLinks'][platform] = link

    # Merge data_enriched sources
    existing_sources = set(existing_store.get('data_enriched', []))
    new_sources = set(new_store.get('data_enriched', []))
    base_store['data_enriched'] = sorted(list(existing_sources | new_sources))

    # Set combined brands
    base_store['brands'] = sorted(list(all_brands))

    if len(all_brands) > 0:
        base_store['brand'] = sorted(list(all_brands))[0]

    return base_store


def main():
    print("="*80)
    print("COMBINING ALL STORE DATA")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    store_map = {}
    stats = {
        'website_enriched': 0,
        'places_enriched': 0,
        'total': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'duplicates_merged': 0,
        'unique_locations': 0
    }

    # Get list of brands that have website enrichment
    website_enriched_brands = set()
    if WEBSITE_ENRICHED_DIR.exists():
        for f in WEBSITE_ENRICHED_DIR.glob('*.json'):
            brand = get_brand_name(f.name)
            website_enriched_brands.add(brand)

    print(f"Brands with website enrichment: {len(website_enriched_brands)}")
    for brand in sorted(website_enriched_brands):
        print(f"  - {brand}")
    print()

    # Process website enriched files first (priority)
    print("1. Processing website enriched stores...")
    print("-" * 80)

    if WEBSITE_ENRICHED_DIR.exists():
        enriched_files = sorted(WEBSITE_ENRICHED_DIR.glob('*.json'))

        for file_path in enriched_files:
            print(f"\nProcessing: {file_path.name}")

            data = load_json_file(file_path)
            if data:
                stores = extract_stores(data, file_path.name)

                for store in stores:
                    key = get_store_key(store)

                    if key in store_map:
                        store_map[key] = merge_stores(store_map[key], store)
                        stats['duplicates_merged'] += 1
                    else:
                        store_map[key] = store

                stats['website_enriched'] += len(stores)
                stats['files_processed'] += 1
    else:
        print(f"  ⚠ Directory not found: {WEBSITE_ENRICHED_DIR}")

    print(f"\n✓ Website enriched: {stats['website_enriched']} stores")

    # Process places enriched files (for brands not in website_enriched)
    print("\n2. Processing places enriched stores (fallback for non-website-enriched brands)...")
    print("-" * 80)

    if PLACES_ENRICHED_DIR.exists():
        places_files = sorted(PLACES_ENRICHED_DIR.glob('*.json'))

        for file_path in places_files:
            brand = get_brand_name(file_path.name)

            if brand in website_enriched_brands:
                print(f"\n⏭️  Skipping {file_path.name} (already have website enriched version)")
                stats['files_skipped'] += 1
                continue

            print(f"\nProcessing: {file_path.name}")

            data = load_json_file(file_path)
            if data:
                stores = extract_stores(data, file_path.name)

                for store in stores:
                    key = get_store_key(store)

                    if key in store_map:
                        store_map[key] = merge_stores(store_map[key], store)
                        stats['duplicates_merged'] += 1
                    else:
                        store_map[key] = store

                stats['places_enriched'] += len(stores)
                stats['files_processed'] += 1
    else:
        print(f"  ⚠ Directory not found: {PLACES_ENRICHED_DIR}")

    print(f"\n✓ Places enriched: {stats['places_enriched']} stores")

    # Convert map to list
    all_stores = list(store_map.values())
    stats['unique_locations'] = len(all_stores)
    stats['total'] = len(all_stores)

    # Count enrichment stats
    enrichment_counts = {
        'geoapify': 0,
        'google_places': 0,
        'openai': 0,
        'none': 0
    }
    for store in all_stores:
        sources = store.get('data_enriched', [])
        if not sources:
            enrichment_counts['none'] += 1
        for source in sources:
            if source in enrichment_counts:
                enrichment_counts[source] += 1

    # Create output directory if needed
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save combined data
    print("\n3. Saving combined data...")
    print("-" * 80)

    combined_data = {
        'metadata': {
            'combined_at': datetime.now().isoformat(),
            'total_stores': stats['total'],
            'website_enriched_stores': stats['website_enriched'],
            'places_enriched_stores': stats['places_enriched'],
            'files_processed': stats['files_processed'],
            'files_skipped': stats['files_skipped'],
            'enrichment_counts': enrichment_counts,
            'sources': {
                'website_enriched_dir': str(WEBSITE_ENRICHED_DIR),
                'places_enriched_dir': str(PLACES_ENRICHED_DIR)
            }
        },
        'stores': all_stores
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved to: {OUTPUT_FILE}")

    file_size = os.path.getsize(OUTPUT_FILE)
    file_size_mb = file_size / (1024 * 1024)

    print(f"  File size: {file_size_mb:.2f} MB")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Website enriched stores:     {stats['website_enriched']:,}")
    print(f"Places enriched stores:      {stats['places_enriched']:,}")
    print(f"{'─'*80}")
    print(f"Total stores loaded:         {stats['website_enriched'] + stats['places_enriched']:,}")
    print(f"Duplicates merged:           {stats['duplicates_merged']:,}")
    print(f"{'─'*80}")
    print(f"Unique locations:            {stats['unique_locations']:,}")
    print(f"\nEnrichment breakdown:")
    print(f"  - Geoapify:      {enrichment_counts['geoapify']:,} stores")
    print(f"  - Google Places: {enrichment_counts['google_places']:,} stores")
    print(f"  - OpenAI:        {enrichment_counts['openai']:,} stores")
    print(f"  - None:          {enrichment_counts['none']:,} stores")
    print(f"\nFiles processed:             {stats['files_processed']}")
    print(f"Files skipped:               {stats['files_skipped']}")
    print(f"\nOutput:                      {OUTPUT_FILE}")
    print(f"File size:                   {file_size_mb:.2f} MB")
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)


if __name__ == '__main__':
    main()
