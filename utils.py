# utils.py — Các hàm tiện ích cho QLottery_bot

from datetime import datetime
import time

# ==============================
# 🆔 MÃ PHIÊN HIỆN TẠI
# ==============================

def get_current_round_id(chat_id: int) -> str:
    """
    Sinh round_id duy nhất theo chat + thời gian.
    Ví dụ: 123456789_20251002_1530
    """
    now = datetime.utcnow()
    return f"{chat_id}_{now.strftime('%Y%m%d_%H%M')}"

# ==============================
# 💵 ĐỊNH DẠNG TIỀN
# ==============================

def format_money(amount: int | float) -> str:
    """Định dạng tiền tệ VNĐ: 10000 -> 10.000₫"""
    return f"{int(amount):,}₫".replace(",", ".")

# ==============================
# ⏰ ĐẾM NGƯỢC (OPTIONAL)
# ==============================

async def send_countdown(context, chat_id, seconds_left):
    """Gửi thông báo đếm ngược vào group"""
    if seconds_left in (30, 10, 5):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ Còn {seconds_left}s trước khi chốt phiên!"
        )

# ==============================
# 🔒 KHÓA / MỞ CHAT (OPTIONAL)
# ==============================

async def lock_group_chat(context, chat_id):
    """Khoá chat nhóm 5s trước khi xổ"""
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions={"can_send_messages": False}
        )
    except Exception as e:
        print(f"[Lock Error] {e}")

async def unlock_group_chat(context, chat_id):
    """Mở chat khi phiên mới bắt đầu"""
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions={"can_send_messages": True}
        )
    except Exception as e:
        print(f"[Unlock Error] {e}")
