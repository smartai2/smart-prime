# Smart Prime — FIRST STAGE Studio 4.5.0

## Visual review diagnostics and readable contact pages

Studio 4.5.0 preserves a failed visual job before temporary files disappear: the approved script and evidence, licensed candidate metadata, source/shot screening, sentence-to-archive/diagram mapping, picture-editor response and contact pages. The picture editor is asked for every sentence's coverage and precise missing visual on rejection. An explicit rejection still stops immediately; a missing reason never turns a rejection into another approval attempt.

Candidate sheets are split into pages of six shots, retaining original shot IDs, rather than sending one very tall image that can become unreadable after image resizing. All pages are reviewed in the same call. Existing relevance, authenticity, motion, variety, storyboard and rendered-picture gates are unchanged. Live acceptance of this change remains pending.

Rejected diagnostics are sent only to the owner via an unlisted, expiring link, retrievable with `/video_diagnostics` without AI calls. The ZIP contains no video and never replaces the latest publishable output. Like finished downloads, it expires within 24 hours and can disappear on free-server restart. It is diagnostic evidence, not approved content.

## Sentence-level evidence upgrade

The 7:27 PM HST Studio 4.4.2 run reached sentence review. It correctly rejected
booster-role and upper-stage-continuation claims with mismatched attached evidence.
Inspection found that the source filter discarded launch evidence containing
"orbital launch pad" and a completed-ascent-burn passage. Version 4.4.3 retains
those passages with their full context, while still filtering unrelated orbital
research. Reviews also receive source dates/titles, and general mechanism scripts
are told to omit variant-specific engine counts. Live output acceptance is pending.


The 7:15 PM HST Studio 4.4 live run reached the free model but stopped at a
13-plus-word sentence. Version 4.4.1 shortens only overlong items, retaining IDs,
source evidence and all other text, then requires normal validation and full factual
review. Rejected fact outlines now show their actual sentences in Telegram diagnostics.
The 7:22 PM run then exposed an overly broad acceleration-scope check: it also
rejected historical uses of "never". Version 4.4.2 restricts that check to
acceleration/thrust/momentum statements and filters unrelated researcher, novelty and
plume-physics material before writing. It prefers twelve distinct sentences rather
than forcing fourteen and encouraging filler; the 80–170 word, evidence, topic and
visual quality requirements remain unchanged. Live output acceptance is still pending.


The November 21 Studio 4.3.1 live test stopped at factual review: whole-script
rewrites kept introducing unsupported timing conditions and staging comparisons.
Studio 4.4 replaces that writer with an explicit fact outline. Every spoken sentence
has its own stable claim ID and exact source evidence; the title and each heading
are checked too. A separate review must return a verdict for every item.

Only explicitly rejected text can change. Evidence, sentence order, visuals and
accepted passages are locked; each correction requires a fresh complete review.
Missing evidence, incomplete reviews, unchanged rejected text and daily quota
exhaustion stop production. There is at most one structural repair, one targeted length repair and two factual
corrections. The text path uses the same free Nemotron route throughout; it does
not switch reviewers to seek approval. Cached approvals are bound to the exact
compiled text and evidence, and old-version approvals are invalidated.

The labeled diagrams, three-frame timed storyboard review, actual rendered-picture
review, licensing requirements and audio/technical checks remain mandatory.
No successful Studio 4.4 unattended delivery is claimed by this code change alone.
Automatic publishing remains paused pending output acceptance and the separate
Google authorization fix. No paid service is required by this change.

Juan can ask in Telegram:

```
/video How Starship's two stages work
Make a Short about why rockets use stages
/video_status
/cancel_video
/video_latest
```

The bot makes a vertical 1080 × 1920 Short, normally 40–85 seconds. One job runs at a time.
It reports progress and stops when Juan says **Smart Freeze**. Automatic public uploads
are opt-in and require a verified FIRST STAGE connection plus all Studio quality checks.
The old arbitrary-inbox public uploader has been removed.

## Production workflow

1. Read source pages; search snippets are discovery hints, not script evidence. Prefer
   primary sources, label reported material, and use encyclopedias only for background.
   Current-news requests need recent, dated reporting. This restriction can stop a job.
2. Build an original 80–170 word explanation from an evidence outline, with one
   complete short sentence and exact source IDs per claim. Check each sentence,
   title and heading in a separate model call; preserve planned-capability wording.
   A rejected item's replacement can use only its original evidence. Accepted text,
   evidence and scene order cannot be rewritten. Corrections require a new complete
   review. This is an AI check, not a guarantee of factual correctness.
3. Find licensed motion footage and photography on Wikimedia Commons or NASA. Reject
   unknown rights, NC/SA licenses, animations masquerading as footage, unrelated bands
   called Starship, and pre-edited comparisons. Require usable resolution and real video.
4. Use explicitly labeled original staging diagrams for ignition/separation mechanisms; real
   archive imagery illustrates the vehicle and launch. Diagrams are not photorealistic or
   claimed recordings of an event. Archive motion checks apply to the archive segments.
   Search the scene actions as well as the broad subject. Sample early close views and later
   moments from distinct launches/actions. Screen photographs/footage separately
   from illustrations, then select one shot per sentence. Enforce at least 60% motion
   coverage by narration words, four distinct shots, and no consecutive repeated shot.
   All archive visuals are labelled; they are never presented as footage of a new event.
5. Synthesize a consistent US English neural voice locally using Piper John medium.
   The model card lists public-domain LibriVox source recordings. Model download is
   SHA-256 checked. No robotic eSpeak fallback is used by Studio.
6. Edit the shots, add a gentle push-in to photographs, burn in phrase-timed captions,
   add attribution and FIRST STAGE branding, and normalize speech in two passes.
7. Review two actual rendered frames per shot before delivery. An explicit picture rejection
   stops delivery; another provider cannot overrule it.
8. Check H.264/AAC playback, full-file decoding, resolution, timeline, caption order,
   duration, integrated loudness and true peak before delivery.

## Delivery

The private owner chat receives temporary, unlisted links first. Telegram then attempts
to fetch the MP4 by URL for an inline video, avoiding the old multipart-upload timeout.
The ZIP includes MP4, SRT, thumbnail, upload description with media credits, script,
source evidence, sentence-by-sentence evidence/verdicts, edit decisions and technical report. Include the supplied attribution
when publishing. The source footage's audio is discarded.

Downloads are available **up to 24 hours on the current Render instance**. Free Render
storage is ephemeral: a restart or redeploy can remove them earlier. Save the package
when it arrives. `/video_latest` retries delivery of the saved video and links without using AI quota; it is not permanent storage.
No additional paid service or storage subscription is enabled by this release.

## Runtime

- Python entrypoint: `python app.py`; dependencies: `pip install -r requirements.txt`.
- Existing `SMART_TOKEN`, `BRAIN_API_KEY`, owner and YouTube settings remain in use.
- Studio uses the free Nemotron 3 Ultra text route for sentence writing/review, and Nemotron 3.5 Super VL/Particle 1 for visual inspection. Text
  reasoning budgets leave room for final JSON; vision reasoning is disabled. Each
  request has a 95-second total deadline. Requests are paced; a non-daily rate limit imposes a bounded
  cooldown before another attempt. This avoids random routes consuming the entire allowance
  without returning a script. No paid fallback is enabled. Availability/rate limits vary.
  A failed editorial or visual check stops the job instead of silently downgrading it.
- Piper runs in a short-lived process, releasing model memory before video encoding.
  Research and archive/image preparation also run in separate processes, which exit
  before narration so search libraries and image buffers do not accumulate in the bot.
  Complete spoken sentences are limited to 12 words/120 characters; freed image and narrator
  buffers are returned to Linux between stages/chunks to protect the free instance.
  A combined 450 MB resident-memory guard stops narration before exhausting the host.
  FFmpeg and ONNX use a single thread. The heavyweight Gradio dashboard was replaced
  by a small FastAPI page to leave memory available on the existing free instance.
- `/health` reports Studio version and whether Telegram polling is running.
- Approved scripts are reused for up to six hours only when the topic, exact source evidence
  and Studio version match. A visual-stage retry does not spend quota rewriting an approved script.
- `STUDIO_CACHE` optionally sets the model and approved-script cache path (default `.studio-cache`).
  The first job downloads approximately 64 MB; the cache can disappear on restart.
- `Smart Freeze` and `/cancel_video` terminate the active narrator/encoder process.
- SQLite reads, writes and cursor consumption are serialized across the Telegram,
  dashboard and rendering threads, including frequent cancellation checks.
- Credentials, request URLs and unlisted download handles must not be logged.

## Validation

Run `python -m pytest -q` after installing `pytest`. Unit/integration tests exercise
evidence matching, source/redirect restrictions, media-rights filtering, current-news
gating, cancellation, caption rendering and private download expiry. A real local edit
has also passed full decoding at 1080 × 1920 with neural speech and archival footage.
Local test success does not replace checking the deployed Telegram workflow.

## Verified implementation references

- Piper API: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
- Narrator model card: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/john/medium/MODEL_CARD
- Wikimedia media API: https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API
- NASA media rules: https://www.nasa.gov/nasa-brand-center/images-and-media/
- FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- Free model routing: https://github.com/OpenRouterTeam/docs/blob/main/guides/routing/routers/free-router.mdx

Piper is distributed under GPL-3.0-or-later. This project uses the installed package;
its license is separate from the voice dataset and individual footage licenses.



## YouTube connection and automatic public uploads

Juan selected automatic public publishing on November 21, 2026. The code supports
that mode, but it remains off until enabled and Google authorization is complete.
No rejected draft qualifies. `/yt_upload` now uses the latest checked Studio output,
its actual title and its complete source/media credits, never an arbitrary inbox file.
`/yt_auto on` enables public uploads after future successful Studio jobs;
`/yt_auto off` disables them. `YT_AUTO_PUBLISH=1` makes the preference survive restarts.
`/video_latest` only resends Telegram delivery and does not upload again.

Configure the existing Google project with a **Web application** OAuth client and
this exact authorized redirect URI:

```
https://smart-prime.onrender.com/youtube/callback
```

Keep its client ID and secret in Render's `YT_CLIENT_ID` and `YT_CLIENT_SECRET`.
Enable YouTube Data API v3 and YouTube Analytics API for the requested scopes.
Use `/connect_youtube`, select FIRST STAGE in Google, and grant the displayed
permissions. The callback exchanges the code server-side using PKCE and a
single-use, ten-minute state. Codes and credentials are not accepted/exported
through Telegram. `/yt_status` verifies the actual channel, upload permissions,
automatic-publishing mode and persistence. The expected channel is
`@FirstStageOfficial`; `YT_CHANNEL_ID` can pin its verified channel ID. A wrong
channel stops connection/upload.

**Persistence still needs configuration after consent:** on the free Render
instance, SQLite does not survive redeployment. The authorized-user credential
JSON can be downloaded once from the success page (ten-minute secure HttpOnly browser cookie, never a credential-bearing URL) and must be saved as the Render secret `YT_TOKEN` or a Render secret file named
`YT_TOKEN.json` (default path `/etc/secrets/YT_TOKEN.json`). Never commit this JSON
or send it through chat. `/yt_status` reports whether the current refresh token
matches persistent storage; a connection is not considered durable merely
because consent succeeded. Google Testing-mode refresh tokens may expire after
seven days; check the project's audience/production configuration in Google.

Uploads use resumable chunks, retain complete credits, honor Freeze/cancellation,
and record the video hash before the first upload request. An uncertain result
stops without blind retries to prevent duplicate publications. The returned
visibility and processing/upload status are reported rather than assuming the
video is already publicly playable. A YouTube failure does not discard the
finished Telegram video. These paths are tested with mocked Google responses;
a real channel authorization and upload must still be verified.
