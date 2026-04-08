#!/usr/bin/env python3
"""
Local viewer server with brand-analysis + add-brand endpoints.

Serves the CRM (index.html + combined.json) on port 8000 and exposes:

    POST /api/analyze-brand   body: {"url": "https://brand.example"}
    POST /api/scrape-brand    body: {"brand_name": "...", "url": "..."}
    POST /api/enrich-brand    body: {"brand_slug": "...", "enrichments": [...]}
    GET  /api/job-status?id=<job_id>
    GET  /api/pricing
    GET  /api/health

Long-running scraping/enrichment is dispatched to background threads and
tracked via in-memory job ids that the frontend polls.
"""

from __future__ import annotations

import json
import os
import sys
import re
import time
import uuid
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urljoin, parse_qs

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


# ── Add-brand workflow: scrape → enrich → combine ────────────────────────────
#
# Long-running work (scraping a brand can take minutes) is dispatched to a
# background thread and tracked through an in-memory JOBS dict. The frontend
# starts a job via POST and then polls GET /api/job-status until status is
# "done" or "failed".

JOBS = {}            # job_id -> dict
JOBS_LOCK = threading.Lock()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DIR              = os.path.join(PROJECT_ROOT, "all_stores", "raw")
PLACES_ENRICHED_DIR  = os.path.join(PROJECT_ROOT, "all_stores", "places_enriched")
WEBSITE_ENRICHED_DIR = os.path.join(PROJECT_ROOT, "all_stores", "website_enriched")

# Per-store cost estimates surfaced in the UI. Numbers come from the inline
# notes in the corresponding enrichment scripts:
#   scripts/enrich_with_geoapify.py:255-260
#   scripts/enrich_websites.py:355-361
#   scripts/enrich_with_google_places.py:203-206
PRICING = {
    "geoapify": {
        "label": "Geoapify",
        "description": "Address, phone, hours, ratings",
        "per_store_usd": 0.0,         # within free tier
        "per_store_credits": 0.2,
        "free_per_day": 3000,         # credits/day, ≈15K stores/day
        "notes": "Free up to ~15,000 stores/day on the Geoapify free plan.",
    },
    "website": {
        "label": "Website (OpenAI)",
        "description": "Product categories, social links, about text",
        "per_store_usd": 0.00225,     # 13K input + 500 output @ gpt-4o-mini
        "notes": "Skips known major chains automatically — actual cost is usually lower.",
    },
    "google_places": {
        "label": "Google Places",
        "description": "Verified address, phone, ratings",
        "per_store_usd": 0.032,       # Text Search New
        "notes": "Most expensive — best for high-value lookups.",
    },
}


def _slugify(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[\s-]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    return text.strip("_")


def _make_job(kind: str, **payload) -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "running",
            "message": "Starting…",
            "started_at": time.time(),
            "finished_at": None,
            "result": None,
            "error": None,
            **payload,
        }
    return job_id


def _update_job(job_id: str, **changes) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(changes)


def _get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _finish_job(job_id: str, status: str, **changes) -> None:
    _update_job(job_id, status=status, finished_at=time.time(), **changes)


def _scrape_brand_worker(job_id: str, brand_name: str, url: str) -> None:
    """Run the scraper in a background thread.

    Imports `scrape_all_stores` lazily so the server starts fast and Selenium
    isn't loaded until somebody actually triggers a scrape.
    """
    try:
        _update_job(job_id, message=f"Detecting platform for {brand_name}…")
        os.makedirs(RAW_DIR, exist_ok=True)

        # Lazy import — avoids loading Selenium etc. at server startup.
        sys.path.insert(0, PROJECT_ROOT)
        import scrape_all_stores  # type: ignore[import-not-found]

        result = scrape_all_stores.scrape_brand(brand_name, url, RAW_DIR)
        if not result.get("success"):
            _finish_job(
                job_id, "failed",
                message=f"All scrapers failed for {brand_name}",
                error="No platform matched or all scrapers returned 0 stores.",
            )
            return

        output_file = result["output_file"]
        store_count = 0
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                stores = data.get("stores") or data.get("places") or []
                store_count = len(stores) if isinstance(stores, list) else int(data.get("total_stores", 0))
        except Exception:
            pass

        brand_slug = _slugify(brand_name)
        _finish_job(
            job_id, "done",
            message=f"Scraped {store_count} stores for {brand_name}",
            result={
                "brand_name": brand_name,
                "brand_slug": brand_slug,
                "scraper": result.get("scraper"),
                "output_file": output_file,
                "store_count": store_count,
            },
        )
    except Exception as e:
        traceback.print_exc()
        _finish_job(job_id, "failed", error=f"{type(e).__name__}: {e}")


def _run_combine() -> None:
    """Re-run combine_all_stores so the new brand shows up in combined.json."""
    sys.path.insert(0, PROJECT_ROOT)
    import combine_all_stores  # type: ignore[import-not-found]
    # combine_all_stores.main() reads CWD-relative paths, so chdir first.
    cwd = os.getcwd()
    try:
        os.chdir(PROJECT_ROOT)
        combine_all_stores.main()
    finally:
        os.chdir(cwd)


def _enrich_brand_worker(job_id: str, brand_slug: str, enrichments: list[str]) -> None:
    """Run the requested enrichments on a single brand, then re-combine."""
    try:
        raw_file = os.path.join(RAW_DIR, f"{brand_slug}.json")
        if not os.path.exists(raw_file):
            _finish_job(job_id, "failed", error=f"Raw file not found: {raw_file}")
            return

        os.makedirs(PLACES_ENRICHED_DIR, exist_ok=True)
        os.makedirs(WEBSITE_ENRICHED_DIR, exist_ok=True)

        # Lazy import the enrichers — they pull in API clients that we'd
        # rather not load until they're actually used.
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

        ran = []

        # Geoapify first (gives addresses + state for downstream enrichers).
        if "geoapify" in enrichments:
            _update_job(job_id, message="Enriching with Geoapify…")
            from enrich_with_geoapify import enrich_stores as geoapify_enrich  # type: ignore
            geoapify_out = os.path.join(PLACES_ENRICHED_DIR, f"{brand_slug}_geoapify.json")
            geoapify_enrich(raw_file, geoapify_out)
            ran.append("geoapify")

        # Google Places next (also produces a places_enriched file).
        if "google_places" in enrichments:
            _update_job(job_id, message="Enriching with Google Places…")
            from enrich_with_google_places import enrich_stores as google_enrich  # type: ignore
            google_out = os.path.join(PLACES_ENRICHED_DIR, f"{brand_slug}_google.json")
            google_enrich(raw_file, google_out)
            ran.append("google_places")

        # Website enrichment runs against the most-enriched input we have so
        # far (it benefits from having website URLs filled in by Geoapify or
        # Google Places).
        if "website" in enrichments:
            _update_job(job_id, message="Enriching websites with OpenAI…")
            from enrich_websites import enrich_stores as website_enrich  # type: ignore
            geoapify_out = os.path.join(PLACES_ENRICHED_DIR, f"{brand_slug}_geoapify.json")
            google_out = os.path.join(PLACES_ENRICHED_DIR, f"{brand_slug}_google.json")
            if "geoapify" in enrichments and os.path.exists(geoapify_out):
                website_input = geoapify_out
            elif "google_places" in enrichments and os.path.exists(google_out):
                website_input = google_out
            else:
                website_input = raw_file
            website_out = os.path.join(WEBSITE_ENRICHED_DIR, f"{brand_slug}_website_enriched.json")
            website_enrich(website_input, website_out)
            ran.append("website")

        _update_job(job_id, message="Re-combining all stores…")
        _run_combine()

        _finish_job(
            job_id, "done",
            message=f"Enrichment complete: {', '.join(ran) if ran else 'no enrichments selected'}",
            result={"brand_slug": brand_slug, "enrichments": ran},
        )
    except Exception as e:
        traceback.print_exc()
        _finish_job(job_id, "failed", error=f"{type(e).__name__}: {e}")


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

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "hasOpenAI": client is not None,
                "service": "store-scraper viewer",
                "supportsAddBrand": True,
            })
            return

        if path == "/api/pricing":
            self._send_json(200, {"pricing": PRICING})
            return

        if path == "/api/job-status":
            qs = parse_qs(parsed.query)
            job_id = (qs.get("id") or [""])[0]
            if not job_id:
                self._send_json(400, {"error": "Missing 'id' query parameter"})
                return
            job = _get_job(job_id)
            if not job:
                self._send_json(404, {"error": f"Job {job_id} not found"})
                return
            self._send_json(200, job)
            return

        return super().do_GET()

    def _handle_analyze_brand(self):
        try:
            body = self._read_json_body()
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

    def _handle_scrape_brand(self):
        try:
            body = self._read_json_body()
            brand_name = (body.get("brand_name") or body.get("brandName") or "").strip()
            url = (body.get("url") or "").strip()
            if not brand_name:
                self._send_json(400, {"error": "Missing 'brand_name' in request body"})
                return
            if not url:
                self._send_json(400, {"error": "Missing 'url' in request body"})
                return

            url = normalize_url(url)
            job_id = _make_job("scrape", brand_name=brand_name, url=url)
            t = threading.Thread(
                target=_scrape_brand_worker,
                args=(job_id, brand_name, url),
                daemon=True,
            )
            t.start()
            self._send_json(202, {"job_id": job_id})
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def _handle_enrich_brand(self):
        try:
            body = self._read_json_body()
            brand_slug = (body.get("brand_slug") or body.get("brandSlug") or "").strip()
            enrichments = body.get("enrichments") or []
            if not brand_slug:
                self._send_json(400, {"error": "Missing 'brand_slug' in request body"})
                return
            if not isinstance(enrichments, list):
                self._send_json(400, {"error": "'enrichments' must be a list"})
                return
            valid = {"geoapify", "website", "google_places"}
            invalid = [e for e in enrichments if e not in valid]
            if invalid:
                self._send_json(400, {
                    "error": f"Unknown enrichment(s): {invalid}. "
                             f"Valid options: {sorted(valid)}",
                })
                return

            job_id = _make_job(
                "enrich",
                brand_slug=brand_slug,
                enrichments=enrichments,
            )
            t = threading.Thread(
                target=_enrich_brand_worker,
                args=(job_id, brand_slug, enrichments),
                daemon=True,
            )
            t.start()
            self._send_json(202, {"job_id": job_id})
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/analyze-brand":
            return self._handle_analyze_brand()
        if path == "/api/scrape-brand":
            return self._handle_scrape_brand()
        if path == "/api/enrich-brand":
            return self._handle_enrich_brand()
        self.send_error(404, "Not Found")


def main():
    if client is None:
        print("WARNING: OPENAI_API_KEY not found in .env — /api/analyze-brand will return 500.")
    print(f"Serving CRM on http://localhost:{PORT}")
    print(f"  Brand analysis:   POST http://localhost:{PORT}/api/analyze-brand")
    print(f"  Add brand:        POST http://localhost:{PORT}/api/scrape-brand")
    print(f"  Enrich brand:     POST http://localhost:{PORT}/api/enrich-brand")
    print(f"  Job status:       GET  http://localhost:{PORT}/api/job-status?id=<id>")
    print(f"  Pricing:          GET  http://localhost:{PORT}/api/pricing")
    print("Press Ctrl+C to stop.")
    server = ThreadingHTTPServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
