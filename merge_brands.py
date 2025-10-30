#!/usr/bin/env python3
"""
Merge multiple CPG brand store locator datasets into one combined dataset.

This script:
1. Loads multiple enriched JSON files (one per brand)
2. Combines all stores
3. Deduplicates by store ID (Google Places ID)
4. Tracks which brands are available at each store
5. Outputs a single combined JSON file

Usage:
  python merge_brands.py brand1.json brand2.json brand3.json output.json

Example:
  python merge_brands.py alice_enriched.json yolele_enriched.json combined.json
"""

import json
import sys
from datetime import datetime
from collections import Counter


def extract_brand_name(filename):
    """
    Extract brand name from filename.

    Examples:
        alice_enriched.json -> Alice Mushrooms
        yolele_enriched.json -> Yolele
        rooted_fare_enriched.json -> Rooted Fare
    """
    # Remove path and extension
    base = filename.split('/')[-1].replace('_enriched.json', '').replace('_raw.json', '').replace('_google.json', '')

    # Convert to title case and handle special cases
    brand_map = {
        'alice': 'Alice Mushrooms',
        'yolele': 'Yolele',
        'rooted_fare': 'Rooted Fare',
        'rishi_tea': 'Rishi Tea',
        'only_bean': 'The Only Bean'
    }

    return brand_map.get(base, base.replace('_', ' ').title())


def get_store_id(store):
    """
    Get a unique identifier for a store.
    Prioritizes Google Places ID, falls back to Stockist ID.
    """
    # Try Google Places ID first (most reliable for deduplication)
    google_places = store.get('google_places', {})
    google_id = google_places.get('id')
    if google_id:
        return f"google:{google_id}"

    # Fall back to Stockist ID
    stockist_id = store.get('id')
    if stockist_id:
        return f"stockist:{stockist_id}"

    # Last resort: use name + address hash
    name = store.get('name', '')
    address = store.get('address_line_1', '') or google_places.get('formattedAddress', '')
    return f"hash:{hash(name + address)}"


def merge_brands(input_files, output_file):
    """
    Merge multiple brand datasets into one combined file.

    Args:
        input_files (list): List of input JSON file paths
        output_file (str): Output JSON file path
    """
    print("="*80)
    print("MULTI-BRAND STORE DATASET MERGER")
    print("="*80)
    print()

    all_stores = {}  # Dict mapping store_id -> store data
    brand_stats = {}  # Track stats per brand

    # Load each brand dataset
    for idx, filename in enumerate(input_files, 1):
        brand_name = extract_brand_name(filename)
        print(f"[{idx}/{len(input_files)}] Loading {brand_name} from {filename}...")

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            stores = data.get('stores', [])
            actual_stores = [s for s in stores if 'name' in s or 'id' in s]

            print(f"  Found {len(actual_stores)} stores")

            brand_stats[brand_name] = {
                'total_stores': len(actual_stores),
                'new_stores': 0,
                'existing_stores': 0
            }

            # Process each store
            for store in actual_stores:
                store_id = get_store_id(store)

                if store_id in all_stores:
                    # Store already exists - add this brand to the list
                    all_stores[store_id]['brands'].append(brand_name)
                    all_stores[store_id]['brand_count'] += 1
                    brand_stats[brand_name]['existing_stores'] += 1
                else:
                    # New store - add it
                    store['brands'] = [brand_name]
                    store['brand_count'] = 1
                    all_stores[store_id] = store
                    brand_stats[brand_name]['new_stores'] += 1

            print(f"  → {brand_stats[brand_name]['new_stores']} new stores")
            print(f"  → {brand_stats[brand_name]['existing_stores']} duplicate stores (already in dataset)")
            print()

        except Exception as e:
            print(f"  ✗ Error loading {filename}: {e}")
            print()
            continue

    # Convert to list
    merged_stores = list(all_stores.values())

    print("="*80)
    print("MERGE SUMMARY")
    print("="*80)
    print()
    print(f"Total unique stores: {len(merged_stores)}")
    print()

    print("Stores by brand:")
    for brand, stats in brand_stats.items():
        print(f"  {brand:20} - {stats['total_stores']} total ({stats['new_stores']} unique)")
    print()

    # Count stores by number of brands
    brand_count_dist = Counter(s['brand_count'] for s in merged_stores)
    print("Stores by brand count:")
    for count in sorted(brand_count_dist.keys()):
        stores = brand_count_dist[count]
        if count == 1:
            print(f"  Exclusive to 1 brand:  {stores} stores")
        else:
            print(f"  Found in {count} brands:     {stores} stores")
    print()

    # Find most common multi-brand stores
    multi_brand = [s for s in merged_stores if s['brand_count'] > 1]
    if multi_brand:
        print(f"Top multi-brand stores (found in multiple brand locators):")
        multi_brand.sort(key=lambda x: x['brand_count'], reverse=True)
        for store in multi_brand[:10]:
            name = store.get('google_places', {}).get('displayName', {}).get('text', store.get('name', 'Unknown'))
            brands = ', '.join(store['brands'])
            print(f"  {name[:40]:42} - {store['brand_count']} brands ({brands})")
        print()

    # Create output data structure
    output_data = {
        'merged_at': datetime.now().isoformat(),
        'source_files': input_files,
        'total_stores': len(merged_stores),
        'brand_stats': brand_stats,
        'stores': merged_stores
    }

    # Save to file
    print(f"Saving combined dataset to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print()
    print("="*80)
    print("✓ MERGE COMPLETE!")
    print("="*80)
    print()
    print(f"Output: {output_file}")
    print(f"  - {len(merged_stores)} unique stores")
    print(f"  - {len(brand_stats)} brands tracked")
    print(f"  - {len(multi_brand)} stores carry multiple brands")
    print()


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python merge_brands.py <input1.json> <input2.json> ... <output.json>")
        print()
        print("Example:")
        print("  python merge_brands.py alice_enriched.json yolele_enriched.json combined.json")
        return 1

    input_files = sys.argv[1:-1]
    output_file = sys.argv[-1]

    # Validate input files exist
    import os
    for f in input_files:
        if not os.path.exists(f):
            print(f"Error: Input file not found: {f}")
            return 1

    try:
        merge_brands(input_files, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
