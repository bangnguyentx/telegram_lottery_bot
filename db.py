# db.py — SQLite cho QLottery_bot

import sqlite3
from datetime import datetime

DB_PATH = "lottery.db"

# ----- 🔧 KHỞI TẠO -----

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            total_bet REAL DEFAULT 0
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS groups(
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            approved INTEGER DEFAULT 1
        )""")
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
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            round_id TEXT,
            result_number TEXT,
            size TEXT,
            parity TEXT,
            created_at TEXT
        )""")
        conn.commit()

# ----- 👤 USER -----

def ensure_user(user_id, username, first_name):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users(user_id, username, first_name, balance) VALUES (?,?,?,80000)", 
                      (user_id, username, first_name))
            conn.commit()

def get_user(user_id):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return c.fetchone()

def update_balance(user_id, new_balance):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
        conn.commit()

# ----- 📝 BETS -----

def insert_or_update_bet(chat_id, round_id, user_id, bet_type, bet_value, amount):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO bets(chat_id, round_id, user_id, bet_type, bet_value, amount, balance)
        VALUES (?,?,?,?,?,?,(SELECT balance FROM users WHERE user_id=?))
        ON CONFLICT(chat_id, round_id, user_id, bet_type, bet_value)
        DO UPDATE SET amount = amount + excluded.amount
        """, (chat_id, round_id, user_id, bet_type, bet_value, amount, user_id))
        conn.commit()

def get_bets_for_round(chat_id, round_id, user_id):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM bets WHERE chat_id=? AND round_id=? AND user_id=?", 
                  (chat_id, round_id, user_id))
        return c.fetchall()

def get_bets_for_round_all(chat_id, round_id):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT b.*, u.balance FROM bets b JOIN users u ON b.user_id=u.user_id WHERE b.chat_id=? AND b.round_id=?", 
                  (chat_id, round_id))
        return c.fetchall()

def clear_bets_for_round(chat_id, round_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM bets WHERE chat_id=? AND round_id=?", (chat_id, round_id))
        conn.commit()

# ----- 📜 HISTORY & GROUPS -----

def insert_history(chat_id, round_id, result_number, size, parity):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO history(chat_id, round_id, result_number, size, parity, created_at) VALUES (?,?,?,?,?,?)", 
                  (chat_id, round_id, result_number, size, parity, datetime.utcnow().isoformat()))
        conn.commit()

def get_all_groups():
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM groups WHERE approved=1")
        return c.fetchall()
