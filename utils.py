# utils.py — Tiện ích cho QLottery_bot

import asyncio
import random
from datetime import datetime
from telegram import ChatPermissions
from telegram import Bot

from db import get_all_groups, get_bets_for_round_all, update_balance, clear_bets_for_round, insert_history
from handlers import calculate_payout

# 🕒 Thời gian 1 phiên xổ
ROUND_SECONDS = 60

# ----- 🧮 ĐỊNH DANH PHIÊN -----

def get_current_round_id(chat_id: int) -> str:
    ts = int(datetime.utcnow().timestamp())
    epoch = ts // ROUND_SECONDS
    return f"{chat_id}_{epoch}"

# ----- 💬 GỬI THÔNG BÁO -----

async def send_countdown(bot: Bot, chat_id: int, seconds: int):
    if seconds == 30:
        await bot.send_message(chat_id, "⏰ Còn **30 giây** trước khi quay kết quả, hãy nhanh tay cược!")
    elif seconds == 10:
        await bot.send_message(chat_id, "⚠️ Còn **10 giây** cuối, sắp khoá cược!")
    elif seconds == 5:
        await bot.send_message(chat_id, "🔒 Phiên sắp quay — Chat đã bị khoá để chốt cược!")
        await lock_group_chat(bot, chat_id)

# ----- 🔐 KHÓA & MỞ CHAT -----

async def lock_group_chat(bot: Bot, chat_id: int):
    try:
        perms = ChatPermissions(can_send_messages=False)
        await bot.set_chat_permissions(chat_id, perms)
    except Exception:
        pass

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
    except Exception:
        pass

# ----- 🎲 RANDOM KẾT QUẢ -----

def generate_lottery_result(round_id: str) -> str:
    """Tạo kết quả ngẫu nhiên dựa theo thời gian + round_id"""
    now = datetime.utcnow()
    seed = int(now.strftime("%H%M%S") + round_id[-4:])
    random.seed(seed)
    digits = [str(random.randint(0, 9)) for _ in range(6)]
    return "".join(digits)

def categorize_result(result_number: str) -> str:
    """Phân loại: Nhỏ/Lớn + Chẵn/Lẻ dựa theo số cuối"""
    last_digit = int(result_number[-1])
    if last_digit <= 5:
        size = "N"  # Nhỏ
    else:
        size = "L"  # Lớn
    if last_digit % 2 == 0:
        parity = "C"  # Chẵn
    else:
        parity = "LE"  # Lẻ
    return size, parity

# ----- 💸 TRẢ THƯỞNG -----

def settle_bets_for_group(chat_id: int, round_id: str, result_number: str):
    """Tự động trả thưởng cho tất cả user trong group"""
    bets = get_bets_for_round_all(chat_id, round_id)
    size, parity = categorize_result(result_number)

    winners = []
    for b in bets:
        payout = 0
        payout = calculate_payout(
            b["bet_type"], b["bet_value"], b["amount"], result_number, 
            b["bet_type"] if b["bet_type"] in ("N", "L", "C", "LE") else size if b["bet_type"] in ("N", "L") else parity
        )

        if payout > 0:
            update_balance(b["user_id"], (b["balance"] or 0) + payout)
            winners.append((b["user_id"], payout))

    clear_bets_for_round(chat_id, round_id)
    return winners, size, parity

# ----- 🌀 CHU TRÌNH 60S -----

async def start_lottery_cycle(app):
    """Chạy vòng quay xổ số cho toàn bộ group"""
    bot = app.bot
    groups = get_all_groups()

    for g in groups:
        chat_id = g["chat_id"]

        # --- 30s & 10s & 5s countdown ---
        asyncio.create_task(send_countdown(bot, chat_id, 30))
        asyncio.create_task(asyncio.sleep(20))
        asyncio.create_task(send_countdown(bot, chat_id, 10))
        asyncio.create_task(asyncio.sleep(5))
        asyncio.create_task(send_countdown(bot, chat_id, 5))

        # --- Đợi đến lúc quay ---
        await asyncio.sleep(ROUND_SECONDS)

        # --- Quay kết quả ---
        round_id = get_current_round_id(chat_id)
        result = generate_lottery_result(round_id)

        # --- Tính thưởng & trả ---
        winners, size, parity = settle_bets_for_group(chat_id, round_id, result)

        # --- Lưu lịch sử ---
        insert_history(chat_id, round_id, result, size, parity)

        # --- Thông báo kết quả ---
        size_name = "Nhỏ" if size == "N" else "Lớn"
        parity_name = "Chẵn" if parity == "C" else "Lẻ"
        txt = f"🎯 Kết quả phiên {round_id.split('_')[-1]}:\n\n👉 **{result}**\n👉 {size_name} / {parity_name}"

        if winners:
            txt += f"\n\n🏆 Có {len(winners)} người thắng!"
        else:
            txt += "\n\n😢 Không có ai thắng."

        await bot.send_message(chat_id, txt)

        # --- Mở lại chat ---
        await unlock_group_chat(bot, chat_id)
