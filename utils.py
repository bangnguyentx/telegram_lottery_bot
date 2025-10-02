import random
import asyncio
from datetime import datetime
from telegram import ChatPermissions

# ==============================
# 💰 Format tiền có dấu phẩy
# ==============================
def format_money(amount: int) -> str:
    try:
        return f"{amount:,}₫"
    except Exception:
        return f"{amount}₫"

# ==============================
# 🎲 Random kết quả xổ số (6 số)
# - Dùng giờ UTC + 4 số cuối phiên để tạo seed → đảm bảo ổn định
# ==============================
def random_result(period_id: int) -> str:
    now = datetime.utcnow()
    time_str = now.strftime("%H%M")  # HHMM
    seed = int(time_str + str(period_id)[-4:])  # ví dụ 0754 + 2345
    random.seed(seed)
    return "".join(str(random.randint(0, 9)) for _ in range(6))

# ==============================
# 🔐 Khoá chat nhóm (không cho gửi tin nhắn)
# ==============================
async def lock_group_chat(bot, chat_id: int):
    perms = ChatPermissions(can_send_messages=False)
    try:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=perms)
        print(f"[LockChat] Đã khoá chat {chat_id}")
    except Exception as e:
        print(f"[LockChat] Lỗi: {e}")

# ==============================
# 🔓 Mở chat nhóm
# ==============================
async def unlock_group_chat(bot, chat_id: int):
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True
    )
    try:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=perms)
        print(f"[UnlockChat] Đã mở chat {chat_id}")
    except Exception as e:
        print(f"[UnlockChat] Lỗi: {e}")

# ==============================
# ⏱ Countdown gửi thông báo
# - Gửi khi còn 30s, 10s, 5s
# - Khi còn 5s → khoá chat
# ==============================
async def countdown(bot, chat_id: int, delay: int):
    if delay <= 0:
        return

    # Thông báo còn 30s
    if delay > 30:
        await asyncio.sleep(delay - 30)
    if delay >= 30:
        try:
            await bot.send_message(chat_id, "⏳ Còn **30 giây** để tham gia phiên này!")
        except Exception as e:
            print(f"[Countdown] 30s lỗi: {e}")

    # Thông báo còn 10s
    if delay > 10:
        await asyncio.sleep(20)
    if delay >= 10:
        try:
            await bot.send_message(chat_id, "⚠️ Còn **10 giây** trước khi khoá!")
        except Exception as e:
            print(f"[Countdown] 10s lỗi: {e}")

    # Thông báo còn 5s và khoá chat
    if delay > 5:
        await asyncio.sleep(5)
    try:
        await bot.send_message(chat_id, "🚪 Đang khoá chat, chuẩn bị quay số!")
        await lock_group_chat(bot, chat_id)
    except Exception as e:
        print(f"[Countdown] 5s lỗi: {e}")

# ==============================
# 📅 Tạo mã phiên theo thời gian
# ==============================
def generate_period_id() -> int:
    now = datetime.utcnow()
    return int(now.strftime("%y%m%d%H%M%S"))  # ví dụ: 250930123000

# ==============================
# 📝 Kiểm tra 1 user đã nhận quà start chưa
# ==============================
def has_received_start_bonus(conn, user_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT received_bonus FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

# ==============================
# 📝 Đánh dấu user đã nhận quà start
# ==============================
def mark_start_bonus_received(conn, user_id: int):
    cur = conn.cursor()
    cur.execute("UPDATE users SET received_bonus=1 WHERE user_id=?", (user_id,))
    conn.commit()
