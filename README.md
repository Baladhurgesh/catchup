# CatchUp

CatchUp is a Slack agent that turns long YouTube talks into a short, personalized two-host podcast.

Paste a few lecture or conference URLs, say what you care about, and CatchUp returns a grounded `HOST_A` / `HOST_B` recap as an MP3 in the Slack thread. It also uploads the audio to Google Drive and writes timestamped episode notes in Notion.

Technical talks are long. A three-hour conference recap is not useful when you already know the basics and only care about one slice — CUDA kernels, cold-email targeting, local LLM deployment, or whatever you type in the focus box.

## Two-minute demo

[Watch the two-minute demo](YOUR_LOOM_OR_YOUTUBE_URL)

The recording should show `/catchup` from the Slack modal through progress updates, the MP3 in the thread, **Listen** on Drive, and **Open Notes** in Notion.

## External apps

| App | Role |
| --- | --- |
| [Slack](https://api.slack.com/) | Primary UI. Socket Mode slash command `/catchup`, modal, progress, MP3 upload, Listen / Open Notes / Show Sources buttons |
| [YouTube Data API v3](https://developers.google.com/youtube/v3) | Official video metadata (`videos.list`) |
| [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) | Public captions with timestamps (not the official Captions API) |
| [OpenAI](https://platform.openai.com/) | Chunk analysis, insight synthesis, grounded script, optional TTS |
| [Podcastfy](https://github.com/souzatharsis/podcastfy) | Two-host script → MP3. CatchUp converts `HOST_A` / `HOST_B` to `<Person1>` / `<Person2>` |
| [Google Drive](https://developers.google.com/drive) | Shareable MP3 in a `CatchUp Podcasts` folder |
| [Notion](https://developers.notion.com/) | Episode notes: executive summary, key ideas, clickable `youtube.com/watch?v=ID&t=123s` citations |

Optional fallback TTS: Microsoft Edge (`PODCASTFY_TTS_MODEL=edge`) if you do not want OpenAI audio.

## How it works

```text
Slack /catchup
  → YouTube metadata
  → public transcripts
  → 5–8 minute chunks scored against your focus
  → deduplicated insights + grounded claims
  → HOST_A / HOST_B script
  → Podcastfy MP3
  → Slack thread + Drive + Notion
```

One failed source does not fail the job. If audio, Drive, or Notion fails, CatchUp still delivers whatever it has (script and/or Slack MP3) and posts a warning.

## Setup

Python 3.11–3.13 and `ffmpeg`. Prefer 3.12 if you can; 3.13 needs `audioop-lts` (already in `requirements.txt`).

```bash
brew install ffmpeg
git clone https://github.com/Baladhurgesh/catchup.git
cd catchup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with at least Slack, YouTube, and OpenAI. Drive and Notion are optional.

### 1. Slack

1. Create an app at [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From an app manifest**.
2. Paste [`slack-manifest.yaml`](slack-manifest.yaml). That enables Socket Mode, `/catchup`, the global shortcut, App Home, mentions, and DMs.
3. **Basic Information → App-Level Tokens** → create `xapp-...` with `connections:write`.
4. **OAuth & Permissions** → install the app → copy `xoxb-...`.
5. Invite the bot to a channel.

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Then:

```bash
python app.py
```

In Slack, run `/catchup` (or the CatchUp shortcut, or @mention the bot).

To push manifest changes later, set `SLACK_APP_ID` and an app config token (`xoxe-...`) and run `python scripts/apply_slack_manifest.py`. Reinstall the app after that.

### 2. YouTube Data API

1. In [Google Cloud Console](https://console.cloud.google.com/), enable **YouTube Data API v3**.
2. Create an API key. Restrict it to that API if you can.
3. Set `YOUTUBE_API_KEY`.

CatchUp uses the key only for metadata. Transcripts come from public captions.

### 3. OpenAI

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
PODCASTFY_TTS_MODEL=openai   # or edge
```

### 4. Google Drive (optional)

Personal Gmail cannot upload with a service account (`storageQuotaExceeded`). Use user OAuth.

1. Enable **Google Drive API**.
2. **APIs & Services → Credentials → Create OAuth client ID → Desktop app**.
3. If the consent screen is in Testing, add yourself as a test user.
4. Download the client JSON to `credentials/google-oauth-client.json`.
5. Optionally set `GOOGLE_DRIVE_FOLDER_ID` to a folder you own. Otherwise CatchUp creates `CatchUp Podcasts`.

```bash
GOOGLE_OAUTH_CLIENT_FILE=./credentials/google-oauth-client.json
GOOGLE_OAUTH_TOKEN_FILE=./credentials/google-oauth-token.json
GOOGLE_DRIVE_FOLDER_ID=
```

```bash
python scripts/auth_google_drive.py
```

That opens a browser once and saves a refresh token. Do not commit `credentials/`.

If Drive fails, the MP3 is still attached in Slack.

### 5. Notion (optional)

1. Create an internal integration at [notion.so/my-integrations](https://www.notion.so/my-integrations).
2. Put the secret in `NOTION_TOKEN`.
3. Create a parent page, e.g. `CatchUp`.
4. **Share** that page with the integration (invite the integration, not a person).
5. Copy the page ID from the URL into `NOTION_PARENT_PAGE_ID`.

If Notion fails, the podcast is still delivered.

### CLI smoke test (no Slack)

```bash
python app.py --once \
  --urls "https://www.youtube.com/watch?v=wr6PMD06hP0,https://www.youtube.com/watch?v=7Kh_fpxP1yY" \
  --focus "sales outbound: targeting, personalization, and follow-up" \
  --minutes 10 \
  --expertise intermediate \
  --style conversational
```

Set `DEMO_MODE=true` to cache metadata, transcripts, analysis, and MP3s for a fast re-run. Set `FORCE_REGENERATE=true` to bypass the cache.

## Environment variables

| Variable | Required | Used for |
| --- | --- | --- |
| `SLACK_BOT_TOKEN` | Slack bot | Web API |
| `SLACK_APP_TOKEN` | Slack bot | Socket Mode |
| `YOUTUBE_API_KEY` | Yes | Video metadata |
| `OPENAI_API_KEY` | Yes | Analysis, script, optional TTS |
| `OPENAI_MODEL` | No | Default `gpt-4o` |
| `PODCASTFY_TTS_MODEL` | No | `openai` or `edge` |
| `GOOGLE_OAUTH_CLIENT_FILE` | Drive | Desktop OAuth client JSON |
| `GOOGLE_OAUTH_TOKEN_FILE` | Drive | Saved after `auth_google_drive.py` |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Existing folder; created if omitted |
| `NOTION_TOKEN` | Notion | Internal integration secret |
| `NOTION_PARENT_PAGE_ID` | Notion | Page the integration can write into |
| `DEMO_MODE` | No | Cache expensive steps |
| `FORCE_REGENERATE` | No | Bypass cache |

`.env`, `credentials/`, `data/cache/`, and `*.mp3` are gitignored.

## How we tested reliability

### Unit tests

```bash
pytest
```

The suite covers URL parsing, transcript mapping, Notion note blocks (including timestamp links and executive summary), and the orchestrator. Reliability cases:

- **Partial source failure.** One video has no transcript; the job continues with the rest and records a warning.
- **TTS failure.** Podcastfy raises; CatchUp still writes the grounded script and does not crash.
- **Drive / Notion failure.** Upload or page create raises; the MP3 and script are still produced and Slack still gets a result.

### Live end-to-end

We ran the same sales talks through CLI and Slack:

- [Why You're Getting Zero Replies To Your Cold Emails](https://www.youtube.com/watch?v=wr6PMD06hP0)
- [How To Convert Customers With Cold Emails](https://www.youtube.com/watch?v=7Kh_fpxP1yY)

Checks that passed:

- Public captions retrieved; metadata from YouTube Data API.
- Grounded two-host script with source titles and timestamps (no fabricated numbers).
- MP3 generated with Podcastfy and posted in the Slack thread after `/catchup`.
- Drive upload after user OAuth (service-account upload failed on personal Gmail, as expected).
- Notion child page after sharing the parent page with the integration. Notes include an executive summary, key ideas, and timestamped YouTube links.
- Re-run with `DEMO_MODE=true` hit cache and stayed fast.

### Failure behavior we actually hit

| What broke | What CatchUp did |
| --- | --- |
| Service-account Drive upload on personal Gmail (`storageQuotaExceeded`) | Slack still got the MP3; we switched to user OAuth |
| Notion parent page not shared with the integration | Podcast still delivered; page create succeeded after Share → invite integration |
| Videos without public captions | Skipped with a warning; remaining sources continue |

Known remaining gaps: no Whisper fallback yet, and OpenAI TTS can take several minutes for a long episode.

## Project layout

```text
app.py                 CLI (--once) or Slack Socket Mode bot
agent/                 chunk → analyze → synthesize → script → evaluate
services/              YouTube, transcripts, OpenAI, Podcastfy, Drive, Notion
slack/                 slash command, modal, progress, result buttons
scripts/               Drive OAuth login, Slack manifest apply
slack-manifest.yaml    Socket Mode app definition
tests/                 unit + orchestrator reliability cases
```
