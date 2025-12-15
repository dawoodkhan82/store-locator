#!/usr/bin/env python3
"""
Batch Website Enrichment Script

This script processes all raw store JSON files through the website enrichment pipeline.
It automatically skips brands that have already been website enriched.

Usage: python batch_enrich_websites.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Directories
RAW_DIR = Path("all_stores/raw")
WEBSITE_ENRICHED_DIR = Path("all_stores/website_enriched")
ENRICH_SCRIPT = Path("scripts/enrich_websites.py")

def get_brand_name(filename):
    """Extract brand name from filename (remove .json extension)"""
    return filename.replace('.json', '')

def is_already_enriched(brand_name):
    """Check if brand has already been website enriched"""
    # Check for various possible output filename patterns
    possible_names = [
        f"{brand_name}_website_enriched.json",
        f"{brand_name}_enriched.json",
        f"{brand_name}.json"
    ]

    for name in possible_names:
        if (WEBSITE_ENRICHED_DIR / name).exists():
            return True
    return False

def main():
    """Process all raw JSON files through website enrichment"""

    # Check if directories exist
    if not RAW_DIR.exists():
        print(f"❌ Error: Raw directory not found: {RAW_DIR}")
        sys.exit(1)

    if not ENRICH_SCRIPT.exists():
        print(f"❌ Error: Enrichment script not found: {ENRICH_SCRIPT}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    WEBSITE_ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    # Get all raw JSON files
    raw_files = sorted(RAW_DIR.glob("*.json"))

    if not raw_files:
        print(f"❌ No JSON files found in {RAW_DIR}")
        sys.exit(1)

    print("=" * 80)
    print("BATCH WEBSITE ENRICHMENT")
    print("=" * 80)
    print(f"Total brands found: {len(raw_files)}")
    print()

    # Filter out already enriched brands
    brands_to_process = []
    brands_skipped = []

    for raw_file in raw_files:
        brand_name = get_brand_name(raw_file.name)

        if is_already_enriched(brand_name):
            brands_skipped.append(brand_name)
            print(f"⏭️  Skipping {brand_name} (already enriched)")
        else:
            brands_to_process.append((brand_name, raw_file))

    print()
    print(f"📊 Summary:")
    print(f"   - Already enriched: {len(brands_skipped)}")
    print(f"   - To process: {len(brands_to_process)}")
    print()

    if not brands_to_process:
        print("✅ All brands already enriched!")
        return

    # Confirm before processing
    print("Brands to process:")
    for i, (brand_name, _) in enumerate(brands_to_process, 1):
        print(f"   {i}. {brand_name}")
    print()

    response = input(f"Process {len(brands_to_process)} brands? (y/n): ").strip().lower()
    if response != 'y':
        print("❌ Aborted by user")
        return

    print()
    print("=" * 80)
    print("STARTING ENRICHMENT")
    print("=" * 80)

    # Process each brand
    success_count = 0
    error_count = 0

    for i, (brand_name, raw_file) in enumerate(brands_to_process, 1):
        print()
        print(f"[{i}/{len(brands_to_process)}] Processing: {brand_name}")
        print("-" * 80)

        # Construct output filename
        output_file = WEBSITE_ENRICHED_DIR / f"{brand_name}_website_enriched.json"

        # Run enrichment script
        try:
            result = subprocess.run(
                [sys.executable, str(ENRICH_SCRIPT), str(raw_file), str(output_file)],
                capture_output=False,  # Show output in real-time
                text=True
            )

            if result.returncode == 0:
                print(f"✅ Successfully enriched: {brand_name}")
                success_count += 1
            else:
                print(f"❌ Failed to enrich: {brand_name} (exit code: {result.returncode})")
                error_count += 1

        except Exception as e:
            print(f"❌ Error processing {brand_name}: {e}")
            error_count += 1

        print("-" * 80)

    # Final summary
    print()
    print("=" * 80)
    print("ENRICHMENT COMPLETE")
    print("=" * 80)
    print(f"✅ Success: {success_count}")
    print(f"❌ Errors: {error_count}")
    print(f"⏭️  Skipped: {len(brands_skipped)}")
    print(f"📊 Total: {len(raw_files)}")
    print()

    if success_count > 0:
        print(f"📁 Enriched files saved to: {WEBSITE_ENRICHED_DIR}")

if __name__ == "__main__":
    main()
