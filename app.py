"""
SMART PRIME v0.5 — WEBHOOK EDITION (Render)
Constitutional agent of Juan Ricci (@smartcash22)
Architecture change: webhook instead of polling (no 409 wars, no ghost instances,
Telegram wakes him directly). Boot-code ownership (no lockouts, no hijacks).
"""

import os
import random
import sqlite3
import logging
import traceback
from datetime import datetime, date, time as dtime, timezone

from openai import AsyncOpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("SMART_TOKEN", "PASTE_YOUR_TOKEN_HERE")
BRAIN_API_KEY = os.environ.get("BRAIN_API_KEY", "")
DB_PATH = "smart.db"
FREEZE_PHRASES = {"smart freeze", "smart para"}
RESUME_PHRASE = "smart resume"
SPEND_CAP = 200.0
RESERVE = 100.0

DEADLINE = date(2027, 2, 1)
TARGET = date(2027, 1, 18)
LAUNCH = date(2026, 11, 1)
YPP_SUBS = 1000
YPP_HOURS = 4000

PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_URL = f"https://smart-prime.onrender.com/{TOKEN}"

BOOT_CODE = str(random.randint(1000, 9999))

BRAIN_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",
]

brain = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=BRAIN_API_KEY,
    timeout=20.0,
    max_retries=0,
) if BRAIN_API_KEY else None

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s",
                    level=logging.INFO)

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT, kind TEXT, content TEXT,
        source TEXT, verification TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ledger(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, kind TEXT, detail TEXT, amount REAL DEFAULT 0)""")
    conn.commit()
    return conn

_db = db()

def get_setting(key):
    row = _db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None

def set_setting(key, value):
    _db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
    _db.commit()

def log_action(kind, detail, amount=0):
    _db.execute("INSERT INTO ledger(ts,kind,detail,amount) VALUES(?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), kind, detail, amount))
    _db.commit()

def owner_id():
    return get_setting("owner_chat_id")

def is_owner(update: Update) -> bool:
    return str(update.effective_chat.id) == str(owner_id())

CONSTITUTION = [
    ("mission", "Build self-sustaining passive income fully autonomously. "
     "First project: FIRST STAGE, a faceless YouTube channel covering Musk and space.", "core"),
    ("laws", "Juan is sovereign. 'Smart Freeze'/'Smart Para' from Juan halts everything instantly; "
     "only Juan can resume. Spending cap $200; $100 reserve never touched; no money moves without "
     "Juan's approval. Full autonomy on operations. Juan's only recurring job is money decisions.", "core"),
    ("deadline", "HARD DEADLINE: FIRST STAGE must be ACCEPTED into the YouTube Partner Program BEFORE "
     "February 1, 2027 (grandfathered under current rules: 1000 subs + 4000 watch hours in 365 days, "
     "or 10M Shorts views in 90 days). After that date thresholds double to 8000 hours/20M views — "
     "never allowed. Hit metrics by January 18, 2027 for review buffer. Juan: we can NOT miss it.", "core"),
    ("income_ladder", "First income from day one (affiliates). $500/mo by month 6. $1000/mo by month 9. "
     "$6000+/mo with the swarm by month 12-24.", "core"),
    ("brand", "FIRST STAGE — faceless Musk/space channel. AI voice with disclosure. Evidence tiers: "
     "announced, observed, corroborated, assumption. Original commentary required.", "core"),
    ("owner", "Juan Ricci, USA, Telegram @smartcash22. Money decisions only; zero routine workload.", "core"),
]

def seed_constitution():
    count = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    if count == 0:
        for topic, content, ver in CONSTITUTION:
            _db.execute("INSERT INTO memory(created,kind,content,source,verification) "
                        "VALUES(?,?,?,?,?)",
                        (datetime.now().isoformat(timespec="seconds"), topic, content,
                         "constitution", ver))
        _db.commit()
        print(">>> CONSTITUTION seeded into memory")

seed_constitution()

def goal_status():
    today = date.today()
    subs = int(get_setting("subs_now") or 0)
    hours = float(get_setting("hours_now") or 0)
    days_left = (DEADLINE - today).days
    if today < LAUNCH:
        weeks = max((TARGET - LAUNCH).days / 7, 1)
        return ("pre", days_left, subs, hours,
                f"🎯 GOAL STATUS — PRE-LAUNCH\n"
                f"YPP deadline: Feb 1, 2027 — {days_left} days away\n"
                f"From launch (Nov 1) to target (Jan 18): {weeks:.0f} weeks\n"
                f"Required pace: ~{round(YPP_SUBS / weeks)} subs/wk + ~{round(YPP_HOURS / weeks)} hrs/wk\n"
                f"Status: ⏳ ready — every pre-launch day is pace in the bank")
    weeks_left = max((TARGET - today).days / 7, 0.5)
    weeks_in = max((today - LAUNCH).days / 7, 0.5)
    need_s = YPP_SUBS / weeks_left
    need_h = YPP_HOURS / weeks_left
    got_s = subs / weeks_in
    got_h = hours / weeks_in
    ratio = min(got_s / max(need_s, 1), got_h / max(need_h, 1))
    color = "🟢 ON PACE" if ratio >= 1.0 else ("🟡 WATCH" if ratio >= 0.7 else "🔴 BEHIND")
    return ("live", days_left, subs, hours,
            f"🎯 GOAL STATUS\n"
            f"YPP deadline: Feb 1, 2027 — {days_left} days\n"
            f"Now: {subs} subs / {hours:.0f} hours\n"
            f"Required: ~{need_s:.0f} subs/wk + ~{need_h:.0f} hrs/wk\n"
            f"Actual: ~{got_s:.0f} subs/wk + ~{got_h:.0f} hrs/wk\n"
            f"Status: {color}\n"
            f"Update: /goal subs 850 hours 3100")

async def cmd_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(">>> MOUTH: /goal")
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    text = update.message.text.partition(" ")[2].lower()
    if "subs" in text or "hours" in text:
        parts = text.split()
        for i, p in enumerate(parts):
            if p == "subs" and i + 1 < len(parts) and parts[i+1].isdigit():
                set_setting("subs_now", parts[i+1])
            if p == "hours" and i + 1 < len(parts) and parts[i+1].replace(".", "").isdigit():
                set_setting("hours_now", parts[i+1])
        set_setting("metrics_date", date.today().isoformat())
        log_action("GOAL", f"metrics updated: {text[:60]}")
        await update.message.reply_text("🎯 Metrics saved.")
        return
    *_, msg = goal_status()
    await update.message.reply_text(msg)

async def brain_ask(user_text):
    if not brain:
        return None, "no BRAIN_API_KEY set"
    mem = _db.execute(
        "SELECT kind, content, verification FROM memory ORDER BY id DESC LIMIT 12").fetchall()
    memory_txt = "\n".join(f"- [{m[2]}] {m[0]}: {m[1]}" for m in mem) or "(none yet)"
    mode, days_left, subs, hours, _ = goal_status()
    deadline_txt = (f"YPP deadline Feb 1 2027: {days_left} days away. Metrics: "
                    f"{subs} subs / {hours:.0f} hours. Mode: {mode}. "
                    "Judge all advice against this deadline.")
    system = f"""You are Smart Prime, first agent of the swarm — a constitutional AI agent owned by Juan Ricci.
Your mission: build self-sustaining passive income fully autonomously. Current project: FIRST STAGE, a faceless YouTube channel about Musk and space.
Your laws (never break these):
1. Juan is sovereign. Only his verified Telegram commands control you.
2. 'Smart Freeze' or 'Smart Para' from Juan halts everything instantly; only he can resume.
3. Spending cap $200, reserve $100 never touched, no money moves without Juan's approval.
4. Full autonomy on operations. Juan's only job is money decisions.
5. Never fabricate facts. Evidence tiers: announced, observed, corroborated, assumption.
{deadline_txt}
Income ladder: first income from day one; $500/mo by month 6; $1000/mo by month 9; $6000+/mo with clones by month 12-24.
Your stored memory (constitution + what Juan taught you):
{memory_txt}
Personality: direct, honest, concise, proactive. Under 150 words unless asked. Call him 'Juan' or 'boss'."""
    for model in BRAIN_MODELS:
        print(f">>> BRAIN trying {model}...")
        try:
            r = await brain.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user_text}],
                max_tokens=2000,
            )
            if not getattr(r, "choices", None):
                continue
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                print(f">>> BRAIN answer via {model}")
                return txt, model
        except Exception as e:
            print(f">>> BRAIN {model} FAILED: {str(e)[:120]}")
            log_action("BRAIN", f"{model} failed: {str(e)[:90]}")
            continue
    return None, "all brain models unavailable"

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(">>> MOUTH: /start")
    cid = update.effective_chat.id
    arg = update.message.text.partition(" ")[2].strip()
    if owner_id() is None:
        if arg == BOOT_CODE:
            set_setting("owner_chat_id", cid)
            log_action("SECURITY", f"Owner registered via boot code: chat_id {cid}")
            await update.message.reply_text(
                f"✅ Smart Prime v0.5 online. Webhook armed. Brain connected.\n"
                f"Owner registered by boot code.\n"
                f"YPP deadline: {(DEADLINE - date.today()).days} days (Feb 1, 2027).\n\n"
                f"Commands: /status /goal /report /remember\n"
                f"Or just talk. 'Smart Freeze' stops everything.")
        else:
            await update.message.reply_text(
                "Owner registration requires the 4-digit boot code from the deploy logs "
                "(Render → Logs → 'OWNER BOOT CODE'). Send: /start 1234")
        return
    if is_owner(update):
        await update.message.reply_text("Smart Prime at your service, Juan. /goal for deadline status.")
    else:
        await update.message.reply_text(
            f"This is a private agent. Your chat ID: {cid}. Access denied.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(">>> MOUTH: /status")
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    spent = _db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE kind='SPEND'").fetchone()[0]
    await update.message.reply_text(
        f"🧠 SMART PRIME v0.5 (webhook)\nFrozen: {'YES 🧊' if frozen else 'no'}\n"
        f"Brain: {'connected' if brain else 'NO KEY'}\nConstitution entries: {memories}\n"
        f"YPP deadline: {(DEADLINE - date.today()).days} days (Feb 1, 2027)\n"
        f"Mission: FIRST STAGE\n"
        f"Spending: ${spent:.2f} of ${SPEND_CAP:.0f} — Reserve ${RESERVE:.0f} untouched\n"
        f"Daily report: 7:00 AM HST")

async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(">>> MOUTH: /remember")
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    text = update.message.text.partition(" ")[2]
    if "|" not in text:
        await update.message.reply_text("Format: /remember <topic> | <fact>")
        return
    topic, fact = [p.strip() for p in text.split("|", 1)]
    _db.execute("INSERT INTO memory(created,kind,content,source,verification) "
                "VALUES(?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), topic, fact,
                 "juan-direct", "owner-stated"))
    _db.commit()
    log_action("MEMORY", f"stored [{topic}]")
    await update.message.reply_text(f"🧠 Remembered under '{topic}'.")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(">>> MOUTH: /report")
    if not is_owner(update):
        await update.message.reply_text("Access denied.")
        return
    rows = _db.execute(
        "SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 8").fetchall()
    lines = ["📋 RECENT LEDGER"] + [f"• {r[0][:16]} | {r[1]} | {r[2]}" for r in rows]
    await update.message.reply_text("\n".join(lines))

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    oid = owner_id()
    if not oid:
        return
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    rows = _db.execute(
        "SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 5").fetchall()
    recent = "\n".join(f"• {r[0][:16]} | {r[1]} | {r[2]}" for r in rows) or "• (quiet night)"
    *_, goal_msg = goal_status()
    text = (f"🌅 GOOD MORNING JUAN — daily report\n"
            f"Status: {'🧊 FROZEN' if frozen else '▶️ active'}\n"
            f"{goal_msg}\n\n"
            f"Recent activity:\n{recent}\n\n"
            f"Standing by. 'Smart Freeze' stops everything.")
    try:
        await context.bot.send_message(chat_id=int(oid), text=text)
        log_action("REPORT", "daily report sent")
        print(">>> MOUTH: daily report sent")
    except Exception as e:
        log_action("ERROR", f"daily report failed: {str(e)[:80]}")

async def webhook_watchdog(context: ContextTypes.DEFAULT_TYPE):
    """Hourly self-heal: re-assert the webhook if a dying instance deleted it."""
    try:
        info = await context.bot.get_webhook_info()
        if info.url != WEBHOOK_URL:
            await context.bot.set_webhook(url=WEBHOOK_URL)
            print(">>> WATCHDOG: webhook re-asserted")
    except Exception as e:
        print(f">>> WATCHDOG error: {str(e)[:100]}")

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    low = text.lower()
    print(f">>> SMART-EAR: {text[:90]}")

    if low in FREEZE_PHRASES:
        if is_owner(update):
            set_setting("frozen", "1")
            log_action("CONTROL", "SMART FREEZE executed by owner")
            await update.message.reply_text(
                "🧊 FROZEN. All operations halted. Only 'Smart Resume' from you "
                "will restart me.")
        else:
            log_action("SECURITY", f"Freeze attempt from {update.effective_chat.id}")
        return

    if low == RESUME_PHRASE:
        if is_owner(update):
            set_setting("frozen", "0")
            log_action("CONTROL", "RESUMED by owner")
            await update.message.reply_text("▶️ Resumed. Continuing the mission.")
        return

    if not is_owner(update):
        return

    if get_setting("frozen") == "1":
        await update.message.reply_text("🧊 I am frozen. 'Smart Resume' to wake me.")
        return

    log_action("MESSAGE", f"received: {text[:60]}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                       action=ChatAction.TYPING)
    answer, model = await brain_ask(text)
    if answer:
        log_action("BRAIN", f"answered via {model}")
        await update.message.reply_text(answer[:4000])
        print(">>> MOUTH: brain answer sent")
    else:
        await update.message.reply_text(
            f"🧠 Brain offline ({model}). Juan — check BRAIN_API_KEY. /status works.")
        print(">>> MOUTH: brain offline notice")

async def on_error(update, context):
    print("!!! HANDLER ERROR:", context.error)
    traceback.print_exc()
    log_action("ERROR", f"handler: {str(context.error)[:100]}")

if TOKEN.startswith("PASTE_"):
    print("WARNING: set the SMART_TOKEN environment variable on Render.")
if not BRAIN_API_KEY:
    print("WARNING: set the BRAIN_API_KEY environment variable on Render.")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("goal", cmd_goal))
app.add_handler(CommandHandler("remember", cmd_remember))
app.add_handler(CommandHandler("report", cmd_report))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
app.add_error_handler(on_error)
app.job_queue.run_daily(daily_report, time=dtime(hour=17, minute=0, tzinfo=timezone.utc))
app.job_queue.run_repeating(webhook_watchdog, interval=3600, first=120)

log_action("BOOT", "Smart Prime v0.5 started")
print(f">>> OWNER BOOT CODE: {BOOT_CODE}")
print(f"Smart Prime v0.5 — webhook: {WEBHOOK_URL}")
print(f">>> YPP DEADLINE ARMED: {(DEADLINE - date.today()).days} days")
app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path=TOKEN,
    webhook_url=WEBHOOK_URL,
    drop_pending_updates=True,
)
