/**
 * bot.js
 * Node 18+ (CommonJS)
 *
 * Features:
 * - 6-digit rounds every 60s (reveal digits sequentially)
 * - Bets: Nhỏ (/N), Lớn (/L), Chẵn (/C), Lẻ (/Le), Số (/S<number> <amount>)
 * - Admin approve group via /approve_group <chat_id>
 * - Group requests via /batdau in group -> notifies admin
 * - Admin override current round silently via /Nho, /Lon, /Chan, /Le
 * - /congtien, /code generation, /top10, withdraw approve/decline
 * - /start gives 80k bonus once (with free_locked logic)
 * - History up to 15 rounds, payouts auto-credit
 *
 * Database: PostgreSQL (use env DATABASE_URL)
 *
 * Usage: node bot.js
 */

require('dotenv').config();

const { Telegraf } = require('telegraf');
const { Pool } = require('pg');
const http = require('http');

// -----------------------------
// Config & Env
// -----------------------------
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = process.env.ADMIN_ID ? parseInt(process.env.ADMIN_ID, 10) : null;
const DATABASE_URL = process.env.DATABASE_URL;
const LOG_CHANNEL_ID = process.env.LOG_CHANNEL_ID ? process.env.LOG_CHANNEL_ID : null;
const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : (process.env.NODE_ENV === 'production' ? 10000 : 3000);

// Basic checks
if (!BOT_TOKEN) {
  console.error('Missing BOT_TOKEN in environment variables. Exiting.');
  process.exit(1);
}
if (!DATABASE_URL) {
  console.error('Missing DATABASE_URL in environment variables. Exiting.');
  process.exit(1);
}
if (!ADMIN_ID) {
  console.warn('ADMIN_ID not provided. Some admin features will not work until you set ADMIN_ID.');
}

// Setup a small HTTP server so Render Web Service won't complain about no open port.
// If you use Background Worker in Render, you can remove this.
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Telegram Bot is running\n');
}).listen(PORT, () => {
  console.log(`HTTP server listening on port ${PORT}`);
});

// -----------------------------
// Postgres pool
// -----------------------------
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: (process.env.NODE_ENV === 'production') ? { rejectUnauthorized: false } : false,
});

// Helper to run queries
async function db(query, params = []) {
  const client = await pool.connect();
  try {
    const res = await client.query(query, params);
    return res;
  } finally {
    client.release();
  }
}

// -----------------------------
// Utility functions
// -----------------------------
function formatMoney(v) {
  if (typeof v !== 'number' && typeof v !== 'bigint') v = parseInt(v || 0, 10) || 0;
  const s = v.toString();
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "₫";
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function pickRandomDigit() { return Math.floor(Math.random() * 10); }
function nowISO() { return new Date().toISOString(); }

// Payout multipliers
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

// -----------------------------
// Initialize DB tables (idempotent)
// -----------------------------
async function initDb() {
  // Create tables if not exist
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
    CREATE TABLE IF NOT EXISTS groups (
      chat_id BIGINT PRIMARY KEY,
      approved BOOLEAN DEFAULT FALSE,
      running BOOLEAN DEFAULT FALSE
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

  console.log('[DB] Initialized tables (if not existed).');
}

// -----------------------------
// Bot init
// -----------------------------
const bot = new Telegraf(BOT_TOKEN);

// Crash reporting
process.on('uncaughtException', async (err) => {
  console.error('[CRASH] uncaughtException', err);
  const text = `⚠️ BOT CRASH at ${nowISO()}:\n${err.stack ? err.stack.substring(0, 2000) : String(err)}`;
  try {
    if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
    if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, text);
  } catch (e) { console.error('Failed sending crash to admin/log channel', e); }
  process.exit(1);
});
process.on('unhandledRejection', async (reason) => {
  console.error('[CRASH] unhandledRejection', reason);
  const text = `⚠️ UnhandledRejection at ${nowISO()}:\n${String(reason).substring(0, 2000)}`;
  try {
    if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
    if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, text);
  } catch (e) { console.error('Failed sending rejection to admin/log channel', e); }
});

// -----------------------------
// DB helpers (users/groups/rounds/bets)
// -----------------------------
async function ensureUserByTg(ctxOrTgId) {
  let tg_id, username;
  if (typeof ctxOrTgId === 'number' || typeof ctxOrTgId === 'bigint') {
    tg_id = ctxOrTgId;
    username = null;
  } else {
    tg_id = ctxOrTgId.from.id;
    username = ctxOrTgId.from.username || ctxOrTgId.from.first_name || null;
  }
  const res = await db('SELECT * FROM users WHERE tg_id=$1', [tg_id]);
  if (res.rowCount === 0) {
    const ins = await db('INSERT INTO users(tg_id, username, balance, free_given, free_locked) VALUES($1,$2,0,false,true) RETURNING *', [tg_id, username]);
    return ins.rows[0];
  }
  return res.rows[0];
}

async function getGroup(chat_id) {
  const res = await db('SELECT * FROM groups WHERE chat_id=$1', [chat_id]);
  if (res.rowCount === 0) return null;
  return res.rows[0];
}

async function setGroupApproved(chat_id, approved = true, running = false) {
  await db('INSERT INTO groups(chat_id, approved, running) VALUES($1,$2,$3) ON CONFLICT (chat_id) DO UPDATE SET approved=$2, running=$3', [chat_id, approved, running]);
}

async function getLatestRunningRound(chat_id) {
  const res = await db("SELECT * FROM rounds WHERE chat_id=$1 AND status='running' ORDER BY started_at DESC LIMIT 1", [chat_id]);
  if (res.rowCount === 0) return null;
  return res.rows[0];
}

// -----------------------------
// Commands & handlers (private + group common)
// -----------------------------

// /start in private: give free bonus once and show menu
bot.start(async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') {
      // if in group, instruct
      return ctx.reply("Xin chào! Để bot hoạt động trong nhóm, add bot và dùng lệnh /batdau trong nhóm. Để sử dụng tiền & menu, chat riêng với bot.");
    }
    const u = await ensureUserByTg(ctx);
    if (!u.free_given) {
      // give 80k
      const bonus = parseInt(process.env.FREE_BONUS || '80000', 10);
      await db('UPDATE users SET balance = balance + $1, free_given=true, free_locked = true WHERE tg_id=$2', [bonus, ctx.from.id]);
      await ctx.replyWithMarkdown(`👋 Chào *${ctx.from.first_name}*!\nBạn được tặng *${formatMoney(bonus)}* miễn phí.\nLưu ý: số tiền free phải cược đủ điều kiện trước khi rút.\n\nMenu:`, {
        reply_markup: {
          keyboard: [
            [{ text: "🎮 Game" }, { text: "💳 Nạp tiền" }, { text: "🏧 Rút tiền" }]
          ],
          resize_keyboard: true
        }
      });
      // log
      if (LOG_CHANNEL_ID) {
        await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[BONUS] User ${ctx.from.id} (${ctx.from.username||ctx.from.first_name}) received ${formatMoney(bonus)} at ${nowISO()}`);
      }
    } else {
      ctx.reply(`Xin chào ${ctx.from.first_name}! Bạn đã nhận bonus trước đó. Sử dụng menu để chơi.`);
    }
  } catch (e) {
    console.error('start error', e);
  }
});

// menu buttons in private
bot.hears('🎮 Game', (ctx) => {
  ctx.reply("🎮 Game: Quay 6 chữ số.\nCách cược:\n/N<amount> cược Nhỏ (0-5)\n/L<amount> cược Lớn (6-9)\n/C<amount> cược Chẵn\n/Le<amount> cược Lẻ\n/S<number> <amount> cược số cụ thể\nLink nhóm: @QLROOM\nLiên hệ nạp: @HOANGDUNGG789");
});
bot.hears('💳 Nạp tiền', (ctx) => {
  ctx.reply("Để nạp tiền, liên hệ: @HOANGDUNGG789");
});
bot.hears('🏧 Rút tiền', (ctx) => {
  ctx.reply("Để rút tiền hãy nhập lệnh:\n/ruttien <Ngân hàng> <Số tài khoản> <Số tiền>\nRút tối thiểu 100000₫\nPhải cược đủ điều kiện trước khi rút.");
});

// /ruttien in private -> creates withdraw request to admin
bot.command('ruttien', async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') return;
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 4) return ctx.reply("Sai cú pháp. /ruttien <Ngân hàng> <Số tài khoản> <Số tiền>");
    const bank = parts.slice(1, parts.length-2+1)[0]; // simple: parts[1]
    const acc = parts[2];
    const amount = parseInt(parts[3], 10);
    if (isNaN(amount) || amount < 100000) return ctx.reply("Số tiền rút tối thiểu 100000₫");
    const u = await ensureUserByTg(ctx);
    if ((u.rounds_played || 0) < 1) {
      return ctx.reply("Bạn chưa cược đủ vòng (yêu cầu ít nhất 1 vòng) trước khi rút.");
    }
    // notify admin
    const text = `📤 Yêu cầu rút tiền:\nUser: ${ctx.from.username||ctx.from.first_name} (${ctx.from.id})\nNgân hàng: ${bank}\nSTK: ${acc}\nSố tiền: ${formatMoney(amount)}\nThời gian: ${nowISO()}`;
    if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
    await ctx.reply("Vui lòng chờ, admin sẽ xử lý trong vòng 1 giờ. Nếu sau 1 giờ chưa thấy thông báo, nhắn admin nhé!");
  } catch (e) {
    console.error('/ruttien error', e);
  }
});

// admin approve/decline withdraw
bot.command('approve_withdraw', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin được dùng lệnh này.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply("Usage: /approve_withdraw <tg_id> <amount>");
  const tg_id = parseInt(parts[1], 10), amount = parseInt(parts[2], 10);
  const u = await ensureUserByTg(tg_id);
  if (u.balance < amount) return ctx.reply("User không đủ tiền.");
  await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, tg_id]);
  await bot.telegram.sendMessage(tg_id, `Yêu cầu rút ${formatMoney(amount)} đã *ĐƯỢC DUYỆT*.\nAdmin đã trừ số tiền này khỏi tài khoản bạn.`, { parse_mode: 'Markdown' });
  ctx.reply("Đã duyệt rút tiền.");
});
bot.command('decline_withdraw', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin được dùng lệnh này.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply("Usage: /decline_withdraw <tg_id>");
  const tg_id = parseInt(parts[1], 10);
  await bot.telegram.sendMessage(tg_id, `Yêu cầu rút tiền của bạn đã *BỊ TỪ CHỐI*. Vui lòng liên hệ admin để biết lý do.`, { parse_mode: 'Markdown' });
  ctx.reply('Đã gửi tin nhắn từ chối.');
});

// top10 nạp nhiều nhất
bot.command('top10', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  const res = await db('SELECT username,tg_id,total_deposit FROM users ORDER BY total_deposit DESC LIMIT 10');
  if (res.rowCount === 0) return ctx.reply('Chưa có dữ liệu người nạp.');
  const lines = res.rows.map((r, i) => `${i+1}. ${r.username||r.tg_id} — ${formatMoney(r.total_deposit||0)}`);
  ctx.reply(lines.join('\n'));
});

// admin congtien
bot.command('congtien', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply('Usage: /congtien <tg_id> <amount>');
  const tg_id = parseInt(parts[1], 10), amount = parseInt(parts[2], 10);
  if (isNaN(amount) || amount <= 0) return ctx.reply('Số tiền không hợp lệ.');
  await ensureUserByTg(tg_id);
  await db('UPDATE users SET balance = balance + $1, total_deposit = total_deposit + $1 WHERE tg_id=$2', [amount, tg_id]);
  ctx.reply(`Đã cộng ${formatMoney(amount)} cho ${tg_id}`);
  await bot.telegram.sendMessage(tg_id, `Admin đã cộng cho bạn ${formatMoney(amount)}`);
  if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[CONGTIEN] Admin ${ctx.from.id} cộng ${formatMoney(amount)} cho ${tg_id} at ${nowISO()}`);
});

// /code <amount> <rounds>
bot.command('code', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply('Usage: /code <amount> <rounds_required>');
  const amount = parseInt(parts[1], 10), rounds = parseInt(parts[2], 10);
  if (isNaN(amount) || isNaN(rounds)) return ctx.reply('Số không hợp lệ.');
  const code = 'C' + Math.random().toString(36).substring(2, 10).toUpperCase();
  await db('INSERT INTO codes(code, amount, rounds_required) VALUES($1,$2,$3)', [code, amount, rounds]);
  ctx.reply(`Tạo code thành công: ${code} — ${formatMoney(amount)} — rounds required: ${rounds}`);
});

// approve group (admin)
bot.command('approve_group', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply('Usage: /approve_group <chat_id>');
  const chat_id = parseInt(parts[1], 10);
  await setGroupApproved(chat_id, true, false);
  ctx.reply(`Group ${chat_id} approved. To start running: issue /startbot_in_group ${chat_id} (admin only).`);
  if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[APPROVE_GROUP] Admin ${ctx.from.id} approved group ${chat_id} at ${nowISO()}`);
});

// admin start runner for group
bot.command('startbot_in_group', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply('Usage: /startbot_in_group <chat_id>');
  const chat_id = parseInt(parts[1], 10);
  await setGroupApproved(chat_id, true, true);
  ctx.reply(`Group ${chat_id} set to running.`);
  if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[START_GROUP] Admin ${ctx.from.id} started group ${chat_id} at ${nowISO()}`);
  startRunnerForGroup(chat_id);
});

// /batdau in group: requests admin to approve
bot.command('batdau', async (ctx) => {
  if (ctx.chat.type === 'private') return ctx.reply('Lệnh này chỉ dùng trong nhóm.');
  const chatId = ctx.chat.id;
  await db('INSERT INTO groups(chat_id, approved, running) VALUES($1,false,false) ON CONFLICT (chat_id) DO NOTHING', [chatId]);
  const text = `📩 Yêu cầu bật bot cho group: ${ctx.chat.title || chatId}\nchat_id: ${chatId}\nGõ /approve_group ${chatId} để bật`;
  if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text);
  await ctx.reply('Yêu cầu đã gửi admin. Chờ admin phê duyệt.');
});

// Admin override commands: /Nho /Lon /Chan /Le (silent)
const OVERRIDES = { Nho: 'Nho', Lon: 'Lon', Chan: 'Chan', Le: 'Le' };
bot.command(['Nho','Lon','Chan','Le'], async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply('Chỉ admin.');
  // find latest running round overall
  const q = await db("SELECT * FROM rounds WHERE status='running' ORDER BY started_at DESC LIMIT 1");
  if (q.rowCount === 0) return ctx.reply('Không có phiên đang chạy.');
  const round = q.rows[0];
  const cmd = ctx.message.text.replace('/', '').split(' ')[0];
  const overrideVal = OVERRIDES[cmd] || null;
  await db('UPDATE rounds SET override=$1 WHERE id=$2', [overrideVal, round.id]);
  ctx.reply(`Override ${overrideVal} set for round ${round.id} (silent).`);
  if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[OVERRIDE] Admin ${ctx.from.id} set override ${overrideVal} for round ${round.id} at ${nowISO()}`);
});

// /history in group: last up to 15 finished rounds
bot.command('history', async (ctx) => {
  if (ctx.chat.type === 'private') return ctx.reply('Lệnh lịch sử chỉ dùng trong nhóm.');
  const chat_id = ctx.chat.id;
  const res = await db('SELECT id, sequence, started_at FROM rounds WHERE chat_id=$1 AND status=$2 ORDER BY started_at DESC LIMIT 15', [chat_id, 'finished']);
  if (res.rowCount === 0) return ctx.reply('Chưa có lịch sử.');
  const lines = res.rows.map(r => `#${r.id} — ${r.sequence} — ${new Date(r.started_at).toLocaleString()}`);
  ctx.reply(lines.join('\n'));
});

// generic error handler for bot commands
bot.catch(async (err) => {
  console.error('Bot error', err);
  if (ADMIN_ID) {
    try { await bot.telegram.sendMessage(ADMIN_ID, `Bot error: ${String(err)}`); } catch(e){/*ignore*/ }
  }
});

// -----------------------------
// Betting parser & handlers (group only)
// Syntax expected (in group):
//   /N1000  or /N 1000
//   /L1000
//   /C1000
//   /Le1000
//   /S1 1000  or /S 1 1000 or /S91 1000 (multi-digit)
// -----------------------------
bot.on('text', async (ctx) => {
  try {
    const text = ctx.message.text.trim();
    // only consider bets in groups
    if (ctx.chat.type === 'private') return;
    // simple patterns
    const matchSimple = text.match(/^\/(N|L|C|Le)\s*([0-9]+)$/i);
    const matchS1 = text.match(/^\/S\s*([0-9]{1,6})\s+([0-9]+)$/i);
    const matchS2 = text.match(/^\/S([0-9]{1,6})\s*([0-9]+)$/i);
    if (!matchSimple && !matchS1 && !matchS2) return;

    // ensure group running
    const group = await getGroup(ctx.chat.id);
    if (!group || !group.approved || !group.running) {
      return ctx.reply('Game chưa được bật ở nhóm này.');
    }

    // ensure user exists
    const user = await ensureUserByTg(ctx);
    // get latest running round in this group
    const runningRound = await getLatestRunningRound(ctx.chat.id);
    if (!runningRound) return ctx.reply('Không có phiên đang chạy hiện tại.');

    if (matchSimple) {
      const type = matchSimple[1];
      const amount = parseInt(matchSimple[2], 10);
      if (isNaN(amount) || amount <= 0) return ctx.reply('Số tiền không hợp lệ.');
      if (user.balance < amount) return ctx.reply('Bạn không đủ số dư.');
      // deduct balance
      await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
      await db('INSERT INTO bets(round_id,user_id,bet_type,bet_value,amount) VALUES($1,$2,$3,$4,$5)', [runningRound.id, user.id, type.toUpperCase(), null, amount]);
      return ctx.reply(`Đã đặt ${type.toUpperCase()} ${formatMoney(amount)} cho phiên hiện tại.`);
    }
    const matchS = matchS1 || matchS2;
    if (matchS) {
      const numbers = matchS[1];
      const amount = parseInt(matchS[2], 10);
      if (isNaN(amount) || amount <= 0) return ctx.reply('Số tiền không hợp lệ.');
      if (user.balance < amount) return ctx.reply('Bạn không đủ số dư.');
      await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
      await db('INSERT INTO bets(round_id,user_id,bet_type,bet_value,amount) VALUES($1,$2,$3,$4,$5)', [runningRound.id, user.id, 'S', numbers, amount]);
      return ctx.reply(`Đã đặt Số ${numbers} ${formatMoney(amount)} cho phiên hiện tại.`);
    }
  } catch (e) {
    console.error('bet handler error', e);
  }
});

// -----------------------------
// Runner: manage per-group loop
// -----------------------------
const runners = new Map(); // chat_id => { cancel: fn }

async function startRunnerForGroup(chat_id) {
  if (runners.has(chat_id)) return; // already running
  console.log(`[RUNNER] Starting runner for group ${chat_id}`);

  // create an initial running round if none exists
  let roundRes = await db('INSERT INTO rounds(chat_id,status) VALUES($1,$2) RETURNING *', [chat_id, 'running']);
  let round = roundRes.rows[0];

  let cancelFlag = false;
  runners.set(chat_id, { cancel: () => { cancelFlag = true; } });

  // loop until canceled or group.running==false
  (async () => {
    while (!cancelFlag) {
      try {
        // generate random 6 digits
        const digits = [pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit(), pickRandomDigit()];
        // store sequence as string
        await db('UPDATE rounds SET sequence=$1 WHERE id=$2', [digits.join(','), round.id]);

        // announce start
        try { await bot.telegram.sendMessage(chat_id, `🎲 Phiên #${round.id} bắt đầu! Quay 6 chữ số trong 60s...`); } catch(e){ console.warn('announce start failed', e); }

        // timing: 30s left -> after 30s
        await sleep(30000);
        try { await bot.telegram.sendMessage(chat_id, '⏳ Còn 30s đến kết quả...'); } catch(e){}

        // after another 20s -> 10s left
        await sleep(20000);
        try { await bot.telegram.sendMessage(chat_id, '⏳ Còn 10s đến kết quả...'); } catch(e){}

        // reveal digits sequentially. Lock chat 5s before final reveal.
        for (let i = 0; i < 6; i++) {
          if (i === 5) {
            // lock chat 5s before final reveal
            try {
              // Restrict the bot? Actually we need to prevent users sending messages: restrictChatMember for "all members" requires ChatPermissions changes.
              // Use setChatPermissions to disallow sending messages
              await bot.telegram.setChatPermissions(chat_id, { can_send_messages: false, can_send_media_messages: false, can_send_other_messages: false, can_add_web_page_previews: false });
            } catch (e) { console.warn('lock chat failed', e); }
            await sleep(5000);
          } else {
            await sleep(10000);
          }
          // reveal digit
          try { await bot.telegram.sendMessage(chat_id, `🔢 Số thứ ${i+1}: ${digits[i]}`); } catch (e) {}
        }

        // unlock chat
        try {
          await bot.telegram.setChatPermissions(chat_id, { can_send_messages: true, can_send_media_messages: true, can_send_other_messages: true, can_add_web_page_previews: true });
        } catch (e) { console.warn('unlock chat failed', e); }

        // finalize round
        await db("UPDATE rounds SET status='finished' WHERE id=$1", [round.id]);
        // resolve bets and payouts
        await resolveBetsForRound(round.id, chat_id);

        // small pause then create next round if group still running
        await sleep(1000);

        const g = await getGroup(chat_id);
        if (!g || !g.running) {
          console.log(`[RUNNER] Group ${chat_id} not running anymore. Exiting runner.`);
          cancelFlag = true;
          break;
        }
        const nextRes = await db('INSERT INTO rounds(chat_id,status) VALUES($1,$2) RETURNING *', [chat_id, 'running']);
        round = nextRes.rows[0];
      } catch (e) {
        console.error('[RUNNER] error', e);
        // notify admin/log
        const text = `[RUNNER ERROR] group ${chat_id} error: ${String(e).substring(0,2000)}`;
        try { if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, text); if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, text); } catch (_) {}
        // wait a bit then continue
        await sleep(5000);
      }
    }
    runners.delete(chat_id);
  })();
}

// resolve bets for a finished round
async function resolveBetsForRound(roundId, chat_id) {
  console.log(`[RESOLVE] Resolving bets for round ${roundId}`);
  const rRes = await db('SELECT * FROM rounds WHERE id=$1', [roundId]);
  if (rRes.rowCount === 0) return console.warn('resolve: round not found');
  const round = rRes.rows[0];
  const seq = (round.sequence || '').split(',').map(s => parseInt(s, 10));
  const seqStr = seq.join('');
  const override = round.override;

  // get bets & users
  const betsRes = await db('SELECT b.*, u.tg_id, u.balance FROM bets b JOIN users u ON u.id=b.user_id WHERE b.round_id=$1', [roundId]);
  if (betsRes.rowCount === 0) {
    await bot.telegram.sendMessage(chat_id, `🏁 Phiên #${roundId} kết thúc. Kết quả: ${seq.join(',')}\nKhông có cược nào đặt.`);
    return;
  }

  for (const bet of betsRes.rows) {
    if (bet.paid) continue;
    let win = false;
    let payout = 0;
    try {
      if (['N','L'].includes(bet.bet_type)) {
        // use final digit to determine small/large
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
          // single digit: win if any of 6 digits equals it
          if (seq.includes(parseInt(v, 10))) {
            win = true;
            payout = Math.floor(Number(bet.amount) * MULTIPLIERS.single);
          }
        } else {
          // multi-digit: check contiguous substring
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
      console.error('Error evaluating bet', bet, e);
    }

    // finalize
    await db('UPDATE bets SET paid=true WHERE id=$1', [bet.id]);
    // increment rounds_played for user
    await db('UPDATE users SET rounds_played = rounds_played + 1 WHERE id=$1', [bet.user_id]);

    if (win && payout > 0) {
      await db('UPDATE users SET balance = balance + $1 WHERE id=$2', [payout, bet.user_id]);
      // notify user privately
      try { await bot.telegram.sendMessage(bet.tg_id, `🎉 Bạn thắng ${formatMoney(payout)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`); } catch(e){ console.warn('notify winner failed', e); }
    } else {
      try { await bot.telegram.sendMessage(bet.tg_id, `😕 Bạn thua cược ${formatMoney(bet.amount)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`); } catch(e){ }
    }
  }

  // announce summary in group
  try {
    await bot.telegram.sendMessage(chat_id, `🏁 Phiên #${roundId} kết thúc. Kết quả: ${seq.join(',')}\nLịch sử tối đa 15 phiên có thể xem bằng /history`);
  } catch (e) {
    console.warn('announce summary failed', e);
  }
  // optionally log to LOG_CHANNEL
  if (LOG_CHANNEL_ID) {
    await bot.telegram.sendMessage(LOG_CHANNEL_ID, `[ROUND] #${roundId} in ${chat_id} finished. seq=${seq.join(',')} at ${nowISO()}`);
  }
}

// -----------------------------
// Startup: init DB & start runners for groups already running
// -----------------------------
(async () => {
  try {
    // connect to DB once to validate
    await pool.connect();
    console.log('[DB] pool connected.');
    // init tables
    await initDb();

    // resume runners for groups that were marked running
    const groupsRes = await db('SELECT chat_id FROM groups WHERE approved=true AND running=true');
    for (const g of groupsRes.rows) {
      startRunnerForGroup(g.chat_id);
    }

    // launch bot (polling)
    await bot.launch();
    console.log('[BOT] Telegraf launched (polling).');

    // graceful stop
    process.once('SIGINT', () => { console.log('SIGINT received'); bot.stop('SIGINT'); pool.end(); process.exit(0); });
    process.once('SIGTERM', () => { console.log('SIGTERM received'); bot.stop('SIGTERM'); pool.end(); process.exit(0); });
  } catch (e) {
    console.error('[Init error]', e);
    // notify admin
    try {
      if (ADMIN_ID) await bot.telegram.sendMessage(ADMIN_ID, `Init error: ${e.message}`);
      if (LOG_CHANNEL_ID) await bot.telegram.sendMessage(LOG_CHANNEL_ID, `Init error: ${e.message}`);
    } catch (_) {}
    process.exit(1);
  }
})();
