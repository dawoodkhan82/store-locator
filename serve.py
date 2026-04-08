#!/usr/bin/env python3
"""
Local viewer server with a brand-analysis endpoint.

Serves the CRM (index.html + combined.json) on port 8000 and exposes:

    POST /api/analyze-brand   body: {"url": "https://brand.example"}

The endpoint fetches the brand site, extracts text + social links, and
uses OpenAI (via .env OPENAI_API_KEY) to classify the brand into the same
category/specialty/storeType taxonomy the CRM already uses, so we can match
it against enriched store records.
"""

import json
import os
import sys
import re
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

# Single source of truth for store types — reused from the store classification pipeline.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from classify_store_type import STORE_TYPES  # type: ignore[import-not-found]  # noqa: E402

load_dotenv()

PORT = int(os.getenv("VIEWER_PORT", "8000"))
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
MAX_TEXT_LENGTH = 60000

CATEGORY_VOCAB = [
    "Produce", "Bakery", "Dairy", "Snacks", "Beverages", "Prepared Foods",
    "Catering", "Grocery", "Meat", "Deli", "Health Foods", "Frozen Foods",
    "Seafood", "Meat & Seafood", "Beer & Wine", "Coffee", "Wine",
    "Bulk", "Pet Supplies", "Pizza", "Gifts", "Personal Care",
    "Sandwiches", "Beer", "Vitamins & Body Care", "Condiments", "Cheese",
    "Ice Cream", "Candy", "Household Supplies", "Hot Foods",
    "Fresh & Chilled", "Breakfast", "Local Products", "Floral",
    "Health & Wellness", "Apparel & Gifts", "Liquors",
]

SPECIALTY_VOCAB = [
    "local", "sustainable", "prepared foods", "organic", "artisanal",
    "gourmet", "curated", "farm-to-table", "plant-based", "gluten-free",
    "non-GMO", "vegan", "small-batch", "international", "fresh",
    "paleo", "keto", "natural", "wellness", "emerging brands",
    "seasonal", "expert advice", "luxury", "premium", "craft",
    "family-owned", "kosher", "handcrafted", "handmade", "fair trade",
    "specialty", "vegetarian", "holistic",
]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def fetch_page(url: str) -> dict:
    """Fetch a page and return cleaned text + link list."""
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    # Get title for brand name fallback
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")

    # Collect absolute links
    base = resp.url
    links = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", "")).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        links.append(urljoin(base, href))

    return {
        "final_url": resp.url,
        "title": title,
        "text": text[:MAX_TEXT_LENGTH],
        "links": links,
    }


SOCIAL_PATTERNS = {
    "instagram": re.compile(r"instagram\.com/", re.I),
    "facebook":  re.compile(r"facebook\.com/", re.I),
    "twitter":   re.compile(r"(?:twitter\.com|x\.com)/", re.I),
    "tiktok":    re.compile(r"tiktok\.com/", re.I),
    "youtube":   re.compile(r"youtube\.com/", re.I),
    "linkedin":  re.compile(r"linkedin\.com/", re.I),
    "pinterest": re.compile(r"pinterest\.com/", re.I),
}


def extract_social_links(links: list) -> dict:
    socials = {}
    for link in links:
        for platform, pattern in SOCIAL_PATTERNS.items():
            if platform in socials:
                continue
            if pattern.search(link):
                # Skip share/intent links
                if "intent" in link.lower() or "/share" in link.lower():
                    continue
                socials[platform] = link
    return socials


def classify_brand_with_openai(page: dict, url: str) -> dict:
    """Use OpenAI to classify the brand into our taxonomy."""
    if client is None:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    text = page["text"]
    title = page["title"]
    links_sample = "\n".join(page["links"][:60])

    prompt = f"""You are analyzing a CPG (consumer packaged goods) brand website to determine
which types of grocery stores would be the best fit to stock this brand's products.

Brand URL: {url}
Page Title: {title}

Website Content (cleaned text):
{text}

Some links from the site (for context / social detection):
{links_sample}

Return a JSON object with EXACTLY these fields:

1. "brandName": string — the brand's actual name (not the domain).

2. "tagline": string — one short marketing-style phrase describing the brand (max 120 chars).

3. "description": string — 1-2 sentence description of what the brand makes and who it's for (max 300 chars).

4. "productCategories": array of strings — which of these store-side product categories describe
   this brand's products. Pick ONLY from this controlled list, up to 6 most relevant:
   {json.dumps(CATEGORY_VOCAB)}

5. "specialties": array of strings — attributes that describe this brand. Pick ONLY from this
   controlled list, up to 8 most relevant:
   {json.dumps(SPECIALTY_VOCAB)}

6. "idealStoreTypes": array of strings — which types of stores would be the best fit to stock
   this brand. Pick ONLY from this controlled list, ordered best-fit first, up to 5:
   {json.dumps(STORE_TYPES)}

7. "keywords": array of strings — up to 10 freeform keywords/phrases that describe the brand
   (e.g., "cold brew", "single-origin chocolate", "hot sauce"). These will help match to store
   text descriptions.

8. "priceTier": one of "value", "mainstream", "premium", "luxury".

9. "targetCustomer": short phrase describing the target customer (max 120 chars).

Return ONLY the JSON object. If a field can't be determined, use an empty string or empty array.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You classify CPG brands into a fixed taxonomy. Respond with valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1200,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    data.setdefault("brandName", "")
    data.setdefault("tagline", "")
    data.setdefault("description", "")
    data["productCategories"] = [c for c in data.get("productCategories", []) if c in CATEGORY_VOCAB]
    data["specialties"] = [s for s in data.get("specialties", []) if s in SPECIALTY_VOCAB]
    data["idealStoreTypes"] = [t for t in data.get("idealStoreTypes", []) if t in STORE_TYPES]
    data["keywords"] = [k for k in data.get("keywords", []) if isinstance(k, str) and k.strip()][:10]
    if data.get("priceTier") not in {"value", "mainstream", "premium", "luxury"}:
        data["priceTier"] = "mainstream"
    data.setdefault("targetCustomer", "")

    return data


def analyze_brand(url: str) -> dict:
    url = normalize_url(url)
    if not url:
        raise ValueError("URL is required")

    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    page = fetch_page(url)
    socials = extract_social_links(page["links"])
    classification = classify_brand_with_openai(page, url)

    if not classification.get("brandName"):
        classification["brandName"] = parsed.netloc.replace("www.", "").split(".")[0].title()

    return {
        "url": url,
        "finalUrl": page["final_url"],
        "fetchedTitle": page["title"],
        "socialLinks": socials,
        **classification,
    }


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("[viewer] " + (format % args) + "\n")

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "hasOpenAI": client is not None,
                "service": "store-scraper viewer",
            })
            return
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/analyze-brand":
            self.send_error(404, "Not Found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
            url = (body.get("url") or "").strip()
            if not url:
                self._send_json(400, {"error": "Missing 'url' in request body"})
                return
            result = analyze_brand(url)
            self._send_json(200, result)
        except requests.HTTPError as e:
            self._send_json(502, {
                "error": f"Failed to fetch brand site: HTTP {e.response.status_code}",
            })
        except requests.RequestException as e:
            self._send_json(502, {"error": f"Failed to fetch brand site: {e}"})
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    if client is None:
        print("WARNING: OPENAI_API_KEY not found in .env — /api/analyze-brand will return 500.")
    print(f"Serving CRM on http://localhost:{PORT}")
    print(f"Brand analysis:   POST http://localhost:{PORT}/api/analyze-brand")
    print("Press Ctrl+C to stop.")
    server = ThreadingHTTPServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
