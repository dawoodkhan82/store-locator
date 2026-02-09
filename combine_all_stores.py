#!/usr/bin/env python3
"""
Combine All Store Data

This script combines store data with the following priority:
1. Use website_enriched files (OpenAI enriched) if available
2. Fall back to places_enriched files (Geoapify/Google Places enriched)
3. Fall back to raw files (scraped store data without enrichment)

Output: all_stores/combined/combined.json
"""

import json
import os
import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Directories
WEBSITE_ENRICHED_DIR = Path('all_stores/website_enriched')
PLACES_ENRICHED_DIR = Path('all_stores/places_enriched')
RAW_DIR = Path('all_stores/raw')
OUTPUT_DIR = Path('all_stores/combined')
OUTPUT_FILE = OUTPUT_DIR / 'combined.json'

# Wholesale CRM CSV file
WHOLESALE_CRM_CSV = Path('Wholesale_CRM_1f5fc65a08aa80e6ac25db4424caaa0a_all.csv')

# Store names that should be combined (base name, then number or city)
STORE_NAMES_TO_COMBINE = [
    'Alfred coffee',
    'Festival foods',
    'Haggen',
    'Harmons',
    'Erewhon',
    'Jewel',
    "Balducci'S",
    'Bel Air',
    'Kowalskis',
    'Mar-Val Foods',
    "Mariano'S",
    "Mccaffrey'S",
    'Nob Hill Foods',
    'Pcc Community Markets',
    'Raleys',
    'Rosauers',
    'Sendiks',
    'The Fresh Market',
    'Union Market',
    'Urm Stores',
    "Woodman'S",
    'ASG Met Fresh'
]

# Military keywords
MILITARY_KEYWORDS = [
    'military', 'navy', 'army', 'air force', 'base', 'afb', 'naval', 
    'usaf', 'usn', 'usmc', 'fort ', 'camp ', 'commissary', 'exchange',
    'px ', 'bx ', 'nco club', 'officers club'
]


def get_brand_name(filename):
    """Extract brand name from filename (remove suffixes)."""
    name = filename.replace('.json', '')
    # Remove suffixes in order (most specific first, then more general)
    # Keep removing until no more suffixes match
    suffixes = ['_website_enriched', '_foursquare', '_geoapify', '_google', '_places', '_enriched']
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                changed = True
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


def extract_coordinates(store):
    """
    Extract latitude and longitude from store data, including enrichment sources.

    Returns tuple of (latitude, longitude) or (None, None) if not found.
    """
    lat = None
    lng = None

    # Check existing top-level coordinates
    if store.get('lat') and store.get('lng'):
        try:
            return float(store['lat']), float(store['lng'])
        except (ValueError, TypeError):
            pass

    if store.get('location'):
        loc = store['location']
        if loc.get('latitude') and loc.get('longitude'):
            try:
                return float(loc['latitude']), float(loc['longitude'])
            except (ValueError, TypeError):
                pass

    # Extract from Geoapify enrichment (GeoJSON format: [lng, lat])
    geoapify = store.get('geoapify', {})
    geometry = geoapify.get('geometry', {})
    coords = geometry.get('coordinates', [])
    if coords and len(coords) >= 2:
        try:
            lng = float(coords[0])
            lat = float(coords[1])
            return lat, lng
        except (ValueError, TypeError):
            pass

    # Extract from Google Places enrichment
    google_places = store.get('google_places', {})
    location = google_places.get('location', {})
    if location.get('latitude') and location.get('longitude'):
        try:
            return float(location['latitude']), float(location['longitude'])
        except (ValueError, TypeError):
            pass

    return None, None


def load_wholesale_crm_csv(csv_path):
    """
    Load wholesale CRM data from CSV file.
    
    Extracts only: Shop Name, Address, IG Link
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        List of store dictionaries with name, address, and instagram fields
    """
    stores = []
    
    if not csv_path.exists():
        print(f"  ⚠ CSV file not found: {csv_path}")
        return stores
    
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
            reader = csv.DictReader(f)
            for row in reader:
                shop_name = row.get('Shop Name', '').strip()
                address = row.get('Address', '').strip()
                ig_link = row.get('IG Link', '').strip()
                
                # Skip rows without a shop name
                if not shop_name:
                    continue
                
                store = {
                    'name': shop_name,
                    'source': 'wholesale_crm',
                    'brand': 'wholesale_crm'
                }
                
                # Add address if present
                if address:
                    store['address_line_1'] = address
                    store['formattedAddress'] = address
                
                # Add Instagram link if present
                if ig_link:
                    store['enrichment'] = {
                        'socialLinks': {
                            'instagram': ig_link
                        }
                    }
                
                stores.append(store)
                
    except Exception as e:
        print(f"  ✗ Error loading CSV: {e}")
    
    return stores


def load_foursquare_instagram_stores(foursquare_file):
    """
    Load Foursquare enriched file and extract stores that have Instagram links.
    
    Args:
        foursquare_file: Path to Foursquare enriched JSON file
        
    Returns:
        List of stores with Instagram links from Foursquare
    """
    stores_with_ig = []
    
    if not foursquare_file.exists():
        return stores_with_ig
    
    try:
        data = load_json_file(foursquare_file)
        if not data:
            return stores_with_ig
        
        # Handle different data structures
        if isinstance(data, dict):
            stores = data.get('stores', []) or data.get('places', [])
        elif isinstance(data, list):
            stores = data
        else:
            stores = []
        
        # Extract stores that have Instagram links
        for store in stores:
            enrichment = store.get('enrichment', {})
            social_links = enrichment.get('socialLinks', {})
            instagram = social_links.get('instagram')
            
            if instagram and instagram.strip():
                # Store has Instagram, include it
                stores_with_ig.append(store)
        
    except Exception as e:
        print(f"  ⚠ Error loading {foursquare_file.name}: {e}")
    
    return stores_with_ig


def normalize_store_name_for_matching(name):
    """
    Normalize store name for fuzzy matching.
    
    - Lowercase
    - Remove punctuation
    - Remove common suffixes (LLC, Inc, Co, etc.)
    - Collapse whitespace
    """
    if not name:
        return ""
    
    normalized = name.lower().strip()
    
    # Remove common business suffixes
    suffixes = [' llc', ' inc', ' co', ' corp', ' ltd', ' company', ' store', ' market', ' shop']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    
    # Remove punctuation
    normalized = re.sub(r'[^\w\s]', '', normalized)
    
    # Collapse whitespace
    normalized = ' '.join(normalized.split())
    
    return normalized


def find_matching_store(crm_store, store_map, name_index):
    """
    Find a matching store in the store_map for a CRM store.
    
    Uses normalized name matching to find existing stores.
    
    Args:
        crm_store: Store dictionary from CRM CSV
        store_map: Dictionary of existing stores (key -> store)
        name_index: Dictionary mapping normalized names to store keys
        
    Returns:
        Matching store key if found, None otherwise
    """
    crm_name = crm_store.get('name', '')
    normalized_crm_name = normalize_store_name_for_matching(crm_name)
    
    if not normalized_crm_name:
        return None
    
    # Check for exact normalized name match
    if normalized_crm_name in name_index:
        return name_index[normalized_crm_name]
    
    # Check for partial matches (CRM name contains existing store name or vice versa)
    for existing_name, store_key in name_index.items():
        if existing_name in normalized_crm_name or normalized_crm_name in existing_name:
            # Only match if significant overlap (at least 5 chars)
            if len(existing_name) >= 5 or len(normalized_crm_name) >= 5:
                return store_key
    
    return None


def build_name_index(store_map):
    """
    Build an index of normalized store names to store keys for fast matching.
    
    Args:
        store_map: Dictionary of stores (key -> store)
        
    Returns:
        Dictionary mapping normalized names to store keys
    """
    name_index = {}
    
    for key, store in store_map.items():
        # Get store name from various fields
        name = (
            store.get('name') or 
            store.get('displayName', {}).get('text') or 
            ''
        )
        
        normalized = normalize_store_name_for_matching(name)
        if normalized and normalized not in name_index:
            name_index[normalized] = key
    
    return name_index


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

    # From address parsing (including raw file format)
    if not country:
        addr = store.get('formattedAddress', '') or store.get('full_address', '') or store.get('address_line_1', '') or ''
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


def is_usa_store(store):
    """
    Check if a store is located in the United States.

    Args:
        store (dict): Store data

    Returns:
        bool: True if store is in USA, False otherwise
    """
    # First, check coordinates to filter out stores with bad country data
    # (e.g., stores labeled "United States" but actually in Asia)
    lat, lng = extract_coordinates(store)
    if lat is not None and lng is not None:
        # USA bounds: longitude must be negative (Americas), latitude 15-72 (includes AK, HI, PR)
        if lng > 0:  # Positive longitude = Eastern hemisphere (Asia, Europe, Africa)
            return False
        if lat < 15 or lat > 72:  # Outside USA latitude range
            return False

    country = store.get('country')

    # Check if country is explicitly United States
    if country == 'United States':
        return True

    # Check if country is unknown but has a valid US state code
    if country in (None, 'Unknown') and store.get('state_code'):
        # Valid 2-letter US state codes
        us_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
            'DC', 'PR', 'VI', 'GU', 'AS', 'MP'  # Include territories
        }
        if store['state_code'].upper() in us_states:
            return True

    return False


def extract_stores(data, source_file):
    """Extract stores array from JSON data and add source brand and enrichment info."""
    # Handle different formats
    if isinstance(data, dict):
        stores = data.get('stores') or data.get('places') or []
        # Get scraped_at from the file metadata (prefer scraped_at, fall back to enriched_at)
        scraped_at = data.get('scraped_at') or data.get('enriched_at')
    elif isinstance(data, list):
        stores = data
        scraped_at = None
    else:
        stores = []
        scraped_at = None

    # Extract brand name from filename
    brand_name = get_brand_name(source_file)

    # Add brand and enrichment info to each store
    for store in stores:
        if not store.get('brand'):
            store['brand'] = brand_name
        if not store.get('source'):
            store['source'] = brand_name

        # Add scraped_at date if available
        if scraped_at and not store.get('scraped_at'):
            store['scraped_at'] = scraped_at

        # Extract coordinates from enrichment data if not already present
        if not store.get('lat') or not store.get('lng'):
            lat, lng = extract_coordinates(store)
            if lat and lng:
                store['lat'] = lat
                store['lng'] = lng
                store['location'] = {
                    'latitude': lat,
                    'longitude': lng
                }

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

    # Set combined brands
    base_store['brands'] = sorted(list(all_brands))

    if len(all_brands) > 0:
        base_store['brand'] = sorted(list(all_brands))[0]

    # Keep the earliest scraped_at date
    existing_date = existing_store.get('scraped_at')
    new_date = new_store.get('scraped_at')
    if existing_date and new_date:
        base_store['scraped_at'] = min(existing_date, new_date)
    elif new_date:
        base_store['scraped_at'] = new_date

    return base_store


def has_instacart_website(store):
    """Check if store has instacart.com as website."""
    website_fields = ['websiteUri', 'url', 'website', 'website_url']
    for field in website_fields:
        value = store.get(field, '')
        if value and 'instacart.com' in str(value).lower():
            return True
    return False


def is_military_site(store):
    """Check if store is a military site."""
    name = str(store.get('name', '') or store.get('displayName', {}).get('text', '')).lower()
    address = str(
        store.get('formattedAddress', '') or 
        store.get('address', '') or 
        store.get('address_line_1', '')
    ).lower()
    
    text_to_check = f"{name} {address}"
    
    for keyword in MILITARY_KEYWORDS:
        if keyword.lower() in text_to_check:
            return True
    
    return False


def get_base_store_name(name):
    """
    Extract base store name, removing numbers, city names, etc.
    For example: "Alfred coffee #5" -> "Alfred coffee"
                 "Alfred coffee Los Angeles" -> "Alfred coffee"
    """
    if not name:
        return ""
    
    name_lower = name.lower().strip()
    
    # Check if name starts with any of the store names to combine
    for store_base in STORE_NAMES_TO_COMBINE:
        store_base_lower = store_base.lower()
        if name_lower.startswith(store_base_lower):
            # Extract the base name (preserve original case from STORE_NAMES_TO_COMBINE)
            base_len = len(store_base)
            if len(name) > base_len:
                # Check if what follows is a number, city indicator, etc.
                remainder = name[base_len:].strip()
                # More strict matching - only combine if there's a clear pattern
                if (re.match(r'^#\s*\d+', remainder) or
                    re.match(r'^(No\.|Store)\s*\d+', remainder, re.IGNORECASE) or
                    re.match(r'^\d+', remainder) or
                    (len(remainder.split()) <= 2 and len(remainder) < 30 and 
                     any(word[0].isupper() for word in remainder.split() if word))):
                    return store_base
            else:
                # Exact match
                return store_base
    
    return name


def combine_duplicate_stores(stores):
    """
    Combine stores that have the same base name (e.g., "Alfred coffee #5", "Alfred coffee LA").
    Keeps the store with the most complete data.
    """
    # Group stores by base name
    stores_by_base = defaultdict(list)
    
    for store in stores:
        name = store.get('name', '') or store.get('displayName', {}).get('text', '')
        base_name = get_base_store_name(name)
        
        if base_name and base_name != name:  # Only combine if we found a base name
            stores_by_base[base_name.lower()].append(store)
        else:
            # Store doesn't match any base name pattern, keep as-is
            stores_by_base[f"__unique__{len(stores_by_base)}"].append(store)
    
    combined_stores = []
    stats = {
        'combined_groups': 0,
        'stores_combined': 0
    }
    
    for base_name, store_group in stores_by_base.items():
        if base_name.startswith('__unique__'):
            # Not a combinable store, keep all
            combined_stores.extend(store_group)
        elif len(store_group) > 1:
            # Multiple stores with same base name - combine them
            stats['combined_groups'] += 1
            stats['stores_combined'] += len(store_group)
            
            # Find the store with most complete data
            best_store = None
            best_score = -1
            
            for store in store_group:
                score = 0
                # Score based on data completeness
                if store.get('enrichment'):
                    score += 10
                if store.get('websiteUri') or store.get('url'):
                    score += 5
                if store.get('phone') or store.get('internationalPhoneNumber'):
                    score += 3
                if store.get('lat') and store.get('lng'):
                    score += 2
                if store.get('address') or store.get('formattedAddress'):
                    score += 1
                
                if score > best_score:
                    best_score = score
                    best_store = store
            
            # Merge brands from all stores
            if best_store:
                all_brands = set()
                for store in store_group:
                    if store.get('brand'):
                        all_brands.add(store['brand'])
                    if store.get('brands'):
                        all_brands.update(store['brands'])
                    if store.get('source'):
                        all_brands.add(store['source'])
                
                if all_brands:
                    best_store['brands'] = sorted(list(all_brands))
                    if not best_store.get('brand') and all_brands:
                        best_store['brand'] = sorted(list(all_brands))[0]
                
                combined_stores.append(best_store)
        else:
            # Only one store with this base name, keep it
            combined_stores.extend(store_group)
    
    return combined_stores, stats


def main():
    print("="*80)
    print("COMBINING ALL STORE DATA")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    store_map = {}
    stats = {
        'website_enriched': 0,
        'places_enriched': 0,
        'raw': 0,
        'total': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'duplicates_merged': 0,
        'unique_locations': 0,
        'foursquare_files': 0,
        'foursquare_stores_processed': 0,
        'foursquare_ig_added': 0
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

    # Get list of brands that have places enrichment
    places_enriched_brands = set()
    if PLACES_ENRICHED_DIR.exists():
        for f in PLACES_ENRICHED_DIR.glob('*.json'):
            brand = get_brand_name(f.name)
            places_enriched_brands.add(brand)

    # Process raw files (for brands not in website_enriched or places_enriched)
    print("\n3. Processing raw stores (fallback for non-enriched brands)...")
    print("-" * 80)

    if RAW_DIR.exists():
        raw_files = sorted(RAW_DIR.glob('*.json'))

        for file_path in raw_files:
            brand = get_brand_name(file_path.name)

            if brand in website_enriched_brands:
                print(f"\n⏭️  Skipping {file_path.name} (already have website enriched version)")
                stats['files_skipped'] += 1
                continue

            if brand in places_enriched_brands:
                print(f"\n⏭️  Skipping {file_path.name} (already have places enriched version)")
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

                stats['raw'] += len(stores)
                stats['files_processed'] += 1
    else:
        print(f"  ⚠ Directory not found: {RAW_DIR}")

    print(f"\n✓ Raw: {stats['raw']} stores")

    # Process Wholesale CRM CSV (add Instagram links and new stores)
    print("\n3.5. Processing Wholesale CRM data...")
    print("-" * 80)

    if WHOLESALE_CRM_CSV.exists():
        print(f"\nLoading: {WHOLESALE_CRM_CSV}")
        crm_stores = load_wholesale_crm_csv(WHOLESALE_CRM_CSV)
        print(f"  → {len(crm_stores)} stores from CSV")

        # Build name index for matching
        name_index = build_name_index(store_map)

        crm_matched = 0
        crm_added = 0
        crm_ig_added = 0

        for crm_store in crm_stores:
            # Try to find matching store
            matching_key = find_matching_store(crm_store, store_map, name_index)

            if matching_key:
                # Merge Instagram link into existing store
                existing_store = store_map[matching_key]

                # Add Instagram link if CRM has one and existing store doesn't
                crm_ig = crm_store.get('enrichment', {}).get('socialLinks', {}).get('instagram')
                if crm_ig:
                    if 'enrichment' not in existing_store:
                        existing_store['enrichment'] = {}
                    if 'socialLinks' not in existing_store['enrichment']:
                        existing_store['enrichment']['socialLinks'] = {}
                    
                    # Only add if existing store doesn't have Instagram
                    if not existing_store['enrichment']['socialLinks'].get('instagram'):
                        existing_store['enrichment']['socialLinks']['instagram'] = crm_ig
                        crm_ig_added += 1

                crm_matched += 1
            else:
                # Add as new store
                key = get_store_key(crm_store)
                if key not in store_map:
                    store_map[key] = crm_store
                    crm_added += 1
                    
                    # Update name index
                    normalized = normalize_store_name_for_matching(crm_store.get('name', ''))
                    if normalized:
                        name_index[normalized] = key

        stats['crm_total'] = len(crm_stores)
        stats['crm_matched'] = crm_matched
        stats['crm_added'] = crm_added
        stats['crm_ig_added'] = crm_ig_added

        print(f"\n✓ CRM Processing complete:")
        print(f"  - Matched to existing stores: {crm_matched}")
        print(f"  - Instagram links added: {crm_ig_added}")
        print(f"  - New stores added: {crm_added}")
    else:
        print(f"  ⚠ CSV file not found: {WHOLESALE_CRM_CSV}")
        stats['crm_total'] = 0
        stats['crm_matched'] = 0
        stats['crm_added'] = 0
        stats['crm_ig_added'] = 0

    # Process Foursquare enriched files (add Instagram links)
    print("\n3.6. Processing Foursquare Instagram links...")
    print("-" * 80)

    if PLACES_ENRICHED_DIR.exists():
        foursquare_files = sorted(PLACES_ENRICHED_DIR.glob('*_foursquare.json'))
        
        if foursquare_files:
            print(f"  Found {len(foursquare_files)} Foursquare enriched files")
            
            # Build name index for matching
            name_index = build_name_index(store_map)
            
            fsq_ig_added = 0
            fsq_stores_processed = 0
            fsq_files_processed = 0
            
            for foursquare_file in foursquare_files:
                brand = get_brand_name(foursquare_file.name)
                print(f"\n  Processing: {foursquare_file.name} (brand: {brand})")
                
                # Load stores with Instagram from Foursquare file
                fsq_stores = load_foursquare_instagram_stores(foursquare_file)
                
                if not fsq_stores:
                    print(f"    → No stores with Instagram in this file")
                    continue
                
                fsq_stores_processed += len(fsq_stores)
                fsq_files_processed += 1
                
                # Match and merge Instagram links
                file_ig_added = 0
                for fsq_store in fsq_stores:
                    # Try to find matching store by location key first
                    fsq_key = get_store_key(fsq_store)
                    
                    if fsq_key in store_map:
                        # Found by location key
                        existing_store = store_map[fsq_key]
                    else:
                        # Try to find by name
                        matching_key = find_matching_store(fsq_store, store_map, name_index)
                        if matching_key:
                            existing_store = store_map[matching_key]
                        else:
                            # Store not found, skip
                            continue
                    
                    # Add Instagram link if store doesn't have one
                    fsq_ig = fsq_store.get('enrichment', {}).get('socialLinks', {}).get('instagram')
                    if fsq_ig:
                        if 'enrichment' not in existing_store:
                            existing_store['enrichment'] = {}
                        if 'socialLinks' not in existing_store['enrichment']:
                            existing_store['enrichment']['socialLinks'] = {}
                        
                        # Only add if existing store doesn't have Instagram
                        if not existing_store['enrichment']['socialLinks'].get('instagram'):
                            existing_store['enrichment']['socialLinks']['instagram'] = fsq_ig
                            fsq_ig_added += 1
                            file_ig_added += 1
                
                print(f"    → Processed {len(fsq_stores)} stores with Instagram, added {file_ig_added} links")
            
            stats['foursquare_files'] = fsq_files_processed
            stats['foursquare_stores_processed'] = fsq_stores_processed
            stats['foursquare_ig_added'] = fsq_ig_added
            
            print(f"\n✓ Foursquare Processing complete:")
            print(f"  - Files processed: {fsq_files_processed}")
            print(f"  - Stores with Instagram processed: {fsq_stores_processed}")
            print(f"  - Instagram links added: {fsq_ig_added}")
        else:
            print(f"  → No Foursquare enriched files found")
            stats['foursquare_files'] = 0
            stats['foursquare_stores_processed'] = 0
            stats['foursquare_ig_added'] = 0
    else:
        print(f"  ⚠ Directory not found: {PLACES_ENRICHED_DIR}")
        stats['foursquare_files'] = 0
        stats['foursquare_stores_processed'] = 0
        stats['foursquare_ig_added'] = 0

    # Convert map to list
    all_stores_unfiltered = list(store_map.values())

    # Filter to USA stores only
    print("\n4. Filtering to USA stores only...")
    print("-" * 80)
    all_stores = [store for store in all_stores_unfiltered if is_usa_store(store)]
    non_usa_count = len(all_stores_unfiltered) - len(all_stores)
    print(f"  Removed {non_usa_count} non-USA stores")
    print(f"  Keeping {len(all_stores)} USA stores")

    stats['non_usa_filtered'] = non_usa_count

    # Filter out instacart.com stores
    print("\n4.5. Filtering out instacart.com stores...")
    print("-" * 80)
    stores_before_instacart = len(all_stores)
    all_stores = [store for store in all_stores if not has_instacart_website(store)]
    instacart_count = stores_before_instacart - len(all_stores)
    stats['instacart_filtered'] = instacart_count
    if instacart_count > 0:
        print(f"  Removed {instacart_count:,} stores with instacart.com websites")
    print(f"  Keeping {len(all_stores):,} stores")

    # Filter out military sites
    print("\n4.6. Filtering out military sites...")
    print("-" * 80)
    stores_before_military = len(all_stores)
    all_stores = [store for store in all_stores if not is_military_site(store)]
    military_count = stores_before_military - len(all_stores)
    stats['military_filtered'] = military_count
    if military_count > 0:
        print(f"  Removed {military_count:,} military sites")
    print(f"  Keeping {len(all_stores):,} stores")

    # Combine stores with same base name
    print("\n4.7. Combining stores with same base name...")
    print("-" * 80)
    all_stores, combine_stats = combine_duplicate_stores(all_stores)
    stats['combined_groups'] = combine_stats['combined_groups']
    stats['combined_stores'] = combine_stats['stores_combined'] - combine_stats['combined_groups']
    if combine_stats['combined_groups'] > 0:
        print(f"  Combined {combine_stats['combined_groups']:,} groups")
        print(f"  → {combine_stats['stores_combined']:,} stores were combined into {combine_stats['combined_groups']:,} stores")
    print(f"  Keeping {len(all_stores):,} stores")

    stats['unique_locations'] = len(all_stores)
    stats['total'] = len(all_stores)

    # Enrichment stats no longer tracked
    enrichment_counts = {
        'geoapify': 0,
        'google_places': 0,
        'openai': 0,
        'none': 0
    }

    # Create output directory if needed
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save combined data
    print("\n5. Saving combined data...")
    print("-" * 80)

    combined_data = {
        'metadata': {
            'combined_at': datetime.now().isoformat(),
            'total_stores': stats['total'],
            'usa_only': True,
            'non_usa_filtered': stats['non_usa_filtered'],
            'website_enriched_stores': stats['website_enriched'],
            'places_enriched_stores': stats['places_enriched'],
            'raw_stores': stats['raw'],
            'files_processed': stats['files_processed'],
            'files_skipped': stats['files_skipped'],
            'enrichment_counts': enrichment_counts,
            'sources': {
                'website_enriched_dir': str(WEBSITE_ENRICHED_DIR),
                'places_enriched_dir': str(PLACES_ENRICHED_DIR),
                'raw_dir': str(RAW_DIR)
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
    print(f"Raw stores:                  {stats['raw']:,}")
    print(f"{'─'*80}")
    print(f"Total stores loaded:         {stats['website_enriched'] + stats['places_enriched'] + stats['raw']:,}")
    print(f"Duplicates merged:           {stats['duplicates_merged']:,}")
    print(f"Non-USA stores filtered:     {stats['non_usa_filtered']:,}")
    print(f"Instacart stores filtered:   {stats.get('instacart_filtered', 0):,}")
    print(f"Military sites filtered:     {stats.get('military_filtered', 0):,}")
    if stats.get('combined_groups', 0) > 0:
        print(f"Stores combined:             {stats.get('combined_stores', 0):,}")
    print(f"{'─'*80}")
    print(f"Final USA stores:            {stats['unique_locations']:,}")
    print(f"\nWholesale CRM integration:")
    print(f"  - CSV stores processed:    {stats.get('crm_total', 0):,}")
    print(f"  - Matched existing stores: {stats.get('crm_matched', 0):,}")
    print(f"  - Instagram links added:   {stats.get('crm_ig_added', 0):,}")
    print(f"  - New stores added:        {stats.get('crm_added', 0):,}")
    print(f"\nFoursquare Instagram integration:")
    print(f"  - Files processed:         {stats.get('foursquare_files', 0):,}")
    print(f"  - Stores with IG processed: {stats.get('foursquare_stores_processed', 0):,}")
    print(f"  - Instagram links added:   {stats.get('foursquare_ig_added', 0):,}")
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
