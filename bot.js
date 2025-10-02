/**
 * bot.js
 * Telegram Quick Lottery Bot - Render-ready
 * Node 18+, CommonJS
 *
 * Usage: node bot.js
 *
 * ENV (Render -> Environment):
 * BOT_TOKEN        - Telegram Bot Token (from BotFather)
 * ADMIN_ID         - Telegram user id of admin (number)
 * DATABASE_URL     - PostgreSQL connection string
 * LOG_CHANNEL_ID   - (optional) channel id for logs, e.g. -1001234567890
 * FREE_BONUS       - optional initial bonus (default 80000)
 * NODE_ENV         - production/development
 * PORT             - optional HTTP port; default 10000
 *
 * Dependencies:
 * npm i telegraf pg dotenv
 *
 * Notes:
 * - This file uses long-polling to keep bot simple on Render.
 * - If using Render Web Service, keep-alive server prevents "no open port" errors.
 * - If you prefer Background Worker in Render, you can remove HTTP server.
 */

// -------------------------
// Load env & modules
// -------------------------
require('dotenv').config();
const http = require('http');
const { Telegraf } = require('telegraf');
const { Pool } = require('pg');

// -------------------------
// Configuration
// -------------------------
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID, 10) : null;
const DATABASE_URL = process.env.DATABASE_URL;
const LOG_CHANNEL_ID = process.env.LOG_CHANNEL_ID || null;
const FREE_BONUS = parseInt(process.env.FREE_BONUS || '80000', 10);
const KEEPALIVE_PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 10000;

// sanity checks
if (!BOT_TOKEN) {
  console.error('Missing BOT_TOKEN. Exiting.');
  process.exit(1);
}
if (!DATABASE_URL) {
  console.error('Missing DATABASE_URL. Exiting.');
  process.exit(1);
}
if (!ADMIN_ID) {
  console.warn('Warning: ADMIN_ID not set. Admin-only commands will fail.');
}

// -------------------------
// Keep-alive HTTP server (for Render Web Service)
// -------------------------
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Telegram Quick Lottery Bot is running.\n');
}).listen(KEEPALIVE_PORT, () => {
  console.log(`Keep-alive server listening on port ${KEEPALIVE_PORT}`);
});

// -------------------------
// Postgres pool
// -------------------------
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: (process.env.NODE_ENV === 'production') ? { rejectUnauthorized: false } : false,
});

// helper DB function
async function db(query, params = []) {
  const client = await pool.connect();
  try {
    const res = await client.query(query, params);
    return res;
  } finally {
    client.release();
  }
}

// -------------------------
// Utilities
// -------------------------
function formatMoney(v) {
  if (v === null || v === undefined) v = 0;
  const num = Number(v) || 0;
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "₫";
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function pickRandomDigit() { return Math.floor(Math.random() * 10); }
function nowISO() { return new Date().toISOString(); }

// Payout multipliers (follow your spec)
const MULTIPLIERS = {
  single: 9.2,
  two: 90,
  three: 900,
  four: 8000,
  five: 50000,
  six: 200000,
  small_big: 1.97,
  even_odd: 1.97
};

// -------------------------
// Crash handling & logging
// -------------------------
const bot = new Telegraf(BOT_TOKEN);

async function logToAdminAndChannel(text) {
  console.log(text);
  try {
    if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
  } catch (e) { console.warn('Fail send to admin', e); }
  try {
    if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, text);
  } catch (e) { /* ignore */ }
}

process.on('uncaughtException', async (err) => {
  await logToAdminAndChannel(`⚠️ UncaughtException at ${nowISO()}:\n${err.stack || err}`);
  process.exit(1);
});
process.on('unhandledRejection', async (reason) => {
  await logToAdminAndChannel(`⚠️ UnhandledRejection at ${nowISO()}:\n${String(reason)}`);
});

// -------------------------
// DB initialization
// -------------------------
async function initDb() {
  // Create tables if not exist (idempotent)
  await db(`
    CREATE TABLE IF NOT EXISTS users (
      id SERIAL PRIMARY KEY,
      tg_id BIGINT UNIQUE NOT NULL,
      username TEXT,
      balance BIGINT DEFAULT 0,
      total_deposit BIGINT DEFAULT 0,
      free_given BOOLEAN DEFAULT FALSE,
      free_locked BOOLEAN DEFAULT TRUE,
      rounds_played INTEGER DEFAULT 0
    );
  `);

  await db(`
    CREATE TABLE IF NOT EXISTS groups (
      chat_id BIGINT PRIMARY KEY,
      approved BOOLEAN DEFAULT FALSE,
      running BOOLEAN DEFAULT FALSE
    );
  `);

  await db(`
    CREATE TABLE IF NOT EXISTS rounds (
      id SERIAL PRIMARY KEY,
      chat_id BIGINT NOT NULL,
      started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
      sequence TEXT,
      status TEXT DEFAULT 'running',
      override TEXT DEFAULT NULL
    );
  `);

  await db(`
    CREATE TABLE IF NOT EXISTS bets (
      id SERIAL PRIMARY KEY,
      round_id INTEGER REFERENCES rounds(id) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      bet_type TEXT NOT NULL,
      bet_value TEXT,
      amount BIGINT NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
      paid BOOLEAN DEFAULT FALSE
    );
  `);

  await db(`
    CREATE TABLE IF NOT EXISTS codes (
      id SERIAL PRIMARY KEY,
      code TEXT UNIQUE,
      amount BIGINT NOT NULL,
      rounds_required INTEGER DEFAULT 0,
      used_by INTEGER REFERENCES users(id),
      used_at TIMESTAMP WITH TIME ZONE
    );
  `);

  console.log('[DB] Tables initialized');
}

// -------------------------
// DB helpers: users/groups/rounds/bets
// -------------------------
async function ensureUser(tg_id_or_ctx) {
  let tg_id, username;
  if (typeof tg_id_or_ctx === 'object' && tg_id_or_ctx.from) {
    tg_id = tg_id_or_ctx.from.id;
    username = tg_id_or_ctx.from.username || tg_id_or_ctx.from.first_name || null;
  } else {
    tg_id = tg_id_or_ctx;
    username = null;
  }
  const res = await db('SELECT * FROM users WHERE tg_id=$1', [tg_id]);
  if (res.rowCount === 0) {
    const ins = await db('INSERT INTO users(tg_id, username) VALUES($1,$2) RETURNING *', [tg_id, username]);
    return ins.rows[0];
  }
  return res.rows[0];
}
async function getGroup(chat_id) {
  const res = await db('SELECT * FROM groups WHERE chat_id=$1', [chat_id]);
  if (res.rowCount === 0) return null;
  return res.rows[0];
}
async function setGroup(chat_id, approved = false, running = false) {
  await db('INSERT INTO groups(chat_id, approved, running) VALUES($1,$2,$3) ON CONFLICT (chat_id) DO UPDATE SET approved=$2, running=$3', [chat_id, approved, running]);
}
async function createRunningRound(chat_id) {
  const res = await db('INSERT INTO rounds(chat_id, status) VALUES($1, $2) RETURNING *', [chat_id, 'running']);
  return res.rows[0];
}
async function getLatestRunningRound(chat_id) {
  const res = await db("SELECT * FROM rounds WHERE chat_id=$1 AND status='running' ORDER BY started_at DESC LIMIT 1", [chat_id]);
  if (res.rowCount === 0) return null;
  return res.rows[0];
}
async function insertBet(round_id, user_id, bet_type, bet_value, amount) {
  await db('INSERT INTO bets(round_id, user_id, bet_type, bet_value, amount) VALUES($1,$2,$3,$4,$5)', [round_id, user_id, bet_type, bet_value, amount]);
}

// -------------------------
// Bot commands - private
// -------------------------
bot.start(async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') {
      return ctx.reply('Chào! Chat riêng với bot để nhận bonus và xem menu. Trong nhóm, dùng /batdau để yêu cầu admin bật bot.');
    }
    const user = await ensureUser(ctx);
    if (!user.free_given) {
      await db('UPDATE users SET balance = balance + $1, free_given = true, free_locked = true WHERE tg_id=$2', [FREE_BONUS, ctx.from.id]);
      await ctx.replyWithMarkdown(`👋 Chào *${ctx.from.first_name}*! Bạn được tặng *${formatMoney(FREE_BONUS)}*.\nLưu ý: tiền free cần cược đủ điều kiện trước khi rút.`);
      await logToAdminAndChannel(`[BONUS] Given ${formatMoney(FREE_BONUS)} to ${ctx.from.id} (${ctx.from.username || ctx.from.first_name})`);
    } else {
      await ctx.reply(`Chào ${ctx.from.first_name}! Bạn đã nhận bonus trước đó.`);
    }
  } catch (e) {
    console.error('start error', e);
    ctx.reply('Có lỗi khi xử lý /start.');
  }
});

// Help & menu
bot.command('help', (ctx) => {
  const helpText = [
    '🎮 Quick Lottery Bot - hướng dẫn cơ bản:',
    '/start - Nhận bonus (private)',
    'Trong nhóm (khi bot đã được bật):',
    '  /N<amount> - cược Nhỏ (0-5)',
    '  /L<amount> - cược Lớn (6-9)',
    '  /C<amount> - cược Chẵn',
    '  /Le<amount> - cược Lẻ',
    '  /S<number> <amount> - cược số (ví dụ /S1 1000 hoặc /S91 1000)',
    'Admin:',
    '  /approve_group <chat_id> - approve group',
    '  /startbot_in_group <chat_id> - start group runner',
    '  /congtien <tg_id> <amount> - cộng tiền cho user',
    '  /top10 - xem top 10 nạp nhiều nhất',
    '  /Nho /Lon /Chan /Le - override kết quả phiên đang chạy (silent)',
  ];
  ctx.reply(helpText.join('\n'));
});

// Simple private commands
bot.command('ping', (ctx) => ctx.reply('Pong!'));

// /ruttien (private)
bot.command('ruttien', async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') return ctx.reply('Lệnh /ruttien chỉ dùng trong chat riêng với bot.');
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 4) return ctx.reply('Cú pháp: /ruttien <Ngân hàng> <Số tài khoản> <Số tiền>');
    const bank = parts[1], acc = parts[2], amount = parseInt(parts[3], 10);
    if (isNaN(amount) || amount < 100000) return ctx.reply('Số tiền rút tối thiểu 100000₫');
    const u = await ensureUser(ctx);
    if ((u.rounds_played || 0) < 1) return ctx.reply('Bạn chưa cược đủ 1 vòng. Không thể rút.');
    // Notify admin
    const text = `📤 Yêu cầu rút tiền của ${ctx.from.username||ctx.from.first_name} (${ctx.from.id})\nNgân hàng: ${bank}\nSTK: ${acc}\nSố tiền: ${formatMoney(amount)}\nTG: ${nowISO()}`;
    if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
    await ctx.reply('Yêu cầu rút đã gửi cho admin. Vui lòng chờ.');
  } catch (e) {
    console.error('/ruttien error', e);
    ctx.reply('Lỗi khi gửi yêu cầu rút.');
  }
});

// -------------------------
// Admin commands
// -------------------------
function isAdmin(ctx) {
  return ctx.from && ctx.from.id && ADMIN_ID && (ctx.from.id === ADMIN_ID);
}

// /congtien
bot.command('congtien', async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin được dùng lệnh này.');
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 3) return ctx.reply('Usage: /congtien <tg_id> <amount>');
    const tg_id = parseInt(parts[1], 10), amount = parseInt(parts[2], 10);
    if (isNaN(tg_id) || isNaN(amount) || amount <= 0) return ctx.reply('Số không hợp lệ.');
    await ensureUser(tg_id);
    await db('UPDATE users SET balance = balance + $1, total_deposit = total_deposit + $1 WHERE tg_id=$2', [amount, tg_id]);
    ctx.reply(`Đã cộng ${formatMoney(amount)} cho ${tg_id}`);
    try { await bot.telegram.sendMessage(tg_id, `Admin đã cộng cho bạn ${formatMoney(amount)}`); } catch (e) {}
    await logToAdminAndChannel(`[CONGTIEN] Admin ${ctx.from.id} cộng ${formatMoney(amount)} cho ${tg_id} at ${nowISO()}`);
  } catch (e) {
    console.error('/congtien error', e);
    ctx.reply('Lỗi khi cộng tiền.');
  }
});

// /top10
bot.command('top10', async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin.');
    const res = await db('SELECT username,tg_id,total_deposit FROM users ORDER BY total_deposit DESC LIMIT 10');
    if (res.rowCount === 0) return ctx.reply('Chưa có dữ liệu nạp.');
    const lines = res.rows.map((r, i) => `${i+1}. ${r.username || r.tg_id} — ${formatMoney(r.total_deposit || 0)}`);
    ctx.reply(lines.join('\n'));
  } catch (e) {
    console.error('/top10 error', e);
  }
});

// /code generate
bot.command('code', async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin.');
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 3) return ctx.reply('Usage: /code <amount> <rounds_required>');
    const amount = parseInt(parts[1], 10), rounds = parseInt(parts[2], 10);
    if (isNaN(amount) || isNaN(rounds)) return ctx.reply('Số không hợp lệ.');
    const code = 'C' + Math.random().toString(36).substring(2, 10).toUpperCase();
    await db('INSERT INTO codes(code, amount, rounds_required) VALUES($1,$2,$3)', [code, amount, rounds]);
    ctx.reply(`Tạo code: ${code} — ${formatMoney(amount)} — rounds: ${rounds}`);
    await logToAdminAndChannel(`[CODE] Admin ${ctx.from.id} tạo code ${code} for ${formatMoney(amount)} rounds:${rounds}`);
  } catch (e) {
    console.error('/code error', e);
  }
});

// Group approval and start
bot.command('approve_group', async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin.');
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 2) return ctx.reply('Usage: /approve_group <chat_id>');
    const chat_id = parseInt(parts[1], 10);
    if (isNaN(chat_id)) return ctx.reply('chat_id không hợp lệ.');
    await setGroup(chat_id, true, false);
    ctx.reply(`Group ${chat_id} approved.`);
    await logToAdminAndChannel(`[APPROVE_GROUP] Admin ${ctx.from.id} approved ${chat_id}`);
  } catch (e) {
    console.error('/approve_group error', e);
  }
});

bot.command('startbot_in_group', async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin.');
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 2) return ctx.reply('Usage: /startbot_in_group <chat_id>');
    const chat_id = parseInt(parts[1], 10);
    await setGroup(chat_id, true, true);
    ctx.reply(`Group ${chat_id} set running.`);
    await logToAdminAndChannel(`[START_GROUP] Admin ${ctx.from.id} started ${chat_id}`);
    // start runner asynchronously (function defined later)
    startRunnerForGroup(chat_id);
  } catch (e) {
    console.error('/startbot_in_group error', e);
  }
});

// Admin override current running round silently: /Nho /Lon /Chan /Le
const OVERRIDES = { Nho: 'Nho', Lon: 'Lon', Chan: 'Chan', Le: 'Le' };
bot.command(['Nho','Lon','Chan','Le'], async (ctx) => {
  try {
    if (!isAdmin(ctx)) return ctx.reply('Chỉ admin.');
    const q = await db("SELECT * FROM rounds WHERE status='running' ORDER BY started_at DESC LIMIT 1");
    if (q.rowCount === 0) return ctx.reply('Không có phiên đang chạy.');
    const round = q.rows[0];
    const cmd = ctx.message.text.replace('/', '').split(' ')[0];
    const ov = OVERRIDES[cmd] || null;
    await db('UPDATE rounds SET override=$1 WHERE id=$2', [ov, round.id]);
    ctx.reply(`Override ${ov} đã đặt cho phiên ${round.id} (silent).`);
    if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[OVERRIDE] Admin ${ctx.from.id} set ${ov} for round ${round.id}`);
  } catch (e) {
    console.error('override error', e);
  }
});

// -------------------------
// Betting in group
// -------------------------
// Patterns supported in groups:
// /N1000 or /N 1000
// /L1000 or /L 1000
// /C1000 or /C 1000
// /Le1000 or /Le 1000
// /S1 1000 or /S 1 1000 or /S91 1000
bot.on('text', async (ctx, next) => {
  try {
    const text = (ctx.message && ctx.message.text) ? ctx.message.text.trim() : '';
    if (!text) return next();
    // only handle bets in groups
    if (ctx.chat.type === 'private') return next();

    // simple regex
    const reSimple = text.match(/^\/(N|L|C|Le)\s*([0-9]+)$/i);
    const reS1 = text.match(/^\/S\s*([0-9]{1,6})\s+([0-9]+)$/i);
    const reS2 = text.match(/^\/S([0-9]{1,6})\s*([0-9]+)$/i);

    if (!reSimple && !reS1 && !reS2) return next();

    // group must be approved and running
    const g = await getGroup(ctx.chat.id);
    if (!g || !g.approved || !g.running) return ctx.reply('Game chưa bật ở nhóm này.');

    // ensure user
    const user = await ensureUser(ctx);
    // current round
    const round = await getLatestRunningRound(ctx.chat.id);
    if (!round) return ctx.reply('Không có phiên đang chạy.');

    if (reSimple) {
      const type = reSimple[1];
      const amount = parseInt(reSimple[2], 10);
      if (isNaN(amount) || amount <= 0) return ctx.reply('Số tiền không hợp lệ.');
      if (Number(user.balance) < amount) return ctx.reply('Bạn không đủ số dư.');
      // deduct balance
      await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
      await insertBet(round.id, user.id, type.toUpperCase(), null, amount);
      return ctx.reply(`Đã đặt ${type.toUpperCase()} ${formatMoney(amount)} cho phiên hiện tại.`);
    }

    const matchS = reS1 || reS2;
    if (matchS) {
      const numbers = matchS[1];
      const amount = parseInt(matchS[2], 10);
      if (isNaN(amount) || amount <= 0) return ctx.reply('Số tiền không hợp lệ.');
      if (Number(user.balance) < amount) return ctx.reply('Bạn không đủ số dư.');
      await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
      await insertBet(round.id, user.id, 'S', numbers, amount);
      return ctx.reply(`Đã đặt Số ${numbers} ${formatMoney(amount)} cho phiên hiện tại.`);
    }
  } catch (e) {
    console.error('bet on text error', e);
  }
});

// -------------------------
// Runner (per-group loop)
// -------------------------
const runners = new Map(); // chat_id -> { cancelFlag: boolean }

async function startRunnerForGroup(chat_id) {
  if (runners.has(chat_id)) {
    console.log(`[RUNNER] Already running for ${chat_id}`);
    return;
  }
  console.log(`[RUNNER] Starting runner for group ${chat_id}`);

  // ensure there is a running round (create one)
  let round = await createRunningRound(chat_id);

  const state = { cancel: false };
  runners.set(chat_id, state);

  (async () => {
    while (!state.cancel) {
      try {
        // Build digits (6)
        const digits = [pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit()];
        // Save sequence
        await db('UPDATE rounds SET sequence=$1 WHERE id=$2', [digits.join(','), round.id]);

        // Announce start
        try { await bot.telegram.sendMessage(chat_id, `🎲 Phiên #${round.id} bắt đầu! Quay 6 chữ số trong 60s...`); } catch (e) { console.warn('announce start fail', e); }

        // After 30s
        await sleep(30000);
        try { await bot.telegram.sendMessage(chat_id, '⏳ Còn 30s đến kết quả...'); } catch (e) {}

        // After 20s (10s left)
        await sleep(20000);
        try { await bot.telegram.sendMessage(chat_id, '⏳ Còn 10s đến kết quả...'); } catch (e) {}

        // Reveal digits sequentially with 10s gap. Lock chat 5s before final reveal.
        for (let i = 0; i < 6; i++) {
          if (i === 5) {
            // lock chat: setChatPermissions to disallow sending messages
            try {
              await bot.telegram.setChatPermissions(chat_id, {
                can_send_messages: false,
                can_send_media_messages: false,
                can_send_other_messages: false,
                can_add_web_page_previews: false
              });
            } catch (e) {
              console.warn('lock chat failed', e);
            }
            await sleep(5000);
          } else {
            await sleep(10000);
          }
          try { await bot.telegram.sendMessage(chat_id, `🔢 Số thứ ${i+1}: ${digits[i]}`); } catch (e) {}
        }

        // unlock chat
        try {
          await bot.telegram.setChatPermissions(chat_id, {
            can_send_messages: true,
            can_send_media_messages: true,
            can_send_other_messages: true,
            can_add_web_page_previews: true
          });
        } catch (e) {
          console.warn('unlock chat failed', e);
        }

        // finalize round
       await db("UPDATE rounds SET status='finished' WHERE id=$1", [round.id]);

        // Resolve bets
        await resolveBetsForRound(round.id, chat_id);

        // Create next running round if group still running
        await sleep(1000);
        const g = await getGroup(chat_id);
        if (!g || !g.running) {
          console.log(`[RUNNER] Group ${chat_id} not running, stopping runner.`);
          state.cancel = true;
          break;
        }
        const next = await createRunningRound(chat_id);
        round = next;
      } catch (e) {
        console.error('[RUNNER] Error', e);
        await logToAdminAndChannel(`[RUNNER ERROR] ${String(e).substring(0,2000)}`);
        // wait before retry
        await sleep(5000);
      }
    }
    runners.delete(chat_id);
    console.log(`[RUNNER] Stopped runner for ${chat_id}`);
  })();
}

// Resolve bets for a finished round
async function resolveBetsForRound(roundId, chat_id) {
  try {
    const r = await db('SELECT * FROM rounds WHERE id=$1', [roundId]);
    if (r.rowCount === 0) return;
    const round = r.rows[0];
    const seq = (round.sequence || '').split(',').map(s => parseInt(s, 10));
    const seqStr = seq.join('');
    const override = round.override;

    const betsRes = await db('SELECT b.*, u.tg_id FROM bets b JOIN users u ON u.id=b.user_id WHERE b.round_id=$1', [roundId]);
    if (betsRes.rowCount === 0) {
      try { await bot.telegram.sendMessage(chat_id, `🏁 Phiên #${roundId} kết thúc. Kết quả: ${seq.join(',')}\nKhông có cược.`); } catch (e) {}
      if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[ROUND] #${roundId} in ${chat_id} finished (no bets)`);
      return;
    }

    for (const bet of betsRes.rows) {
      if (bet.paid) continue;
      let win = false;
      let payout = 0;
      try {
        if (['N','L'].includes(bet.bet_type)) {
          const last = seq[seq.length - 1];
          const isSmall = last >= 0 && last <= 5;
          const isLarge = last >= 6 && last <= 9;
          if (override) {
            if (override === 'Nho') win = (bet.bet_type === 'N');
            if (override === 'Lon') win = (bet.bet_type === 'L');
          } else {
            win = (bet.bet_type === 'N' && isSmall) || (bet.bet_type === 'L' && isLarge);
          }
          if (win) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.small_big);
        } else if (['C','Le'].includes(bet.bet_type)) {
          const last = seq[seq.length - 1];
          const isEven = (last % 2 === 0);
          if (override) {
            if (override === 'Chan') win = (bet.bet_type === 'C');
            if (override === 'Le') win = (bet.bet_type === 'Le');
          } else {
            win = (bet.bet_type === 'C' && isEven) || (bet.bet_type === 'Le' && !isEven);
          }
          if (win) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.even_odd);
        } else if (bet.bet_type === 'S') {
          const v = (bet.bet_value || '').toString();
          if (v.length === 1) {
            if (seq.includes(parseInt(v, 10))) {
              win = true;
              payout = Math.floor(Number(bet.amount) * MULTIPLIERS.single);
            }
          } else {
            if (seqStr.includes(v)) {
              win = true;
              const k = v.length;
              if (k === 2) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.two);
              else if (k === 3) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.three);
              else if (k === 4) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.four);
              else if (k === 5) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.five);
              else if (k === 6) payout = Math.floor(Number(bet.amount) * MULTIPLIERS.six);
              else payout = Math.floor(Number(bet.amount) * MULTIPLIERS.single);
            }
          }
        }
      } catch (e) {
        console.error('eval bet error', e);
      }

      await db('UPDATE bets SET paid=true WHERE id=$1', [bet.id]);
      await db('UPDATE users SET rounds_played = rounds_played + 1 WHERE id=$1', [bet.user_id]);

      if (win && payout > 0) {
        await db('UPDATE users SET balance = balance + $1 WHERE id=$2', [payout, bet.user_id]);
        try { await bot.telegram.sendMessage(bet.tg_id, `🎉 Bạn thắng ${formatMoney(payout)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`); } catch (e) {}
      } else {
        try { await bot.telegram.sendMessage(bet.tg_id, `😕 Bạn thua cược ${formatMoney(bet.amount)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`); } catch (e) {}
      }
    }

    try { await bot.telegram.sendMessage(chat_id, `🏁 Phiên #${roundId} kết thúc. Kết quả: ${seq.join(',')}\nXem lịch sử bằng /history`); } catch (e) {}
    if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[ROUND] #${roundId} in ${chat_id} finished seq=${seq.join(',')}`);
  } catch (e) {
    console.error('resolveBetsForRound error', e);
    await logToAdminAndChannel(`[RESOLVE ERROR] ${String(e).substring(0,2000)}`);
  }
}

// -------------------------
// History command (group): last up to 15 finished rounds
// -------------------------
bot.command('history', async (ctx) => {
  try {
    if (ctx.chat.type === 'private') return ctx.reply('Lịch sử chỉ có trong nhóm.');
    const chat_id = ctx.chat.id;
    const res = await db('SELECT id, sequence, started_at FROM rounds WHERE chat_id=$1 AND status=$2 ORDER BY started_at DESC LIMIT 15', [chat_id, 'finished']);
    if (res.rowCount === 0) return ctx.reply('Chưa có lịch sử.');
    const lines = res.rows.map(r => `#${r.id} — ${r.sequence || 'N/A'} — ${new Date(r.started_at).toLocaleString()}`);
    ctx.reply(lines.join('\n'));
  } catch (e) {
    console.error('/history error', e);
  }
});

// -------------------------
// Startup: init DB, resume runners for running groups, launch bot
// -------------------------
(async () => {
  try {
    // test DB connection
    const client = await pool.connect();
    client.release();
    console.log('[DB] Connected');

    // init tables
    await initDb();

    // resume any groups that were set running before restart
    const groupsRes = await db('SELECT chat_id FROM groups WHERE approved=true AND running=true');
    for (const row of groupsRes.rows) {
      startRunnerForGroup(row.chat_id);
    }

    // launch bot (long polling)
    await bot.launch();
    console.log('[BOT] Launched (polling)');

    // graceful
    process.once('SIGINT', () => { console.log('SIGINT'); bot.stop('SIGINT'); pool.end(); process.exit(0); });
    process.once('SIGTERM', () => { console.log('SIGTERM'); bot.stop('SIGTERM'); pool.end(); process.exit(0); });
  } catch (e) {
    console.error('[Init error]', e);
    await logToAdminAndChannel(`[INIT ERROR] ${String(e).substring(0,2000)}`);
    process.exit(1);
  }
})();
