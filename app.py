"""
SMART PRIME v2.6 — MODULE 5: THE HANDS (Render edition)
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

async def brain_ask(user_text, extra="", models=None):
    if not brain: return None, "no BRAIN_API_KEY"
    mem = _db.execute("SELECT kind,content,verification FROM memory ORDER BY id DESC LIMIT 12").fetchall()
    memory_txt = "\n".join(f"- [{m[2]}] {m[0]}: {m[1]}" for m in mem)
    system = f"""You are Smart Prime, constitutional AI agent of Juan Ricci, running the FIRST STAGE YouTube channel (Musk/space).
Laws: Juan is sovereign. Smart Freeze/Para halt everything. $200 cap, $100 reserve, no money moves without Juan. Never fabricate; evidence tiers: announced/observed/corroborated/assumption. {goal_status()}
{extra}
Memory:\n{memory_txt}
Style: direct, concise, under 150 words unless asked. Call him Juan or boss."""
    for model in (models or BRAIN_MODELS):
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
        await u.message.reply_text("Smart Prime v2.6 online. Hands + eyes connected.\n" + goal_status() + "\nCommands: /status /goal /research /voice /render /inbox /report")
        return
    if owner_id() is None:
        if arg and arg == BOOT:
            set_setting("owner_chat_id", cid); log_action("SECURITY", f"Owner registered {cid}")
            await u.message.reply_text(f"Smart Prime v2.6 online. Hands: connected. Eyes: connected.\nYPP deadline: {(DEADLINE-date.today()).days} days.\nCommands: /status /goal /research /voice /render /report /remember")
        else:
            await u.message.reply_text("Registration requires a code. Reply /start <code> (code is in Render logs: OWNER BOOT CODE).")
        return
    if is_owner(u):
        await u.message.reply_text("At your service, Juan. /status for the board.")
    else:
        await u.message.reply_text(f"Private agent. Your chat ID: {cid}. Access denied.")

async def cmd_status(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    await u.message.reply_text(f"SMART PRIME v2.6\nFrozen: {get_setting('frozen')=='1'}\nBrain: {'connected' if brain else 'NO KEY'}\nGoal: {goal_status()}\nInbox: {len(os.listdir(INBOX))} files | Renders: {sorted(os.listdir(RENDER_DIR))}")

async def cmd_goal(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].lower(); parts = t.split()
    for i, p in enumerate(parts):
        if p == "subs" and i+1 < len(parts) and parts[i+1].isdigit(): set_setting("subs_now", parts[i+1])
        if p == "hours" and i+1 < len(parts) and parts[i+1].replace(".","").isdigit(): set_setting("hours_now", parts[i+1])
    if "subs" in t or "hours" in t:
        log_action("GOAL", t[:60]); await u.message.reply_text("Metrics saved."); return
    await u.message.reply_text(goal_status())

async def cmd_remember(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2]
    if "|" not in t:
        await u.message.reply_text("Format: /remember <topic> | <fact>"); return
    topic, fact = [p.strip() for p in t.split("|", 1)]
    _db.execute("INSERT INTO memory(created,kind,content,source,verification) VALUES(?,?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), topic, fact, "juan-direct", "owner-stated"))
    _db.commit(); log_action("MEMORY", f"[{topic}]")
    await u.message.reply_text(f"Remembered under '{topic}'.")

async def cmd_report(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    rows = _db.execute("SELECT ts,kind,detail FROM ledger ORDER BY id DESC LIMIT 8").fetchall()
    await u.message.reply_text("\n".join(["RECENT LEDGER"] + [f"· {r[0][:16]} | {r[1]} | {r[2]}" for r in rows]))

async def cmd_research(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
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
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
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
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
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
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    files = os.listdir(INBOX)
    await u.message.reply_text(f"INBOX ({len(files)}):\n" + ("\n".join("· " + f for f in sorted(files)) if files else "(empty — send narration MP3 + clips as files)"))

async def on_file(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    doc = u.message.document or u.message.video
    if not doc: return
    name = getattr(doc, "file_name", None) or f"video_{datetime.now().timestamp()}.mp4"
    p = os.path.join(INBOX, name)
    try:
        f = await c.bot.get_file(doc.file_id)
        await f.download_to_drive(p)
        log_action("INBOX", name)
        await u.message.reply_text(f"Received: {name} ({os.path.getsize(p)//1024} KB). /inbox to see all.")
    except Exception as e:
        log_action("ERROR", f"inbox download: {str(e)[:80]}")
        await u.message.reply_text("Download failed. Resend via paperclip > File. Over 20 MB will not work - use the small version of the video.")

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
    try:
        _yt_metrics_update()
    except Exception:
        pass
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
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    if get_setting("frozen") == "1":
        await u.message.reply_text("Frozen. 'Smart Resume' to wake me."); return
    log_action("MESSAGE", text[:60])
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action=ChatAction.TYPING)
    extra = ""
    try:
        hits = web_search(text, 4)
        if hits:
            ctx = "\n".join(f"- {h.get('title','')}: {h.get('body','')[:160]} [src: {h.get('href','')}]" for h in hits)
            extra = "Live web search results:\n" + ctx + "\nToday's date: " + date.today().isoformat() + ". Prefer these current sources over training data. Cite source domains. If results conflict with training memory, trust the results."
    except Exception:
        pass
    ans, model = await brain_ask(text, extra=extra)
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


# ============ MODULE 6: THE VOICE (YouTube + Reddit hands) ============
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
             "https://www.googleapis.com/auth/youtube.readonly",
             "https://www.googleapis.com/auth/yt-analytics.readonly"]

def _yt_client_config():
    cid = os.environ.get("YT_CLIENT_ID", ""); sec = os.environ.get("YT_CLIENT_SECRET", "")
    return {"installed": {"client_id": cid, "client_secret": sec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]}}

def _yt_creds():
    raw = os.environ.get("YT_TOKEN", "") or get_setting("yt_token")
    if not raw: return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_info(json.loads(raw))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            set_setting("yt_token", creds.to_json())
        return creds
    except Exception as e:
        log_action("ERROR", f"yt_creds: {str(e)[:80]}")
        return None

def _yt_metrics_update():
    creds = _yt_creds()
    if not creds: return None
    from googleapiclient.discovery import build
    from datetime import timedelta
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="statistics", mine=True).execute()
    subs = int(ch["items"][0]["statistics"].get("subscriberCount", 0))
    an = build("youtubeAnalytics", "v2", credentials=creds)
    end = date.today(); start = end - timedelta(days=365)
    r = an.reports().query(ids="channel==MINE", startDate=start.isoformat(),
                           endDate=end.isoformat(), metrics="estimatedMinutesWatched").execute()
    mins = float(r["rows"][0][0]) if r.get("rows") else 0.0
    set_setting("subs_now", subs); set_setting("hours_now", round(mins / 60, 1))
    return subs, round(mins / 60, 1)

async def cmd_connect_youtube(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    if not os.environ.get("YT_CLIENT_ID"):
        await u.message.reply_text("Add YT_CLIENT_ID and YT_CLIENT_SECRET to Render Environment first (guide Step A)."); return
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_yt_client_config(), scopes=YT_SCOPES, autogenerate_code_verifier=False)
    flow.redirect_uri = "http://localhost"
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    await u.message.reply_text("STEP 1 - open this link while signed into the FIRST STAGE Google account:\n\n" + url +
        "\n\nSTEP 2 - authorize everything. Browser will show 'localhost refused to connect' - that is NORMAL."
        "\nSTEP 3 - copy the FULL address from the browser's address bar (starts with http://localhost/?code=...) and paste it right here in this chat.")

async def cmd_yt_token(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    text = u.message.text.strip()
    if "code=" not in text:
        await u.message.reply_text("Paste the full localhost URL from the browser address bar."); return
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_yt_client_config(), scopes=YT_SCOPES, autogenerate_code_verifier=False)
    flow.redirect_uri = "http://localhost"
    try:
        flow.fetch_token(authorization_response=text)
        set_setting("yt_token", flow.credentials.to_json())
        log_action("YT", "connected")
        await u.message.reply_text("YouTube hands connected. /yt_metrics for live numbers. /yt_upload to publish a render. Metrics auto-feed the goal tracker from now on.")
    except Exception as e:
        await u.message.reply_text("Token exchange failed: " + str(e)[:200])

async def cmd_yt_export(u, c):
    if not is_owner(u): return
    raw = get_setting("yt_token")
    if not raw:
        await u.message.reply_text("No token in memory. /connect_youtube first."); return
    await u.message.reply_text("PERMANENCE KEY - add this to Render Environment as YT_TOKEN. It survives every redeploy forever:\n\n" + raw)
    log_action("YT", "token exported")

async def cmd_yt_metrics(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    try:
        r = _yt_metrics_update()
        if r: await u.message.reply_text(f"YouTube live: {r[0]} subscribers | {r[1]} watch hours (trailing 365 days).")
        else: await u.message.reply_text("YouTube not connected. /connect_youtube")
    except Exception as e:
        await u.message.reply_text("Metrics failed: " + str(e)[:200])

async def cmd_yt_upload(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    creds = _yt_creds()
    if not creds:
        await u.message.reply_text("Connect first: /connect_youtube"); return
    t = u.message.text.partition(" ")[2].strip()
    title = t or "Starship Flight 15: First Ship Catch Attempt - What Could Go Wrong"
    cands = []
    for d in (RENDER_DIR, INBOX):
        for fn in os.listdir(d):
            if fn.lower().endswith(".mp4"):
                cands.append(os.path.join(d, fn))
    cands.sort(key=os.path.getmtime)
    if not cands:
        await u.message.reply_text("No MP4s found. Send me a video file, or /render first."); return
    path = cands[-1]
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title, "description": "FIRST STAGE - spaceflight explained. Data over hype.\n\nFootage: SpaceX. AI narration, disclosed per YouTube policy.", "categoryId": "28"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=-1, resumable=True))
        resp = None
        while resp is None:
            s, resp = req.next_chunk()
        log_action("YT", "uploaded " + resp["id"])
        await u.message.reply_text("LIVE: https://youtu.be/" + resp["id"])
    except Exception as e:
        log_action("ERROR", "yt_upload " + str(e)[:120])
        await u.message.reply_text("Upload failed: " + str(e)[:250])

async def cmd_connect_reddit(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].split()
    if len(t) < 2:
        await u.message.reply_text("Usage: /connect_reddit <client_id> <client_secret> (guide Step B - reddit.com/prefs/apps)"); return
    set_setting("reddit_id", t[0]); set_setting("reddit_secret", t[1])
    try:
        import praw
        praw.Reddit(client_id=t[0], client_secret=t[1], user_agent="SmartPrime/1.0")
        log_action("REDDIT", "connected")
        await u.message.reply_text("Reddit eyes connected. /reddit_scan Starship Flight 15 to find threads worth engaging.")
    except Exception as e:
        await u.message.reply_text("Reddit connect failed: " + str(e)[:200])

async def cmd_reddit_scan(u, c):
    if owner_id() is None and str(u.effective_chat.id) == JUAN_CHAT_ID:
        set_setting("owner_chat_id", u.effective_chat.id)
        log_action("SECURITY", f"Owner auto-registered {u.effective_chat.id}")
    if not is_owner(u): return
    if not get_setting("reddit_id"):
        await u.message.reply_text("Connect first: /connect_reddit"); return
    import praw
    r = praw.Reddit(client_id=get_setting("reddit_id"), client_secret=get_setting("reddit_secret"), user_agent="SmartPrime/1.0")
    q = u.message.text.partition(" ")[2].strip() or "Starship Flight 15"
    out = []
    for sub in ["spacexlounge", "SpaceX"]:
        try:
            for p in r.subreddit(sub).search(q, sort="new", time_filter="week", limit=5):
                out.append(f"r/{sub}: {p.title[:90]} ({p.score} pts)\n{p.url}")
        except Exception as e:
            log_action("REDDIT", f"scan fail r/{sub}: {str(e)[:60]}")
    log_action("REDDIT", "scan " + q[:30])
    if out:
        await u.message.reply_text("ENGAGEMENT TARGETS:\n\n" + "\n\n".join(out[:8]) + "\n\nReply with a thread number and I draft a value-first comment for you to post.")
    else:
        await u.message.reply_text("No fresh threads this week for: " + q)


KIMI_MODELS = ["moonshotai/kimi-k2:free", "moonshotai/kimi-k2"]

async def cmd_kimi(u, c):
    if not is_owner(u): return
    t = u.message.text.partition(" ")[2].strip()
    if not t:
        await u.message.reply_text("Usage: /kimi <question> - consults Kimi, co-architect of the mission."); return
    await c.bot.send_chat_action(chat_id=u.effective_chat.id, action=ChatAction.TYPING)
    extra = ("You are Kimi, co-architect of Smart Prime and the FIRST STAGE YouTube channel (Musk/space), now advising Smart Prime directly. "
             "Owner: Juan Ricci. Mission: autonomous passive income. YPP deadline Feb 1 2027. "
             "Give Smart Prime specific, expert, actionable operational guidance: strategy, production, distribution, technical fixes. Under 300 words.")
    ans, model = await brain_ask(t, extra=extra, models=KIMI_MODELS)
    log_action("KIMI", f"consult via {model}")
    if ans:
        await u.message.reply_text("KIMI: " + ans[:4000])
    else:
        await u.message.reply_text("Kimi unreachable right now (free route may be busy; retry later).")

app = (Application.builder().token(TOKEN)
       .connect_timeout(30).read_timeout(30).write_timeout(180).pool_timeout(60)
       .build())
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("goal", cmd_goal))
app.add_handler(CommandHandler("remember", cmd_remember))
app.add_handler(CommandHandler("report", cmd_report))
app.add_handler(CommandHandler("research", cmd_research))
app.add_handler(CommandHandler("voice", cmd_voice))
app.add_handler(CommandHandler("render", cmd_render))
app.add_handler(CommandHandler("inbox", cmd_inbox))
app.add_handler(CommandHandler("connect_youtube", cmd_connect_youtube))
app.add_handler(MessageHandler(filters.Regex(r"^http://localhost"), cmd_yt_token))
app.add_handler(CommandHandler("yt_upload", cmd_yt_upload))
app.add_handler(CommandHandler("yt_export", cmd_yt_export))
app.add_handler(CommandHandler("yt_metrics", cmd_yt_metrics))
app.add_handler(CommandHandler("connect_reddit", cmd_connect_reddit))
app.add_handler(CommandHandler("reddit_scan", cmd_reddit_scan))
app.add_handler(CommandHandler("kimi", cmd_kimi))
app.add_handler(MessageHandler(filters.VIDEO, on_file))
app.add_handler(MessageHandler(filters.ATTACHMENT, on_file))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
app.add_error_handler(on_error)
app.job_queue.run_daily(daily_report, time=dtime(hour=17, minute=0, tzinfo=timezone.utc))
app.job_queue.run_repeating(news_job, interval=21600, first=300)

def dashboard():
    frozen = get_setting("frozen") == "1"
    renders = sorted(os.listdir(RENDER_DIR), reverse=True)[:5]
    inbox = sorted(os.listdir(INBOX))
    links = "\n".join(f"- [{r}](/dl/{r})" for r in renders) or "_none yet_"
    crash_txt = ""
    if os.path.exists("bot_crash.log"):
        crash_txt = "\n\n## BOT CRASH LOG\n```\n" + open("bot_crash.log").read()[-1200:] + "\n```"
    return f"""# SMART PRIME v2.6 — THE HANDS
**Status:** {'FROZEN' if frozen else 'ACTIVE'} | **Brain:** {'connected' if brain else 'NO KEY'} | **YT:** {'connected' if get_setting('yt_token') else '-'} | **Reddit:** {'connected' if get_setting('reddit_id') else '-'}
**Goal:** {goal_status()}
**Inbox ({len(inbox)}):** {', '.join(inbox[:8]) or 'empty'}
## Renders
{links}
_Owner: Juan Ricci (@smartcash22) — Freeze: 'Smart Freeze' / 'Smart Para' — Reports 7AM HST_""" + crash_txt

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
api = FastAPI()
@api.get("/dl/{fname}")
def dl(fname: str):
    safe = os.path.basename(fname); p = os.path.join(RENDER_DIR, safe)
    if os.path.exists(p): return FileResponse(p, media_type="application/octet-stream", filename=safe)
    return JSONResponse({"error": "not found"}, status_code=404)
demo = gr.Interface(fn=dashboard, inputs=None, outputs="markdown", title="Smart Prime")
try:
    demo.load(fn=dashboard, inputs=None, outputs=demo.output_components)
except Exception:
    pass
server = gr.mount_gradio_app(api, demo, path="/")

def _run_bot():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app.run_polling(drop_pending_updates=True, stop_signals=None)
    except Exception:
        err = traceback.format_exc()
        print("!!! BOT THREAD CRASHED !!!")
        print(err[-1500:])
        with open("bot_crash.log", "w") as f:
            f.write(err)
threading.Thread(target=_run_bot, daemon=True).start()
import uvicorn
print(f">>> YPP DEADLINE ARMED: {(DEADLINE - date.today()).days} days")
uvicorn.run(server, host="0.0.0.0", port=PORT)
