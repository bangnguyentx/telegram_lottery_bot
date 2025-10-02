import sqlite3
from datetime import datetime

DB_FILE = "lottery.db"

def connect():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        total_bet REAL DEFAULT 0,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_id INTEGER,
        round_id TEXT,
        bet_type TEXT,
        bet_value TEXT,
        amount REAL,
        timestamp TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rounds(
        round_id TEXT PRIMARY KEY,
        result TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def ensure_user(uid, username):
    conn = connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, username, balance, total_bet, created_at) VALUES (?,?,?,?,?)",
                (uid, username, 80000, 0, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def update_balance(uid, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()

def insert_bet(uid, chat_id, round_id, bet_type, bet_value, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO bets(user_id, chat_id, round_id, bet_type, bet_value, amount, timestamp) VALUES (?,?,?,?,?,?,?)",
                (uid, chat_id, round_id, bet_type, bet_value, amount, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
