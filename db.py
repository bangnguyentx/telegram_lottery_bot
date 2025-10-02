# db.py — SQLite cho QLottery_bot

import sqlite3
from datetime import datetime

DB_PATH = "lottery.db"

# ==============================
# 🔧 KẾT NỐI & KHỞI TẠO
# ==============================

def get_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit ON
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # 🧍‍♂️ USERS
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            total_bet REAL DEFAULT 0
        )
        """)

        # 👥 GROUPS
        c.execute("""
        CREATE TABLE IF NOT EXISTS groups(
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            approved INTEGER DEFAULT 1
        )
        """)

        # 🎟️ BETS
        c.execute("""
        CREATE TABLE IF NOT EXISTS bets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            round_id TEXT,
            user_id INTEGER,
            bet_type TEXT,
            bet_value TEXT,
            amount REAL,
            balance REAL,
            UNIQUE(chat_id, round_id, user_id, bet_type, bet_value)
        )
        """)

        # 📝 HISTORY
        c.execute("""
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            round_id TEXT,
            result_number TEXT,
            size TEXT,
            parity TEXT,
            created_at TEXT
        )
        """)
        conn.commit()

# ==============================
# 👤 USERS
# ==============================

def ensure_user(user_id: int, username: str, first_name: str):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if not c.fetchone():
            c.execute("""
            INSERT INTO users(user_id, username, first_name, balance)
            VALUES (?,?,?,80000)
            """, (user_id, username, first_name))

def get_user(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return c.fetchone()

def check_user_balance(user_id: int, amount: float) -> bool:
    """Kiểm tra xem user có đủ tiền cược không"""
    user = get_user(user_id)
    return user and user["balance"] >= amount

def update_balance(user_id: int, new_balance: float):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))

def deduct_balance(user_id: int, amount: float) -> bool:
    """Trừ tiền khi cược, tránh âm tài khoản"""
    user = get_user(user_id)
    if not user or user["balance"] < amount:
        return False
    new_balance = user["balance"] - amount
    update_balance(user_id, new_balance)
    return True

# ==============================
# 👥 GROUPS
# ==============================

def ensure_group(chat_id: int, title: str):
    """Lưu group nếu chưa có"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM groups WHERE chat_id=?", (chat_id,))
        if not c.fetchone():
            c.execute("INSERT INTO groups(chat_id, title, approved) VALUES (?,?,1)", (chat_id, title))

def get_all_groups():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM groups WHERE approved=1")
        return c.fetchall()

# ==============================
# 🎟️ BETS
# ==============================

def insert_or_update_bet(chat_id, round_id, user_id, bet_type, bet_value, amount):
    """Cộng dồn nếu cược trùng loại, tránh duplicate"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO bets(chat_id, round_id, user_id, bet_type, bet_value, amount, balance)
        VALUES (?,?,?,?,?,?,(SELECT balance FROM users WHERE user_id=?))
        ON CONFLICT(chat_id, round_id, user_id, bet_type, bet_value)
        DO UPDATE SET amount = amount + excluded.amount
        """, (chat_id, round_id, user_id, bet_type, bet_value, amount, user_id))

def get_bets_for_round(chat_id, round_id, user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        SELECT * FROM bets 
        WHERE chat_id=? AND round_id=? AND user_id=?
        """, (chat_id, round_id, user_id))
        return c.fetchall()

def get_bets_for_round_all(chat_id, round_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        SELECT b.*, u.balance 
        FROM bets b 
        JOIN users u ON b.user_id=u.user_id 
        WHERE b.chat_id=? AND b.round_id=?
        """, (chat_id, round_id))
        return c.fetchall()

def clear_bets_for_round(chat_id, round_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bets WHERE chat_id=? AND round_id=?", (chat_id, round_id))

# ==============================
# 📝 HISTORY
# ==============================

def insert_history(chat_id, round_id, result_number, size, parity):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO history(chat_id, round_id, result_number, size, parity, created_at)
        VALUES (?,?,?,?,?,?)
        """, (chat_id, round_id, result_number, size, parity, datetime.utcnow().isoformat()))
