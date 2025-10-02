# utils.py — Tiện ích cho QLottery_bot
import asyncio
import random
from datetime import datetime
from telegram import ChatPermissions, Bot
from db import get_all_groups, get_bets_for_round_all, update_balance, clear_bets_for_round, insert_history

ROUND_SECONDS = 60

def get_current_round_id(chat_id: int) -> str:
    ts = int(datetime.utcnow().timestamp())
    epoch = ts // ROUND_SECONDS
    return f"{chat_id}_{epoch}"

def format_money(amount: int) -> str:
    return f"{amount:,}₫".replace(",", ".")

async def send_countdown(bot: Bot, chat_id: int, seconds: int):
    try:
        if seconds == 30:
            await bot.send_message(chat_id, "⏰ Còn 30 giây trước khi quay kết quả!")
        elif seconds == 10:
            await bot.send_message(chat_id, "⚠️ Còn 10 giây cuối, sắp khoá cược!")
        elif seconds == 5:
            await bot.send_message(chat_id, "🔒 Phiên sắp quay — Chat đã bị khoá!")
            await lock_group_chat(bot, chat_id)
    except Exception as e:
        print(f"[Countdown] {e}")

async def lock_group_chat(bot: Bot, chat_id: int):
    try:
        perms = ChatPermissions(can_send_messages=False)
        await bot.set_chat_permissions(chat_id, perms)
    except Exception as e:
        print(f"[Lock] {e}")

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
        print(f"[Unlock] {e}")

def generate_lottery_result(round_id: str) -> str:
    now = datetime.utcnow()
    seed = int(now.strftime("%H%M%S") + round_id[-4:])
    random.seed(seed)
    return "".join(str(random.randint(0, 9)) for _ in range(6))

def categorize_result(result_number: str):
    last_digit = int(result_number[-1])
    size = "N" if last_digit <= 4 else "L"
    parity = "C" if last_digit % 2 == 0 else "LE"
    return size, parity

def calculate_payout(bet_type: str, bet_value: str, amount: int, result_number: str) -> int:
    size, parity = categorize_result(result_number)
    if bet_type in ("N", "L", "C", "LE"):
        if bet_type == size or bet_type == parity:
            return int(amount * 1.97)
        return 0
    elif bet_type == "S" and result_number.endswith(bet_value):
        n = len(bet_value)
        mult = {1: 9.2, 2: 90, 3: 900, 4: 8000, 5: 50000, 6: 200000}.get(n, 0)
        return int(amount * mult)
    return 0

def settle_bets_for_group(chat_id: int, round_id: str, result_number: str):
    bets = get_bets_for_round_all(chat_id, round_id)
    winners = []
    for b in bets:
        payout = calculate_payout(b["bet_type"], b["bet_value"], b["amount"], result_number)
        if payout > 0:
            update_balance(b["user_id"], (b["balance"] or 0) + payout)
            winners.append((b["user_id"], payout))
    clear_bets_for_round(chat_id, round_id)
    return winners, *categorize_result(result_number)

async def start_lottery_cycle(app):
    bot = app.bot
    groups = get_all_groups()
    for g in groups:
        chat_id = g["chat_id"]
        asyncio.create_task(send_countdown(bot, chat_id, 30))
        asyncio.create_task(asyncio.sleep(20))
        asyncio.create_task(send_countdown(bot, chat_id, 10))
        asyncio.create_task(asyncio.sleep(5))
        asyncio.create_task(send_countdown(bot, chat_id, 5))

    await asyncio.sleep(ROUND_SECONDS)

    for g in groups:
        chat_id = g["chat_id"]
        round_id = get_current_round_id(chat_id)
        result = generate_lottery_result(round_id)
        winners, size, parity = settle_bets_for_group(chat_id, round_id, result)
        insert_history(chat_id, round_id, result, size, parity)

        size_name = "Nhỏ" if size == "N" else "Lớn"
        parity_name = "Chẵn" if parity == "C" else "Lẻ"
        txt = f"🎯 Kết quả phiên {round_id.split('_')[-1]}:\n👉 **{result}**\n👉 {size_name} / {parity_name}"
        txt += f"\n\n🏆 Có {len(winners)} người thắng!" if winners else "\n\n😢 Không có ai thắng."
        await bot.send_message(chat_id, txt)
        await unlock_group_chat(bot, chat_id)
