import os
import io
import zipfile
import asyncio
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
import logging
# image processing removed — client-side canvas will perform cropping
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Image Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite по умолчанию
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# We'll use Wikimedia Commons API (no API key required) to provide free image search.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia requires a descriptive User-Agent. Provide a clear User-Agent identifying this
# local project so requests are not rejected with 403.
COMMONS_HEADERS = {
    "User-Agent": "image-search-project/0.1 (dev@example.com)"
}

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
OPENVERSE_API = "https://api.openverse.engineering/v1/images/"
SERPAPI_URL = "https://serpapi.com/search.json"


async def _commons_total_hits(client: httpx.AsyncClient, query: str) -> int:
    """Get total hits for a query in File namespace (namespace=6)."""
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": 1,
        "formatversion": 2,
    }
    resp = await client.get(COMMONS_API, params=params)
    resp.raise_for_status()
    j = resp.json()
    return j.get("query", {}).get("searchinfo", {}).get("totalhits", 0)


async def _commons_search_page(client: httpx.AsyncClient, query: str, page: int, per_page: int):
    """Search File: pages and request thumbnail (iiurlwidth=300). Returns list of normalized results."""
    offset = (page - 1) * per_page
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": per_page,
        "gsroffset": offset,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 300,
        "formatversion": 2,
    }
    resp = await client.get(COMMONS_API, params=params)
    resp.raise_for_status()
    j = resp.json()

    pages = j.get("query", {}).get("pages", [])
    results = []
    # pages may be a list (formatversion=2) or dict; handle list
    for p in pages:
        pageid = p.get("pageid")
        title = p.get("title", "")
        imageinfo = p.get("imageinfo", [])
        info = imageinfo[0] if imageinfo else {}

        # Prefer thumbnail (300px) if available; fallback to full url
        thumb = info.get("thumburl") or info.get("thumb") or info.get("url")
        width = info.get("thumbwidth") or info.get("width")
        height = info.get("thumbheight") or info.get("height")

        results.append({
            "id": pageid,
            "title": title.replace("File:", ""),
            "alt_description": title.replace("File:", ""),
            "download_url": thumb,
            "width": width,
            "height": height,
            # Keep a minimal 'raw' structure to help frontend if needed
            "raw": info,
        })

    return results


async def _openverse_search_page(client: httpx.AsyncClient, query: str, page: int, per_page: int):
    """Search Openverse and normalize results."""
    params = {
        "q": query,
        "page": page,
        "page_size": per_page,
    }
    resp = await client.get(OPENVERSE_API, params=params)
    resp.raise_for_status()
    j = resp.json()
    results = []
    for item in j.get("results", []):
        thumb = item.get("thumbnail") or item.get("url")
        results.append({
            "id": item.get("id"),
            "title": item.get("title") or item.get("creator"),
            "alt_description": item.get("title") or item.get("creator"),
            "download_url": thumb,
            "width": None,
            "height": None,
            "raw": item,
            "source": "openverse",
        })
    total = j.get("result_count") or j.get("count") or 0
    return results, total


async def _serpapi_search_page(client: httpx.AsyncClient, query: str, page: int, per_page: int):
    """Search SerpApi (Google Images via SerpApi) and normalize results. Requires SERPAPI_KEY."""
    if not SERPAPI_KEY:
        return [], 0
    params = {
        "engine": "google_images",
        "q": query,
        # image page index (0-based)
        "ijn": max(0, page - 1),
        "api_key": SERPAPI_KEY,
        # SerpApi may ignore num for images, but include it
        "num": per_page,
    }
    resp = await client.get(SERPAPI_URL, params=params)
    resp.raise_for_status()
    j = resp.json()
    results = []
    for item in j.get("image_results", []):
        # SerpApi image_results typically have 'original', 'thumbnail', 'link', 'title'
        img_url = item.get("original") or item.get("link") or item.get("thumbnail")
        title = item.get("title") or item.get("source")
        results.append({
            "id": item.get("position") or item.get("id") or img_url,
            "title": title,
            "alt_description": title,
            "download_url": img_url,
            "width": None,
            "height": None,
            "raw": item,
            "source": "serpapi",
        })
    total = j.get("search_information", {}).get("total_results") or 0
    try:
        total = int(total)
    except Exception:
        total = 0
    return results, total


# server-side image proxy removed — frontend will perform canvas cropping


@app.get("/search")
async def search_images(
    query: str = Query(..., min_length=1, description="Search query (supports Cyrillic)") ,
    page: int = Query(1, ge=1, le=10),
    per_page: int = Query(50, ge=1, le=50),
):
    """Run SerpApi (if available) + Openverse concurrently, merge and deduplicate results.

    Order of preference: serpapi -> openverse -> commons. We return up to `per_page` items combined.
    Total is the sum of totals reported by each provider (approximate).
    """
    async with httpx.AsyncClient(timeout=20.0, headers=COMMONS_HEADERS) as client:
        try:
            # Launch provider requests in parallel. Use return_exceptions=True so one failing
            # provider doesn't take the whole search down.
            tasks = [
                _openverse_search_page(client, query, page, per_page),
                _serpapi_search_page(client, query, page, per_page),
                _commons_search_page(client, query, page, per_page),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            openv_res, serp_res, commons_res = results

            # If any provider raised an exception, log it and treat as empty result set
            openv_list, openv_total = ([], 0)
            serp_list, serp_total = ([], 0)
            commons_list = []

            if isinstance(openv_res, Exception):
                logging.exception("Openverse search failed")
            else:
                openv_list, openv_total = openv_res

            if isinstance(serp_res, Exception):
                logging.exception("SerpApi search failed")
            else:
                serp_list, serp_total = serp_res

            if isinstance(commons_res, Exception):
                logging.exception("Commons search failed")
            else:
                commons_list = commons_res

            combined: List[Dict] = []
            seen = set()

            def add_item(item):
                key = item.get("download_url") or f"{item.get('source')}::{item.get('id')}::{item.get('title')}"
                if not key or key in seen:
                    return
                seen.add(key)
                combined.append(item)

            # Prefer SerpApi first (usually better metadata and handling of multi-word queries), then Openverse, then Commons
            for it in (serp_list or []):
                add_item(it)
            for it in (openv_list or []):
                add_item(it)
            for it in (commons_list or []):
                # add source=commons if missing
                it.setdefault("source", "commons")
                add_item(it)

            # If combined smaller than requested, we don't try additional pages here; frontend can request next page.
            sliced = combined[:per_page]

            # Keep original download_url (frontend will crop client-side using canvas)
            for it in sliced:
                it['download_url'] = it.get('download_url')

            # Safely get commons total hits; if it fails, don't fail the whole request.
            try:
                commons_total = await _commons_total_hits(client, query)
            except Exception:
                logging.exception("Failed to fetch commons total hits")
                commons_total = 0

            total = (serp_total or 0) + (openv_total or 0) + commons_total

            return {"total": total, "results": sliced}
        except httpx.HTTPStatusError as e:
            logging.exception("HTTP error when calling provider")
            return {"error": "Provider API error", "status": getattr(e.response, 'status_code', None), "message": str(e)}
        except Exception as e:
            logging.exception("Unexpected error in /search")
            return {"error": "Unexpected error", "message": str(e)}


@app.get("/download")
async def download_page_zip(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1, le=10),
    per_page: int = Query(50, ge=1, le=50),
):
    """Return a ZIP archive containing thumbnails (300px) for the requested search page."""
    async with httpx.AsyncClient(timeout=30.0, headers=COMMONS_HEADERS) as client:
        try:
            results = await _commons_search_page(client, query, page, per_page)

            urls = [r.get("download_url") for r in results if r.get("download_url")]

            # Fetch all images concurrently (bounded concurrency)
            sem = asyncio.Semaphore(8)

            async def fetch(url, idx):
                async with sem:
                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                        return idx, r.content
                    except Exception:
                        return idx, None

            tasks = [fetch(u, i) for i, u in enumerate(urls)]
            fetched = await asyncio.gather(*tasks)

            mem = io.BytesIO()
            with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for idx, content in fetched:
                    if not content:
                        continue
                    name = f"image_{page}_{idx + 1}.jpg"
                    zf.writestr(name, content)

            mem.seek(0)
            fname = f"images_{query.replace(' ', '_')}_page{page}.zip"
            return StreamingResponse(mem, media_type="application/zip", headers={
                "Content-Disposition": f"attachment; filename=\"{fname}\""
            })
        except httpx.HTTPStatusError as e:
            return {"error": "Commons API error", "status": e.response.status_code}
        except Exception as e:
            return {"error": "Unexpected error", "message": str(e)}