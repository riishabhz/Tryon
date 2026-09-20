"""Live product scraper for UK retailers (women's and men's clothing).

The FastAPI backend calls search() on demand when the user types a query.
A query like "black mens tshirt" is parsed into a gender ("men"), a
clothing type ("tshirts") and leftover filter words ("black"). The type
picks each store's dedicated listing page where one exists (e.g. River
Island's men's T-shirts page); otherwise the broader tops/bottoms page is
fetched and narrowed down by the type's keywords.

Stores come in two kinds:
  * listing stores (M&S, River Island, Seasalt, Zara): a fixed category page
    or feed per gender/type, parsed by PARSERS[store];
  * search stores (H&M, boohoo): the store's own public search service is
    queried with the user's words, filtered by gender (SEARCH_STORES).
Results are cached per URL / query for CACHE_TTL seconds.
"""

# Drip Lab — built by Rishabh Bhardwaj.
# Personal, non-commercial use only. See LICENSE.

import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "identity",
}

STORES = {
    "ms": "M&S",
    "riverisland": "River Island",
    "seasalt": "Seasalt",
    "zara": "Zara",
    "hm": "H&M",
    "boohoo": "boohoo",
}

# Stores to switch off, e.g. DRIPLAB_DISABLED_STORES=zara on a hosted server
# whose IP a store blocks.
for _key in os.getenv("DRIPLAB_DISABLED_STORES", "").split(","):
    STORES.pop(_key.strip(), None)

GENDERS = ["women", "men"]

# Clothing types -> the try-on garment group they belong to.
TYPES = {
    "dresses":  {"label": "Dresses",  "group": "dresses"},
    "tops":     {"label": "Tops",     "group": "tops"},
    "tshirts":  {"label": "T-shirts", "group": "tops"},
    "shirts":   {"label": "Shirts",   "group": "tops"},
    "polos":    {"label": "Polos",    "group": "tops"},
    "knitwear": {"label": "Knitwear", "group": "tops"},
    "hoodies":  {"label": "Hoodies",  "group": "tops"},
    "jeans":    {"label": "Jeans",    "group": "bottoms"},
    "trousers": {"label": "Trousers", "group": "bottoms"},
    "joggers":  {"label": "Joggers",  "group": "bottoms"},
    "shorts":   {"label": "Shorts",   "group": "bottoms"},
    "skirts":   {"label": "Skirts",   "group": "bottoms"},
}

# Listing pages per gender -> type -> store. Verified Sept 2026.
# A missing entry falls back to FALLBACK_TYPE and is then narrowed by
# TYPE_MATCH keywords on the product name.
MS = "https://www.marksandspencer.com"
RI = "https://www.riverisland.com"
SS = "https://www.seasaltcornwall.com"

CATALOG = {
    "women": {
        "dresses":  {"ms": f"{MS}/l/women/dresses", "riverisland": f"{RI}/c/women/dresses",
                     "seasalt": f"{SS}/dresses"},
        "tops":     {"ms": f"{MS}/l/women/tops", "riverisland": f"{RI}/c/women/tops",
                     "seasalt": f"{SS}/clothing/tops"},
        "tshirts":  {"ms": f"{MS}/l/women/tops/tshirts", "seasalt": f"{SS}/clothing/t-shirts"},
        "shirts":   {"ms": f"{MS}/l/women/tops/shirts-and-blouses"},
        "knitwear": {"ms": f"{MS}/l/women/knitwear/jumpers", "riverisland": f"{RI}/c/women/knitwear",
                     "seasalt": f"{SS}/clothing/jumpers-cardigans"},
        "jeans":    {"ms": f"{MS}/l/women/jeans", "riverisland": f"{RI}/c/women/jeans"},
        "trousers": {"ms": f"{MS}/l/women/trousers", "riverisland": f"{RI}/c/women/trousers",
                     "seasalt": f"{SS}/trousers"},
        "shorts":   {"ms": f"{MS}/l/women/shorts", "riverisland": f"{RI}/c/women/shorts"},
        "skirts":   {"ms": f"{MS}/l/women/skirts", "riverisland": f"{RI}/c/women/skirts"},
    },
    "men": {
        "tops":     {"ms": f"{MS}/l/men/mens-tops", "riverisland": f"{RI}/c/men/t-shirts-and-vests",
                     "seasalt": f"{SS}/mens-clothing/shirts"},
        "tshirts":  {"ms": f"{MS}/l/men/mens-tops/mens-tshirts",
                     "riverisland": f"{RI}/c/men/t-shirts-and-vests"},
        "shirts":   {"ms": f"{MS}/l/men/mens-shirts", "riverisland": f"{RI}/c/men/shirts",
                     "seasalt": f"{SS}/mens-clothing/shirts"},
        "polos":    {"ms": f"{MS}/l/men/mens-tops/mens-polo-shirts",
                     "riverisland": f"{RI}/c/men/polo-shirts"},
        "knitwear": {"ms": f"{MS}/l/men/mens-knitwear", "riverisland": f"{RI}/c/men/jumpers-and-cardigans",
                     "seasalt": f"{SS}/mens-clothing/knitwear"},
        "hoodies":  {"ms": f"{MS}/l/men/mens-hoodies",
                     "riverisland": f"{RI}/c/men/hoodies-and-sweatshirts"},
        "jeans":    {"ms": f"{MS}/l/men/mens-jeans", "riverisland": f"{RI}/c/men/jeans",
                     "seasalt": f"{SS}/mens-clothing/trousers-jeans-shorts"},
        "trousers": {"ms": f"{MS}/l/men/mens-trousers", "riverisland": f"{RI}/c/men/trousers",
                     "seasalt": f"{SS}/mens-clothing/trousers-jeans-shorts"},
        "joggers":  {"riverisland": f"{RI}/c/men/joggers"},
        "shorts":   {"ms": f"{MS}/l/men/mens-shorts", "riverisland": f"{RI}/c/men/shorts",
                     "seasalt": f"{SS}/mens-clothing/trousers-jeans-shorts"},
    },
}

# Zara serves each category as a JSON feed; IDs come from
# https://www.zara.com/uk/en/categories?ajax=true (verified Sept 2026).
ZARA_CATEGORIES = {
    "women": {"dresses": 2420895, "tops": 2637229, "tshirts": 2420416,
              "shirts": 2420368, "knitwear": 2419846, "jeans": 2419242,
              "trousers": 2420794, "shorts": 2420482, "skirts": 2420453},
    "men":   {"tops": 2432040, "tshirts": 2432040, "shirts": 2431993,
              "polos": 2432056, "knitwear": 2432264, "hoodies": 2732450,
              "jeans": 2731471, "trousers": 2432095, "shorts": 2432163},
}
for _g, _types in ZARA_CATEGORIES.items():
    for _t, _cid in _types.items():
        CATALOG[_g].setdefault(_t, {})["zara"] = (
            f"https://www.zara.com/uk/en/category/{_cid}/products?ajax=true")

# Zara categories are loose (its "dresses" feed includes blazers), so its
# items are also narrowed by Zara's own garment family.
ZARA_FAMILIES = {
    "dresses":  {"DRESS"},
    "tshirts":  {"T-SHIRT"},
    "shirts":   {"SHIRT", "BLOUSE", "OVERSHIRT"},
    "polos":    {"POLO SHIRT"},
    "knitwear": {"SWEATER", "CARDIGAN", "KNITTED WAISTCOAT"},
    "hoodies":  {"SWEATSHIRT"},
    "trousers": {"TROUSERS", "LEGGINGS"},
    "shorts":   {"SHORTS", "BERMUDA"},
    "skirts":   {"SKIRT"},
}

# What to ask a search store for, per type.
TYPE_QUERY = {
    "dresses": "dress", "tops": "top", "tshirts": "t-shirt", "shirts": "shirt",
    "polos": "polo shirt", "knitwear": "jumper", "hoodies": "hoodie",
    "jeans": "jeans", "trousers": "trousers", "joggers": "joggers",
    "shorts": "shorts", "skirts": "skirt",
}

FALLBACK_TYPE = {
    "tshirts": "tops", "shirts": "tops", "polos": "tops", "knitwear": "tops",
    "hoodies": "tops", "jeans": "trousers", "joggers": "trousers",
    "shorts": "trousers", "skirts": "trousers", "tops": None,
    "trousers": None, "dresses": None,
}

# Name keywords that identify a type (used to narrow fallback pages).
TYPE_MATCH = {
    "tshirts":  ["t-shirt", "tshirt", "t shirt", "tee"],
    "shirts":   ["shirt", "blouse"],
    "polos":    ["polo"],
    "knitwear": ["jumper", "cardigan", "sweater"],
    "hoodies":  ["hoodie", "sweatshirt"],
    "jeans":    ["jean"],
    "joggers":  ["jogger"],
    "shorts":   ["short"],
    "skirts":   ["skirt"],
    "dresses":  ["dress"],
    "trousers": ["trouser", "pant", "legging", "chino", "jogger"],
}

# Query words -> type ("t-shirt" is normalised to "tshirt" before lookup).
TYPE_KEYWORDS = {
    "tshirts":  ["tshirt", "tshirts", "tee", "tees"],
    "polos":    ["polo", "polos"],
    "shirts":   ["shirt", "shirts", "blouse", "blouses"],
    "knitwear": ["jumper", "jumpers", "sweater", "sweaters", "knit", "knits",
                 "knitwear", "cardigan", "cardigans"],
    "hoodies":  ["hoodie", "hoodies", "sweatshirt", "sweatshirts"],
    "jeans":    ["jean", "jeans", "denim"],
    "joggers":  ["jogger", "joggers", "trackies", "sweatpants"],
    "trousers": ["trouser", "trousers", "pant", "pants", "chino", "chinos",
                 "legging", "leggings"],
    "shorts":   ["short", "shorts", "jorts"],
    "skirts":   ["skirt", "skirts"],
    "dresses":  ["dress", "dresses", "gown", "gowns", "frock"],
    "tops":     ["top", "tops", "vest", "vests"],
}

GENDER_KEYWORDS = {
    "men":   ["men", "mens", "man", "male", "boy", "boys", "guy", "guys",
              "him", "his", "gents"],
    "women": ["women", "womens", "woman", "female", "girl", "girls", "ladies",
              "lady", "her"],
}

STOPWORDS = {"for", "a", "an", "the", "with", "in", "and", "some", "of", "on",
             "to", "me", "my", "i", "want", "need", "looking", "clothes",
             "clothing", "outfit", "outfits"}

CACHE_TTL = 15 * 60  # seconds
_cache = {}  # url -> (timestamp, products)


def fetch_url(url, timeout=20):
    """Fetch a URL with browser-like headers. Returns (html, error)."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except Exception as e:
        return None, str(e)


def extract_price(text):
    if not text:
        return ""
    prices = re.findall(r'£[\d,]+\.?\d*', text)
    return prices[-1] if prices else text.strip()


# ---------------------------------------------------------------------------
# Store-specific parsers (updated Aug 2026 for current site structures)
# ---------------------------------------------------------------------------

def parse_ms(html, base_url):
    """M&S renders the product list into Next.js __NEXT_DATA__ JSON."""
    products = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                  html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            prods = (data.get("props", {}).get("pageProps", {})
                     .get("serverSideGqlResponseFed", {})
                     .get("productPageData", {}).get("search", {})
                     .get("results", {}).get("products", []))
            for p in prods:
                title = (p.get("title") or "").strip()
                seo = p.get("seoPath") or ""
                if not title or not seo:
                    continue
                image = tryon_image = ""
                asset_url = ("https://assets.digitalcontent.marksandspencer.app"
                             "/image/upload/w_800,q_auto,f_auto/{}")
                variants = p.get("variants") or []
                if variants:
                    assets = variants[0].get("mediaAssets") or []
                    main = next((a for a in assets if a.get("type") == "Main"),
                                assets[0] if assets else None)
                    if main and main.get("assetId"):
                        image = asset_url.format(main["assetId"])
                    cutout = next((a for a in assets if a.get("type") == "Cut_Out"), None)
                    if cutout and cutout.get("assetId"):
                        tryon_image = asset_url.format(cutout["assetId"])
                price = ""
                list_price = (p.get("price") or {}).get("listPrice") or {}
                amount = list_price.get("amount")
                low, high = list_price.get("minimumAmount"), list_price.get("maximumAmount")
                def gbp(x):
                    return f"£{x:g}" if float(x).is_integer() else f"£{x:.2f}"
                if isinstance(amount, (int, float)):
                    price = gbp(amount)
                elif isinstance(low, (int, float)):
                    price = gbp(low) if low == high else f"from {gbp(low)}"
                colour = (variants[0].get("colour") or "") if variants else ""
                if not colour:
                    m_col = re.search(r"[?&]color=([A-Z]+)", seo)
                    colour = m_col.group(1) if m_col else ""
                products.append({
                    "name": unescape(title)[:100],
                    "url": f"https://www.marksandspencer.com{seo}",
                    "image": image,
                    "price": price,
                    "colour": colour.title(),
                    "tryon_image": tryon_image,
                })
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    if not products:
        # Fallback: bare product links with alt text
        link_pattern = re.compile(
            r'href="(/[^"]*?/p/clp\d+[^"]*)"[^>]*>.*?(?:alt="([^"]*)")',
            re.DOTALL
        )
        for m in link_pattern.finditer(html):
            path, alt = m.groups()
            if len(alt) > 5:
                products.append({
                    "name": unescape(alt.strip())[:100],
                    "url": f"https://www.marksandspencer.com{path}",
                    "image": "",
                    "price": "",
                })
    return products


def parse_riverisland(html, base_url):
    """River Island server-renders product cards: data-qa="product-card"."""
    products = []
    blocks = re.split(r'data-qa="product-card"', html)[1:]
    for block in blocks:
        block = block[:5000]
        link = re.search(r'href="(/p/[^"]+)"', block)
        if not link:
            continue
        alt = re.search(r'<img[^>]+alt="([^"]*)"', block)
        src = re.search(r'src="(https://images\.riverisland\.com/[^"]+)"', block)
        price = re.search(r'data-qa="product-price"[^>]*>\s*([^<]+?)\s*<', block)
        name = alt.group(1).strip() if alt else ""
        if not name:
            # Derive from the URL slug: /p/pink-denim-midi-dress-940983
            slug = link.group(1).rsplit("/", 1)[-1]
            name = re.sub(r"-\d+$", "", slug).replace("-", " ").title()
        products.append({
            "name": unescape(name)[:100],
            "url": f"https://www.riverisland.com{link.group(1)}",
            "image": src.group(1) if src else "",
            "price": extract_price(price.group(1)) if price else "",
        })
    return products


def parse_seasalt(html, base_url):
    """Seasalt (Magento): <li class="item product product-item"> tiles."""
    products = []
    blocks = re.split(r'<li class="item product product-item"', html)[1:]
    for block in blocks:
        block = block[:8000]
        name = re.search(r'aria-label="([^"]+)"', block)
        link = re.search(r'href="(https://www\.seasaltcornwall\.com/[^"]+)"', block)
        img = re.search(r'src="(https://res\.cloudinary\.com/[^"]+)"', block)
        price = re.search(r'class="price"[^>]*>([^<]*£[^<]*)<', block)
        if not price:
            price = re.search(r'(£[\d,]+\.?\d*)', block)
        if not (name and link):
            continue
        products.append({
            "name": unescape(name.group(1).strip())[:100],
            "url": link.group(1),
            "image": img.group(1) if img else "",
            "price": extract_price(price.group(1)) if price else "",
        })
    return products


def parse_zara(text, base_url):
    """Zara category feed (JSON): productGroups -> elements -> commercialComponents."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    products = []
    for group in data.get("productGroups", []):
        for element in group.get("elements", []):
            for item in element.get("commercialComponents", []):
                seo = item.get("seo") or {}
                if item.get("kind") == "Marketing" or not item.get("name")                         or not seo.get("keyword") or not seo.get("seoProductId"):
                    continue
                colours = (item.get("detail") or {}).get("colors") or [{}]
                colour = colours[0]
                media = [m for m in colour.get("xmedia") or [] if m.get("url")]
                image = media[0]["url"] + "&w=750" if media else ""
                # "plain" / "-e1" is the front flat-lay of the garment alone.
                flat = next((m for m in media if m.get("kind") == "plain"
                             or m.get("name", "").endswith("-e1")), None)
                pence = colour.get("price") or item.get("price")
                products.append({
                    "name": item["name"].title()[:100],
                    "url": (f"https://www.zara.com/uk/en/{seo['keyword']}"
                            f"-p{seo['seoProductId']}.html"),
                    "image": image,
                    "price": f"£{pence / 100:.2f}" if isinstance(pence, int) else "",
                    "colour": "" if (colour.get("name") or "").lower() == "only one"
                              else colour.get("name") or "",
                    "family": item.get("familyName") or "",
                    "tryon_image": flat["url"] + "&w=1024" if flat else "",
                })
    return products


PARSERS = {
    "ms": parse_ms,
    "riverisland": parse_riverisland,
    "seasalt": parse_seasalt,
    "zara": parse_zara,
}


# ---------------------------------------------------------------------------
# Search stores: query the store's own public search service
# ---------------------------------------------------------------------------

def _get_json(url, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data,
                                 headers={**HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def search_hm(gender, text):
    dept = "men_all" if gender == "men" else "ladies_all"
    params = urllib.parse.urlencode({
        "query": text, "page": 1, "page-size": 36, "department": dept,
        "touchPoint": "DESKTOP", "pageSource": "SEARCH", "sort": "RELEVANCE",
    })
    data = _get_json(
        f"https://api.hm.com/search-services/v1/en_gb/search/resultpage?{params}")
    products = []
    for p in (data.get("searchHits") or {}).get("productList", []):
        image = p.get("productImage") or p.get("modelImage") or ""
        prices = p.get("prices") or [{}]
        products.append({
            "name": p.get("productName", "")[:100],
            "url": "https://www2.hm.com" + p.get("url", ""),
            "image": f"{image}?imwidth=768" if image else "",
            "price": prices[0].get("formattedPrice", ""),
            "colour": p.get("colorName") or "",
        })
    return products


# boohoo's public, search-only Algolia key — the same one its own website
# sends from every visitor's browser (found in its JS bundle).
BOOHOO_ALGOLIA = {"app": "HNC30IYYNP", "key": "6e5de83d201b6bdaac45d449a9466a42",
                  "index": "boohooww-dbz-prod"}


def search_boohoo(gender, text):
    body = json.dumps({
        "query": text,
        "hitsPerPage": 36,
        "filters": (f'gender:"{"Male" if gender == "men" else "Female"}" '
                    'AND department:"Clothing"'),
    }).encode()
    cfg = BOOHOO_ALGOLIA
    data = _get_json(
        f"https://{cfg['app'].lower()}-dsn.algolia.net/1/indexes/{cfg['index']}/query",
        data=body,
        headers={"X-Algolia-Application-Id": cfg["app"],
                 "X-Algolia-API-Key": cfg["key"],
                 "Content-Type": "application/json"})
    products = []
    for h in data.get("hits", []):
        if not h.get("slug"):
            continue
        images = h.get("images") or []
        price = h.get("price")
        colour = h.get("colour") or ""
        products.append({
            "name": (h.get("name") or "")[:100],
            "url": (f"https://www.boohoo.com/product/{h['slug']}"
                    + (f"?colour={urllib.parse.quote(colour)}" if colour else "")),
            "image": f"{images[0]}?w=750" if images else "",
            "price": f"£{price:.2f}" if isinstance(price, (int, float)) else "",
            "colour": colour.title(),
        })
    return products


SEARCH_STORES = {
    "hm": search_hm,
    "boohoo": search_boohoo,
}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def available_types(gender):
    """Types offered for a gender, in display order."""
    catalog = CATALOG.get(gender, {})
    return [{"key": t, "label": TYPES[t]["label"]} for t in TYPES if t in catalog]


def parse_query(query):
    """Split a free-text query into (gender, type, filter_words).

    The type comes from the LAST type word, since English puts the head noun
    last ("shirt dress" is a dress, "denim skirt" is a skirt) — except that
    any mention of "polo" means a polo shirt.
    """
    q = (query or "").lower().replace("'", "")
    q = re.sub(r"\bt[\s-]?shirts?\b", "tshirt", q)
    words = re.findall(r"[a-z0-9]+", q)

    gender = None
    for w in words:
        for g, kws in GENDER_KEYWORDS.items():
            if w in kws:
                gender = gender or g

    word_to_type = {w: t for t, kws in TYPE_KEYWORDS.items() for w in kws}
    ctype = None
    for w in words:
        if w in word_to_type:
            ctype = word_to_type[w]
    if "polo" in words or "polos" in words:
        ctype = "polos"

    gender_words = {w for kws in GENDER_KEYWORDS.values() for w in kws}
    filters = [w for w in words
               if w not in gender_words and w not in word_to_type
               and w not in STOPWORDS and len(w) > 1]
    return gender, ctype, filters


def _tag(products, store_key):
    for p in products:
        p["store"] = STORES[store_key]
        p["store_key"] = store_key
    return products


def _cached(key, loader):
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    products = loader()
    _cache[key] = (time.time(), products)
    return products


def _fetch_source(source):
    """Load one planned source: ("page", store, url) or ("search", store, gender, text)."""
    kind, store_key = source[0], source[1]
    if kind == "page":
        url = source[2]

        def load():
            html, err = fetch_url(url)
            if err:
                raise RuntimeError(f"{STORES[store_key]}: {err}")
            return _tag(PARSERS[store_key](html, url), store_key)
    else:
        gender, text = source[2], source[3]

        def load():
            try:
                found = SEARCH_STORES[store_key](gender, text)
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"{STORES[store_key]}: HTTP {e.code}")
            except Exception as e:
                raise RuntimeError(f"{STORES[store_key]}: {e}")
            return _tag(found, store_key)
    return _cached(source, load)


def _plan_source(gender, ctype, store_key, filters):
    """Return (source, narrow) for one store and type, or (None, False).

    narrow=True means the results are broader than the type and must be
    filtered by TYPE_MATCH keywords."""
    if store_key in SEARCH_STORES:
        text = " ".join(filters + [TYPE_QUERY[ctype]])
        return ("search", store_key, gender, text), True
    catalog = CATALOG[gender]
    url = catalog.get(ctype, {}).get(store_key)
    if url:
        return ("page", store_key, url), False
    fallback = FALLBACK_TYPE.get(ctype)
    if fallback:
        url = catalog.get(fallback, {}).get(store_key)
        if url:
            return ("page", store_key, url), True
    return None, False


def _fits_type(p, ctype, narrow):
    """Whether a product belongs to the requested type."""
    families = ZARA_FAMILIES.get(ctype)
    if p.get("family") and families and p["family"] not in families:
        return False
    keywords = TYPE_MATCH.get(ctype)
    if narrow and keywords and not _matches_words(p["name"], keywords):
        return False
    return True


def _matches_words(name, words):
    """Words that start a word in the name ("red" won't match "tailored")."""
    name = name.lower()
    return [w for w in words if re.search(r"(?<![a-z])" + re.escape(w), name)]


DEFAULT_TYPES = {"women": ["dresses", "tops", "trousers"],
                 "men": ["tops", "shirts", "trousers"]}


def search(query="", ctype="auto", gender="women", stores=None, max_per_store=12):
    """Live search across stores. Returns a dict ready to serialize as JSON."""
    query = (query or "").strip()
    q_gender, q_type, filters = parse_query(query)

    gender = q_gender or (gender if gender in GENDERS else "women")
    if ctype not in TYPES:
        ctype = q_type
    store_keys = [s for s in (stores or list(STORES)) if s in STORES]

    note = ""
    if ctype and ctype not in CATALOG[gender]:
        note = (f"No {'men' if gender == 'men' else 'women'}'s "
                f"{TYPES[ctype]['label'].lower()} at these stores.")
        return _result(query, gender, ctype, store_keys, [], [], True, note)

    types = [ctype] if ctype else DEFAULT_TYPES[gender]

    # (store, type) -> (source, narrow)
    plan = {}
    for sk in store_keys:
        for t in types:
            source, narrow = _plan_source(gender, t, sk, filters)
            if source:
                plan[(sk, t)] = (source, narrow)

    sources = {source for source, _ in plan.values()}
    loaded, errors = {}, []
    with ThreadPoolExecutor(max_workers=min(len(sources), 16) or 1) as pool:
        futures = {pool.submit(_fetch_source, src): src for src in sources}
        for fut in as_completed(futures):
            try:
                loaded[futures[fut]] = fut.result()
            except Exception as e:
                errors.append(str(e))

    # Build the candidate pool per store, deduped by URL.
    per_store = {sk: [] for sk in store_keys}
    seen = set()
    for (sk, t), (source, narrow) in plan.items():
        for p in loaded.get(source, []):
            if not _fits_type(p, t, narrow) or p["url"] in seen:
                continue
            seen.add(p["url"])
            item = dict(p)
            item.pop("family", None)
            item.update(type=t, category=TYPES[t]["group"], gender=gender)
            per_store[sk].append(item)

    # Narrow by the leftover query words (colour, pattern, fit…).
    query_matched = True
    if filters:
        pool_all = [p for items in per_store.values() for p in items]
        def text(p):
            return f"{p['name']} {p.get('colour', '')}"
        all_hit = {id(p) for p in pool_all
                   if len(_matches_words(text(p), filters)) == len(filters)}
        any_hit = {id(p) for p in pool_all if _matches_words(text(p), filters)}
        keep = all_hit or any_hit
        if keep:
            per_store = {sk: [p for p in items if id(p) in keep]
                         for sk, items in per_store.items()}
        else:
            query_matched = False

    # Cap per store, then interleave stores so results feel mixed.
    capped = [items[:max_per_store] for items in per_store.values()]
    products = []
    for i in range(max((len(c) for c in capped), default=0)):
        for c in capped:
            if i < len(c):
                products.append(c[i])

    return _result(query, gender, ctype, store_keys, products, errors,
                   query_matched, note)


def _result(query, gender, ctype, store_keys, products, errors, matched, note):
    return {
        "query": query,
        "gender": gender,
        "type": ctype,
        "type_label": TYPES[ctype]["label"] if ctype else "",
        "stores_searched": [STORES[k] for k in store_keys],
        "query_matched": matched,
        "note": note,
        "errors": errors,
        "total": len(products),
        "products": products,
    }
