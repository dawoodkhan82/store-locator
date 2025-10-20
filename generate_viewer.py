#!/usr/bin/env python3
"""
Generate an interactive HTML viewer for grocery store search results.

This script reads a JSON file containing store data and generates a self-contained
HTML page with list and map views.
"""

import json
import sys
import os
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def load_json_data(json_file):
    """Load and parse the JSON data file."""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_html(data, output_file='viewer.html'):
    """Generate the HTML viewer with embedded data."""

    # Extract places data
    places = data.get('places', [])
    timestamp = data.get('timestamp', '')
    total_results = data.get('total_results', len(places))

    # Get API key from environment
    api_key = os.getenv('GOOGLE_MAPS_API_KEY', 'YOUR_GOOGLE_MAPS_API_KEY')

    # Calculate statistics
    avg_rating = sum(p.get('rating', 0) for p in places if p.get('rating')) / len([p for p in places if p.get('rating')]) if places else 0

    # Convert data to JSON string for embedding
    places_json = json.dumps(places, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manhattan Specialty Grocery Stores - Viewer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://maps.googleapis.com/maps/api/js?key={api_key}&libraries=marker"></script>
    <style>
        .store-card {{
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        .store-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }}
        .modal.active {{
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .modal-content {{
            background-color: white;
            padding: 2rem;
            border-radius: 12px;
            max-width: 600px;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
        }}
        #map {{
            height: calc(100vh - 180px);
            width: 100%;
            border-radius: 8px;
        }}
        .rating-star {{
            color: #FFC107;
        }}
        .view-tab {{
            transition: all 0.2s;
        }}
        .view-tab.active {{
            background-color: #3B82F6;
            color: white;
        }}
    </style>
</head>
<body class="bg-gray-50">
    <!-- Header -->
    <header class="bg-white shadow-sm sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <h1 class="text-2xl font-bold text-gray-900">Manhattan Specialty Grocery Stores</h1>
            <p class="text-sm text-gray-600 mt-1">
                {total_results} stores found • Average rating: {avg_rating:.1f} ⭐
            </p>
        </div>
    </header>

    <!-- View Tabs -->
    <div class="max-w-7xl mx-auto px-4 py-4">
        <div class="flex gap-2">
            <button onclick="switchView('list')" id="listTab" class="view-tab active px-6 py-2 rounded-lg font-medium">
                📋 List View
            </button>
            <button onclick="switchView('map')" id="mapTab" class="view-tab px-6 py-2 rounded-lg font-medium bg-gray-200">
                🗺️ Map View
            </button>
        </div>
    </div>

    <!-- Search and Filters -->
    <div class="max-w-7xl mx-auto px-4 pb-4">
        <div class="bg-white rounded-lg shadow-sm p-4">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <input
                    type="text"
                    id="searchInput"
                    placeholder="Search by name or address..."
                    class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    onkeyup="filterStores()"
                >
                <select id="ratingFilter" class="px-4 py-2 border border-gray-300 rounded-lg" onchange="filterStores()">
                    <option value="0">All Ratings</option>
                    <option value="4">4+ Stars</option>
                    <option value="3">3+ Stars</option>
                    <option value="2">2+ Stars</option>
                </select>
                <select id="sortBy" class="px-4 py-2 border border-gray-300 rounded-lg" onchange="sortStores()">
                    <option value="name">Sort by Name</option>
                    <option value="rating">Sort by Rating</option>
                    <option value="reviews">Sort by Review Count</option>
                </select>
            </div>
        </div>
    </div>

    <!-- List View -->
    <div id="listView" class="max-w-7xl mx-auto px-4 pb-8">
        <div id="storeGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <!-- Store cards will be inserted here -->
        </div>
        <div id="noResults" class="hidden text-center py-12">
            <p class="text-gray-500 text-lg">No stores found matching your criteria.</p>
        </div>
    </div>

    <!-- Map View -->
    <div id="mapView" class="hidden max-w-7xl mx-auto px-4 pb-8">
        <div id="map"></div>
    </div>

    <!-- Modal for store details -->
    <div id="storeModal" class="modal" onclick="closeModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <button onclick="closeModal()" class="absolute top-4 right-4 text-gray-500 hover:text-gray-700 text-2xl">&times;</button>
            <div id="modalContent">
                <!-- Details will be inserted here -->
            </div>
        </div>
    </div>

    <script>
        // Embedded data
        const STORES_DATA = {places_json};
        let filteredStores = [...STORES_DATA];
        let map = null;
        let markers = [];

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {{
            renderStores(STORES_DATA);
        }});

        // Switch between views
        function switchView(view) {{
            const listView = document.getElementById('listView');
            const mapView = document.getElementById('mapView');
            const listTab = document.getElementById('listTab');
            const mapTab = document.getElementById('mapTab');

            if (view === 'list') {{
                listView.classList.remove('hidden');
                mapView.classList.add('hidden');
                listTab.classList.add('active');
                mapTab.classList.remove('active');
            }} else {{
                listView.classList.add('hidden');
                mapView.classList.remove('hidden');
                listTab.classList.remove('active');
                mapTab.classList.add('active');

                // Initialize map if not already done
                if (!map) {{
                    initMap();
                }}
            }}
        }}

        // Render store cards
        function renderStores(stores) {{
            const grid = document.getElementById('storeGrid');
            const noResults = document.getElementById('noResults');

            if (stores.length === 0) {{
                grid.classList.add('hidden');
                noResults.classList.remove('hidden');
                return;
            }}

            grid.classList.remove('hidden');
            noResults.classList.add('hidden');

            grid.innerHTML = stores.map(store => {{
                const name = store.displayName?.text || 'Unknown';
                const address = store.formattedAddress || 'No address';
                const rating = store.rating || 'N/A';
                const ratingCount = store.userRatingCount || 0;
                const status = store.businessStatus || 'UNKNOWN';
                const statusColor = status === 'OPERATIONAL' ? 'text-green-600' : 'text-red-600';
                const ratingStars = rating !== 'N/A' ? '⭐'.repeat(Math.round(rating)) : '';

                return `
                    <div class="store-card bg-white rounded-lg shadow-sm p-6" onclick='showStoreDetails(${{JSON.stringify(store).replace(/'/g, "&apos;")}})'>
                        <h3 class="font-bold text-lg text-gray-900 mb-2">${{name}}</h3>
                        <p class="text-sm text-gray-600 mb-3">${{address}}</p>
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                                <span class="text-yellow-500">${{ratingStars}}</span>
                                <span class="text-sm font-medium">${{rating}}</span>
                                <span class="text-xs text-gray-500">(${{ratingCount}})</span>
                            </div>
                            <span class="text-xs font-medium ${{statusColor}}">${{status}}</span>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        // Show store details in modal
        function showStoreDetails(store) {{
            const name = store.displayName?.text || 'Unknown';
            const address = store.formattedAddress || 'No address';
            const rating = store.rating || 'N/A';
            const ratingCount = store.userRatingCount || 0;
            const phone = store.internationalPhoneNumber || 'No phone';
            const website = store.websiteUri || '';
            const mapsUri = store.googleMapsUri || '';
            const types = store.types?.join(', ') || 'N/A';
            const lat = store.location?.latitude || 'N/A';
            const lng = store.location?.longitude || 'N/A';
            const status = store.businessStatus || 'UNKNOWN';

            const modalContent = `
                <h2 class="text-2xl font-bold text-gray-900 mb-4">${{name}}</h2>

                <div class="space-y-3">
                    <div>
                        <span class="font-semibold text-gray-700">Rating:</span>
                        <span class="ml-2">${{rating}} ⭐ (${{ratingCount}} reviews)</span>
                    </div>

                    <div>
                        <span class="font-semibold text-gray-700">Address:</span>
                        <p class="text-gray-600 mt-1">${{address}}</p>
                    </div>

                    <div>
                        <span class="font-semibold text-gray-700">Phone:</span>
                        <a href="tel:${{phone}}" class="ml-2 text-blue-600 hover:underline">${{phone}}</a>
                    </div>

                    ${{website ? `
                    <div>
                        <span class="font-semibold text-gray-700">Website:</span>
                        <a href="${{website}}" target="_blank" class="ml-2 text-blue-600 hover:underline">Visit Website</a>
                    </div>
                    ` : ''}}

                    <div>
                        <span class="font-semibold text-gray-700">Status:</span>
                        <span class="ml-2">${{status}}</span>
                    </div>

                    <div>
                        <span class="font-semibold text-gray-700">Categories:</span>
                        <p class="text-gray-600 mt-1 text-sm">${{types}}</p>
                    </div>

                    <div>
                        <span class="font-semibold text-gray-700">Coordinates:</span>
                        <p class="text-gray-600 mt-1 text-sm">${{lat}}, ${{lng}}</p>
                    </div>

                    ${{mapsUri ? `
                    <div class="pt-4">
                        <a href="${{mapsUri}}" target="_blank" class="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
                            View on Google Maps
                        </a>
                    </div>
                    ` : ''}}
                </div>
            `;

            document.getElementById('modalContent').innerHTML = modalContent;
            document.getElementById('storeModal').classList.add('active');
        }}

        // Close modal
        function closeModal(event) {{
            if (!event || event.target.id === 'storeModal') {{
                document.getElementById('storeModal').classList.remove('active');
            }}
        }}

        // Filter stores
        function filterStores() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const minRating = parseFloat(document.getElementById('ratingFilter').value);

            filteredStores = STORES_DATA.filter(store => {{
                const name = (store.displayName?.text || '').toLowerCase();
                const address = (store.formattedAddress || '').toLowerCase();
                const rating = store.rating || 0;

                const matchesSearch = name.includes(searchTerm) || address.includes(searchTerm);
                const matchesRating = rating >= minRating;

                return matchesSearch && matchesRating;
            }});

            sortStores();
        }}

        // Sort stores
        function sortStores() {{
            const sortBy = document.getElementById('sortBy').value;

            filteredStores.sort((a, b) => {{
                if (sortBy === 'name') {{
                    const nameA = a.displayName?.text || '';
                    const nameB = b.displayName?.text || '';
                    return nameA.localeCompare(nameB);
                }} else if (sortBy === 'rating') {{
                    return (b.rating || 0) - (a.rating || 0);
                }} else if (sortBy === 'reviews') {{
                    return (b.userRatingCount || 0) - (a.userRatingCount || 0);
                }}
                return 0;
            }});

            renderStores(filteredStores);
        }}

        // Initialize Google Map
        function initMap() {{
            // Center of Manhattan
            const center = {{ lat: 40.7831, lng: -73.9712 }};

            map = new google.maps.Map(document.getElementById('map'), {{
                zoom: 12,
                center: center,
                styles: [
                    {{
                        featureType: 'poi',
                        elementType: 'labels',
                        stylers: [{{ visibility: 'off' }}]
                    }}
                ]
            }});

            // Add markers
            STORES_DATA.forEach(store => {{
                const position = {{
                    lat: store.location?.latitude || 0,
                    lng: store.location?.longitude || 0
                }};

                if (position.lat && position.lng) {{
                    const rating = store.rating || 0;
                    let markerColor = '#10B981'; // green
                    if (rating < 3) markerColor = '#EF4444'; // red
                    else if (rating < 4) markerColor = '#F59E0B'; // yellow

                    const marker = new google.maps.Marker({{
                        position: position,
                        map: map,
                        title: store.displayName?.text || 'Unknown',
                        icon: {{
                            path: google.maps.SymbolPath.CIRCLE,
                            scale: 8,
                            fillColor: markerColor,
                            fillOpacity: 0.9,
                            strokeColor: 'white',
                            strokeWeight: 2
                        }}
                    }});

                    const infoWindow = new google.maps.InfoWindow({{
                        content: `
                            <div style="padding: 8px;">
                                <h3 style="font-weight: bold; margin-bottom: 4px;">${{store.displayName?.text || 'Unknown'}}</h3>
                                <p style="font-size: 12px; color: #666; margin-bottom: 4px;">${{store.formattedAddress || ''}}</p>
                                <p style="font-size: 12px;">⭐ ${{store.rating || 'N/A'}} (${{store.userRatingCount || 0}} reviews)</p>
                                <button onclick='showStoreDetails(${{JSON.stringify(store).replace(/'/g, "&apos;")}})' style="margin-top: 8px; background: #3B82F6; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;">
                                    View Details
                                </button>
                            </div>
                        `
                    }});

                    marker.addListener('click', () => {{
                        infoWindow.open(map, marker);
                    }});

                    markers.push(marker);
                }}
            }});
        }}
    </script>
</body>
</html>"""

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"HTML viewer generated: {output_file}")
    return output_file


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python generate_viewer.py <json_file>")
        print("\nSearching for JSON files in current directory...")
        json_files = list(Path('.').glob('manhattan_specialty_grocery_stores_*.json'))
        if json_files:
            json_file = str(json_files[0])
            print(f"Found: {json_file}")
        else:
            print("No JSON files found.")
            return 1
    else:
        json_file = sys.argv[1]

    if not os.path.exists(json_file):
        print(f"Error: File not found: {json_file}")
        return 1

    print(f"Loading data from: {json_file}")
    data = load_json_data(json_file)

    print(f"Found {data.get('total_results', 0)} stores")

    output_file = generate_html(data)

    # Check if API key was loaded
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if api_key and api_key != 'YOUR_GOOGLE_MAPS_API_KEY':
        print(f"✓ Google Maps API key loaded from .env")
    else:
        print("⚠ Warning: Google Maps API key not found in .env file")
        print("  The map view will not work without an API key.")
        print("  Add GOOGLE_MAPS_API_KEY to your .env file or edit viewer.html manually.")

    # Open in browser
    print(f"\nOpening {output_file} in your default browser...")
    webbrowser.open('file://' + os.path.abspath(output_file))

    print("\n✓ Done! The viewer should open in your browser.")

    return 0


if __name__ == '__main__':
    exit(main())
