import asyncio
import json
import logging
import re
import time
from urllib.parse import quote, urlparse, parse_qs

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from get_proxy import UrbanVpnProxy, UA

import urllib3
urllib3.disable_warnings()

logger = logging.getLogger("mualink")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "\033[90m%(asctime)s\033[0m │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(_h)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DEFAULT_MUALINK_URL = "https://mual.ink/jjE89"
MUALINK_ORIGIN = "https://mual.ink"

async def background_proxy_refresh():
    """Background task to keep VN proxies hot."""
    while True:
        try:
            logger.info("🔄 Background: Refreshing VN Proxy Pool...")
            urban = UrbanVpnProxy()
            # Run in thread to not block event loop
            proxies = await asyncio.to_thread(urban.get_proxies_by_country, "VN", validate=True)
            if proxies:
                logger.info(f"✅ Background: Hot Pool updated with {len(proxies)} proxies")
        except Exception as e:
            logger.error(f"❌ Background Proxy Error: {e}")
        await asyncio.sleep(200)  # Refresh every 200 seconds (cache TTL is 240)

@app.on_event("startup")
async def startup_event():
    # Vercel Serverless không hỗ trợ background task chạy ngầm vô hạn.
    # Nên chúng ta tắt background_proxy_refresh() đi.
    pass

async def aio_fetch_links(mualink_url: str):
    """Generator function that yields SSE progress and final result."""
    mualink_url = mualink_url or DEFAULT_MUALINK_URL
    start = time.time()

    yield {"step": "proxy", "msg": "Đang tìm kiếm proxy VN tốt nhất..."}
    
    urban = UrbanVpnProxy()
    proxies_list = await asyncio.to_thread(urban.get_proxies_by_country, "VN", validate=False)
    
    if not proxies_list:
        yield {"error": "Không lấy được proxy VN", "proxy_count": 0}
        return

    yield {"step": "proxy", "msg": f"Tìm thấy {len(proxies_list)} proxy VN. Bắt đầu bypass..."}

    # aiohttp ClientSession
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        for i, p in enumerate(proxies_list[:5]):
            proxy_label = f"{p['host']}:{p['port']}"
            safe_user = quote(p.get("username", ""), safe="")
            safe_pass = quote(p.get("password", ""), safe="")
            scheme = p.get("scheme", "http")
            
            if safe_user:
                proxy_url = f"{scheme}://{safe_user}:{safe_pass}@{p['host']}:{p['port']}"
            else:
                proxy_url = f"{scheme}://{p['host']}:{p['port']}"

            yield {"step": "request", "msg": f"[{i+1}/5] Đang kết nối qua {proxy_label}..."}
            
            try:
                # 1. GET mualink page
                async with session.get(mualink_url, proxy=proxy_url, timeout=15, ssl=False) as resp:
                    if resp.status != 200:
                        yield {"step": "warn", "msg": f"[{i+1}/5] Lỗi HTTP {resp.status} khi tải trang"}
                        continue
                    html = await resp.text()

                # 2. Parse form
                forms = re.findall(r'<form\b[^>]*>.*?</form>', html, re.DOTALL)
                if not forms:
                    yield {"step": "warn", "msg": f"[{i+1}/5] Không tìm thấy form xác thực"}
                    continue

                form_html = forms[0]
                action_match = re.search(r'action="([^"]*)"', form_html)
                if not action_match:
                    yield {"step": "warn", "msg": f"[{i+1}/5] Không tìm thấy URL đích"}
                    continue
                action = action_match.group(1)

                inputs = {}
                for inp in re.finditer(r'<input\b[^>]*>', form_html):
                    name_m = re.search(r'name="([^"]*)"', inp.group())
                    if name_m:
                        val_m = re.search(r'value="([^"]*)"', inp.group())
                        inputs[name_m.group(1)] = val_m.group(1) if val_m else ""

                yield {"step": "request", "msg": f"[{i+1}/5] Đang gửi form vượt link..."}

                # 3. POST bypass
                post_headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": MUALINK_ORIGIN,
                    "Referer": mualink_url,
                }
                post_url = MUALINK_ORIGIN + action
                async with session.post(post_url, data=inputs, headers=post_headers, proxy=proxy_url, timeout=15, ssl=False) as resp2:
                    if resp2.status != 200:
                        yield {"step": "warn", "msg": f"[{i+1}/5] Lỗi HTTP {resp2.status} khi gửi form"}
                        continue
                    html2 = await resp2.text()

                # 4. Extract note ID
                final_url = None
                m = re.search(r'window\.location\.href\s*=\s*"([^"]*)"', html2)
                if m:
                    loc = m.group(1).replace("\\/", "/")
                    parsed = urlparse(loc)
                    qs = parse_qs(parsed.query)
                    final_url = qs.get("url", [loc])[0]

                note_id = None
                if final_url:
                    nid_m = re.search(r'/([^/]+)$', final_url)
                    if nid_m:
                        note_id = nid_m.group(1)
                
                if not note_id:
                    yield {"step": "warn", "msg": f"[{i+1}/5] Không trích xuất được ID Note"}
                    continue

                yield {"step": "request", "msg": f"[{i+1}/5] Đã lấy Note ID ({note_id}), đang đọc nội dung..."}

                # 5. GET note
                note_url = f"https://note2s.net/notes/{note_id}"
                async with session.get(note_url, proxy=proxy_url, timeout=15, ssl=False) as resp3:
                    if resp3.status != 200:
                        yield {"step": "warn", "msg": f"[{i+1}/5] Lỗi HTTP {resp3.status} khi tải Note"}
                        continue
                    note_html = await resp3.text()

                # 6. Extract links
                content_area = re.search(
                    r'<div[^>]*class="[^"]*content-fit[^"]*"[^>]*>(.*?)</div>',
                    note_html, re.DOTALL,
                )
                content = content_area.group(1) if content_area else note_html
                all_links = re.findall(r'<a\s+[^>]*href="([^"]*)"', content)
                filtered = [
                    link for link in all_links
                    if (link.startswith("http") or link.startswith("t.me"))
                    and "cloudflare" not in link
                    and "kenhvip.online" not in link
                ]

                elapsed = round(time.time() - start, 2)
                
                yield {"step": "success", "msg": f"✅ Thành công lấy {len(filtered)} links trong {elapsed}s"}
                yield {
                    "done": True,
                    "links": filtered,
                    "note_id": note_id,
                    "proxy_used": proxy_label,
                    "elapsed_sec": elapsed,
                    "proxy_index": i + 1,
                }
                return

            except asyncio.TimeoutError:
                yield {"step": "warn", "msg": f"[{i+1}/5] Proxy bị timeout"}
                continue
            except aiohttp.ClientError as e:
                yield {"step": "warn", "msg": f"[{i+1}/5] Proxy lỗi kết nối"}
                continue
            except Exception as e:
                yield {"step": "warn", "msg": f"[{i+1}/5] Lỗi không xác định: {type(e).__name__}"}
                continue

    yield {"error": "Tất cả proxy đều thất bại", "proxy_tried": min(5, len(proxies_list))}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/get-links-stream")
async def get_links_stream(url: str = ""):
    custom_url = url.strip() or None
    
    async def event_generator():
        async for data in aio_fetch_links(custom_url):
            yield f"data: {json.dumps(data)}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/get-links")
async def get_links(url: str = ""):
    """Non-streaming version for backward compatibility / bulk mode."""
    custom_url = url.strip() or None
    result = None
    async for data in aio_fetch_links(custom_url):
        if "done" in data or "error" in data:
            result = data
    return JSONResponse(result or {"error": "Lỗi không xác định"})

if __name__ == "__main__":
    import uvicorn
    logger.info("🌐 FastAPI Mualink Bypass Dashboard → http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)
