<!-- Developer by : Mr_Manas_Op -->
# Telegram Music Bot

**Developer by : Mr_Manas_Op**

A modular Telegram bot that plays music and video in group voice chats, built with
Pyrogram + py-tgcalls, SQLite and ffmpeg.

> **Status:** the code has been syntax-checked and its pure helper functions were unit-checked.
> It has **not** been run against real Telegram servers, and **no load or performance testing
> has been done**. Treat it as a complete, reviewed starting point and test it in your own
> group before relying on it. All numbers in the server report below are estimates.

---

## 1. How it works

```
Telegram group  ──commands──▶  Bot account (Pyrogram, bot token)
                                    │
                                    ▼
                            PlayerManager (queues, loop, volume)
                                    │
                                    ▼
                  Assistant account (Pyrogram user session) + py-tgcalls + ffmpeg
                                    │
                                    ▼
                          Streams audio/video into the voice chat
```

Telegram bots cannot join voice chats, so a **dedicated assistant user account** does the
streaming. The bot account handles commands and buttons.

### Music sources (all legitimate, no circumvention)

| Source | How to use | Notes |
|---|---|---|
| Jamendo catalogue | `/play song name`, `/search` | Creative Commons music. Needs a free `JAMENDO_CLIENT_ID`. |
| Direct links | `/play https://…/file.mp3`, `/vplay https://…/clip.mp4` | Must be a direct link to an audio/video file. Streaming-site pages (YouTube etc.) are **not** supported. |
| Telegram files | Reply to an audio/video/voice/file with `/play` or `/vplay` | You are responsible for having the rights to the content you play. |

Lyrics come from the public lyrics.ovh service.

## 2. Commands

| Group | Commands |
|---|---|
| Playback | `/play` `/vplay` `/pause` `/resume` `/skip` `/end` `/stop` `/replay` `/seek` `/volume` `/mute` `/unmute` |
| Queue | `/queue` `/shuffle` `/loop` `/remove` `/skipto` `/clear` `/song` `/current` |
| Search | `/search` `/lyrics` `/playlist` `/save` `/myplaylist` |
| Settings | `/settings` `/admincache` `/reload` |
| Basic | `/start` `/help` `/ping` `/about` |

Behaviour notes:

* `/stop` stops the current track but keeps the queue (`/resume` continues with the next track).
  `/end` stops and clears everything. `/clear` removes only upcoming tracks.
* `/loop` with no argument cycles *off → track → queue*. `/loop off|track|queue` sets it directly.
* `/seek 90` or `/seek 1:30` restarts the stream from that position.
* `/volume` accepts 1–200. `/mute` and `/unmute` control the stream without changing the volume.
* `/lyrics artist - title`, or just `/lyrics` while a track with an artist is playing.
* Playlists: `/playlist create|view|play|remove|delete`, `/save [name]` (default "Favorites").

**Permissions.** Anyone can queue music and view information. Playback controls (pause, skip,
stop, seek, volume, loop, remove, …) require a group admin; the person who requested the
current track may also `/skip` it. Admins can switch controls to "everyone" in `/settings`.
Bot owners listed in `OWNER_IDS` can always control playback.

## 3. Installation

### Prerequisites

1. **Python 3.10–3.12** (3.11 recommended) and **ffmpeg** (with `ffprobe`) on the server.
2. **API ID / API hash** from <https://my.telegram.org> → *API development tools*.
3. **Bot token** from [@BotFather](https://t.me/BotFather).
4. A **dedicated Telegram user account** to act as the assistant (do not use your personal account).
5. *(Optional but recommended)* a free Jamendo client id from <https://devportal.jamendo.com>.

### Steps

```bash
git clone <your-repo-url> telegram-music-bot
cd telegram-music-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install -y ffmpeg            # Debian/Ubuntu

cp .env.example .env                  # then edit .env
python generate_session.py            # log in as the assistant account, copy the string to .env
python main.py
```

## 4. Configuration

All settings are environment variables (see `.env.example`).

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `API_ID`, `API_HASH` | yes | – | Telegram API credentials |
| `BOT_TOKEN` | yes | – | Bot token from BotFather |
| `SESSION_STRING` | yes | – | Assistant account session |
| `OWNER_IDS` | no | – | Comma-separated user IDs that get error notifications and can always control playback |
| `JAMENDO_CLIENT_ID` | no | – | Enables search and plain-text `/play` |
| `DATA_DIR` / `DATABASE_PATH` / `DOWNLOAD_DIR` / `LOG_DIR` | no | `data`, `data/music.db`, `data/downloads`, `logs` | Storage locations |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `MAX_QUEUE` | no | `50` | Max queued tracks per group |
| `MAX_DURATION_MINUTES` | no | `180` | Longest track accepted |
| `MAX_FILE_MB` | no | `100` | Largest Telegram upload accepted |
| `RATE_LIMIT_COUNT` / `RATE_LIMIT_WINDOW` | no | `6` / `10` | Max commands per user per window (seconds) |
| `ALLOW_DIRECT_URLS` | no | `true` | Disable to forbid link playback |

### Setting up a group

1. Add the bot to the group and promote it to admin with **Invite users** (so it can add the assistant) and **Delete messages** (so it can tidy old player messages).
2. Start a **voice chat** in the group (the bot cannot create one).
3. Send `/play <song>`. The assistant account joins automatically; if that fails, add it to the group manually.

## 5. Deployment

### Docker (recommended)

```bash
cp .env.example .env     # fill in the values; SESSION_STRING must already be generated
docker compose up -d --build
docker compose logs -f
```

State (database, sessions) and logs live in named volumes `musicbot_data` and `musicbot_logs`.

### systemd (without Docker)

```ini
# /etc/systemd/system/musicbot.service
[Unit]
Description=Telegram Music Bot
After=network-online.target

[Service]
User=musicbot
WorkingDirectory=/opt/telegram-music-bot
ExecStart=/opt/telegram-music-bot/.venv/bin/python main.py
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

### Security checklist

* Keep `.env` out of git (already in `.gitignore` / `.dockerignore`) and `chmod 600 .env`.
* The session string is full access to the assistant account. Use a dedicated account.
* Run as a non-root user (the Dockerfile does).
* Direct-link playback performs DNS/IP checks to block private addresses, but redirects are
  followed by ffmpeg. If the host can reach sensitive internal services, set `ALLOW_DIRECT_URLS=false`
  or isolate the container's network.
* Input is validated (timestamps, positions, names, URL scheme, file size, duration), commands are
  rate limited per user, and admin-only actions are checked against Telegram's admin list
  (cached 10 minutes; `/admincache` refreshes it).

## 6. Project layout

```
main.py                 entry point
config.py               environment configuration
generate_session.py     one-off helper to create the assistant session string
database/db.py          async SQLite (settings, playlists, stats)
services/               clients, player engine, media, sources, jamendo, lyrics
plugins/                one module per command group + voice-chat events
helpers/                permissions, decorators, formatting, message builders
keyboards/              inline keyboards
utils/                  logging, rate limiter, URL safety
```

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Configuration error: Missing required environment variable" | Fill in `.env` (see section 4). |
| "There is no active voice chat" | Start a voice chat in the group first. |
| "I couldn't add the assistant account automatically" | Add the assistant to the group, or give the bot the *Invite users* admin right. |
| "Media tools are not installed" | Install ffmpeg (`ffprobe` must be on `PATH`). |
| Commands do nothing | Check the bot is in the group, privacy mode is fine for commands, and see `logs/bot.log`. |
| "Only group admins can use this command" | Ask an admin, run `/admincache` after promoting someone, or set controls to *Everyone* in `/settings`. |
| Search says it is not configured | Set `JAMENDO_CLIENT_ID`. |
| `AUTH_KEY_DUPLICATED` / session errors | A session string can only be used by one running instance; regenerate it. |
| `/seek` restarts from the beginning or errors | Seeking passes `-ss` to ffmpeg via py-tgcalls (`ffmpeg_parameters`); verify against your installed py-tgcalls version. |
| Playback stops after upgrading py-tgcalls | Its API changes between releases; keep the pinned range in `requirements.txt`. |

Known limitations: the queue lives in memory (it is lost on restart; playlists and settings persist);
one assistant account serves all groups; video is limited to 480p.

---

## 8. Server requirements report

Labels used below: **[Source]** derived from reading this code and its dependencies,
**[Estimate]** engineering judgement, **[Assumption]** something I assumed,
**[Tested]** measured results. **There are no [Tested] results: no load, performance or
real-Telegram testing was performed.** Validate every estimate on your own hardware.

### 8.1 What the code does that drives resource use

* **[Source]** One Python process runs two Pyrogram clients, py-tgcalls (native `ntgcalls` library) and an asyncio event loop. Command handling is I/O bound and light.
* **[Source]** Each active voice chat decodes media with ffmpeg and encodes it for WebRTC. This is the dominant CPU cost and scales with the number of *simultaneous streams*, not with the number of users.
* **[Source]** Audio-only playback ignores video (`video_flags=IGNORE`); `/vplay` decodes and re-encodes video at up to 480p, which costs far more CPU.
* **[Source]** Telegram uploads are downloaded to disk (limited by `MAX_FILE_MB`, 2 at a time) and deleted when the track leaves the queue; Jamendo and direct links are streamed, not stored.
* **[Source]** SQLite (WAL mode) stores settings, playlists and counters; settings are cached to avoid repeated queries.
* **[Source]** No GPU code, no hardware encoding.

### 8.2 Requirements

| # | Item | Minimum | Recommended | Basis |
|---|---|---|---|---|
| 1 | CPU | 1 vCPU | 2–4 vCPU | [Estimate] audio streams are light; video needs headroom |
| 2 | Recommended cores by load | 2 vCPU ≈ up to ~10–20 audio chats; 4 vCPU ≈ ~30–50 audio chats; add ~½–1 vCPU per concurrent video chat | | [Estimate] **untested** |
| 3 | RAM | 1 GB (tight) | 2 GB (up to ~20 chats), 4 GB (~50 chats) | [Estimate] ~150–250 MB base process + ~30–60 MB per active stream |
| 4 | GPU | Not needed | Not needed | [Source] software ffmpeg only |
| 5 | Storage | 10 GB | 25–40 GB SSD | [Estimate] OS + Python + ffmpeg ≈ 3–5 GB; logs ≤ 20 MB; downloads bounded by queue size × `MAX_FILE_MB` (worst case can be large, so lower `MAX_FILE_MB` on small disks) |
| 6 | Bandwidth | ~100–150 MB/hour per audio chat (in + out) | 1 TB+/month transfer plan | [Estimate] roughly 0.2–0.3 Mbps down + 0.05–0.1 Mbps up per audio stream; video 480p roughly 1–2 Mbps each way, ≈ 0.5–1 GB/hour |
| 7 | Database | SQLite (included) | SQLite until thousands of active groups | [Source] single-writer file DB; moving to PostgreSQL would need code changes (not implemented) |
| 8 | OS | Ubuntu 22.04/24.04 LTS or Debian 12 (x86-64) | same, with Docker | [Assumption] py-tgcalls ships Linux x86-64/arm64 wheels |

### 8.3 Capacity estimates

* **Concurrent users [Estimate]:** command traffic is small; a single instance can handle hundreds of people active at once. The real limit is Telegram's per-bot/per-account flood limits, not CPU.
* **Concurrent voice chats [Estimate, untested]:** ~10–20 audio on 2 vCPU/2 GB; ~30–50 on 4 vCPU/4 GB; video: ~2–4 on 2 vCPU. A single assistant account also has Telegram's own limit on how many chats it can join; check current limits before serving hundreds of groups.

### 8.4 VPS recommendation and cost

| Scale | Spec | Approx. monthly cost [Estimate] |
|---|---|---|
| Hobby / a few groups | 1–2 vCPU, 2 GB RAM, 25 GB SSD | ≈ $5–7 (₹420–600) |
| Small community | 2–4 vCPU, 4 GB RAM, 40–80 GB SSD | ≈ $10–18 (₹850–1,550) |
| Heavier / some video | 4–8 vCPU, 8–16 GB RAM, 80+ GB SSD | ≈ $25–50 (₹2,100–4,300) |

[Assumption] Prices vary by provider, region and promotions; INR figures use roughly ₹85–87 per USD.
Check live pricing before buying. Prefer a provider with unmetered or ≥1 TB bandwidth.

### 8.5 External services

Telegram (API credentials, bot token, assistant account), ffmpeg on the host, Jamendo API
(optional, free key), lyrics.ovh (public, no key, availability not guaranteed).

### 8.6 Scaling recommendations [Estimate]

1. Scale vertically first (more vCPU), because ffmpeg work dominates.
2. Lower `MAX_QUEUE` and `MAX_FILE_MB`, and keep video optional, on small servers.
3. To go beyond one assistant account or one machine you need multiple assistants/processes and a shared state store — this is **not implemented** and would require code changes.
4. Monitor with `docker stats` / `htop` and `logs/bot.log` and measure real usage before sizing up.

## 9. Licensing and responsible use

You are responsible for the content you stream. Use music you have the right to play (for example
Creative Commons tracks from Jamendo, your own files, or licensed streams). This project does not
download from or circumvent protections on streaming platforms.

---

Developer by : Mr_Manas_Op
