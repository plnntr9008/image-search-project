import os
import io
import zipfile
import asyncio
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
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


@app.get("/search")
async def search_images(
    query: str = Query(..., min_length=1, description="Search query (supports Cyrillic)") ,
    page: int = Query(1, ge=1, le=10),
    per_page: int = Query(50, ge=1, le=50),
):
    async with httpx.AsyncClient(timeout=20.0, headers=COMMONS_HEADERS) as client:
        try:
            total = await _commons_total_hits(client, query)
            results = await _commons_search_page(client, query, page, per_page)
            return {"total": total, "results": results}
        except httpx.HTTPStatusError as e:
            return {"error": "Commons API error", "status": e.response.status_code}
        except Exception as e:
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