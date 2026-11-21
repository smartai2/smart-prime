# Smart Prime — FIRST STAGE Studio 4.1

Juan can ask in Telegram:

```
/video How Starship's two stages work
Make a Short about why rockets use stages
/video_status
/cancel_video
/video_latest
```

The bot makes a vertical 1080 × 1920 Short, normally 40–85 seconds. One job runs at a time.
It reports progress and stops when Juan says **Smart Freeze**. It does not publish the new
Studio videos to YouTube automatically. The older inbox and YouTube commands remain separate.

## Production workflow

1. Read source pages; search snippets are discovery hints, not script evidence. Prefer
   primary sources, label reported material, and use encyclopedias only for background.
   Current-news requests need recent, dated reporting. This restriction can stop a job.
2. Write an original 80–170 word explanation that answers the requested mechanism, in complete short sentences, validate exact
   supporting quotations, preserve planned-capability wording, and obtain an editorial
   check in a separate model call. This is an AI check, not a guarantee
   of factual correctness. Review the included script and sources before publication.
   Reviewers can propose minimal corrections, which must pass exact-evidence validation
   and a new editorial call. This avoids rewriting accepted passages and saves free quota.
3. Find licensed motion footage and photography on Wikimedia Commons or NASA. Reject
   unknown rights, NC/SA licenses, animations masquerading as footage, unrelated bands
   called Starship, and pre-edited comparisons. Require usable resolution and real video.
4. Search the scene actions as well as the broad subject. Sample early close views and later
   moments from distinct launches/actions. Screen photographs/footage separately
   from illustrations, then select one shot per sentence. Enforce at least 60% motion
   coverage by narration words, four distinct shots, and no consecutive repeated shot.
   All archive visuals are labelled; they are never presented as footage of a new event.
5. Synthesize a consistent US English neural voice locally using Piper John medium.
   The model card lists public-domain LibriVox source recordings. Model download is
   SHA-256 checked. No robotic eSpeak fallback is used by Studio.
6. Edit the shots, add a gentle push-in to photographs, burn in phrase-timed captions,
   add attribution and FIRST STAGE branding, and normalize speech in two passes.
7. Check H.264/AAC playback, full-file decoding, resolution, timeline, caption order,
   duration, integrated loudness and true peak before delivery.

## Delivery

The private owner chat receives temporary, unlisted links first. Telegram then attempts
to fetch the MP4 by URL for an inline video, avoiding the old multipart-upload timeout.
The ZIP includes MP4, SRT, thumbnail, upload description with media credits, script,
source evidence, edit decisions and technical report. Include the supplied attribution
when publishing. The source footage's audio is discarded.

Downloads are available **up to 24 hours on the current Render instance**. Free Render
storage is ephemeral: a restart or redeploy can remove them earlier. Save the package
when it arrives. `/video_latest` retries delivery of the saved video and links without using AI quota; it is not permanent storage.
No additional paid service or storage subscription is enabled by this release.

## Runtime

- Python entrypoint: `python app.py`; dependencies: `pip install -r requirements.txt`.
- Existing `SMART_TOKEN`, `BRAIN_API_KEY`, owner and YouTube settings remain in use.
- Studio uses verified free multimodal routes (Nemotron 3.5 Super VL and Particle 1) that allow reasoning to be disabled, with a 95-second total
  request deadline. Requests are paced; a non-daily rate limit imposes a bounded
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


