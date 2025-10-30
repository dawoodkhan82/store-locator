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


def generate_html(data, output_file='index.html'):
    """Generate the HTML viewer with embedded data."""

    # Support both data structures: Manhattan stores (places) and Stockist stores (stores)
    if 'places' in data:
        places = data.get('places', [])
    elif 'stores' in data:
        # Transform Stockist stores to match Manhattan format
        places = []
        for store in data.get('stores', []):
            google_places = store.get('google_places', {})

            # Create a normalized format matching Manhattan stores
            normalized = {
                'id': google_places.get('id', store.get('id')),
                'displayName': google_places.get('displayName', {'text': store.get('name', 'Unknown')}),
                'formattedAddress': google_places.get('formattedAddress',
                    f"{store.get('address_line_1', '')}, {store.get('city', '')}, {store.get('state', '')} {store.get('postal_code', '')}".strip()),
                'location': google_places.get('location', {
                    'latitude': float(store.get('latitude', 0)),
                    'longitude': float(store.get('longitude', 0))
                }),
                'rating': google_places.get('rating'),
                'userRatingCount': google_places.get('userRatingCount'),
                'websiteUri': google_places.get('websiteUri', store.get('website')),
                'internationalPhoneNumber': google_places.get('internationalPhoneNumber', store.get('phone')),
                'businessStatus': google_places.get('businessStatus'),
                'types': google_places.get('types', []),
                'googleMapsUri': google_places.get('googleMapsUri'),
                'enrichment': store.get('enrichment', {}),
                # Keep original Stockist data
                'stockist_data': {
                    'filters': store.get('filters', []),
                    'city': store.get('city'),
                    'state': store.get('state')
                }
            }
            places.append(normalized)
    else:
        print("Error: No 'places' or 'stores' key found in data")
        return

    # Note: Chain store filtering (Whole Foods, Target, etc.) now happens during scraping
    # to avoid wasting API credits. No filtering needed here.

    timestamp = data.get('timestamp', data.get('enriched_at', ''))
    total_results = len(places)

    # Determine title based on data source
    if 'stores' in data:
        title = "Stockist Store Locator Results"
        header_title = "Store Locator Results"
    else:
        title = "Manhattan Specialty Grocery Stores"
        header_title = "Manhattan Specialty Grocery Stores"

    # Convert data to JSON string for embedding
    places_json = json.dumps(places, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .store-row {{
            transition: background-color 0.2s ease;
            cursor: pointer;
        }}
        .store-row:hover {{
            background-color: #f3f4f6 !important;
        }}
        table {{
            border-collapse: separate;
            border-spacing: 0;
        }}
        th {{
            position: sticky;
            top: 0;
            background-color: #1f2937;
            color: white;
            z-index: 10;
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
        #apiKeyPrompt {{
            display: none;
            position: fixed;
            z-index: 2000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.7);
            justify-content: center;
            align-items: center;
        }}
        #apiKeyPrompt.active {{
            display: flex;
        }}
    </style>
</head>
<body class="bg-gray-50">
    <!-- API Key Prompt Modal -->
    <div id="apiKeyPrompt">
        <div class="bg-white rounded-lg shadow-xl p-8 max-w-md">
            <h2 class="text-2xl font-bold text-gray-900 mb-4">Google Maps API Key Required</h2>
            <p class="text-gray-600 mb-4">To use the map view, please enter your Google Maps API key:</p>
            <input
                type="text"
                id="apiKeyInput"
                placeholder="Enter your API key..."
                class="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
            <div class="flex gap-3">
                <button
                    onclick="saveApiKey()"
                    class="flex-1 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 font-medium"
                >
                    Enter
                </button>
                <button
                    onclick="skipApiKey()"
                    class="flex-1 bg-gray-200 text-gray-700 px-6 py-2 rounded-lg hover:bg-gray-300 font-medium"
                >
                    Skip
                </button>
            </div>
            <p class="text-xs text-gray-500 mt-4">
                Your API key is stored locally in your browser and never sent anywhere.
                <a href="https://developers.google.com/maps/documentation/javascript/get-api-key" target="_blank" class="text-blue-600 hover:underline">
                    Get a free API key
                </a>
            </p>
        </div>
    </div>
    <!-- Header -->
    <header class="bg-white shadow-sm sticky top-0 z-50">
        <div class="max-w-full mx-auto px-4 py-4">
            <h1 class="text-2xl font-bold text-gray-900">{header_title}</h1>
            <p class="text-sm text-gray-600 mt-1">
                {total_results} stores found
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
    <div class="max-w-full mx-auto px-4 pb-4">
        <div class="bg-white rounded-lg shadow-sm p-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <input
                    type="text"
                    id="searchInput"
                    placeholder="Search by name, address, categories, or specialties..."
                    class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    onkeyup="filterStores()"
                >
                <select id="sortBy" class="px-4 py-2 border border-gray-300 rounded-lg" onchange="sortStores()">
                    <option value="name">Sort by Name</option>
                    <option value="address">Sort by Address</option>
                </select>
            </div>
        </div>
    </div>

    <!-- List View (Table) -->
    <div id="listView" class="max-w-full mx-auto px-4 pb-8">
        <div class="bg-white rounded-lg shadow-sm overflow-x-auto">
            <table id="storeTable" class="min-w-full divide-y divide-gray-200">
                <thead>
                    <tr>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Store Name</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Address</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Categories</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Specialties</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Social</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Website</th>
                        <th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">Phone</th>
                    </tr>
                </thead>
                <tbody id="storeTableBody" class="bg-white divide-y divide-gray-200">
                    <!-- Table rows will be inserted here -->
                </tbody>
            </table>
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
        let mapsLoaded = false;

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {{
            renderStores(STORES_DATA);
        }});

        // Save API key to localStorage and load Google Maps
        function saveApiKey() {{
            const apiKey = document.getElementById('apiKeyInput').value.trim();
            if (!apiKey) {{
                alert('Please enter an API key');
                return;
            }}

            // Save to localStorage
            localStorage.setItem('googleMapsApiKey', apiKey);

            // Hide prompt
            document.getElementById('apiKeyPrompt').classList.remove('active');

            // Load Google Maps
            loadGoogleMaps(apiKey);
        }}

        // Skip API key entry
        function skipApiKey() {{
            document.getElementById('apiKeyPrompt').classList.remove('active');

            // Switch to map view but show message instead of map
            const listView = document.getElementById('listView');
            const mapView = document.getElementById('mapView');
            const listTab = document.getElementById('listTab');
            const mapTab = document.getElementById('mapTab');

            listView.classList.add('hidden');
            mapView.classList.remove('hidden');
            listTab.classList.remove('active');
            mapTab.classList.add('active');

            // Show message in map container
            document.getElementById('map').innerHTML = `
                <div class="flex items-center justify-center h-full bg-gray-100 rounded-lg">
                    <div class="text-center p-8">
                        <h3 class="text-xl font-bold text-gray-700 mb-4">Map View Unavailable</h3>
                        <p class="text-gray-600 mb-6">You skipped entering a Google Maps API key.</p>
                        <p class="text-gray-600 mb-6">The map cannot be displayed, but you can still use the List View to browse all stores.</p>
                        <button
                            onclick="switchView('list')"
                            class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 mr-2"
                        >
                            Go to List View
                        </button>
                        <button
                            onclick="document.getElementById('apiKeyPrompt').classList.add('active')"
                            class="bg-gray-300 text-gray-700 px-6 py-2 rounded-lg hover:bg-gray-400"
                        >
                            Enter API Key
                        </button>
                    </div>
                </div>
            `;
        }}

        // Dynamically load Google Maps script
        function loadGoogleMaps(apiKey) {{
            if (mapsLoaded) {{
                initMap();
                return;
            }}

            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${{apiKey}}&libraries=marker`;
            script.async = true;
            script.defer = true;
            script.onload = function() {{
                mapsLoaded = true;
                initMap();
            }};
            script.onerror = function() {{
                alert('Failed to load Google Maps. Please check your API key and try again.');
                localStorage.removeItem('googleMapsApiKey');
            }};
            document.head.appendChild(script);
        }}

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
                // Check if we have an API key
                const savedKey = localStorage.getItem('googleMapsApiKey');

                if (!savedKey && !mapsLoaded) {{
                    // Show API key prompt
                    document.getElementById('apiKeyPrompt').classList.add('active');
                    return;
                }}

                listView.classList.add('hidden');
                mapView.classList.remove('hidden');
                listTab.classList.remove('active');
                mapTab.classList.add('active');

                // Initialize map if not already done
                if (!map && mapsLoaded) {{
                    initMap();
                }} else if (!mapsLoaded && savedKey) {{
                    loadGoogleMaps(savedKey);
                }}
            }}
        }}

        // Render store table rows
        function renderStores(stores) {{
            const tableBody = document.getElementById('storeTableBody');
            const noResults = document.getElementById('noResults');
            const tableContainer = document.getElementById('storeTable').parentElement;

            if (stores.length === 0) {{
                tableContainer.classList.add('hidden');
                noResults.classList.remove('hidden');
                return;
            }}

            tableContainer.classList.remove('hidden');
            noResults.classList.add('hidden');

            tableBody.innerHTML = stores.map((store, index) => {{
                const name = store.displayName?.text || 'Unknown';
                const address = store.formattedAddress || 'No address';
                const phone = store.internationalPhoneNumber || '-';
                const website = store.websiteUri || '';

                // Enrichment data
                const enrichment = store.enrichment || {{}};
                const productCategories = enrichment.productCategories || [];
                const specialties = enrichment.specialties || [];
                const socialLinks = enrichment.socialLinks || {{}};

                // Build social links HTML with SVG icons
                const socialIcons = [];
                if (socialLinks.instagram) socialIcons.push('<a href="' + socialLinks.instagram + '" target="_blank" class="hover:opacity-80" title="Instagram"><svg class="w-5 h-5" fill="currentColor" style="color: #E4405F;" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg></a>');
                if (socialLinks.facebook) socialIcons.push('<a href="' + socialLinks.facebook + '" target="_blank" class="hover:opacity-80" title="Facebook"><svg class="w-5 h-5" fill="currentColor" style="color: #1877F2;" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></a>');
                if (socialLinks.twitter) socialIcons.push('<a href="' + socialLinks.twitter + '" target="_blank" class="hover:opacity-80" title="Twitter/X"><svg class="w-5 h-5" fill="currentColor" style="color: #000000;" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>');
                if (socialLinks.tiktok) socialIcons.push('<a href="' + socialLinks.tiktok + '" target="_blank" class="hover:opacity-80" title="TikTok"><svg class="w-5 h-5" fill="currentColor" style="color: #000000;" viewBox="0 0 24 24"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 5 20.1a6.34 6.34 0 0 0 10.86-4.43v-7a8.16 8.16 0 0 0 4.77 1.52v-3.4a4.85 4.85 0 0 1-1-.1z"/></svg></a>');

                const rowColor = index % 2 === 0 ? 'bg-white' : 'bg-gray-50';

                return `
                    <tr class="store-row ${{rowColor}}" onclick='showStoreDetails(${{JSON.stringify(store).replace(/'/g, "&apos;")}})'>
                        <td class="px-4 py-3 text-sm font-medium text-gray-900">${{name}}</td>
                        <td class="px-4 py-3 text-sm text-gray-600">${{address.substring(0, 50)}}${{address.length > 50 ? '...' : ''}}</td>
                        <td class="px-4 py-3 text-sm">
                            <div class="flex flex-wrap gap-1">
                                ${{productCategories.slice(0, 3).map(c => `<span class="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded">${{c}}</span>`).join('')}}
                                ${{productCategories.length > 3 ? `<span class="text-xs text-gray-500">+${{productCategories.length - 3}}</span>` : ''}}
                            </div>
                        </td>
                        <td class="px-4 py-3 text-sm">
                            <div class="flex flex-wrap gap-1">
                                ${{specialties.slice(0, 3).map(s => `<span class="px-2 py-0.5 bg-green-100 text-green-800 text-xs rounded">${{s}}</span>`).join('')}}
                                ${{specialties.length > 3 ? `<span class="text-xs text-gray-500">+${{specialties.length - 3}}</span>` : ''}}
                            </div>
                        </td>
                        <td class="px-4 py-3 text-sm">
                            <div class="flex gap-2">
                                ${{socialIcons.join('')}}
                            </div>
                        </td>
                        <td class="px-4 py-3 text-sm">
                            ${{website ? `<a href="${{website}}" target="_blank" class="text-blue-600 hover:underline" onclick="event.stopPropagation()">🔗 Link</a>` : '-'}}
                        </td>
                        <td class="px-4 py-3 text-sm text-gray-600">${{phone}}</td>
                    </tr>
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

            // Enriched data
            const editorialSummary = store.editorialSummary?.text || '';
            const generativeSummary = store.generativeSummary?.overview?.text || '';
            const reviews = store.reviews || [];
            const enrichment = store.enrichment || {{}};
            const productCategories = enrichment.productCategories || [];
            const aboutText = enrichment.aboutText || '';
            const specialties = enrichment.specialties || [];
            const socialLinks = enrichment.socialLinks || {{}};

            const modalContent = `
                <h2 class="text-2xl font-bold text-gray-900 mb-4">${{name}}</h2>

                ${{generativeSummary ? `
                <div class="mb-4 p-3 bg-blue-50 border-l-4 border-blue-500 rounded">
                    <p class="text-sm text-gray-700"><strong>✨ AI Summary:</strong> ${{generativeSummary}}</p>
                </div>
                ` : ''}}

                ${{editorialSummary ? `
                <div class="mb-4 p-3 bg-gray-50 rounded">
                    <p class="text-sm text-gray-700">${{editorialSummary}}</p>
                </div>
                ` : ''}}

                <div class="space-y-4">
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

                    ${{Object.keys(socialLinks).length > 0 ? `
                    <div>
                        <span class="font-semibold text-gray-700 block mb-2">Social Media:</span>
                        <div class="flex flex-wrap gap-3">
                            ${{socialLinks.instagram ? `<a href="${{socialLinks.instagram}}" target="_blank" class="flex items-center gap-1 hover:opacity-80" title="Instagram"><svg class="w-5 h-5" fill="currentColor" style="color: #E4405F;" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg><span class="text-sm">Instagram</span></a>` : ''}}
                            ${{socialLinks.facebook ? `<a href="${{socialLinks.facebook}}" target="_blank" class="flex items-center gap-1 hover:opacity-80" title="Facebook"><svg class="w-5 h-5" fill="currentColor" style="color: #1877F2;" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg><span class="text-sm">Facebook</span></a>` : ''}}
                            ${{socialLinks.twitter ? `<a href="${{socialLinks.twitter}}" target="_blank" class="flex items-center gap-1 hover:opacity-80" title="Twitter/X"><svg class="w-5 h-5" fill="currentColor" style="color: #000000;" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg><span class="text-sm">Twitter/X</span></a>` : ''}}
                            ${{socialLinks.tiktok ? `<a href="${{socialLinks.tiktok}}" target="_blank" class="flex items-center gap-1 hover:opacity-80" title="TikTok"><svg class="w-5 h-5" fill="currentColor" style="color: #000000;" viewBox="0 0 24 24"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 5 20.1a6.34 6.34 0 0 0 10.86-4.43v-7a8.16 8.16 0 0 0 4.77 1.52v-3.4a4.85 4.85 0 0 1-1-.1z"/></svg><span class="text-sm">TikTok</span></a>` : ''}}
                        </div>
                    </div>
                    ` : ''}}

                    ${{specialties.length > 0 ? `
                    <div>
                        <span class="font-semibold text-gray-700 block mb-2">Specialties:</span>
                        <div class="flex flex-wrap gap-2">
                            ${{specialties.map(s => `<span class="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">${{s}}</span>`).join('')}}
                        </div>
                    </div>
                    ` : ''}}

                    ${{productCategories.length > 0 ? `
                    <div>
                        <span class="font-semibold text-gray-700 block mb-2">Product Categories:</span>
                        <div class="flex flex-wrap gap-2">
                            ${{productCategories.map(c => `<span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">${{c}}</span>`).join('')}}
                        </div>
                    </div>
                    ` : ''}}

                    ${{aboutText ? `
                    <div>
                        <span class="font-semibold text-gray-700 block mb-2">About:</span>
                        <p class="text-gray-600 text-sm">${{aboutText}}</p>
                    </div>
                    ` : ''}}

                    ${{reviews.length > 0 ? `
                    <div>
                        <span class="font-semibold text-gray-700 block mb-2">Recent Reviews:</span>
                        <div class="space-y-3 max-h-60 overflow-y-auto">
                            ${{reviews.slice(0, 3).map(r => `
                                <div class="border-l-2 border-gray-300 pl-3">
                                    <div class="flex items-center gap-2 mb-1">
                                        <span class="font-medium text-sm">${{r.authorAttribution?.displayName || 'Anonymous'}}</span>
                                        <span class="text-yellow-500 text-sm">${{'⭐'.repeat(r.rating || 0)}}</span>
                                    </div>
                                    <p class="text-gray-600 text-sm">${{r.text?.text?.substring(0, 200) || ''}}${{r.text?.text?.length > 200 ? '...' : ''}}</p>
                                </div>
                            `).join('')}}
                        </div>
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

            filteredStores = STORES_DATA.filter(store => {{
                const name = (store.displayName?.text || '').toLowerCase();
                const address = (store.formattedAddress || '').toLowerCase();

                // Search in enrichment data
                const enrichment = store.enrichment || {{}};
                const categories = (enrichment.productCategories || []).join(' ').toLowerCase();
                const specialties = (enrichment.specialties || []).join(' ').toLowerCase();
                const aboutText = (enrichment.aboutText || '').toLowerCase();

                const matchesSearch = name.includes(searchTerm) ||
                                    address.includes(searchTerm) ||
                                    categories.includes(searchTerm) ||
                                    specialties.includes(searchTerm) ||
                                    aboutText.includes(searchTerm);

                return matchesSearch;
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
                }} else if (sortBy === 'address') {{
                    const addressA = a.formattedAddress || '';
                    const addressB = b.formattedAddress || '';
                    return addressA.localeCompare(addressB);
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
        print("Usage: python generate_viewer.py <json_file> [output_html]")
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

    # Get optional output filename (default to index.html)
    output_filename = sys.argv[2] if len(sys.argv) > 2 else 'index.html'

    if not os.path.exists(json_file):
        print(f"Error: File not found: {json_file}")
        return 1

    print(f"Loading data from: {json_file}")
    data = load_json_data(json_file)

    print(f"Found {data.get('total_results', 0)} stores")

    output_file = generate_html(data, output_file=output_filename)

    # Open in browser
    print(f"\nOpening {output_file} in your default browser...")
    webbrowser.open('file://' + os.path.abspath(output_file))

    print("\n✓ Done! The viewer should open in your browser.")
    print("\n📝 Note: When you click the Map View tab, you'll be prompted to enter")
    print("   your Google Maps API key. It will be saved in your browser's localStorage.")
    print("   The HTML file does NOT contain any API key - safe to share!")

    return 0


if __name__ == '__main__':
    exit(main())
