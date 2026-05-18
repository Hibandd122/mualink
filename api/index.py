import os
import sys
import asyncio
import logging

# Thêm thư mục gốc vào sys.path để import được request_mualink
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from request_mualink import app, aio_fetch_links

# Token Bot
API_TOKEN = '7560246529:AAEHp4Khf5Ok7YObZWDIrTQO_65Ad19vSWg'
ALLOWED_USER_ID = 6196604499

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message()
async def handle_url_message(message: types.Message):
    if message.from_user.id != ALLOWED_USER_ID:
        await message.reply("🚫 Bạn không có quyền sử dụng bot này.")
        return

    text = message.text.strip()
    if not text.startswith("http"):
        await message.reply("⚠️ Vui lòng gửi một link hợp lệ (bắt đầu bằng http).")
        return

    status_msg = await message.reply("⏳ Đang khởi tạo quá trình bypass...")
    
    last_text = ""
    try:
        async for progress in aio_fetch_links(text):
            if "step" in progress:
                new_text = f"⏳ <i>{progress['msg']}</i>"
                if new_text != last_text:
                    try:
                        await status_msg.edit_text(new_text)
                        last_text = new_text
                    except Exception as e:
                        pass
            elif "error" in progress:
                await status_msg.edit_text(f"❌ <b>Lỗi:</b> {progress['error']}")
                return
            elif "done" in progress and progress.get("done"):
                links = progress.get("links", [])
                if not links:
                    await status_msg.edit_text("⚠️ Không tìm thấy link đích nào.")
                    return
                
                result_text = f"✅ <b>Bẻ khóa thành công!</b>\n\n"
                for i, link in enumerate(links, 1):
                    result_text += f"{i}. {link}\n"
                    
                try:
                    await status_msg.edit_text(result_text, link_preview_options=types.LinkPreviewOptions(is_disabled=True))
                except TypeError:
                    await status_msg.edit_text(result_text, disable_web_page_preview=True)
                return
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Đã xảy ra lỗi không xác định:</b>\n{str(e)}")

# Webhook Endpoint cho Telegram
@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        # Bắn update vào Dispatcher để xử lý
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Lỗi xử lý webhook: {e}")
    return {"status": "ok"}

# Endpoint phụ để tiện set webhook bằng tay
@app.get("/api/set_webhook")
async def set_webhook(url: str):
    try:
        webhook_url = f"{url}/api/webhook"
        result = await bot.set_webhook(url=webhook_url)
        return {"status": "success", "result": result, "webhook_url": webhook_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}
