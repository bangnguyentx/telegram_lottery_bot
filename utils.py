# utils.py — Tiện ích cho QLottery_bot

import asyncio
import random
from datetime import datetime
from telegram import ChatPermissions, Bot

from db import (
    get_all_groups,
    get_bets_for_round_all,
    update_balance,
    clear_bets_for_round,
    insert_history,
)

# 🕒 Thời gian 1 phiên xổ
ROUND_SECONDS = 60

# ----- 🧮 ĐỊNH DANH PHIÊN -----

def get_current_round_id(chat_id: int) -> str:
    """Tạo round_id theo chat_id + epoch 60s"""
    ts = int(datetime.utcnow().timestamp())
    epoch = ts // ROUND_SECONDS
    return f"{chat_id}_{epoch}"

# ----- 💰 Format tiền -----

def format_money(amount: int) -> str:
    return f"{amount:,}₫".replace(",", ".")

# ----- 💬 GỬI THÔNG BÁO -----

async def send_countdown(bot: Bot, chat_id: int, seconds: int):
    """Gửi thông báo đếm ngược ở 30s, 10s, 5s"""
    try:
        if seconds == 30:
            await bot.send_message(chat_id, "⏰ Còn **30 giây** trước khi quay kết quả, hãy nhanh tay cược!")
        elif seconds == 10:
            await bot.send_message(chat_id, "⚠️ Còn **10 giây** cuối, sắp khoá cược!")
        elif seconds == 5:
            await bot.send_message(chat_id, "🔒 Phiên sắp quay — Chat đã bị khoá để chốt cược!")
            await lock_group_chat(bot, chat_id)
    except Exception as e:
        print(f"[Countdown] Error: {e}")

# ----- 🔐 KHÓA & MỞ CHAT -----

async def lock_group_chat(bot: Bot, chat_id: int):
    try:
        perms = ChatPermissions(can_send_messages=False)
        await bot.set_chat_permissions(chat_id, perms)
    except Exception as e:
        print(f"[LockChat] {e}")

async def unlock_group_chat(bot: Bot, chat_id: int):
    try:
        perms = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        await bot.set_chat_permissions(chat_id, perms)
    except Exception as e:
        print(f"[UnlockChat] {e}")

# ----- 🎲 RANDOM KẾT QUẢ -----

def generate_lottery_result(round_id: str) -> str:
    """Tạo kết quả ngẫu nhiên dựa theo thời gian + round_id"""
    now = datetime.utcnow()
    seed = int(now.strftime("%H%M%S") + round_id[-4:])
    random.seed(seed)
    digits = [str(random.randint(0, 9)) for _ in range(6)]
    return "".join(digits)

def categorize_result(result_number: str):
    """Phân loại: Nhỏ/Lớn + Chẵn/Lẻ dựa theo số cuối"""
    last_digit = int(result_number[-1])
    size = "N" if last_digit <= 4 else "L"
    parity = "C" if last_digit % 2 == 0 else "LE"
    return size, parity

# ----- 🧮 TÍNH TIỀN THẮNG -----

def calculate_payout(bet_type: str, bet_value: str, amount: int, result_number: str) -> int:
    """Trả về số tiền thắng theo loại cược"""
    if bet_type in ("N", "L", "C", "LE"):
        size, parity = categorize_result(result_number)
        if bet_type == size or bet_type == parity:
            return int(amount * 1.97)
        return 0

    elif bet_type == "S":
        if result_number.endswith(bet_value):
            n = len(bet_value)
            if n == 1: return int(amount * 9.2)
            if n == 2: return int(amount * 90)
            if n == 3: return int(amount * 900)
            if n == 4: return int(amount * 8000)
            if n == 5: return int(amount * 50000)
            if n == 6: return int(amount * 200000)
    return 0

# ----- 💸 TRẢ THƯỞNG -----

def settle_bets_for_group(chat_id: int, round_id: str, result_number: str):
    """Tự động trả thưởng cho tất cả user trong group"""
    bets = get_bets_for_round_all(chat_id, round_id)
    winners = []

    for b in bets:
        payout = calculate_payout(b["bet_type"], b["bet_value"], b["amount"], result_number)
        if payout > 0:
            update_balance(b["user_id"], (b["balance"] or 0) + payout)
            winners.append((b["user_id"], payout))

    clear_bets_for_round(chat_id, round_id)
    return winners, *categorize_result(result_number)

# ----- 🌀 CHU TRÌNH 60S -----

async def start_lottery_cycle(app):
    """Chạy vòng quay xổ số cho toàn bộ group"""
    bot = app.bot
    groups = get_all_groups()

    for g in groups:
        chat_id = g["chat_id"]

        # --- Countdown ---
        asyncio.create_task(send_countdown(bot, chat_id, 30))
        asyncio.create_task(asyncio.sleep(20))
        asyncio.create_task(send_countdown(bot, chat_id, 10))
        asyncio.create_task(asyncio.sleep(5))
        asyncio.create_task(send_countdown(bot, chat_id, 5))

    # Đợi đúng 60s rồi quay cho tất cả nhóm cùng lúc
    await asyncio.sleep(ROUND_SECONDS)

    for g in groups:
        chat_id = g["chat_id"]
        round_id = get_current_round_id(chat_id)
        result = generate_lottery_result(round_id)
        winners, size, parity = settle_bets_for_group(chat_id, round_id, result)

        insert_history(chat_id, round_id, result, size, parity)

        size_name = "Nhỏ" if size == "N" else "Lớn"
        parity_name = "Chẵn" if parity == "C" else "Lẻ"
        txt = f"🎯 Kết quả phiên {round_id.split('_')[-1]}:\n\n👉 **{result}**\n👉 {size_name} / {parity_name}"

        if winners:
            txt += f"\n\n🏆 Có {len(winners)} người thắng!"
        else:
            txt += "\n\n😢 Không có ai thắng."

        await bot.send_message(chat_id, txt)
        await unlock_group_chat(bot, chat_id)
