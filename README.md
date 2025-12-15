# Store Locator Viewer

A lightweight, standalone HTML viewer for browsing store data with a clean Notion-like interface.

## Features

- **Zero dependencies** - Just one HTML file, no build process needed
- **Dynamic JSON loading** - Loads data on-demand, supports 10k+ stores
- **Multiple ways to load data**:
  - Default: Automatically loads from `../all_stores/combined/combined.json`
  - URL parameter: `?file=path/to/your/data.json`
  - File picker: Click "Load different file" in the header
  - Drag & drop: Upload any JSON file
- **Notion-style design** - Clean, minimal, professional
- **Real-time search** - Filter by name, address, categories, or specialties
- **Responsive** - Works on desktop, tablet, and mobile

## Usage

### Option 1: Open Directly
Simply open `index.html` in your browser. It will automatically try to load `../all_stores/combined/combined.json`.

### Option 2: Specify a File via URL
```
file:///path/to/viewer/index.html?file=../all_stores/combined/combined.json
```

### Option 3: Use a Local Server
For better performance with large files, use a local server:

```bash
# Using Python
cd viewer
python3 -m http.server 8000

# Then open: http://localhost:8000?file=../all_stores/combined/combined.json
```

### Option 4: Load Any JSON File
Click "Load different file" in the header and select any compatible JSON file.

## JSON Format

The viewer supports multiple formats:

### Format 1: Stores array
```json
{
  "stores": [
    {
      "name": "Store Name",
      "address_line_1": "123 Main St",
      "city": "City",
      "state": "ST",
      "postal_code": "12345",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "phone": "+1-555-123-4567",
      "website": "https://example.com",
      "enrichment": {
        "productCategories": ["Organic", "Vegan"],
        "specialties": ["Local", "Sustainable"],
        "socialLinks": {
          "instagram": "https://instagram.com/...",
          "facebook": "https://facebook.com/..."
        }
      }
    }
  ]
}
```

### Format 2: Places array (Google Places format)
```json
{
  "places": [
    {
      "displayName": { "text": "Store Name" },
      "formattedAddress": "123 Main St, City, ST 12345",
      "location": {
        "latitude": 40.7128,
        "longitude": -74.0060
      },
      "rating": 4.5,
      "userRatingCount": 100,
      "websiteUri": "https://example.com",
      "internationalPhoneNumber": "+1 555-123-4567"
    }
  ]
}
```

## No More generate_viewer.py Needed!

The old Python script that generated massive HTML files is no longer necessary. This standalone viewer:

- ✅ Loads JSON dynamically (no embedded data)
- ✅ Handles 10k+ stores without performance issues
- ✅ Works offline (just needs the JSON file accessible)
- ✅ Can load different files without regenerating HTML
- ✅ Smaller file size (~40KB vs potentially 10MB+ with embedded data)

## Development

To modify the viewer, just edit `index.html`. All styles and JavaScript are contained in one file for maximum portability.

## Browser Compatibility

Works in all modern browsers:
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
