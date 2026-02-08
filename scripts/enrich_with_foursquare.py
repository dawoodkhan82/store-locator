#!/usr/bin/env python3
"""
Foursquare Places API Instagram Enrichment Script

This script enriches already-enriched stores with Instagram profiles from Foursquare Places API.
It only adds Instagram links to stores that don't already have them.

Usage: python enrich_with_foursquare.py <input_json> [output_json]

Examples:
  python enrich_with_foursquare.py all_stores/combined/combined.json
  python enrich_with_foursquare.py stores.json enriched.json --test
"""

import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables (ignore errors if .env file not accessible)
try:
    load_dotenv()
except Exception:
    pass  # Continue without .env file if not accessible

# Foursquare API configuration
FOURSQUARE_API_KEY = os.getenv('FOURSQUARE_API_KEY')
PLACES_SEARCH_URL = 'https://places-api.foursquare.com/places/search'
PLACE_MATCH_URL = 'https://places-api.foursquare.com/places/match'
API_VERSION = '2025-06-17'

# Fields to request from Foursquare API
# Only request minimal fields needed for Instagram lookup
REQUESTED_FIELDS = ','.join([
    'name',
    'location',
    'social_media'
])


def get_store_coordinates(store):
    """
    Extract latitude and longitude from store data.

    Args:
        store (dict): Store data object

    Returns:
        tuple: (lat, lng) or (None, None) if not found
    """
    # Try different coordinate field names
    lat = store.get('lat') or store.get('latitude')
    lng = store.get('lng') or store.get('longitude')

    if lat and lng:
        try:
            return float(lat), float(lng)
        except (ValueError, TypeError):
            pass

    # Try nested location object
    location = store.get('location', {})
    if location:
        lat = location.get('latitude') or location.get('lat')
        lng = location.get('longitude') or location.get('lng')
        if lat and lng:
            try:
                return float(lat), float(lng)
            except (ValueError, TypeError):
                pass

    return None, None


def search_foursquare_place(store_name, lat, lng, address=None, city=None, state=None):
    """
    Search for a store in Foursquare Places API.

    Uses Place Match if we have good coordinates, otherwise falls back to Place Search.

    Args:
        store_name (str): Name of the store
        lat (float): Latitude
        lng (float): Longitude
        address (str): Street address (optional)
        city (str): City name (optional)
        state (str): State/province (optional)

    Returns:
        dict: Foursquare place data or None if not found
    """
    headers = {
        'accept': 'application/json',
        'X-Places-Api-Version': API_VERSION,
        'Authorization': f'Bearer {FOURSQUARE_API_KEY}'
    }

    # Try Place Match first if we have coordinates (more accurate)
    if lat and lng:
        match_params = {
            'name': store_name,
            'll': f"{lat},{lng}",
            'fields': REQUESTED_FIELDS
        }

        # Add address if available
        if address:
            match_params['address'] = address
        if city:
            match_params['city'] = city
        if state:
            match_params['state'] = state

        try:
            response = requests.get(
                PLACE_MATCH_URL,
                params=match_params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('place'):
                    return data['place']
            elif response.status_code == 404:
                # No match found, try search
                pass
            else:
                print(f"    ! Match API returned {response.status_code}")

        except Exception as e:
            print(f"    ! Match request error: {str(e)[:50]}")

    # Fall back to Place Search
    search_params = {
        'query': store_name,
        'fields': REQUESTED_FIELDS,
        'limit': 1
    }

    if lat and lng:
        search_params['ll'] = f"{lat},{lng}"
        search_params['radius'] = 1000  # 1km radius
    elif city and state:
        search_params['near'] = f"{city}, {state}"

    try:
        response = requests.get(
            PLACES_SEARCH_URL,
            params=search_params,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return results[0]
        else:
            print(f"    ! Search API returned {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"    ! Search request error: {str(e)[:50]}")

    return None


def extract_instagram_handle(fsq_data):
    """
    Extract Instagram handle from Foursquare API response and convert to full URL.

    Args:
        fsq_data (dict): Raw Foursquare place data

    Returns:
        str: Instagram profile URL or None if not found
    """
    social_media = fsq_data.get('social_media', {})
    instagram_handle = social_media.get('instagram')
    
    if not instagram_handle:
        return None
    
    # Foursquare returns Instagram as a handle (username without @)
    # Convert to full Instagram profile URL
    handle = instagram_handle.strip().lstrip('@')
    if handle:
        return f"https://www.instagram.com/{handle}/"
    return None


def store_has_instagram(store):
    """
    Check if store already has an Instagram link.

    Args:
        store (dict): Store data object

    Returns:
        bool: True if store has Instagram, False otherwise
    """
    enrichment = store.get('enrichment', {})
    social_links = enrichment.get('socialLinks', {})
    instagram = social_links.get('instagram', '')
    return bool(instagram and instagram.strip())


def enrich_stores(input_file, output_file='stores_foursquare_enriched.json', limit=None):
    """
    Enrich stores with Instagram profiles from Foursquare Places API.
    Only adds Instagram to stores that don't already have one.

    Args:
        input_file (str): Input JSON file with stores
        output_file (str): Output JSON file
        limit (int): Optional limit for testing
    """
    if not FOURSQUARE_API_KEY:
        print("Error: FOURSQUARE_API_KEY not found in .env file")
        print("Add your API key: FOURSQUARE_API_KEY=your_key_here")
        print("\nTo get a Foursquare API key:")
        print("  1. Go to https://foursquare.com/developers/signup")
        print("  2. Create a project and get your API key")
        print("  3. Add it to your .env file")
        return 1

    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("FOURSQUARE PLACES API - INSTAGRAM ENRICHMENT")
    print("=" * 80)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}")
    print(f"Only enriching stores that don't already have Instagram profiles\n")

    # Load input data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle different data structures
    if isinstance(data, dict):
        stores = data.get('stores', []) or data.get('places', [])
    elif isinstance(data, list):
        stores = data
    else:
        print(f"Error: Unexpected data format in {input_file}")
        return 1
    
    total = len(stores)

    if limit:
        stores = stores[:limit]
        print(f"LIMIT MODE: Only processing {limit} stores\n")

    # Filter to only stores without Instagram
    stores_needing_ig = [s for s in stores if not store_has_instagram(s)]
    stores_with_ig = total - len(stores_needing_ig)

    print(f"Total stores: {total}")
    print(f"Stores with Instagram: {stores_with_ig}")
    print(f"Stores needing Instagram: {len(stores_needing_ig)}\n")

    if not stores_needing_ig:
        print("All stores already have Instagram profiles. Nothing to enrich.")
        return 0

    enriched_count = 0
    not_found_count = 0
    skipped_count = 0
    total_instagram_found = 0  # Total Instagram links found (including existing)
    total_social_media_found = 0  # Total social media links found

    # Count existing social media links
    for store in stores:
        enrichment = store.get('enrichment', {})
        social_links = enrichment.get('socialLinks', {})
        if social_links.get('instagram'):
            total_instagram_found += 1
        if social_links.get('facebook') or social_links.get('twitter') or social_links.get('instagram'):
            total_social_media_found += 1

    print(f"Existing social media links:")
    print(f"  - Instagram: {total_instagram_found}")
    print(f"  - Any social media: {total_social_media_found}\n")

    for idx, store in enumerate(stores_needing_ig, 1):
        store_name = store.get('name', 'Unknown') or store.get('displayName', {}).get('text', 'Unknown')
        address = store.get('address_line_1', '') or store.get('address', '') or store.get('formattedAddress', '')
        city = store.get('city', '')
        state = store.get('state', '') or store.get('state_code', '')
        lat, lng = get_store_coordinates(store)

        print(f"[{idx}/{len(stores_needing_ig)}] {store_name}")
        if lat and lng:
            print(f"  Coords: {lat:.4f}, {lng:.4f}")
        elif city or state:
            print(f"  Location: {city}, {state}")

        # Check again if store has Instagram (in case it was added during processing)
        if store_has_instagram(store):
            skipped_count += 1
            print(f"  ⊘ Already has Instagram, skipping")
            continue

        # Search Foursquare
        fsq_data = search_foursquare_place(store_name, lat, lng, address, city, state)

        if fsq_data:
            # Extract Instagram URL
            instagram_url = extract_instagram_handle(fsq_data)

            if instagram_url:
                # Add Instagram to store's enrichment
                if 'enrichment' not in store:
                    store['enrichment'] = {}
                if 'socialLinks' not in store['enrichment']:
                    store['enrichment']['socialLinks'] = {}
                
                store['enrichment']['socialLinks']['instagram'] = instagram_url
                enriched_count += 1
                total_instagram_found += 1
                total_social_media_found += 1
                print(f"  ✓ Added Instagram: {instagram_url}")
            else:
                not_found_count += 1
                print(f"  x No Instagram found on Foursquare")
        else:
            not_found_count += 1
            print(f"  x Not found on Foursquare")

        # Rate limiting - Foursquare allows 50 requests/second but let's be respectful
        time.sleep(0.2)

    # Prepare output - preserve original structure
    if isinstance(data, dict) and 'stores' in data:
        # Update the existing data structure
        data['enriched_at'] = datetime.now().isoformat()
        data['foursquare_enrichment'] = {
            'total_stores': total,
            'stores_with_instagram_before': stores_with_ig,
            'stores_needing_instagram': len(stores_needing_ig),
            'instagram_added': enriched_count,
            'not_found': not_found_count,
            'skipped': skipped_count
        }
        result = data
    else:
        # Create new structure if input was just a list
        result = {
            'source_file': input_file,
            'enriched_at': datetime.now().isoformat(),
            'enrichment_source': 'foursquare_instagram',
            'total_stores': total,
            'stores_with_instagram_before': stores_with_ig,
            'stores_needing_instagram': len(stores_needing_ig),
            'instagram_added': enriched_count,
            'not_found': not_found_count,
            'skipped': skipped_count,
            'stores': stores
        }

    # Save to file
    print(f"\n{'=' * 80}")
    print(f"Saving enriched data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Final count of social media links
    final_instagram_count = 0
    final_social_media_count = 0
    for store in stores:
        enrichment = store.get('enrichment', {})
        social_links = enrichment.get('socialLinks', {})
        if social_links.get('instagram'):
            final_instagram_count += 1
        if social_links.get('facebook') or social_links.get('twitter') or social_links.get('instagram'):
            final_social_media_count += 1

    print(f"\n{'=' * 80}")
    print(f"✓ INSTAGRAM ENRICHMENT COMPLETE!")
    print(f"{'=' * 80}")
    print(f"\nSUMMARY:")
    print(f"  Total stores processed: {total}")
    print(f"  Stores with Instagram (before): {stores_with_ig}")
    print(f"  Stores needing Instagram: {len(stores_needing_ig)}")
    print(f"  Instagram links added: {enriched_count}")
    print(f"  Not found on Foursquare: {not_found_count}")
    if skipped_count > 0:
        print(f"  Skipped (got Instagram during processing): {skipped_count}")
    if len(stores_needing_ig) > 0:
        print(f"  Success rate: {enriched_count/len(stores_needing_ig)*100:.1f}%")
    
    print(f"\nFINAL COUNTS:")
    print(f"  Total Instagram links: {final_instagram_count} ({final_instagram_count/total*100:.1f}% of stores)")
    print(f"  Total social media links: {final_social_media_count} ({final_social_media_count/total*100:.1f}% of stores)")
    print(f"  Instagram links added this run: {enriched_count}")

    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python enrich_with_foursquare.py <input_json> [output_json] [--test]")
        print("\nExamples:")
        print("  python enrich_with_foursquare.py all_stores/combined/combined.json")
        print("  python enrich_with_foursquare.py stores.json enriched.json --test")
        print("\nThis script enriches stores with Instagram profiles from Foursquare.")
        print("It only adds Instagram to stores that don't already have one.")
        return 1

    # Parse arguments
    limit = None
    if '--test' in sys.argv:
        limit = 5
        sys.argv.remove('--test')
        print("TEST MODE: Will only process 5 stores\n")

    input_file = sys.argv[1]

    # Generate output filename
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        # Default: input_foursquare.json
        input_path = Path(input_file)
        output_file = str(input_path.parent / f"{input_path.stem}_foursquare{input_path.suffix}")

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        return 1

    try:
        return enrich_stores(input_file, output_file, limit=limit)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\n x Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
