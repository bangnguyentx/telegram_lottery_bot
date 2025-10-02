import random
import asyncio
from datetime import datetime
from telegram import ChatPermissions

# 🧮 Định dạng tiền: 1000000 -> "1,000,000₫"
def format_money(amount: int) -> str:
    return f"{amount:,}₫"

# 🎲 Random 6 chữ số (0–9)
def generate_result(round_id: int) -> str:
    """
    Cách random: lấy thời gian hiện tại (HHMMSS) + 4 số cuối round_id,
    cộng lại -> nếu tổng lẻ thì ra số ngẫu nhiên chẵn, nếu tổng chẵn thì ra số ngẫu nhiên lẻ.
    Sau đó random đủ 6 số.
    """
    now = datetime.utcnow()
    seed = int(now.strftime("%H%M%S")) + int(str(round_id)[-4:])
    random.seed(seed)
    digits = [str(random.randint(0, 9)) for _ in range(6)]
    return "".join(digits)

# 🟡 Icon lịch sử phiên
def get_history_icon(result: str) -> str:
    """ 
    Quy ước:
      - ⚪ = Nhỏ (0–5)
      - ⚫ = Lớn (6–9)
      - 🟠 = Chẵn
      - 🔵 = Lẻ
    Lấy chữ số cuối cùng để quyết định lớn/nhỏ/chẵn/lẻ
    """
    last_digit = int(result[-1])
    icons = ""
    if last_digit <= 5:
        icons += "⚪"
    else:
        icons += "⚫"
    if last_digit % 2 == 0:
        icons += "🟠"
    else:
        icons += "🔵"
    return icons + f" {last_digit}"

# 🔐 Khóa chat nhóm khi còn 5s
async def lock_chat(context, chat_id):
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        print(f"[lock_chat] Lỗi: {e}")

# 🔓 Mở chat nhóm khi sang phiên mới
async def unlock_chat(context, chat_id):
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(can_send_messages=True)
        )
    except Exception as e:
        print(f"[unlock_chat] Lỗi: {e}")

# ⏱️ Countdown 60s cho mỗi phiên
async def countdown_and_announce(context, chat_id, round_id, announce_fn):
    """
    - Gửi thông báo còn 30s / 10s / 5s
    - Khóa chat khi còn 5s
    - Hết giờ thì gọi announce_fn() để xử lý tung kết quả
    """
    try:
        await asyncio.sleep(30)
        await context.bot.send_message(chat_id, "⏳ Còn 30 giây để đặt cược...")
        await asyncio.sleep(20)
        await context.bot.send_message(chat_id, "⏳ Còn 10 giây để đặt cược...")
        await asyncio.sleep(5)
        await context.bot.send_message(chat_id, "⏳ Còn 5 giây, chuẩn bị khoá chat!")
        await lock_chat(context, chat_id)
        await asyncio.sleep(5)
        # Hết giờ: xử lý kết quả
        await announce_fn()
        await unlock_chat(context, chat_id)
    except Exception as e:
        print(f"[countdown_and_announce] Lỗi: {e}")
