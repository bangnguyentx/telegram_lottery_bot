// 🟦 1️⃣ Fake HTTP server cho Render (nếu bạn dùng Web Service)
import http from 'http';
const port = process.env.PORT || 10000;
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('✅ Telegram Bot is running on Render\n');
}).listen(port, () => {
  console.log(`🌐 Web server listening on port ${port}`);
});

// 🟩 2️⃣ Load biến môi trường từ file .env
import dotenv from 'dotenv';
dotenv.config();

// 🟨 3️⃣ Import các thư viện cần thiết
import { Telegraf } from 'telegraf';
import pkg from 'pg';
const { Pool } = pkg;

// 🟥 4️⃣ Lấy Environment Variables
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_ID = parseInt(process.env.ADMIN_ID, 10);
const DATABASE_URL = process.env.DATABASE_URL;

if (!BOT_TOKEN || !DATABASE_URL) {
  console.error('❌ Thiếu BOT_TOKEN hoặc DATABASE_URL trong biến môi trường!');
  process.exit(1);
}

// 🟦 5️⃣ Khởi tạo kết nối DB
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: {
    rejectUnauthorized: false, // Render DB thường yêu cầu SSL
  },
});

pool.connect()
  .then(() => console.log('✅ Đã kết nối PostgreSQL thành công'))
  .catch(err => {
    console.error('❌ Lỗi kết nối DB:', err);
    process.exit(1);
  });

// 🟧 6️⃣ Khởi tạo Bot
const bot = new Telegraf(BOT_TOKEN);

// Ví dụ đơn giản — kiểm tra bot
bot.start((ctx) => ctx.reply('Xin chào 👋 Bot đã hoạt động 24/7 trên Render!'));

// 🟫 7️⃣ Khởi động Bot
bot.launch().then(() => {
  console.log('🤖 Bot Telegram đã khởi động thành công!');
});

// Đảm bảo bot shutdown gọn khi Render gửi tín hiệu
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
if (!BOT_TOKEN || !ADMIN_ID || !DATABASE_URL) {
  console.error("Missing BOT_TOKEN, ADMIN_ID or DATABASE_URL in env.");
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
const pool = new Pool({ connectionString: DATABASE_URL, ssl: (process.env.NODE_ENV === 'production') ? { rejectUnauthorized: false } : false });

// helper DB
async function db(query, params = []) {
  const client = await pool.connect();
  try {
    const res = await client.query(query, params);
    return res;
  } finally {
    client.release();
  }
}

// Utility
function formatMoney(v) {
  return v.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "₫";
}

function pickRandomDigit() {
  return Math.floor(Math.random() * 10); // 0..9
}

// Payout multipliers (as described)
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

// Crash reporting to admin
process.on('uncaughtException', (err) => {
  console.error('Uncaught', err);
  bot.telegram.sendMessage(ADMIN_ID, `⚠️ BOT CRASH: ${err.message}\n${err.stack ? err.stack.substring(0,2000) : ''}`);
  process.exit(1);
});
process.on('unhandledRejection', (reason) => {
  console.error('UnhandledRejection', reason);
  bot.telegram.sendMessage(ADMIN_ID, `⚠️ UnhandledRejection: ${String(reason).substring(0,2000)}`);
});

// Create user helper
async function ensureUser(ctxOrTgId) {
  const tg_id = (typeof ctxOrTgId === 'number') ? ctxOrTgId : ctxOrTgId.from.id;
  const username = (typeof ctxOrTgId === 'number') ? null : (ctxOrTgId.from.username || ctxOrTgId.from.first_name);
  const res = await db('SELECT * FROM users WHERE tg_id=$1', [tg_id]);
  if (res.rowCount === 0) {
    const ins = await db('INSERT INTO users(tg_id, username, balance, free_given, free_locked) VALUES($1,$2,0,false,true) RETURNING *', [tg_id, username]);
    return ins.rows[0];
  }
  return res.rows[0];
}

// /start in private
bot.start(async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') {
      // group start
      return ctx.reply("Xin chào! Thêm bot vào nhóm và dùng /batdau để yêu cầu admin bật chơi.");
    }
    const u = await ensureUser(ctx);
    // give 80k once
    if (!u.free_given) {
      await db('UPDATE users SET balance = balance + $1, free_given=true, free_locked = true WHERE tg_id=$2', [80000, ctx.from.id]);
      await db('UPDATE users SET rounds_played = rounds_played WHERE tg_id=$1', [ctx.from.id]); // no-op to ensure presence
      ctx.replyWithMarkdown(`Chào *${ctx.from.first_name}*! Bạn được tặng *80,000₫* miễn phí.\nLưu ý: Số tiền free cần cược đủ các điều kiện và admin xác nhận trước khi rút.\n\nMenu:`, {
        reply_markup: {
          keyboard: [
            [{ text: "🎮 Game" }, { text: "💳 Nạp tiền" }, { text: "🏧 Rút tiền" }]
          ],
          resize_keyboard: true,
          one_time_keyboard: false
        }
      });
    } else {
      ctx.reply(`Chào ${ctx.from.first_name}! Bạn đã có tài khoản. Số dư hiện tại sẽ hiển thị khi dùng lệnh khác.`);
    }
  } catch (e) {
    console.error(e);
  }
});

// Simple text menu handlers (private)
bot.hears('🎮 Game', (ctx) => {
  ctx.reply("Game: Hệ thống quay 6 chữ số. Cách cược:\n- /N<amount> cược Nhỏ (0-5)\n- /L<amount> cược Lớn (6-9)\n- /C<amount> cược Chẵn\n- /Le<amount> cược Lẻ\n- /S<number> <amount> cược số cụ thể\nLink nhóm: @QLROOM\nHướng dẫn chi tiết: ...");
});
bot.hears('💳 Nạp tiền', (ctx) => {
  ctx.reply("Để nạp tiền, liên hệ: @HOANGDUNGG789");
});
bot.hears('🏧 Rút tiền', (ctx) => {
  ctx.reply("Để rút tiền hãy nhập lệnh:\n/ruttien <Ngân hàng> <Số tài khoản> <Số tiền>\nRút tối thiểu 100000₫\nPhải cược đủ điều kiện (xem điều khoản).");
});

// /ruttien
bot.command('ruttien', async (ctx) => {
  try {
    if (ctx.chat.type !== 'private') return;
    const parts = ctx.message.text.split(/\s+/);
    if (parts.length < 4) return ctx.reply("Sai cú pháp. /ruttien <Ngân hàng> <Số tài khoản> <Số tiền>");
    const bank = parts[1], acc = parts[2], amount = parseInt(parts[3],10);
    const u = await ensureUser(ctx);
    if (isNaN(amount) || amount < 100000) return ctx.reply("Số tiền rút tối thiểu 100000₫");
    // check rounds_played vs requirement
    if ((u.rounds_played || 0) < 1) {
      return ctx.reply("Bạn chưa cược đủ. Yêu cầu cược ít nhất 1 vòng trước khi rút.");
    }
    // create a withdraw request: send to admin
    const msg = `Yêu cầu rút tiền từ @${ctx.from.username || ctx.from.first_name}\nNgân hàng: ${bank}\nSTK: ${acc}\nSố tiền: ${formatMoney(amount)}\nTG user: ${u.tg_id}\nGõ /approve_withdraw ${u.tg_id} ${amount} để duyệt hoặc /decline_withdraw ${u.tg_id}`;
    await bot.telegram.sendMessage(ADMIN_ID, msg);
    await ctx.reply("Vui lòng chờ, admin sẽ xử lý trong vòng 1 giờ. Nếu sau 1 giờ chưa có thông báo, nhắn admin nhé!");
  } catch (e) { console.error(e); }
});

// Admin: approve/decline withdraw
bot.command('approve_withdraw', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply("Usage: /approve_withdraw <tg_id> <amount>");
  const tg_id = parseInt(parts[1],10), amount = parseInt(parts[2],10);
  const res = await db('SELECT * FROM users WHERE tg_id=$1',[tg_id]);
  if (res.rowCount===0) return ctx.reply('User not found');
  const u = res.rows[0];
  if (u.balance < amount) return ctx.reply("User không đủ tiền.");
  await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2',[amount, tg_id]);
  // notify user
  await bot.telegram.sendMessage(tg_id, `Yêu cầu rút ${formatMoney(amount)} đã *ĐƯỢC DUYỆT*. Vui lòng kiểm tra tài khoản.`, { parse_mode: 'Markdown' });
  ctx.reply("Đã duyệt và trừ tiền user.");
});
bot.command('decline_withdraw', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply("Usage: /decline_withdraw <tg_id>");
  const tg_id = parseInt(parts[1],10);
  await bot.telegram.sendMessage(tg_id, `Yêu cầu rút tiền của bạn đã *BỊ TỪ CHỐI*. Vui lòng liên hệ admin để biết lý do.`, { parse_mode: 'Markdown' });
  ctx.reply("Đã gửi thông báo từ chối tới user.");
});

// Admin top10 nạp nhiều nhất (by total_deposit)
bot.command('top10', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const res = await db('SELECT username,tg_id,total_deposit FROM users ORDER BY total_deposit DESC LIMIT 10');
  const lines = res.rows.map((r,i)=>`${i+1}. ${r.username||r.tg_id} — ${formatMoney(r.total_deposit||0)}`);
  ctx.reply("Top 10 nạp nhiều nhất:\n" + lines.join("\n"));
});

// /congtien <tg_id> <amount>
bot.command('congtien', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply("Usage: /congtien <tg_id> <amount>");
  const tg_id = parseInt(parts[1],10), amount = parseInt(parts[2],10);
  await ensureUser(tg_id);
  await db('UPDATE users SET balance = balance + $1, total_deposit = total_deposit + $1 WHERE tg_id=$2',[amount,tg_id]);
  ctx.reply(`Đã cộng ${formatMoney(amount)} cho ${tg_id}`);
  await bot.telegram.sendMessage(tg_id, `Admin đã cộng cho bạn ${formatMoney(amount)}`);
});

// /code <amount> <rounds>
bot.command('code', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply("Usage: /code <amount> <rounds_required>");
  const amount = parseInt(parts[1],10), rounds = parseInt(parts[2],10);
  const code = 'C' + Math.random().toString(36).substring(2,9).toUpperCase();
  await db('INSERT INTO codes(code, amount, rounds_required) VALUES($1,$2,$3)', [code, amount, rounds]);
  ctx.reply(`Tạo code: ${code} — ${formatMoney(amount)} — rounds: ${rounds}`);
});

// Approve group: admin command
bot.command('approve_group', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply("Usage: /approve_group <chat_id>");
  const chat_id = parseInt(parts[1],10);
  await db('INSERT INTO groups(chat_id, approved, running) VALUES($1, true, false) ON CONFLICT (chat_id) DO UPDATE SET approved=true', [chat_id]);
  ctx.reply(`Group ${chat_id} approved. Groups running must be started with /startbot_in_group`);
});

// Group command /batdau to request admin
bot.command('batdau', async (ctx) => {
  if (ctx.chat.type === 'private') return ctx.reply('Lệnh chỉ dùng trong nhóm.');
  const chatId = ctx.chat.id;
  await ensureUser(ctx.from);
  // store group if not exist
  await db('INSERT INTO groups(chat_id, approved, running) VALUES($1,false,false) ON CONFLICT (chat_id) DO NOTHING', [chatId]);
  await bot.telegram.sendMessage(ADMIN_ID, `Yêu cầu bật bot cho group: ${ctx.chat.title || chatId}\nchat_id: ${chatId}\nGõ /approve_group ${chatId} để bật`);
  ctx.reply("Yêu cầu đã gửi admin. Chờ admin phê duyệt.");
});

// Admin command: start the auto-rounds for group (internal name)
bot.command('startbot_in_group', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return ctx.reply("Only admin.");
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply("Usage: /startbot_in_group <chat_id>");
  const chat_id = parseInt(parts[1],10);
  await db('UPDATE groups SET running=true, approved=true WHERE chat_id=$1', [chat_id]);
  ctx.reply(`Group ${chat_id} will run now.`);
});

// admin override result commands (silent, no notification to group)
const OVERRIDES = { '/Nho': 'Nho', '/Lon': 'Lon', '/Chan': 'Chan', '/Le': 'Le' };
bot.command(['Nho','Lon','Chan','Le'], async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  // find latest running round not finished
  const q = await db("SELECT * FROM rounds WHERE status='running' ORDER BY started_at DESC LIMIT 1");
  if (q.rowCount === 0) return ctx.reply("No running round.");
  const round = q.rows[0];
  const cmd = '/' + ctx.message.text.replace('/','').split(' ')[0];
  const overrideVal = OVERRIDES[cmd] || (ctx.message.text==='/' ? null : ctx.message.text.replace('/',''));
  await db('UPDATE rounds SET override=$1 WHERE id=$2', [overrideVal, round.id]);
  ctx.reply(`Override set to ${overrideVal} for round ${round.id} (silent).`);
});

// Betting handlers in group and private (same syntax). Parse patterns like /N1000 or /S1 1000 or /S1 1000
bot.on('text', async (ctx) => {
  try {
    const text = ctx.message.text.trim();
    // betting commands only supported in groups for placing bets against current group round
    const inGroup = ctx.chat.type !== 'private';
    // parse patterns:
    // /N1000 or /N 1000
    const matchSimple = text.match(/^\/(N|L|C|Le)(\s?)(\d+)$/i);
    const matchS = text.match(/^\/S\s*([0-9]{1,6})\s+(\d+)$/i) || text.match(/^\/S([0-9]{1,6})\s*(\d+)$/i);
    if (!matchSimple && !matchS) return; // ignore other text
    const user = await ensureUser(ctx);
    if (inGroup) {
      // check group approved and running
      const group = await db('SELECT * FROM groups WHERE chat_id=$1', [ctx.chat.id]);
      if (group.rowCount === 0 || !group.rows[0].approved || !group.rows[0].running) {
        return ctx.reply("Game chưa được bật ở nhóm này.");
      }
      // get current running round
      const rres = await db("SELECT * FROM rounds WHERE chat_id=$1 AND status='running' ORDER BY started_at DESC LIMIT 1",[ctx.chat.id]);
      if (rres.rowCount===0) return ctx.reply("Không có phiên đang chạy.");
      const round = rres.rows[0];
      if (matchSimple) {
        const type = matchSimple[1].toUpperCase(); // N L C Le
        const amount = parseInt(matchSimple[3],10);
        if (isNaN(amount) || amount <= 0) return ctx.reply("Số tiền không hợp lệ.");
        // check balance
        if (user.balance < amount) return ctx.reply("Bạn không đủ số dư.");
        await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
        // store bet
        await db('INSERT INTO bets(round_id,user_id,bet_type,bet_value,amount) VALUES($1,$2,$3,$4,$5)', [round.id, user.id, type, null, amount]);
        ctx.reply(`Đã đặt ${type === 'N' ? 'Nhỏ' : type === 'L' ? 'Lớn' : type === 'C' ? 'Chẵn' : 'Lẻ'} ${formatMoney(amount)} cho phiên hiện tại.`);
      } else if (matchS) {
        const numbers = matchS[1]; // can be multi-digit combination like 91 (user wanted multi-number bet?)
        const amount = parseInt(matchS[2],10);
        if (isNaN(amount) || amount <= 0) return ctx.reply("Số tiền không hợp lệ.");
        if (user.balance < amount) return ctx.reply("Bạn không đủ số dư.");
        // note: we allow betting on a sequence of digits (e.g., '91' interpret as betting that those digits appear in the result? We'll treat as "exact sequence substring" for multi-digit)
        await db('UPDATE users SET balance = balance - $1 WHERE tg_id=$2', [amount, ctx.from.id]);
        await db('INSERT INTO bets(round_id,user_id,bet_type,bet_value,amount) VALUES($1,$2,$3,$4,$5)', [round.id, user.id, 'S', numbers, amount]);
        ctx.reply(`Đã đặt Số ${numbers} ${formatMoney(amount)} cho phiên hiện tại.`);
      }
    } else {
      // private betting - not allowed in private for group rounds
      ctx.reply("Đặt cược chỉ được thực hiện trong nhóm khi game đang chạy.");
    }
  } catch (e) {
    console.error(e);
  }
});

// --- Core: round runner per group ---
// We'll implement a map of group -> interval runner
const runners = new Map();

async function startRunnerForGroup(chat_id) {
  if (runners.has(chat_id)) return;
  console.log('Start runner for', chat_id);
  // create first round
  let currentRoundRes = await db('INSERT INTO rounds(chat_id,status) VALUES($1,$2) RETURNING *', [chat_id, 'running']);
  let round = currentRoundRes.rows[0];

  const runOnce = async () => {
    try {
      // for each full round: generate 6 digits that will be revealed every 10s
      const digits = [];
      for (let i=0;i<6;i++) digits.push(pickRandomDigit());
      // Save sequence so eventual override logic can use it
      await db('UPDATE rounds SET sequence=$1 WHERE id=$2', [digits.join(','), round.id]);
      // If there's override logic (admin set override earlier), we will still store but when resolving we'll honor override
      // Announce round start
      await bot.telegram.sendMessage(chat_id, `🎲 Phiên #${round.id} bắt đầu! Quay 6 chữ số trong 60s...`);
      // Timers:
      // At 30s left => after 30s
      await new Promise(r => setTimeout(r, 30000));
      await bot.telegram.sendMessage(chat_id, `⏳ Còn 30s đến kết quả...`);
      // After another 20s: at 10s left
      await new Promise(r => setTimeout(r, 20000));
      await bot.telegram.sendMessage(chat_id, `⏳ Còn 10s đến kết quả...`);
      // Now reveal digits every 10s (six digits). But we still need to lock 5s before revealing final result.
      // We'll reveal digits sequentially each 10s, but prior to final digit lock chat 5s.
      for (let i=0;i<6;i++) {
        if (i === 5) {
          // lock chat 5s before final reveal
          try {
            await bot.telegram.restrictChatMember(chat_id, bot.botInfo.id, { can_send_messages: false });
          } catch (e) {
            // ignore if can't restrict (bot must be admin)
            console.warn('restrictChatMember error', e && e.description);
          }
          await new Promise(r => setTimeout(r, 5000));
        } else {
          await new Promise(r => setTimeout(r, 10000));
        }
        // reveal i-th digit
        await bot.telegram.sendMessage(chat_id, `🔢 Số thứ ${i+1}: ${digits[i]}`);
      }
      // Unlock chat
      try {
        await bot.telegram.restrictChatMember(chat_id, bot.botInfo.id, { can_send_messages: true });
      } catch(e){ /* ignore */ }
      // Mark round finished
      await db('UPDATE rounds SET status=$1 WHERE id=$2', ['finished', round.id]);
      // Resolve bets for this round:
      await resolveBetsForRound(round.id, chat_id);
      // keep last 15 history: we don't delete rounds but group will request history later
      // create next round and continue after small pause
      await new Promise(r => setTimeout(r, 1000));
      const next = await db('INSERT INTO rounds(chat_id,status) VALUES($1,$2) RETURNING *', [chat_id, 'running']);
      round = next.rows[0];
    } catch (e) {
      console.error('Runner error', e);
      await bot.telegram.sendMessage(ADMIN_ID, `Runner error for group ${chat_id}: ${e.message}`);
    }
  };

  // run in loop
  let canceled = false;
  runners.set(chat_id, { cancel: () => canceled = true });
  (async function loop(){
    while(!canceled) {
      await runOnce();
      // check group running flag
      const g = await db('SELECT * FROM groups WHERE chat_id=$1', [chat_id]);
      if (g.rowCount === 0 || !g.rows[0].running) {
        canceled = true;
        break;
      }
    }
    runners.delete(chat_id);
    console.log('Runner stopped for', chat_id);
  })();
}

// Resolve bets
async function resolveBetsForRound(roundId, chat_id) {
  // fetch round and bets
  const rres = await db('SELECT * FROM rounds WHERE id=$1', [roundId]);
  if (rres.rowCount === 0) return;
  const round = rres.rows[0];
  const seq = (round.sequence || '').split(',').map(s => parseInt(s,10));
  // If override present, we will craft a pseudo "winning property" accordingly:
  // override Nho => small (0-5) ; Lon => large (6-9); Chan=>even; Le=>odd
  const override = round.override;
  // combine as string for some bets
  const seqStr = seq.join('');
  const betsRes = await db('SELECT b.*, u.tg_id,u.balance FROM bets b JOIN users u ON u.id=b.user_id WHERE b.round_id=$1', [roundId]);
  for (const bet of betsRes.rows) {
    if (bet.paid) continue;
    let win = false;
    let payout = 0;
    if (bet.bet_type === 'N' || bet.bet_type === 'L') {
      // Determine outcome by last digit? Or sum? We'll use last digit of sequence (final digit) to decide small/large. This is assumption.
      const last = seq[seq.length-1];
      const isSmall = last >= 0 && last <= 5;
      const isLarge = last >= 6 && last <= 9;
      if (override) {
        if (override === 'Nho') win = (bet.bet_type === 'N');
        if (override === 'Lon') win = (bet.bet_type === 'L');
      } else {
        win = (bet.bet_type === 'N' && isSmall) || (bet.bet_type === 'L' && isLarge);
      }
      if (win) payout = Math.floor(bet.amount * MULTIPLIERS.small_big);
    } else if (bet.bet_type === 'C' || bet.bet_type === 'Le') {
      // Even/odd determined by last digit parity
      const last = seq[seq.length-1];
      const isEven = (last % 2 === 0);
      if (override) {
        if (override === 'Chan') win = (bet.bet_type === 'C');
        if (override === 'Le') win = (bet.bet_type === 'Le');
      } else {
        win = (bet.bet_type === 'C' && isEven) || (bet.bet_type === 'Le' && !isEven);
      }
      if (win) payout = Math.floor(bet.amount * MULTIPLIERS.even_odd);
    } else if (bet.bet_type === 'S') {
      // bet_value could be multi-digit like '91' (user expects sequence?) We'll check:
      //  - if bet_value length == 1: if any of 6 digits equals that digit -> win single
      //  - if length>1: if seqStr includes bet_value as contiguous substring, consider matched of length k -> multipliers by k-length
      const v = (bet.bet_value||'').toString();
      if (v.length === 1) {
        if (seq.includes(parseInt(v,10))) {
          // single number present (they described multiplier x9.2)
          win = true;
          payout = Math.floor(bet.amount * MULTIPLIERS.single);
        }
      } else {
        // check if exact contiguous substring occurs
        if (seqStr.includes(v)) {
          win = true;
          const k = v.length;
          if (k === 2) payout = Math.floor(bet.amount * MULTIPLIERS.two);
          else if (k === 3) payout = Math.floor(bet.amount * MULTIPLIERS.three);
          else if (k === 4) payout = Math.floor(bet.amount * MULTIPLIERS.four);
          else if (k === 5) payout = Math.floor(bet.amount * MULTIPLIERS.five);
          else if (k === 6) payout = Math.floor(bet.amount * MULTIPLIERS.six);
          else payout = Math.floor(bet.amount * MULTIPLIERS.single);
        }
      }
    }
    if (win && payout > 0) {
      await db('UPDATE users SET balance = balance + $1, rounds_played = rounds_played + 1 WHERE id=$2', [payout, bet.user_id]);
      await db('UPDATE bets SET paid=true WHERE id=$1', [bet.id]);
      try {
        await bot.telegram.sendMessage(bet.tg_id, `🎉 Bạn thắng ${formatMoney(payout)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`);
      } catch(e){ /* ignore send error */ }
    } else {
      // losing bet: increment rounds_played maybe
      await db('UPDATE users SET rounds_played = rounds_played + 1 WHERE id=$1', [bet.user_id]);
      await db('UPDATE bets SET paid=true WHERE id=$1', [bet.id]);
      try {
        await bot.telegram.sendMessage(bet.tg_id, `😕 Bạn thua cược ${formatMoney(bet.amount)} cho phiên #${roundId}\nKết quả: ${seq.join(',')}`);
      } catch(e){ /* ignore */ }
    }
  }

  // Finally announce summary in group
  await bot.telegram.sendMessage(chat_id, `🏁 Phiên #${roundId} kết thúc. Kết quả: ${seq.join(',')}\n(Lịch sử tối đa 15 phiên có thể xem bằng /history)`);
}

// command /history to show last up to 15 rounds
bot.command('history', async (ctx) => {
  const chat_id = (ctx.chat.type === 'private') ? null : ctx.chat.id;
  if (!chat_id) return ctx.reply('Lịch sử chỉ ở nhóm.');
  const res = await db('SELECT id, sequence, started_at FROM rounds WHERE chat_id=$1 AND status=$2 ORDER BY started_at DESC LIMIT 15', [chat_id, 'finished']);
  if (res.rowCount === 0) return ctx.reply('Chưa có lịch sử.');
  const lines = res.rows.map(r => `#${r.id} — ${r.sequence} — ${new Date(r.started_at).toLocaleString()}`);
  ctx.reply(lines.join("\n"));
});

// Admin: start runner for all approved groups on bot boot
(async function init() {
  try {
    // create tables if not exist minimal (for convenience, you can run SQL separately)
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
        used_by INTEGER,
        used_at TIMESTAMP WITH TIME ZONE
      );
    `);

    // Start runners for groups flagged running
    const groups = await db('SELECT chat_id FROM groups WHERE approved=true AND running=true');
    for (const g of groups.rows) {
      startRunnerForGroup(g.chat_id);
    }
    // Launch webhook or polling (we use long polling here; Render supports long-poll)
    bot.launch();
    console.log('Bot started.');
    // graceful stop
    process.once('SIGINT', () => { bot.stop('SIGINT'); pool.end(); });
    process.once('SIGTERM', () => { bot.stop('SIGTERM'); pool.end(); });
  } catch (e) {
    console.error('Init error', e);
  }
})();
