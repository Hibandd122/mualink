import asyncio
import logging
import os
import re
import time
from urllib.parse import quote, urlparse, parse_qs

import aiohttp

from get_proxy import UrbanVpnProxy, UA

import urllib3
urllib3.disable_warnings()

# ═══════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════
logger = logging.getLogger("mualink")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "\033[90m%(asctime)s\033[0m │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(_h)

# ═══════════════════════════════════════════════════════
#  Telegram Bot Config
# ═══════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7560246529:AAEHp4Khf5Ok7YObZWDIrTQO_65Ad19vSWg")
ALLOWED_USER_IDS = {6196604499}

DEFAULT_MUALINK_URL = "https://mual.ink/jjE89"
MUALINK_ORIGIN = "https://mual.ink"

# ═══════════════════════════════════════════════════════
#  Core Bypass — Proxy Race (song song)
# ═══════════════════════════════════════════════════════
PROXY_RACE_COUNT = 5           # Số proxy chạy song song
PROXY_REQUEST_TIMEOUT = 12     # Timeout mỗi HTTP request (giây)


async def _bypass_with_one_proxy(session, p: dict, idx: int, mualink_url: str) -> dict:
    """Thử bypass với 1 proxy duy nhất. Trả về dict kết quả hoặc raise exception."""
    proxy_label = f"{p['host']}:{p['port']}"
    safe_user = quote(p.get("username", ""), safe="")
    safe_pass = quote(p.get("password", ""), safe="")
    scheme = p.get("scheme", "http")

    if safe_user:
        proxy_url = f"{scheme}://{safe_user}:{safe_pass}@{p['host']}:{p['port']}"
    else:
        proxy_url = f"{scheme}://{p['host']}:{p['port']}"

    # 1. GET mualink page
    async with session.get(mualink_url, proxy=proxy_url, timeout=PROXY_REQUEST_TIMEOUT, ssl=False) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} on GET mualink")
        html = await resp.text()

    forms = re.findall(r'<form\b[^>]*>.*?</form>', html, re.DOTALL)
    if not forms:
        raise RuntimeError("Không tìm thấy form xác thực")

    form_html = forms[0]
    action_match = re.search(r'action="([^"]*)"', form_html)
    if not action_match:
        raise RuntimeError("Không tìm thấy URL đích")
    action = action_match.group(1)

    inputs = {}
    for inp in re.finditer(r'<input\b[^>]*>', form_html):
        name_m = re.search(r'name="([^"]*)"', inp.group())
        if name_m:
            val_m = re.search(r'value="([^"]*)"', inp.group())
            inputs[name_m.group(1)] = val_m.group(1) if val_m else ""

    # 2. POST bypass
    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": MUALINK_ORIGIN,
        "Referer": mualink_url,
    }
    post_url = MUALINK_ORIGIN + action
    async with session.post(post_url, data=inputs, headers=post_headers, proxy=proxy_url, timeout=PROXY_REQUEST_TIMEOUT, ssl=False) as resp2:
        if resp2.status != 200:
            raise RuntimeError(f"HTTP {resp2.status} on POST form")
        html2 = await resp2.text()

    # 3. Extract note ID
    m = re.search(r'window\.location\.href\s*=\s*"([^"]*)"', html2)
    if not m:
        raise RuntimeError("Không trích xuất được URL redirect")
    loc = m.group(1).replace("\\/", "/")
    parsed = urlparse(loc)
    qs = parse_qs(parsed.query)
    final_url = qs.get("url", [loc])[0]

    nid_m = re.search(r'/([^/]+)$', final_url) if final_url else None
    if not nid_m:
        raise RuntimeError("Không trích xuất được ID Note")
    note_id = nid_m.group(1)

    # 4. GET note
    note_url = f"https://note2s.net/notes/{note_id}"
    async with session.get(note_url, proxy=proxy_url, timeout=PROXY_REQUEST_TIMEOUT, ssl=False) as resp3:
        if resp3.status != 200:
            raise RuntimeError(f"HTTP {resp3.status} on GET note")
        note_html = await resp3.text()

    # 5. Extract links
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

    return {
        "links": filtered,
        "note_id": note_id,
        "proxy_used": proxy_label,
        "proxy_index": idx,
    }


async def bypass_mualink(mualink_url: str) -> dict:
    """Race nhiều proxy song song, trả về kết quả của proxy đầu tiên thành công."""
    mualink_url = mualink_url or DEFAULT_MUALINK_URL
    start = time.time()

    urban = UrbanVpnProxy()
    proxies_list = await asyncio.to_thread(urban.get_proxies_by_country, "VN", validate=False)

    if not proxies_list:
        return {"error": "Không lấy được proxy VN"}

    n_race = min(PROXY_RACE_COUNT, len(proxies_list))

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
        tasks = [
            asyncio.create_task(_bypass_with_one_proxy(session, p, i + 1, mualink_url))
            for i, p in enumerate(proxies_list[:n_race])
        ]

        winner = None
        errors = []
        for fut in asyncio.as_completed(tasks):
            try:
                result = await fut
                if result and result.get("links") is not None:
                    winner = result
                    break
            except asyncio.CancelledError:
                pass
            except Exception as e:
                errors.append(f"{type(e).__name__}: {e}")

        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        if winner:
            winner["elapsed_sec"] = round(time.time() - start, 2)
            winner["proxy_total"] = len(proxies_list)
            return winner

    return {"error": f"Tất cả {n_race} proxy đều thất bại", "details": errors[:3]}


# ═══════════════════════════════════════════════════════
#  Telegram Bot
# ═══════════════════════════════════════════════════════
def _register_handlers(dp):
    from aiogram import types
    from aiogram.filters import Command

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        if message.from_user.id not in ALLOWED_USER_IDS:
            await message.reply("🚫 Bạn không có quyền sử dụng bot này.")
            return
        await message.reply(
            "⚡ <b>Mualink Bypass Bot</b>\n\n"
            "Gửi link <code>mual.ink</code> để bẻ khóa tự động.\n\n"
            "/status — Trạng thái proxy pool\n"
            "/help — Hướng dẫn"
        )

    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        if message.from_user.id not in ALLOWED_USER_IDS:
            return
        await message.reply(
            "📖 <b>Hướng dẫn</b>\n\n"
            "Gửi trực tiếp link <code>mual.ink/xxx</code> → bot tự bypass.\n"
            f"⚡ Tốc độ: race <b>{PROXY_RACE_COUNT}</b> proxy song song, "
            f"timeout <b>{PROXY_REQUEST_TIMEOUT}s</b>/proxy.\n"
            "⏱ Thường mất 3-8 giây."
        )

    @dp.message(Command("status"))
    async def cmd_status(message: types.Message):
        if message.from_user.id not in ALLOWED_USER_IDS:
            return
        cache_info = []
        for code, data in UrbanVpnProxy._vn_cache.items():
            remaining = max(0, int(data["expire"] - time.time()))
            cache_info.append(f"  🌐 <b>{code}</b>: {len(data['proxies'])} proxies (TTL: {remaining}s)")

        text = "📊 <b>Proxy Pool Status</b>\n\n"
        text += "\n".join(cache_info) if cache_info else "  <i>Cache trống — sẽ tự refresh khi cần</i>"
        await message.reply(text)

    @dp.message()
    async def handle_message(message: types.Message):
        if message.from_user.id not in ALLOWED_USER_IDS:
            await message.reply("🚫 Bạn không có quyền sử dụng bot này.")
            return

        text = (message.text or "").strip()
        m = re.search(r'https?://\S+', text)
        if not m:
            await message.reply("⚠️ Gửi link <code>mual.ink</code> để bypass. Dùng /help để xem hướng dẫn.")
            return

        url = m.group(0).rstrip('.,;:)]}>"\'')
        status_msg = await message.reply(f"⏳ Đang bypass <code>{url}</code>...")

        try:
            result = await bypass_mualink(url)
        except Exception as e:
            logger.error(f"Bypass error: {e}", exc_info=True)
            await _safe_edit(status_msg, f"❌ <b>Lỗi:</b> <code>{type(e).__name__}: {e}</code>")
            return

        if "error" in result:
            await _safe_edit(status_msg, f"❌ <b>Lỗi:</b> {result['error']}")
            return

        links = result.get("links", [])
        if not links:
            await _safe_edit(status_msg, "⚠️ Bypass thành công nhưng không tìm thấy link đích.")
            return

        reply = (
            f"✅ <b>Bẻ khóa thành công!</b>\n\n"
            f"🔗 <code>{url}</code>\n"
            f"📎 <b>{len(links)} link:</b>\n\n"
        )
        for i, link in enumerate(links, 1):
            reply += f"  {i}. {link}\n"
        reply += f"\n<i>⏱ {result['elapsed_sec']}s · 🌐 {result['proxy_used']}</i>"

        await _safe_edit(status_msg, reply, disable_preview=True)


async def _safe_edit(msg, text: str, disable_preview: bool = False):
    from aiogram import types
    try:
        kwargs = {}
        try:
            kwargs["link_preview_options"] = types.LinkPreviewOptions(is_disabled=True)
        except Exception:
            kwargs["disable_web_page_preview"] = disable_preview
        await msg.edit_text(text, **kwargs)
    except Exception:
        pass


async def background_proxy_refresh():
    """Giữ proxy VN pool luôn sẵn sàng (cache TTL 240s, refresh mỗi 200s)."""
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("🔄 Refreshing VN proxy pool...")
            urban = UrbanVpnProxy()
            proxies = await asyncio.to_thread(urban.get_proxies_by_country, "VN", validate=True)
            if proxies:
                logger.info(f"✅ Pool updated — {len(proxies)} proxies")
        except Exception as e:
            logger.error(f"❌ Proxy refresh error: {e}")
        await asyncio.sleep(200)


async def main():
    from aiogram import Bot, Dispatcher
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    _register_handlers(dp)

    refresh_task = asyncio.create_task(background_proxy_refresh())
    logger.info("🚀 Background proxy refresh — STARTED")

    try:
        logger.info("🤖 Telegram Bot — Polling started")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        refresh_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
