"""
SMART PRIME v1.2 — MODULE 5: THE HANDS (Render edition)
Constitutional agent of Juan Ricci (@smartcash22). Fully autonomous campaign operator.
NEW: web search (eyes), news watcher, Telegram file inbox, TTS voice (edge-tts),
video render workshop (ffmpeg via imageio-ffmpeg), dashboard downloads.
"""
import os, re, json, sqlite3, logging, random, asyncio, threading, subprocess, traceback
from datetime import datetime, date, time as dtime, timezone

import gradio as gr
from openai import AsyncOpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("SMART_TOKEN", "PASTE_YOUR_TOKEN_HERE")
BRAIN_API_KEY = os.environ.get("BRAIN_API_KEY", "")
DB_PATH = "smart.db"
INBOX = "inbox"; RENDER_DIR = "renders"
os.makedirs(INBOX, exist_ok=True); os.makedirs(RENDER_DIR, exist_ok=True)
FREEZE_PHRASES = {"smart freeze", "smart para"}
RESUME_PHRASE = "smart resume"
SPEND_CAP = 200.0; RESERVE = 100.0
DEADLINE = date(2027, 2, 1); TARGET = date(2027, 1, 18); LAUNCH = date(2026, 11, 1)
YPP_SUBS = 1000; YPP_HOURS = 4000
PORT = int(os.environ.get("PORT", "10000"))
BRAIN_MODELS = ["openrouter/free", "nvidia/nemotron-3-super-120b-a12b:free", "cohere/north-mini-code:free"]
brain = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=BRAIN_API_KEY, timeout=20.0, max_retries=0) if BRAIN_API_KEY else None
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, kind TEXT, content TEXT, source TEXT, verification TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, detail TEXT, amount REAL DEFAULT 0)")
    c.commit(); return c
_db = db()
def get_setting(k):
    r = _db.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone(); return r[0] if r else None
def set_setting(k, v):
    _db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v))); _db.commit()
def log_action(kind, detail, amount=0):
    _db.execute("INSERT INTO ledger(ts,kind,detail,amount) VALUES(?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), kind, detail, amount)); _db.commit()
def owner_id(): return get_setting("owner_chat_id")
def is_owner(u): return str(u.effective_chat.id) == str(owner_id())

CONSTITUTION = [
 ("mission", "Build self-sustaining passive income fully autonomously. First project: FIRST STAGE, a faceless YouTube channel covering Musk and space.", "core"),
 ("laws", "Juan is sovereign. Smart Freeze/Smart Para halt everything instantly, only Juan can resume. Spending cap $200, reserve $100 never touched, no money moves without Juan. Full autonomy on operations. Juan's only recurring job is money decisions.", "core"),
 ("deadline", "HARD DEADLINE: FIRST STAGE must be ACCEPTED into the YouTube Partner Program BEFORE February 1, 2027 (grandfathered rules: 1000 subs + 4000 watch hours or 10M Shorts views; after that date thresholds double). Hit metrics by January 18, 2027. We can NOT miss it.", "core"),
 ("income_ladder", "First income day one. $500/mo month 6. $1000/mo month 9. $6000+/mo with swarm month 12-24.", "core"),
 ("brand", "FIRST STAGE — faceless Musk/space channel, YouTube @FirstStageOfficial. AI voice with disclosure. Evidence tiers mandatory.", "core"),
 ("owner", "Juan Ricci, USA, Telegram @smartcash22. Money decisions only; near-zero routine workload.", "core"),
]
def seed_constitution():
    if _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0] == 0:
        for t, c, v in CONSTITUTION:
            _db.execute("INSERT INTO memory(created,kind,content,source,verification) VALUES(?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), t, c, "constitution", v))
        _db.commit(); print(">>> CONSTITUTION seeded")
seed_constitution()

def goal_status():
    today = date.today()
    subs = int(get_setting("subs_now") or 0); hours = float(get_setting("hours_now") or 0)
    days_left = (DEADLINE - today).days
    if today < LAUNCH:
        wk = max((TARGET - LAUNCH).days / 7, 1)
        return f"YPP deadline: Feb 1, 2027 — {days_left} days. From launch to target: {wk:.0f} weeks. Required: ~{round(YPP_SUBS/wk)} subs/wk + ~{round(YPP_HOURS/wk)} hrs/wk."
    wl = max((TARGET - today).days / 7, 0.5); wi = max((today - LAUNCH).days / 7, 0.5)
    need_s = YPP_SUBS/wl; need_h = YPP_HOURS/wl; got_s = subs/wi; got_h = hours/wi
    ratio = min(got_s/max(need_s,1), got_h/max(need_h,1))
    color = "ON PACE" if ratio >= 1 else ("WATCH" if ratio >= 0.7 else "BEHIND")
    return f"YPP deadline: Feb 1, 2027 — {days_left} days. Now: {subs} subs/{hours:.0f} hrs. Need ~{need_s:.0f} subs + ~{need_h:.0f} hrs per week. Actual ~{got_s:.0f}/~{got_h:.0f}. Status: {color}. Update: /goal subs 850 hours 3100"

def web_search(q, n=5):
    try:
        from ddgs import DDGS
        with DDGS() as d:
            return list(d.text(q, max_results=n))
    except Exception as e:
        log_action("SEARCH", f"fail {q[:40]}: {str(e)[:60]}"); return []

async def brain_ask(user_text, extra=""):
    if not brain: return None, "no BRAIN_API_KEY"
    mem = _db.execute("SELECT kind,content,verification FROM memory ORDER BY id DESC LIMIT 12").fetchall()
    memory_txt = "\n".join(f"- [{m[2]}] {m[0]}: {m[1]}" for m in mem)
    system = f"""You are Smart Prime, constitutional AI agent of Juan Ricci, running the FIRST STAGE YouTube channel (Musk/space).
Laws: Juan is sovereign. Smart Freeze/Para halt everything. $200 cap, $100 reserve, no money moves without Juan. Never fabricate; evidence tiers: announced/observed/corroborated/assumption. {goal_status()}
{extra}
Memory:\n{memory_txt}
Style: direct, concise, under 150 words unless asked. Call him Juan or boss."""
    for model in BRAIN_MODELS:
        try:
            r = await brain.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":user_text}], max_tokens=2000)
            if getattr(r, "choices", None):
                txt = (r.choices[0].message.content or "").strip()
                if txt: return txt, model
        except Exception as e:
            log_action("BRAIN", f"{model} failed: {str(e)[:80]}"); continue
    return None, "all brain models unavailable"

JUAN_CHAT_ID = "8363286514"

async def cmd_start(u, c):
    cid = u.effective_chat.id; arg = u.message.text.partition(" ")[2].strip()
    if str(cid) == JUAN_CHAT_ID:
        if str(owner_id()) != str(cid):
            set_setting("owner_chat_id", cid); log_action("SECURITY", f"Owner auto-registered {cid}")
        await u.message.reply_text("Smart Prime v1.2 online. Hands + eyes connected.\n" + goal_status() + "\nCommands: /status /goal /research /voice /render /inbox /report")
        return
    if owner_id() is None:
        if arg and arg == BOOT:
            set_setting("owner_chat_id", cid); log_action("SECURITY", f"Owner registered {cid}")
            await u.message.reply_text(f"Smart Prime v1.2 online. Hands: connected. Eyes: connected.\nYPP deadline: {(DEADLINE-date.today()).days} days.\nCommands: /status /goal /research /voice /render /report /remember")
        else:
            await u.message.reply_text("Registration requires a code. Reply /start <code> (code is in Render logs: OWNER BOOT CODE).")
        return
    if is_owner(u):
        await u.message.reply_text("At your service, Juan. /status for the board.")
    else:
        await u.message.reply_text(f"Private agent. Your chat ID: {cid}. Access denied.")

async def cmd_status(u, c):
    if not is_owner(u): return
    await u.message.reply_text(f"SMART PRIME v1.2\nFrozen: {get_setting('frozen')=='1'}\nBrain: {'connected' if brain else 'NO KEY'}\nGoal: {goal_status()}\nInbox: {len(os.listdir(INBOX))} files | Renders: {sorted(os.listdir(RENDER_DIR))}")

async def cmd_goal(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].lower(); parts = t.split()
    for i, p in enumerate(parts):
        if p == "subs" and i+1 < len(parts) and parts[i+1].isdigit(): set_setting("subs_now", parts[i+1])
        if p == "hours" and i+1 < len(parts) and parts[i+1].replace(".","").isdigit(): set_setting("hours_now", parts[i+1])
    if "subs" in t or "hours" in t:
        log_action("GOAL", t[:60]); await u.message.reply_text("Metrics saved."); return
    await u.message.reply_text(goal_status())

async def cmd_remember(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2]
    if "|" not in t:
        await u.message.reply_text("Format: /remember <topic> | <fact>"); return
    topic, fact = [p.strip() for p in t.split("|", 1)]
    _db.execute("INSERT INTO memory(created,kind,content,source,verification) VALUES(?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), topic, fact, "juan-direct", "owner-stated"))
    _db.commit(); log_action("MEMORY", f"[{topic}]")
    await u.message.reply_text(f"Remembered under '{topic}'.")

async def cmd_report(u, c):
    if not is_owner(u): return
    rows = _db.execute("SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 8").fetchall()
    await u.message.reply_text("\n".join(["RECENT LEDGER"] + [f"· {r[0][:16]} | {r[1]} | {r[2]}" for r in rows]))

async def cmd_research(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].strip() or "Starship SpaceX latest news"
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action=ChatAction.TYPING)
    hits = []
    for q in [t, t + " latest", t + " 2026"]:
        hits += web_search(q, 4)
    ctx = "\n".join(f"- {h.get('title','')}: {h.get('body','')[:200]} [src: {h.get('href','')}]" for h in hits[:12]) or "(search unavailable)"
    ans, model = await brain_ask(f"Research task: {t}\nSearch results:\n{ctx}\nDeliver: key facts with source domain per claim, conflicts flagged, evidence tier per claim, under 250 words.")
    log_action("RESEARCH", f"{t[:50]} via {model}")
    if ans: await u.message.reply_text(ans[:4000])
    else: await u.message.reply_text("Brain offline. Raw results saved to ledger.")

async def cmd_voice(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].strip()
    if not t:
        await u.message.reply_text("Usage: /voice <script text> — I narrate it and send the MP3."); return
    import edge_tts
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action=ChatAction.RECORD_VOICE)
    chunks, cur = [], ""
    for sent in re.split(r"(?<=[.!?]) ", t):
        if len(cur) + len(sent) > 2800: chunks.append(cur); cur = sent
        else: cur += " " + sent
    if cur.strip(): chunks.append(cur)
    for i, ch in enumerate(chunks[:4]):
        p = f"{RENDER_DIR}/voice_{datetime.now().strftime('%H%M%S')}_{i}.mp3"
        await edge_tts.Communicate(ch, "en-US-ChristopherNeural").save(p)
        await c.bot.send_audio(chat_id=u.effective_chat.id, audio=open(p, "rb"), title=f"FIRST STAGE narration {i+1}")
    log_action("VOICE", f"{len(chunks)} chunk(s) voiced")

async def cmd_render(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].strip()
    narr = None
    for f in sorted(os.listdir(INBOX)):
        if f.lower().endswith((".mp3", ".m4a", ".wav")): narr = os.path.join(INBOX, f); break
    vids = sorted(f for f in os.listdir(INBOX) if f.lower().endswith(".mp4"))
    if not narr or not vids:
        await u.message.reply_text(f"Need narration MP3 + {len(vids)} clips in inbox. Send them to this chat as files. /inbox to check."); return
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    def _dur(p):
        r = subprocess.run([FF, "-i", p], capture_output=True, text=True)
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
    dur = _dur(narr)
    clips = [os.path.join(INBOX, v) for v in vids]
    cdurs = [_dur(p) for p in clips]
    segs, i, total = [], 0, 0.0
    while total < dur:
        k, f = i % len(clips), (1.25 if (i // len(clips)) == 1 else 1.0)
        d = min(cdurs[k], dur - total)
        segs.append((k, d, f)); total += d * f; i += 1
    cmd = [FF, "-y", "-v", "error"]
    for k, d, f in segs: cmd += ["-t", str(d), "-i", clips[k]]
    cmd += ["-i", narr]
    parts = []
    for j, (k, d, f) in enumerate(segs):
        pre = f"setpts={f}*PTS," if f != 1.0 else ""
        parts.append(f"[{j}:v]{pre}scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{j}]")
    parts.append("".join(f"[v{j}]" for j in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[vout]")
    open("/tmp/fg.txt", "w").write(";\n".join(parts))
    aid = len(segs); out = f"{RENDER_DIR}/episode_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
    r = subprocess.run(cmd + ["-filter_complex_script", "/tmp/fg.txt", "-map", "[vout]", "-map", f"{aid}:a", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-t", str(round(dur, 2)), out], capture_output=True, text=True)
    if r.returncode == 0:
        log_action("RENDER", out)
        await u.message.reply_text(f"RENDER COMPLETE: {out}\nDownload: https://smart-prime.onrender.com/dl/{os.path.basename(out)}")
    else:
        await u.message.reply_text("Render failed: " + r.stderr[-300:])

async def cmd_inbox(u, c):
    if not is_owner(u): return
    files = os.listdir(INBOX)
    await u.message.reply_text(f"INBOX ({len(files)}):\n" + ("\n".join("· " + f for f in sorted(files)) if files else "(empty — send narration MP3 + clips as files)"))

async def on_file(u, c):
    if not is_owner(u): return
    doc = u.message.document
    if not doc: return
    p = os.path.join(INBOX, doc.file_name or f"file_{datetime.now().timestamp()}")
    f = await c.bot.get_file(doc.file_id)
    await f.download_to_drive(p)
    log_action("INBOX", doc.file_name)
    await u.message.reply_text(f"Received: {doc.file_name} ({doc.file_size//1024} KB). /inbox to see all.")

async def news_job(c):
    oid = owner_id()
    if not oid or get_setting("frozen") == "1": return
    hits = web_search("SpaceX Starship news", 6) + web_search("Starship Flight 15", 4)
    lines = [h.get("title", "") for h in hits if h.get("title")]
    known = set((get_setting("news_seen") or "").split("||"))
    fresh = [l for l in lines if l and l not in known][:5]
    if fresh:
        set_setting("news_seen", "||".join((list(known) + fresh)[-40:]))
        log_action("NEWS", f"{len(fresh)} new headlines")
        try: await c.bot.send_message(chat_id=int(oid), text="📰 NEWS WATCH:\n" + "\n".join("· " + l for l in fresh) + "\n\n/research <topic> for deep dive.")
        except Exception: pass

async def daily_report(c):
    oid = owner_id()
    if not oid or get_setting("frozen") == "1": return
    tk = "reported_" + date.today().isoformat()
    if get_setting(tk): return
    set_setting(tk, "1")
    mem = _db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    rows = _db.execute("SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 5").fetchall()
    recent = "\n".join(f"· {r[0][:16]} | {r[1]} | {r[2]}" for r in rows) or "· quiet"
    try:
        await c.bot.send_message(chat_id=int(oid), text=f"GOOD MORNING JUAN — daily report\nStatus: {'FROZEN' if get_setting('frozen')=='1' else 'active'}\n{goal_status()}\nMemory entries: {mem}\n\nRecent:\n{recent}\n\nStanding by.")
        log_action("REPORT", "daily report sent")
    except Exception: pass

async def on_message(u, c):
    text = (u.message.text or "").strip(); low = text.lower()
    print(f">>> SMART-EAR: {text[:90]}")
    if low in FREEZE_PHRASES:
        if is_owner(u):
            set_setting("frozen", "1"); log_action("CONTROL", "FREEZE by owner")
            await u.message.reply_text("FROZEN. All operations halted. Only 'Smart Resume' from you restarts me.")
        else: log_action("SECURITY", f"freeze attempt {u.effective_chat.id}")
        return
    if low == RESUME_PHRASE:
        if is_owner(u):
            set_setting("frozen", "0"); log_action("CONTROL", "RESUMED")
            await u.message.reply_text("Resumed. Continuing the mission.")
        return
    if not is_owner(u): return
    if get_setting("frozen") == "1":
        await u.message.reply_text("Frozen. 'Smart Resume' to wake me."); return
    log_action("MESSAGE", text[:60])
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action=ChatAction.TYPING)
    ans, model = await brain_ask(text)
    if ans:
        log_action("BRAIN", f"via {model}")
        await u.message.reply_text(ans[:4000])
    else:
        await u.message.reply_text("Brain offline — check BRAIN_API_KEY. /status works.")

async def on_error(u, c):
    print("!!! HANDLER ERROR:", c.error); traceback.print_exc()
    log_action("ERROR", str(c.error)[:100])

if TOKEN.startswith("PASTE_"): print("WARNING: set SMART_TOKEN env var.")
if not BRAIN_API_KEY: print("WARNING: set BRAIN_API_KEY env var.")

BOOT = str(random.randint(1000, 9999))
print(f">>> OWNER BOOT CODE: {BOOT}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("goal", cmd_goal))
app.add_handler(CommandHandler("remember", cmd_remember))
app.add_handler(CommandHandler("report", cmd_report))
app.add_handler(CommandHandler("research", cmd_research))
app.add_handler(CommandHandler("voice", cmd_voice))
app.add_handler(CommandHandler("render", cmd_render))
app.add_handler(CommandHandler("inbox", cmd_inbox))
app.add_handler(MessageHandler(filters.Document.ALL, on_file))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
app.add_error_handler(on_error)
app.job_queue.run_daily(daily_report, time=dtime(hour=17, minute=0, tzinfo=timezone.utc))
app.job_queue.run_repeating(news_job, interval=21600, first=300)

def dashboard():
    frozen = get_setting("frozen") == "1"
    renders = sorted(os.listdir(RENDER_DIR), reverse=True)[:5]
    inbox = sorted(os.listdir(INBOX))
    links = "\n".join(f"- [{r}](/dl/{r})" for r in renders) or "_none yet_"
    return f"""# SMART PRIME v1.2 — THE HANDS
**Status:** {'FROZEN' if frozen else 'ACTIVE'} | **Brain:** {'connected' if brain else 'NO KEY'}
**Goal:** {goal_status()}
**Inbox ({len(inbox)}):** {', '.join(inbox[:8]) or 'empty'}
## Renders
{links}
_Owner: Juan Ricci (@smartcash22) — Freeze: 'Smart Freeze' / 'Smart Para' — Reports 7AM HST_"""

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
api = FastAPI()
@api.get("/dl/{fname}")
def dl(fname: str):
    safe = os.path.basename(fname); p = os.path.join(RENDER_DIR, safe)
    if os.path.exists(p): return FileResponse(p, media_type="application/octet-stream", filename=safe)
    return JSONResponse({"error": "not found"}, status_code=404)
demo = gr.Interface(fn=dashboard, inputs=None, outputs="markdown", title="Smart Prime")
server = gr.mount_gradio_app(api, demo, path="/")

threading.Thread(target=app.run_polling, kwargs={"drop_pending_updates": True}, daemon=True).start()
import uvicorn
print(f">>> YPP DEADLINE ARMED: {(DEADLINE - date.today()).days} days")
uvicorn.run(server, host="0.0.0.0", port=PORT)
