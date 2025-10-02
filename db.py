import sqlite3
from datetime import datetime

DB_PATH = "myloto.db"

def db_connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def db_init():
    conn = db_connect()
    cur = conn.cursor()
    # Bảng user
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        total_bet INTEGER DEFAULT 0,
        received_start_bonus INTEGER DEFAULT 0
    )''')

    # Bảng phiên
    cur.execute('''CREATE TABLE IF NOT EXISTS rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        result TEXT,
        created_at TEXT
    )''')

    # Bảng cược
    cur.execute('''CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        round_id INTEGER,
        bet_type TEXT,
        bet_value TEXT,
        amount INTEGER,
        created_at TEXT
    )''')

    conn.commit()
    conn.close()

def get_user(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT id,balance,total_bet,received_start_bonus FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(user_id, bonus=0):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (id,balance,received_start_bonus) VALUES (?,?,?)", (user_id, bonus, 1 if bonus > 0 else 0))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
    conn.commit()
    conn.close()

def record_bet(user_id, round_id, bet_type, bet_value, amount):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bets (user_id, round_id, bet_type, bet_value, amount, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, round_id, bet_type, bet_value, amount, datetime.utcnow().isoformat())
    )
    cur.execute("UPDATE users SET balance = balance - ?, total_bet = total_bet + ? WHERE id=?",
                (amount, amount, user_id))
    conn.commit()
    conn.close()

def get_bets_by_round(round_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id, bet_type, bet_value, amount FROM bets WHERE round_id=?", (round_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def create_round(result):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO rounds (result, created_at) VALUES (?,?)", (result, datetime.utcnow().isoformat()))
    round_id = cur.lastrowid
    conn.commit()
    conn.close()
    return round_id

def get_last_rounds(limit=15):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(f"SELECT result FROM rounds ORDER BY id DESC LIMIT {limit}")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]
