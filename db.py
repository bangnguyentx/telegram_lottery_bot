import sqlite3
from datetime import datetime

DB_PATH = "data.db"  # Tên file database

# ==============================
# 🧰 Kết nối database
# ==============================
def get_conn():
    return sqlite3.connect(DB_PATH)

# ==============================
# 🏗️ Tạo bảng
# ==============================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Bảng người dùng
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            total_bet INTEGER DEFAULT 0,
            received_bonus INTEGER DEFAULT 0
        )
    """)

    # Bảng lịch sử phiên
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            period_id INTEGER PRIMARY KEY,
            result TEXT,
            created_at TEXT
        )
    """)

    # Bảng cược
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            user_id INTEGER,
            bet_type TEXT,
            bet_value TEXT,
            amount INTEGER,
            created_at TEXT
        )
    """)

    # Bảng code nạp
    cur.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            bet_turns INTEGER,
            used_by INTEGER,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()

# ==============================
# 👤 Thêm user mới nếu chưa có
# ==============================
def ensure_user(user_id: int, username: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0)", (user_id, username))
        conn.commit()
    conn.close()

# ==============================
# 💰 Lấy số dư
# ==============================
def get_balance(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

# ==============================
# ➕ Cộng tiền
# ==============================
def add_balance(user_id: int, amount: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# ==============================
# ➖ Trừ tiền (nếu đủ)
# ==============================
def subtract_balance(user_id: int, amount: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return True

# ==============================
# 💸 Đặt cược
# ==============================
def insert_bet(period_id: int, user_id: int, bet_type: str, bet_value: str, amount: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bets (period_id, user_id, bet_type, bet_value, amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (period_id, user_id, bet_type, bet_value, amount, datetime.utcnow().isoformat()))
    cur.execute("UPDATE users SET total_bet = total_bet + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# ==============================
# 🧾 Lưu kết quả phiên
# ==============================
def insert_round(period_id: int, result: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO rounds (period_id, result, created_at) VALUES (?, ?, ?)",
                (period_id, result, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# ==============================
# 🧮 Lấy tất cả cược theo phiên
# ==============================
def get_bets_by_period(period_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, bet_type, bet_value, amount FROM bets WHERE period_id=?", (period_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ==============================
# 📝 Lấy lịch sử phiên (tối đa 15 bản ghi)
# ==============================
def get_last_rounds(limit: int = 15):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT period_id, result FROM rounds ORDER BY period_id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows[::-1]  # đảo ngược để hiện từ cũ → mới

# ==============================
# 🧑‍💻 Lấy top 10 người nạp nhiều nhất (giả sử = balance hiện tại)
# ==============================
def get_top10_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    return rows

# ==============================
# 🧾 Code nạp tiền
# ==============================
def create_code(code: str, amount: int, bet_turns: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO codes (code, amount, bet_turns, created_at) VALUES (?, ?, ?, ?)",
                (code, amount, bet_turns, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def redeem_code(code: str, user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT amount, used_by FROM codes WHERE code=?", (code,))
    row = cur.fetchone()
    if not row or row[1] is not None:
        conn.close()
        return 0
    amount = row[0]
    cur.execute("UPDATE codes SET used_by=? WHERE code=?", (user_id, code))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return amount
