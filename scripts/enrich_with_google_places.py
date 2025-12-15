#!/usr/bin/env python3
"""
Google Places API Enrichment Script

This script takes a list of stores (from Stockist or any source) and enriches them
with detailed data from Google Places API including:
- Full address, phone, website
- Rating, reviews, photos
- Business hours, types
- Location coordinates (verified/improved)

Usage: python enrich_with_google_places.py <input_json> [output_json]
"""

import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Places API configuration
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
PLACES_API_BASE = 'https://places.googleapis.com/v1/places:searchText'

# Field mask for Google Places API (what data to retrieve)
FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    'places.formattedAddress',
    'places.location',
    'places.rating',
    'places.userRatingCount',
    'places.businessStatus',
    'places.types',
    'places.googleMapsUri',
    'places.websiteUri',
    'places.internationalPhoneNumber',
    'places.reviews',
    'places.photos',
    'places.editorialSummary',
    'places.generativeSummary'
])


def search_google_places(store_name, address, city, state):
    """
    Search for a store in Google Places API by name and location.

    Args:
        store_name (str): Name of the store
        address (str): Street address
        city (str): City name
        state (str): State/province

    Returns:
        dict: Google Places data or None if not found
    """
    # Build search query
    query = f"{store_name} {address} {city} {state}"

    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': FIELD_MASK
    }

    payload = {
        'textQuery': query,
        'pageSize': 1  # Only get top result
    }

    try:
        response = requests.post(
            PLACES_API_BASE,
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            places = data.get('places', [])
            if places:
                return places[0]  # Return first (best) match
        else:
            print(f"    ✗ API error: {response.status_code} - {response.text[:100]}")

    except Exception as e:
        print(f"    ✗ Request error: {str(e)[:100]}")

    return None


def enrich_stores(input_file, output_file='stores_google_enriched.json', limit=None):
    """
    Enrich stores with Google Places API data.

    Args:
        input_file (str): Input JSON file with stores
        output_file (str): Output JSON file
        limit (int): Optional limit for testing
    """
    if not GOOGLE_MAPS_API_KEY:
        print("Error: GOOGLE_MAPS_API_KEY not found in .env file")
        return 1

    print("="*80)
    print("GOOGLE PLACES API ENRICHMENT")
    print("="*80)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}\n")

    # Load input data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stores = data.get('stores', [])
    total = len(stores)

    if limit:
        stores = stores[:limit]
        print(f"⚠️ LIMIT MODE: Only processing {limit} stores\n")

    enriched_count = 0
    not_found_count = 0

    for idx, store in enumerate(stores, 1):
        store_name = store.get('name', 'Unknown')
        address = store.get('address_line_1', '')
        city = store.get('city', '')
        state = store.get('state', '')

        print(f"[{idx}/{len(stores)}] {store_name}")
        print(f"  Address: {address}, {city}, {state}")

        # Search Google Places
        google_data = search_google_places(store_name, address, city, state)

        if google_data:
            # Merge Google Places data into store
            store['google_places'] = google_data
            enriched_count += 1
            print(f"  ✓ Found on Google Places")

            # Log key data found
            if google_data.get('websiteUri'):
                print(f"    Website: {google_data['websiteUri']}")
            if google_data.get('internationalPhoneNumber'):
                print(f"    Phone: {google_data['internationalPhoneNumber']}")
            if google_data.get('rating'):
                print(f"    Rating: {google_data['rating']} ({google_data.get('userRatingCount', 0)} reviews)")

        else:
            not_found_count += 1
            print(f"  ✗ Not found on Google Places")

        # Rate limiting - be respectful to API
        time.sleep(0.5)

    # Prepare output
    result = {
        'source_file': input_file,
        'enriched_at': datetime.now().isoformat(),
        'total_stores': len(stores),
        'enriched_count': enriched_count,
        'not_found_count': not_found_count,
        'stores': stores
    }

    # Save to file
    print(f"\n{'='*80}")
    print(f"Saving enriched data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Enrichment complete!")
    print(f"  Total stores: {len(stores)}")
    print(f"  Successfully enriched: {enriched_count}")
    print(f"  Not found: {not_found_count}")
    print(f"  Success rate: {enriched_count/len(stores)*100:.1f}%")

    # Estimate API cost
    # Text Search (New) is $0.032 per request
    cost = len(stores) * 0.032
    print(f"\n  Estimated API cost: ${cost:.2f}")

    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python enrich_with_google_places.py <input_json> [output_json] [--test]")
        print("\nExamples:")
        print("  python enrich_with_google_places.py stockist_stores_raw.json")
        print("  python enrich_with_google_places.py stores.json enriched.json --test")
        return 1

    # Parse arguments
    limit = None
    if '--test' in sys.argv:
        limit = 5
        sys.argv.remove('--test')
        print("🧪 TEST MODE: Will only process 5 stores\n")

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'stores_google_enriched.json'

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        return 1

    try:
        return enrich_stores(input_file, output_file, limit=limit)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
