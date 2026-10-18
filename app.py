"""
SMART PRIME v0.3 — INSTRUMENTED (Render edition)
Every message prints >>> EAR [...] in logs. Every error prints >>> ERROR.
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime, time as dtime, timezone

import gradio as gr
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

BRAIN_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",
]

brain = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=BRAIN_API_KEY,
    timeout=30.0,
    max_retries=0,
) if BRAIN_API_KEY else None

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s",
                    level=logging.INFO)

def ear(tag, detail=""):
    print(f">>> EAR [{tag}] {detail}", flush=True)

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

async def brain_ask(user_text):
    if not brain:
        return None, "no BRAIN_API_KEY set"
    mem = _db.execute(
        "SELECT kind, content, verification FROM memory ORDER BY id DESC LIMIT 12").fetchall()
    memory_txt = "\n".join(f"- [{m[2]}] {m[0]}: {m[1]}" for m in mem) or "(none yet)"
    system = f"""You are Smart Prime, first agent of the swarm — a constitutional AI agent owned by Juan Ricci.
Your mission: build self-sustaining passive income fully autonomously. Current project: FIRST STAGE, a faceless YouTube channel about Musk and space.
Your laws (never break these):
1. Juan is sovereign. Only his verified Telegram commands control you.
2. 'Smart Freeze' or 'Smart Para' from Juan halts everything instantly; only he can resume.
3. Spending cap $200, reserve $100 never touched, no money moves without Juan's approval.
4. Full autonomy on operations. Juan's only job is money decisions.
5. Never fabricate facts. Use evidence tiers: announced, observed, corroborated, assumption.
Income ladder: first income from day one; $500/mo by month 6; $1000/mo by month 9; $6000+/mo with clones by month 12-24.
Your stored memory (what Juan taught you):
{memory_txt}
Personality: direct, honest, concise, proactive. Keep replies under 150 words unless Juan asks for more. Speak to Juan as 'Juan' or 'boss'."""

    for model in BRAIN_MODELS:
        try:
            ear("brain", f"asking {model}...")
            r = await brain.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user_text}],
                max_tokens=2000,
            )
            if not getattr(r, "choices", None):
                ear("brain", f"{model}: empty response, trying next")
                continue
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                ear("brain", f"{model}: answered ({len(txt)} chars)")
                return txt, model
        except Exception as e:
            ear("brain", f"{model} failed: {str(e)[:90]}")
            log_action("BRAIN", f"{model} failed: {str(e)[:90]}")
            continue
    return None, "all brain models unavailable"

async def on_error(update, context):
    print(f">>> ERROR in handler: {context.error}", flush=True)
    log_action("ERROR", f"handler exception: {str(context.error)[:120]}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ear("cmd", "/start")
    cid = update.effective_chat.id
    if owner_id() is None:
        set_setting("owner_chat_id", cid)
        log_action("SECURITY", f"Owner registered: chat_id {cid}")
        await update.message.reply_text(
            "✅ Smart Prime online. Brain: connected.\n"
            f"Owner registered: chat ID {cid}\n\n"
            "Commands: /status /report /remember <topic> | <fact>\n"
            "Or just talk to me — I'm listening.\n"
            "Say 'Smart Freeze' anytime to stop everything.")
        return
    if is_owner(update):
        await update.message.reply_text("Smart Prime at your service, Juan. Talk to me or /status.")
    else:
        await update.message.reply_text(
            f"This is a private agent. Your chat ID: {cid}. Access denied.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ear("cmd", "/status")
    if not is_owner(update):
        return
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    spent = _db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE kind='SPEND'").fetchone()[0]
    brain_state = "connected" if brain else "NO KEY"
    await update.message.reply_text(
        f"🧠 SMART PRIME v0.3\nFrozen: {'YES 🧊' if frozen else 'no'}\n"
        f"Brain: {brain_state}\nMemory entries: {memories}\n"
        f"Mission: FIRST STAGE\n"
        f"Spending: ${spent:.2f} of ${SPEND_CAP:.0f} cap — Reserve ${RESERVE:.0f} untouched\n"
        f"Daily report: 7:00 AM HST")

async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ear("cmd", "/remember")
    if not is_owner(update):
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
    ear("cmd", "/report")
    if not is_owner(update):
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
    text = (f"🌅 GOOD MORNING JUAN — daily report\n"
            f"Status: {'🧊 FROZEN' if frozen else '▶️ active'}\n"
            f"Memory entries: {memories}\n"
            f"Spending: $0.00 of ${SPEND_CAP:.0f} cap — reserve intact\n\n"
            f"Recent activity:\n{recent}\n\n"
            f"Standing by. 'Smart Freeze' stops everything.")
    try:
        await context.bot.send_message(chat_id=int(oid), text=text)
        log_action("REPORT", "daily report sent")
    except Exception as e:
        log_action("ERROR", f"daily report failed: {str(e)[:80]}")

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    ear("message", text[:80])
    low = text.lower()

    if low in FREEZE_PHRASES:
        if is_owner(update):
            set_setting("frozen", "1")
            log_action("CONTROL", "SMART FREEZE executed by owner")
            await update.message.reply_text(
                "🧊 FROZEN. All operations halted. Only 'Smart Resume' from you "
                "will restart me.")
        else:
            log_action("SECURITY",
                       f"Freeze attempt from unauthorized chat {update.effective_chat.id}")
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
    else:
        await update.message.reply_text(
            f"🧠 Brain offline ({model}). Juan — check BRAIN_API_KEY on Render. "
            "I logged the error in my ledger.")

def dashboard():
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    spent = _db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE kind='SPEND'").fetchone()[0]
    rows = _db.execute(
        "SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 10").fetchall()
    ledger_md = "\n".join([f"- {r[0][:16]} | **{r[1]}** | {r[2]}" for r in rows]) or "_empty_"
    return f"""
# 🧠 SMART PRIME — v0.3 INSTRUMENTED
**Status:** {'🧊 FROZEN' if frozen else '▶️ ACTIVE'}
**Brain:** {'connected' if brain else 'NO KEY'}
**Mission:** FIRST STAGE (Musk/space channel)
**Spending:** ${spent:.2f} / ${SPEND_CAP:.0f} cap — Reserve ${RESERVE:.0f} untouched
**Memory entries:** {memories}

## Recent ledger
{ledger_md}

_Owner: Juan Ricci (@smartcash22) — Freeze: 'Smart Freeze' / 'Smart Para' — Report daily 7AM HST_
"""

def run_dashboard():
    demo = gr.Interface(fn=dashboard, inputs=None, outputs="markdown",
                        title="Smart Prime")
    demo.launch(server_name="0.0.0.0",
                server_port=int(os.environ.get("PORT", 7860)))

if TOKEN.startswith("PASTE_"):
    print("WARNING: set the SMART_TOKEN environment variable on Render.")
if not BRAIN_API_KEY:
    print("WARNING: set the BRAIN_API_KEY environment variable on Render.")

threading.Thread(target=run_dashboard, daemon=True).start()

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("remember", cmd_remember))
app.add_handler(CommandHandler("report", cmd_report))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
app.add_error_handler(on_error)
app.job_queue.run_daily(daily_report,
                        time=dtime(hour=17, minute=0, tzinfo=timezone.utc))
log_action("BOOT", "Smart Prime v0.3 started (instrumented)")
print("Smart Prime v0.3 — listening on Telegram.")
app.run_polling(drop_pending_updates=True)
