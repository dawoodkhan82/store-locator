// Brand Match — analyze a CPG brand website and classify it into the CRM's
// store taxonomy so we can score/filter stores by fit.
//
// Mirrors the /api/analyze-brand endpoint in serve.py so the same CRM code
// works against either a local Python server (dev) or this edge function
// (GitHub Pages / production).
//
// Deploy:
//   supabase secrets set OPENAI_API_KEY="sk-..."
//   supabase functions deploy analyze-brand --no-verify-jwt
//
// --no-verify-jwt makes the function callable without an Instagram login so
// the public CRM on GitHub Pages can use it with only the anon key.

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import OpenAI from "https://esm.sh/openai@4.52.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const MAX_TEXT_LENGTH = 60000;
const FETCH_TIMEOUT_MS = 15000;

// Must match scripts/classify_store_type.py STORE_TYPES (27 entries).
const STORE_TYPES = [
  "Supermarket", "Warehouse Club", "Discount Grocery",
  "Specialty/Gourmet Grocery", "International Grocery", "Independent Grocery",
  "Natural/Organic Market", "Boutique Grocer", "Co-op", "Convenience Store",
  "Coffee Shop/Cafe", "Wine/Beer/Liquor", "Bakery", "Deli/Prepared Foods",
  "Health/Supplement Store", "Gift/Specialty Shop", "Farmers Market",
  "Restaurant/Eatery", "Gas Station/Travel Stop", "Retail/Department Store",
  "Outdoor/Sporting Goods", "Juice/Smoothie Bar", "Butcher/Meat Shop",
  "Pharmacy/Drug Store", "Hotel/Hospitality", "Delivery Service", "Uncategorized",
];

const CATEGORY_VOCAB = [
  "Produce", "Bakery", "Dairy", "Snacks", "Beverages", "Prepared Foods",
  "Catering", "Grocery", "Meat", "Deli", "Health Foods", "Frozen Foods",
  "Seafood", "Meat & Seafood", "Beer & Wine", "Coffee", "Wine",
  "Bulk", "Pet Supplies", "Pizza", "Gifts", "Personal Care",
  "Sandwiches", "Beer", "Vitamins & Body Care", "Condiments", "Cheese",
  "Ice Cream", "Candy", "Household Supplies", "Hot Foods",
  "Fresh & Chilled", "Breakfast", "Local Products", "Floral",
  "Health & Wellness", "Apparel & Gifts", "Liquors",
];

const SPECIALTY_VOCAB = [
  "local", "sustainable", "prepared foods", "organic", "artisanal",
  "gourmet", "curated", "farm-to-table", "plant-based", "gluten-free",
  "non-GMO", "vegan", "small-batch", "international", "fresh",
  "paleo", "keto", "natural", "wellness", "emerging brands",
  "seasonal", "expert advice", "luxury", "premium", "craft",
  "family-owned", "kosher", "handcrafted", "handmade", "fair trade",
  "specialty", "vegetarian", "holistic",
];

const SOCIAL_PATTERNS: Record<string, RegExp> = {
  instagram: /instagram\.com\//i,
  facebook:  /facebook\.com\//i,
  twitter:   /(?:twitter\.com|x\.com)\//i,
  tiktok:    /tiktok\.com\//i,
  youtube:   /youtube\.com\//i,
  linkedin:  /linkedin\.com\//i,
  pinterest: /pinterest\.com\//i,
};

function normalizeUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : "https://" + trimmed;
}

async function fetchPage(url: string): Promise<{
  finalUrl: string;
  title: string;
  text: string;
  links: string[];
}> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(url, {
      headers: { "User-Agent": USER_AGENT, "Accept": "text/html,*/*" },
      redirect: "follow",
      signal: ctl.signal,
    });
  } finally {
    clearTimeout(timer);
  }
  if (!resp.ok) {
    throw new HttpError(`Failed to fetch brand site: HTTP ${resp.status}`, 502);
  }
  const html = await resp.text();

  const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
  const title = titleMatch ? titleMatch[1].trim() : "";

  // Strip scripts/styles and extract plain text.
  const stripped = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, " ");

  const text = stripped
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_TEXT_LENGTH);

  // Collect absolute <a href> links.
  const base = new URL(resp.url);
  const links: string[] = [];
  const hrefRe = /<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = hrefRe.exec(html)) !== null) {
    const href = m[1].trim();
    if (!href || /^(mailto:|tel:|javascript:)/i.test(href)) continue;
    try {
      links.push(new URL(href, base).toString());
    } catch (_) {
      // Skip unparseable hrefs.
    }
  }

  return { finalUrl: resp.url, title, text, links };
}

function extractSocialLinks(links: string[]): Record<string, string> {
  const socials: Record<string, string> = {};
  for (const link of links) {
    for (const [platform, pattern] of Object.entries(SOCIAL_PATTERNS)) {
      if (platform in socials) continue;
      if (pattern.test(link)) {
        const lower = link.toLowerCase();
        if (lower.includes("intent") || lower.includes("/share")) continue;
        socials[platform] = link;
      }
    }
  }
  return socials;
}

type Brand = {
  brandName: string;
  tagline: string;
  description: string;
  productCategories: string[];
  specialties: string[];
  idealStoreTypes: string[];
  keywords: string[];
  priceTier: string;
  targetCustomer: string;
};

async function classifyBrand(
  openai: OpenAI,
  page: { text: string; title: string; links: string[] },
  url: string,
): Promise<Brand> {
  const linksSample = page.links.slice(0, 60).join("\n");
  const prompt = `You are analyzing a CPG (consumer packaged goods) brand website to determine
which types of grocery stores would be the best fit to stock this brand's products.

Brand URL: ${url}
Page Title: ${page.title}

Website Content (cleaned text):
${page.text}

Some links from the site (for context / social detection):
${linksSample}

Return a JSON object with EXACTLY these fields:

1. "brandName": string — the brand's actual name (not the domain).
2. "tagline": string — one short marketing-style phrase describing the brand (max 120 chars).
3. "description": string — 1-2 sentence description of what the brand makes and who it's for (max 300 chars).
4. "productCategories": array of strings — which of these store-side product categories describe
   this brand's products. Pick ONLY from this controlled list, up to 6 most relevant:
   ${JSON.stringify(CATEGORY_VOCAB)}
5. "specialties": array of strings — attributes that describe this brand. Pick ONLY from this
   controlled list, up to 8 most relevant:
   ${JSON.stringify(SPECIALTY_VOCAB)}
6. "idealStoreTypes": array of strings — which types of stores would be the best fit to stock
   this brand. Pick ONLY from this controlled list, ordered best-fit first, up to 5:
   ${JSON.stringify(STORE_TYPES)}
7. "keywords": array of strings — up to 10 freeform keywords/phrases that describe the brand
   (e.g., "cold brew", "single-origin chocolate", "hot sauce"). These will help match to store
   text descriptions.
8. "priceTier": one of "value", "mainstream", "premium", "luxury".
9. "targetCustomer": short phrase describing the target customer (max 120 chars).

Return ONLY the JSON object. If a field can't be determined, use an empty string or empty array.
`;

  const completion = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "system",
        content: "You classify CPG brands into a fixed taxonomy. Respond with valid JSON only.",
      },
      { role: "user", content: prompt },
    ],
    response_format: { type: "json_object" },
    temperature: 0,
    max_tokens: 1200,
  });

  const raw = completion.choices[0]?.message?.content || "{}";
  const data = JSON.parse(raw);

  const categorySet = new Set(CATEGORY_VOCAB);
  const specialtySet = new Set(SPECIALTY_VOCAB);
  const storeTypeSet = new Set(STORE_TYPES);
  const priceTiers = new Set(["value", "mainstream", "premium", "luxury"]);

  return {
    brandName: typeof data.brandName === "string" ? data.brandName : "",
    tagline: typeof data.tagline === "string" ? data.tagline : "",
    description: typeof data.description === "string" ? data.description : "",
    productCategories: Array.isArray(data.productCategories)
      ? data.productCategories.filter((c: unknown) => typeof c === "string" && categorySet.has(c))
      : [],
    specialties: Array.isArray(data.specialties)
      ? data.specialties.filter((s: unknown) => typeof s === "string" && specialtySet.has(s))
      : [],
    idealStoreTypes: Array.isArray(data.idealStoreTypes)
      ? data.idealStoreTypes.filter((t: unknown) => typeof t === "string" && storeTypeSet.has(t))
      : [],
    keywords: Array.isArray(data.keywords)
      ? data.keywords.filter((k: unknown) => typeof k === "string" && k.trim()).slice(0, 10)
      : [],
    priceTier: priceTiers.has(data.priceTier) ? data.priceTier : "mainstream",
    targetCustomer: typeof data.targetCustomer === "string" ? data.targetCustomer : "",
  };
}

class HttpError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) {
    return jsonResponse({ error: "OPENAI_API_KEY is not configured on the server" }, 500);
  }

  try {
    const body = await req.json().catch(() => ({}));
    const rawUrl = (body?.url ?? "").toString();
    const url = normalizeUrl(rawUrl);
    if (!url) {
      return jsonResponse({ error: "Missing 'url' in request body" }, 400);
    }

    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch (_) {
      return jsonResponse({ error: `Invalid URL: ${url}` }, 400);
    }

    const page = await fetchPage(url);
    const socialLinks = extractSocialLinks(page.links);

    const openai = new OpenAI({ apiKey });
    const classification = await classifyBrand(openai, page, url);

    if (!classification.brandName) {
      const host = parsed.hostname.replace(/^www\./, "").split(".")[0];
      classification.brandName = host
        ? host.charAt(0).toUpperCase() + host.slice(1)
        : "Brand";
    }

    return jsonResponse({
      url,
      finalUrl: page.finalUrl,
      fetchedTitle: page.title,
      socialLinks,
      ...classification,
    });
  } catch (e) {
    if (e instanceof HttpError) {
      return jsonResponse({ error: e.message }, e.status);
    }
    console.error("analyze-brand error:", e);
    const message = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    return jsonResponse({ error: message }, 500);
  }
});
