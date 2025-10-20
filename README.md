# Manhattan Specialty Grocery Store Scraper

A comprehensive Google Maps Places API scraper designed to find specialty grocery stores similar to Pop Up Grocer across all of Manhattan.

## Features

- **Area-Based Search**: Divides Manhattan into 12 neighborhood chunks for comprehensive coverage
- **Multiple Search Queries**: Uses 8 different search queries to find various types of specialty stores
- **Pagination Support**: Retrieves up to 60 results per query (3 pages × 20 results)
- **Smart Deduplication**: Automatically removes duplicate places across all searches
- **Rate Limiting**: Built-in delays to respect API rate limits
- **Progress Tracking**: Real-time progress updates during execution

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Key

1. Get a Google Maps API key from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Enable the **Places API (New)** for your project
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Add your API key to `.env`:
   ```
   GOOGLE_MAPS_API_KEY=your_actual_api_key_here
   ```

## Usage

### Step 1: Run the Scraper

```bash
python scraper.py
```

The script will:
1. Search all 12 Manhattan areas
2. Run 8 queries per area (96 total search combinations)
3. Retrieve up to 60 results per query with pagination
4. Deduplicate and save results to a timestamped JSON file

### Step 2: Visualize Results

Generate an interactive HTML viewer to explore your results:

```bash
python generate_viewer.py manhattan_specialty_grocery_stores_YYYYMMDD_HHMMSS.json
```

Or simply run without arguments to auto-detect the latest JSON file:

```bash
python generate_viewer.py
```

This will:
- Automatically read your Google Maps API key from `.env`
- Generate `viewer.html` with your data and API key embedded
- Automatically open it in your default browser
- Provide both List View and Map View for exploring results

**Note:** The script automatically uses the same Google Maps API key from your `.env` file, so the map view will work immediately!

## Manhattan Areas Covered

1. Lower Manhattan (FiDi, Battery Park, Tribeca)
2. SoHo, NoHo, Little Italy, Nolita
3. Greenwich Village, West Village
4. East Village, Lower East Side
5. Chelsea, Flatiron, Gramercy
6. Midtown West (Hell's Kitchen, Times Square)
7. Midtown East (Murray Hill, Tudor City)
8. Upper West Side South (59th-86th St)
9. Upper West Side North (86th-110th St)
10. Upper East Side South (59th-86th St)
11. Upper East Side North (86th-96th St)
12. Harlem, East Harlem

## Search Queries

The script searches for:
- Curated specialty grocery stores with emerging brands
- Independent specialty grocery stores with small brands
- Boutique grocery stores with artisanal products
- Better-for-you specialty grocery stores
- Curated food marketplaces with independent brands
- Specialty food stores with independent brands
- Artisanal food marketplaces
- Gourmet grocery stores with emerging brands

## Output

Results are saved to: `manhattan_specialty_grocery_stores_YYYYMMDD_HHMMSS.json`

### Output Format

```json
{
  "timestamp": "2025-10-19T12:34:56.789012",
  "total_results": 150,
  "places": [
    {
      "id": "ChIJ...",
      "displayName": {"text": "Store Name"},
      "formattedAddress": "123 Main St, New York, NY 10001",
      "rating": 4.5,
      "userRatingCount": 234,
      "businessStatus": "OPERATIONAL",
      "location": {"latitude": 40.7589, "longitude": -73.9851},
      "types": ["grocery_store", "food"],
      "googleMapsUri": "https://maps.google.com/?cid=...",
      "websiteUri": "https://example.com",
      "internationalPhoneNumber": "+1 212-555-0123"
    }
  ]
}
```

## Interactive Viewer

The HTML viewer (`viewer.html`) provides an intuitive way to explore your results:

### Features

**📋 List View**
- Grid layout of all stores with key information
- Search by name or address
- Filter by minimum rating (4+, 3+, 2+ stars)
- Sort by name, rating, or review count
- Click any store card for detailed modal with full info

**🗺️ Map View**
- Interactive Google Maps showing all store locations
- Color-coded markers by rating:
  - 🟢 Green: 4+ stars
  - 🟡 Yellow: 3-4 stars
  - 🔴 Red: Below 3 stars
- Click markers to see store info window
- Zoom and pan across Manhattan

**Store Details Modal**
- Complete contact information
- Ratings and reviews
- Direct links to Google Maps
- Store categories and types
- Geographic coordinates

### Using the Viewer

1. Generate with: `python generate_viewer.py`
2. API key is automatically loaded from your `.env` file
3. Opens automatically in your browser
4. Both list and map views work immediately
5. Fully self-contained - share the HTML file with anyone (they'll need internet for the map)

## Performance

- **Total searches**: 96 (12 areas × 8 queries)
- **Max results per query**: 60 (with pagination)
- **Theoretical max results**: ~5,760 (before deduplication)
- **Estimated runtime**: 3-5 minutes (with 1.5s delays between requests)

## API Costs

Each search request counts toward your Google Maps API usage:
- Pricing tier depends on fields requested (Basic, Advanced, Preferred)
- Current configuration uses fields across all tiers
- Monitor your usage in [Google Cloud Console](https://console.cloud.google.com/)

## Customization

### Adjust Search Parameters

Edit `scraper.py` to modify:

- **Delay between requests**: Change `delay` parameter in `main()` (default: 1.5 seconds)
- **Max pages per query**: Change `max_pages` in `search_with_pagination()` (default: 3)
- **Areas**: Add/remove/modify `MANHATTAN_AREAS` list
- **Queries**: Add/remove/modify `SEARCH_QUERIES` list

### Add More Field Data

Edit the `FIELD_MASK` constant to request additional fields:

```python
FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    # Add more fields here
    'places.regularOpeningHours',
    'places.priceLevel',
    'places.reviews'
])
```

See [available fields documentation](https://developers.google.com/maps/documentation/places/web-service/place-data-fields) for all options.

## Troubleshooting

### "API key not found" error
- Ensure `.env` file exists with `GOOGLE_MAPS_API_KEY=your_key`
- Check that python-dotenv is installed

### Rate limiting errors
- Increase the `delay` parameter in `main()`
- Reduce number of queries or areas

### No results found
- Verify your API key has Places API (New) enabled
- Check Google Cloud Console for API errors
- Try broader search queries

## License

MIT
