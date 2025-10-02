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

        # 🧍 USERS
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 80000,
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
            c.execute("INSERT INTO users(user_id, username, first_name) VALUES (?,?,?)",
                      (user_id, username, first_name))

def get_user(user_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return c.fetchone()

def update_balance(user_id: int, new_balance: float):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))

# ==============================
# 👥 GROUPS
# ==============================

def get_all_groups():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM groups WHERE approved=1")
        return c.fetchall()

def get_group(chat_id: int):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM groups WHERE chat_id=?", (chat_id,))
        return c.fetchone()

# ==============================
# 🎟️ BETS
# ==============================

def insert_bet(chat_id, round_id, user_id, bet_type, bet_value, amount):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO bets(chat_id, round_id, user_id, bet_type, bet_value, amount, balance)
        VALUES (?,?,?,?,?,?,(SELECT balance FROM users WHERE user_id=?))
        ON CONFLICT(chat_id, round_id, user_id, bet_type, bet_value)
        DO UPDATE SET amount = amount + excluded.amount
        """, (chat_id, round_id, user_id, bet_type, bet_value, amount, user_id))

def get_user_bet_in_round(user_id, chat_id, round_id, bet_type, bet_value):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        SELECT * FROM bets 
        WHERE user_id=? AND chat_id=? AND round_id=? AND bet_type=? AND bet_value=?
        """, (user_id, chat_id, round_id, bet_type, bet_value))
        return c.fetchone()

def update_bet_amount(bet_id, new_amount):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE bets SET amount=? WHERE id=?", (new_amount, bet_id))

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
