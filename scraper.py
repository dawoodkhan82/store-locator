import os
import json
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
API_ENDPOINT = 'https://places.googleapis.com/v1/places:searchText'

FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    'places.formattedAddress',
    'places.rating',
    'places.userRatingCount',
    'places.businessStatus',
    'places.location',
    'places.types',
    'places.googleMapsUri',
    'places.websiteUri',
    'places.internationalPhoneNumber'
])

SEARCH_QUERIES = [
    "curated specialty grocery stores emerging brands",
    "independent specialty grocery stores small brands",
    "boutique grocery stores artisanal products",
    "better-for-you specialty grocery stores",
    "curated food marketplace independent brands",
    "specialty food stores independent brands",
    "artisanal food marketplace",
    "gourmet grocery emerging brands"
]

MANHATTAN_AREAS = [
    {
        "name": "Lower Manhattan (FiDi, Battery Park, Tribeca)",
        "sw": (40.7000, -74.0200),
        "ne": (40.7200, -74.0050)
    },
    {
        "name": "SoHo, NoHo, Little Italy, Nolita",
        "sw": (40.7200, -74.0080),
        "ne": (40.7280, -73.9900)
    },
    {
        "name": "Greenwich Village, West Village",
        "sw": (40.7280, -74.0100),
        "ne": (40.7380, -73.9950)
    },
    {
        "name": "East Village, Lower East Side",
        "sw": (40.7200, -73.9950),
        "ne": (40.7330, -73.9750)
    },
    {
        "name": "Chelsea, Flatiron, Gramercy",
        "sw": (40.7380, -74.0100),
        "ne": (40.7480, -73.9800)
    },
    {
        "name": "Midtown West (Hell's Kitchen, Times Square)",
        "sw": (40.7480, -74.0020),
        "ne": (40.7680, -73.9750)
    },
    {
        "name": "Midtown East (Murray Hill, Tudor City)",
        "sw": (40.7480, -73.9800),
        "ne": (40.7680, -73.9650)
    },
    {
        "name": "Upper West Side South (59th-86th St)",
        "sw": (40.7680, -73.9920),
        "ne": (40.7880, -73.9650)
    },
    {
        "name": "Upper West Side North (86th-110th St)",
        "sw": (40.7880, -73.9920),
        "ne": (40.8050, -73.9550)
    },
    {
        "name": "Upper East Side South (59th-86th St)",
        "sw": (40.7650, -73.9700),
        "ne": (40.7780, -73.9500)
    },
    {
        "name": "Upper East Side North (86th-96th St)",
        "sw": (40.7780, -73.9650),
        "ne": (40.7880, -73.9450)
    },
    {
        "name": "Harlem, East Harlem",
        "sw": (40.8000, -73.9650),
        "ne": (40.8300, -73.9350)
    }
]


def search_grocery_stores(query, location_restriction=None, page_size=20, page_token=None):
    """
    Search for grocery stores using the Google Maps Text Search API.

    Args:
        query (str): The search query text
        location_restriction (dict): Optional location restriction rectangle
        page_size (int): Number of results per page (max 20)
        page_token (str): Token for pagination to get next page

    Returns:
        dict: Response containing 'places' list and optional 'nextPageToken'
    """
    if not API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY not found in environment variables")

    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': API_KEY,
        'X-Goog-FieldMask': FIELD_MASK
    }

    payload = {
        'textQuery': query,
        'pageSize': min(page_size, 20)
    }

    if location_restriction:
        payload['locationRestriction'] = location_restriction

    if page_token:
        payload['pageToken'] = page_token

    try:
        response = requests.post(API_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        return data

    except requests.exceptions.HTTPError as e:
        print(f"  HTTP Error: {e}")
        if response.text:
            print(f"  Response: {response.text}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"  Request Error: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"  JSON Decode Error: {e}")
        print(f"  Response text: {response.text}")
        raise


def search_with_pagination(query, location_restriction=None, max_pages=3):
    """
    Search with pagination to get up to 60 results (3 pages × 20 results).

    Args:
        query (str): The search query text
        location_restriction (dict): Optional location restriction rectangle
        max_pages (int): Maximum number of pages to retrieve (default 3 for 60 results)

    Returns:
        list: Combined list of places from all pages
    """
    all_places = []
    page_token = None
    page_num = 1

    while page_num <= max_pages:
        try:
            data = search_grocery_stores(
                query=query,
                location_restriction=location_restriction,
                page_size=20,
                page_token=page_token
            )

            places = data.get('places', [])
            all_places.extend(places)

            page_token = data.get('nextPageToken')

            if not page_token:
                break

            page_num += 1

            if page_token:
                time.sleep(0.5)

        except Exception as e:
            print(f"  Warning: Page {page_num} failed - {e}")
            break

    return all_places


def deduplicate_places(all_places):
    """
    Remove duplicate places based on their ID.

    Args:
        all_places (list): List of place dictionaries from multiple queries

    Returns:
        list: Deduplicated list of places
    """
    seen_ids = set()
    unique_places = []

    for place in all_places:
        place_id = place.get('id')
        if place_id and place_id not in seen_ids:
            seen_ids.add(place_id)
            unique_places.append(place)

    return unique_places


def create_location_restriction(sw_lat, sw_lng, ne_lat, ne_lng):
    """
    Create a locationRestriction rectangle for the API.

    Args:
        sw_lat (float): Southwest corner latitude
        sw_lng (float): Southwest corner longitude
        ne_lat (float): Northeast corner latitude
        ne_lng (float): Northeast corner longitude

    Returns:
        dict: Location restriction rectangle
    """
    return {
        "rectangle": {
            "low": {
                "latitude": sw_lat,
                "longitude": sw_lng
            },
            "high": {
                "latitude": ne_lat,
                "longitude": ne_lng
            }
        }
    }


def search_area_comprehensive(area, queries, delay=1.5):
    """
    Search a single area with all queries using pagination.

    Args:
        area (dict): Area dictionary with name, sw, and ne coordinates
        queries (list): List of search query strings
        delay (float): Delay between API calls in seconds

    Returns:
        list: All places found in this area
    """
    area_name = area['name']
    sw_lat, sw_lng = area['sw']
    ne_lat, ne_lng = area['ne']

    location_restriction = create_location_restriction(sw_lat, sw_lng, ne_lat, ne_lng)

    print("\n" + "="*80)
    print(f"Searching: {area_name}")
    print("="*80)

    area_places = []

    for i, query in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {query}...", end=" ", flush=True)

        try:
            places = search_with_pagination(
                query=query,
                location_restriction=location_restriction,
                max_pages=3
            )

            area_places.extend(places)
            print(f"✓ {len(places)} results")
            if i < len(queries):
                time.sleep(delay)

        except Exception as e:
            print(f"✗ Error: {e}")
            continue

    return area_places


def search_all_areas(areas, queries, delay=1.5):
    """
    Search all Manhattan areas with all queries.

    Args:
        areas (list): List of area dictionaries
        queries (list): List of search query strings
        delay (float): Delay between API calls in seconds

    Returns:
        list: Deduplicated list of all places found
    """
    all_places = []
    total_combinations = len(areas) * len(queries)

    print("\n" + "#"*80)
    print("COMPREHENSIVE MANHATTAN SEARCH")
    print(f"Areas: {len(areas)} | Queries: {len(queries)} | Total searches: {total_combinations}")
    print("#"*80)

    for area_idx, area in enumerate(areas, 1):
        print(f"\n[AREA {area_idx}/{len(areas)}]")

        area_places = search_area_comprehensive(area, queries, delay)
        all_places.extend(area_places)

        unique_so_far = len(deduplicate_places(all_places))
        print(f"  Area results: {len(area_places)} | Running total: {len(all_places)} | Unique: {unique_so_far}")

    unique_places = deduplicate_places(all_places)

    print("\n" + "#"*80)
    print("SEARCH COMPLETE")
    print(f"Total results: {len(all_places)} | Unique places: {len(unique_places)}")
    print("#"*80 + "\n")

    return unique_places


def save_results(places, filename='grocery_stores.json'):
    """
    Save the search results to a JSON file.

    Args:
        places (list): List of place dictionaries
        filename (str): Output filename
    """
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_results': len(places),
        'places': places
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Results saved to {filename}")


def print_summary(places):
    """
    Print a summary of the search results.

    Args:
        places (list): List of place dictionaries
    """
    print("\n" + "="*80)
    print("SEARCH RESULTS SUMMARY")
    print("="*80 + "\n")

    for i, place in enumerate(places, 1):
        display_name = place.get('displayName', {}).get('text', 'N/A')
        address = place.get('formattedAddress', 'N/A')
        rating = place.get('rating', 'N/A')
        rating_count = place.get('userRatingCount', 'N/A')
        business_status = place.get('businessStatus', 'N/A')

        print(f"{i}. {display_name}")
        print(f"   Address: {address}")
        print(f"   Rating: {rating} ({rating_count} reviews)")
        print(f"   Status: {business_status}")

        if 'googleMapsUri' in place:
            print(f"   Maps: {place['googleMapsUri']}")

        print()


def main():
    """Main function to run comprehensive Manhattan area-based search."""

    print("\n" + "="*80)
    print("GOOGLE MAPS PLACES API - MANHATTAN SPECIALTY GROCERY FINDER")
    print("Finding stores similar to Pop Up Grocer across all Manhattan neighborhoods")
    print("="*80)

    start_time = datetime.now()

    try:
        places = search_all_areas(
            areas=MANHATTAN_AREAS,
            queries=SEARCH_QUERIES,
            delay=1.5
        )

        if not places:
            print("\nNo results found.")
            return 0

        print_summary(places)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'manhattan_specialty_grocery_stores_{timestamp}.json'
        save_results(places, filename=filename)

        end_time = datetime.now()
        duration = end_time - start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)

        print(f"\nExecution time: {minutes}m {seconds}s")
        print("\nScript completed successfully!")

    except KeyboardInterrupt:
        print("\n\nScript interrupted by user.")
        return 1
    except Exception as e:
        print(f"\nError occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
