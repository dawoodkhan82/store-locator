#!/bin/bash
# Master script to scrape, enrich, and combine 5 CPG brand store locators
#
# Brands: Yolele, Alice Mushrooms, Rooted Fare, Rishi Tea, The Only Bean
#
# Usage: bash scrape_all_brands.sh

set -e  # Exit on any error

# Activate virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"

echo "================================================================================"
echo "MULTI-BRAND STORE LOCATOR PIPELINE"
echo "================================================================================"
echo ""
echo "This will scrape 5 CPG brands, enrich with Google Places + website data,"
echo "and combine into a single deduplicated dataset."
echo ""
echo "Estimated time: ~70 minutes"
echo "Estimated cost: ~\$58 in API credits"
echo ""
read -p "Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Cancelled."
    exit 1
fi

echo ""
echo "================================================================================"
echo "PHASE 1: SCRAPING RAW STORE DATA (5 brands)"
echo "================================================================================"
echo ""

# Alice Mushrooms
# echo "[1/5] Scraping Alice Mushrooms..."
# python3 scrape_stockist_stores.py https://alicemushrooms.com/pages/store-locator alice_raw.json
# echo "✓ Alice Mushrooms complete"
# echo ""

# Rooted Fare
echo "[2/5] Scraping Rooted Fare..."
python3 scrape_stockist_stores.py https://rootedfare.com/pages/store-locator-1 rooted_fare_raw.json
echo "✓ Rooted Fare complete"
echo ""

# Rishi Tea
echo "[3/5] Scraping Rishi Tea..."
python3 scrape_stockist_stores.py https://www.rishi-tea.com/pages/store-locator rishi_tea_raw.json
echo "✓ Rishi Tea complete"
echo ""

# The Only Bean
echo "[4/5] Scraping The Only Bean..."
python3 scrape_stockist_stores.py https://theonlybean.com/pages/find-us only_bean_raw.json
echo "✓ The Only Bean complete"
echo ""

# Yolele (re-scrape with filtering)
echo "[5/5] Scraping Yolele (with filtering)..."
python3 scrape_stockist_stores.py https://yolele.com/pages/store-locator yolele_raw.json
echo "✓ Yolele complete"
echo ""

echo "================================================================================"
echo "PHASE 2: GOOGLE PLACES ENRICHMENT (5 brands)"
echo "================================================================================"
echo ""

# Enrich all 5 brands with Google Places data
# echo "[1/5] Enriching Alice Mushrooms with Google Places..."
# python3 -u enrich_with_google_places.py alice_raw.json alice_google.json < /dev/null
# echo "✓ Alice Mushrooms Google enrichment complete"
# echo ""

echo "[2/5] Enriching Rooted Fare with Google Places..."
python3 -u enrich_with_google_places.py rooted_fare_raw.json rooted_fare_google.json < /dev/null
echo "✓ Rooted Fare Google enrichment complete"
echo ""

echo "[3/5] Enriching Rishi Tea with Google Places..."
python3 -u enrich_with_google_places.py rishi_tea_raw.json rishi_tea_google.json < /dev/null
echo "✓ Rishi Tea Google enrichment complete"
echo ""

echo "[4/5] Enriching The Only Bean with Google Places..."
python3 -u enrich_with_google_places.py only_bean_raw.json only_bean_google.json < /dev/null
echo "✓ The Only Bean Google enrichment complete"
echo ""

echo "[5/5] Enriching Yolele with Google Places..."
python3 -u enrich_with_google_places.py yolele_raw.json yolele_google.json < /dev/null
echo "✓ Yolele Google enrichment complete"
echo ""

echo "================================================================================"
echo "PHASE 3: WEBSITE SCRAPING ENRICHMENT (5 brands)"
echo "================================================================================"
echo ""

# Enrich all 5 brands with website data
# echo "[1/5] Enriching Alice Mushrooms with website data..."
# python3 -u enrich_websites.py alice_google.json alice_enriched.json --yes
# echo "✓ Alice Mushrooms website enrichment complete"
# echo ""

echo "[2/5] Enriching Rooted Fare with website data..."
python3 -u enrich_websites.py rooted_fare_google.json rooted_fare_enriched.json --yes
echo "✓ Rooted Fare website enrichment complete"
echo ""

echo "[3/5] Enriching Rishi Tea with website data..."
python3 -u enrich_websites.py rishi_tea_google.json rishi_tea_enriched.json --yes
echo "✓ Rishi Tea website enrichment complete"
echo ""

echo "[4/5] Enriching The Only Bean with website data..."
python3 -u enrich_websites.py only_bean_google.json only_bean_enriched.json --yes
echo "✓ The Only Bean website enrichment complete"
echo ""

echo "[5/5] Enriching Yolele with website data..."
python3 -u enrich_websites.py yolele_google.json yolele_enriched.json --yes
echo "✓ Yolele website enrichment complete"
echo ""

echo "================================================================================"
echo "PHASE 4: MERGING AND DEDUPLICATING ALL BRANDS"
echo "================================================================================"
echo ""

echo "Merging all 5 brands into combined dataset..."
python3 merge_brands.py \
  # alice_enriched.json \
  rooted_fare_enriched.json \
  rishi_tea_enriched.json \
  only_bean_enriched.json \
  yolele_enriched.json \
  all_brands_combined.json

echo "✓ Merge complete"
echo ""

echo "================================================================================"
echo "PHASE 5: GENERATING HTML VIEWER"
echo "================================================================================"
echo ""

echo "Generating interactive HTML viewer..."
python3 generate_viewer.py all_brands_combined.json all_brands.html
echo "✓ Viewer generated"
echo ""

echo "================================================================================"
echo "✓ PIPELINE COMPLETE!"
echo "================================================================================"
echo ""
echo "Output files:"
echo "  - all_brands_combined.json  (deduplicated dataset with brand tracking)"
echo "  - all_brands.html           (interactive viewer)"
echo ""
echo "Individual brand files available in current directory."
echo ""
