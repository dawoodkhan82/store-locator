#!/usr/bin/env python3
"""
Batch Foursquare Enrichment Script

This script processes all raw store JSON files and enriches them with
Foursquare Places API data (website, Instagram, social media, etc.)

Usage: python batch_enrich_foursquare.py [--test] [--brand BRAND_NAME]

Options:
  --test          Only process 5 stores per file (for testing)
  --brand NAME    Only process a specific brand
  --force         Re-process even if already enriched

Output: all_stores/foursquare_enriched/<brand>_foursquare.json
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from scripts.enrich_with_foursquare import enrich_stores

# Directories
RAW_DIR = Path("all_stores/raw")
OUTPUT_DIR = Path("all_stores/foursquare_enriched")


def get_brand_name(filename):
    """Extract brand name from filename."""
    return filename.replace('.json', '')


def is_already_enriched(brand_name):
    """Check if brand has already been Foursquare enriched."""
    output_file = OUTPUT_DIR / f"{brand_name}_foursquare.json"
    return output_file.exists()


def main():
    print("=" * 80)
    print("BATCH FOURSQUARE ENRICHMENT")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Parse arguments
    test_mode = '--test' in sys.argv
    force_mode = '--force' in sys.argv
    target_brand = None

    if '--brand' in sys.argv:
        brand_idx = sys.argv.index('--brand')
        if brand_idx + 1 < len(sys.argv):
            target_brand = sys.argv[brand_idx + 1]
            print(f"Target brand: {target_brand}\n")

    if test_mode:
        print("TEST MODE: Only processing 5 stores per file\n")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get list of raw files
    if not RAW_DIR.exists():
        print(f"Error: Raw directory not found: {RAW_DIR}")
        return 1

    raw_files = sorted(RAW_DIR.glob("*.json"))

    if not raw_files:
        print(f"No JSON files found in {RAW_DIR}")
        return 1

    print(f"Found {len(raw_files)} raw store files\n")

    # Track results
    success_count = 0
    error_count = 0
    skipped_count = 0

    for file_path in raw_files:
        brand_name = get_brand_name(file_path.name)

        # Filter by target brand if specified
        if target_brand and brand_name != target_brand:
            continue

        # Skip if already enriched (unless force mode)
        if not force_mode and is_already_enriched(brand_name):
            print(f"[SKIP] {brand_name} - already enriched")
            skipped_count += 1
            continue

        print(f"\n{'=' * 80}")
        print(f"Processing: {brand_name}")
        print(f"{'=' * 80}")

        output_file = OUTPUT_DIR / f"{brand_name}_foursquare.json"

        try:
            limit = 5 if test_mode else None
            result = enrich_stores(str(file_path), str(output_file), limit=limit)

            if result == 0:
                success_count += 1
                print(f"\n[OK] {brand_name} enriched successfully")
            else:
                error_count += 1
                print(f"\n[ERROR] {brand_name} enrichment failed")

        except Exception as e:
            error_count += 1
            print(f"\n[ERROR] {brand_name}: {str(e)}")

    # Summary
    print(f"\n{'=' * 80}")
    print("BATCH ENRICHMENT SUMMARY")
    print(f"{'=' * 80}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Total: {len(raw_files)}")
    print()

    if success_count > 0:
        print(f"Enriched files saved to: {OUTPUT_DIR}")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    exit(main())
