import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from request_mualink import aio_fetch_links

# Cấu hình log
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Thông tin xác thực
API_TOKEN = '7560246529:AAEHp4Khf5Ok7YObZWDIrTQO_65Ad19vSWg'
ALLOWED_USER_ID = 6196604499

# Khởi tạo bot và dispatcher
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message()
async def handle_url_message(message: types.Message):
    # Kiểm tra ID người dùng
    if message.from_user.id != ALLOWED_USER_ID:
        await message.reply("🚫 Bạn không có quyền sử dụng bot này.")
        return

    text = message.text.strip()
    if not text.startswith("http"):
        await message.reply("⚠️ Vui lòng gửi một link hợp lệ (bắt đầu bằng http).")
        return

    # Gửi tin nhắn trạng thái ban đầu
    status_msg = await message.reply("⏳ Đang khởi tạo quá trình bypass...")
    
    last_text = ""
    try:
        # Gọi hàm aio_fetch_links từ request_mualink
        async for progress in aio_fetch_links(text):
            if "step" in progress:
                # Cập nhật tiến độ
                new_text = f"⏳ <i>{progress['msg']}</i>"
                if new_text != last_text:
                    try:
                        await status_msg.edit_text(new_text)
                        last_text = new_text
                    except Exception as e:
                        logging.debug(f"Edit msg error: {e}")
                        
            elif "error" in progress:
                await status_msg.edit_text(f"❌ <b>Lỗi:</b> {progress['error']}")
                return
                
            elif "done" in progress and progress.get("done"):
                links = progress.get("links", [])
                if not links:
                    await status_msg.edit_text("⚠️ Không tìm thấy link đích nào.")
                    return
                
                # Trình bày kết quả
                result_text = f"✅ <b>Bẻ khóa thành công!</b>\n\n"
                for i, link in enumerate(links, 1):
                    result_text += f"{i}. {link}\n"
                    
                try:
                    await status_msg.edit_text(result_text, link_preview_options=types.LinkPreviewOptions(is_disabled=True))
                except TypeError:
                    # Fallback cho các phiên bản aiogram cũ hơn
                    await status_msg.edit_text(result_text, disable_web_page_preview=True)
                return
                
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        await status_msg.edit_text(f"❌ <b>Đã xảy ra lỗi không xác định:</b>\n{str(e)}")

async def main():
    logging.info("🤖 Bot đang chạy...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
