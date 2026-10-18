"""
SMART PRIME v0.1 — Module 1: The Core
Constitutional agent of Juan Ricci (@smartcash22)
Mission: FIRST STAGE — autonomous income, starting with the Musk/space channel.
"""

import os
import sqlite3
import logging
import asyncio
import threading
from datetime import datetime

import gradio as gr
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("SMART_TOKEN", "PASTE_YOUR_TOKEN_HERE")
DB_PATH = "smart.db"
FREEZE_PHRASES = {"smart freeze", "smart para"}
RESUME_PHRASE = "smart resume"
SPEND_CAP = 200.0
RESERVE = 100.0

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

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if owner_id() is None:
        set_setting("owner_chat_id", cid)
        log_action("SECURITY", f"Owner registered: chat_id {cid}")
        await update.message.reply_text(
            "✅ Smart Prime online.\n"
            f"Owner registered: chat ID {cid}\n\n"
            "If this is you, Juan — this ID is now permanently bound. "
            "No one else can ever command me.\n\n"
            "Commands:\n/status — what I know\n"
            "/report — recent activity\n"
            "/remember <topic> | <fact> — store knowledge\n"
            "Say 'Smart Freeze' anytime to stop everything.")
        return
    if is_owner(update):
        await update.message.reply_text(
            "Smart Prime at your service, Juan. /status for overview.")
    else:
        await update.message.reply_text(
            f"This is a private agent. Your chat ID: {cid}. Access denied.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    spent = _db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE kind='SPEND'").fetchone()[0]
    await update.message.reply_text(
        f"🧠 STATUS\nFrozen: {'YES 🧊' if frozen else 'no'}\n"
        f"Memory entries: {memories}\n"
        f"Phase: v0.1 CORE (brain in Module 2)\n"
        f"Mission: FIRST STAGE\n"
        f"Spending: ${spent:.2f} of ${SPEND_CAP:.0f} cap\n"
        f"Reserve: ${RESERVE:.0f} (untouched)")

async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if not is_owner(update):
        return
    rows = _db.execute(
        "SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 8").fetchall()
    lines = ["📋 RECENT LEDGER"] + [f"• {r[0][:16]} | {r[1]} | {r[2]}" for r in rows]
    await update.message.reply_text("\n".join(lines))

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()

    if text in FREEZE_PHRASES:
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

    if text == RESUME_PHRASE:
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

    log_action("MESSAGE", f"received: {update.message.text[:60]}")
    await update.message.reply_text(
        "🧠 Message received and logged. Full brain arrives in Module 2 — "
        "for now I hear you, remember everything, and obey the freeze. "
        "Try /remember goals | make Juan $500/mo by month 6")

def dashboard():
    frozen = get_setting("frozen") == "1"
    memories = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    spent = _db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE kind='SPEND'").fetchone()[0]
    rows = _db.execute(
        "SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 10").fetchall()
    ledger_md = "\n".join([f"- {r[0][:16]} | **{r[1]}** | {r[2]}" for r in rows]) or "_empty_"
    return f"""
# 🧠 SMART PRIME — v0.1 CORE
**Status:** {'🧊 FROZEN' if frozen else '▶️ ACTIVE'}
**Mission:** FIRST STAGE (Musk/space channel)
**Spending:** ${spent:.2f} / ${SPEND_CAP:.0f} cap — Reserve ${RESERVE:.0f} untouched
**Memory entries:** {memories}

## Recent ledger
{ledger_md}

_Owner: Juan Ricci (@smartcash22) — Freeze: 'Smart Freeze' / 'Smart Para'_
"""

async def bot_main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log_action("BOOT", "Smart Prime v0.1 started (Render edition)")
    await app.run_polling()

def start_bot_thread():
    asyncio.run(bot_main())

if TOKEN.startswith("PASTE_"):
    print("WARNING: set the SMART_TOKEN environment variable on Render.")

threading.Thread(target=start_bot_thread, daemon=True).start()

demo = gr.Interface(fn=dashboard, inputs=None, outputs="markdown",
                    title="Smart Prime")
demo.launch(server_name="0.0.0.0",
            server_port=int(os.environ.get("PORT", 7860)))
