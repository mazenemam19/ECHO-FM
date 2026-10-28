# Echo FM 🎙️ — The News, Reimagined

**Echo FM** is a professional-grade, fully autonomous satirical radio station. It is engineered as a high-fidelity serverless media pipeline that transforms global news into structured, 13-segment audio broadcasts using advanced LLM reasoning, a multi-tier TTS priority chain, and automated video production.

## 🎨 Design & Identity
The station utilizes a **Structured Minimalism** aesthetic, designed to deliver intellectually dense satire with a clean, modern technical presence.

- **Design Language:** Deep Slate (`#1E293B`) and Smooth Emerald (`#10B981`).
- **Typography:** Space Grotesk (Display) and Inter (Body).
- **The Crew (Personas):** 
    - **ALISTAIR:** The Anchor. Sophisticated, currently navigating a deep existential crisis.
    - **VICTORIA:** The Reporter. Over-earnest, reporting live from the field.
    - **RONALD:** The Commentator. Intense, self-aware, and Silicon-Valley cynical.
    - **CASPER:** The Weatherbot. Flat, clinical, and ominous. No jokes.
    - **MARCUS:** The Philosopher. Grave, sincere, and the show's moral conscience.

## 🏗️ Architecture: 100% Serverless
Echo FM operates without a traditional persistent backend. It is an **event-driven** system where GitHub Actions serves as the CPU, Supabase as the Memory, and Netlify as the Display.

- **Orchestration:** GitHub Actions triggers the Python orchestrator on a 6-hour CRON schedule.
- **Telemetry Loop:** Every run begins by fetching the latest engagement metrics (Plays, Likes) from the YouTube Data API for all previous episodes. This ensures station-wide stats are updated by the next scheduled run.
- **Concurrency & Safety:** The pipeline utilizes top-level concurrency groups to cancel overlapping runs and enforces a **14.8-minute (888s)** absolute duration gate to stay within the 15-minute high-fidelity threshold.
- **Stateless Execution:** Every broadcast is a discrete, atomic transaction. No local state is preserved between production runs in the cloud.
- **Webhook Synchronization:** Upon a successful broadcast (Step 11), the pipeline triggers a **Netlify Build Hook**. This initiates a static-site rebuild, during which the frontend fetches the latest metadata from Supabase and updates the dashboard instantly.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- FFmpeg in system PATH (`ffmpeg` and `ffprobe`)
- Node.js 18+ (for proxy scripts and Husky hooks)

### Installation
```bash
git clone https://github.com/mazenemam19/AI-Radio.git
cd AI-Radio
pip install -r requirements.txt
npm install
```

### Development Quality Gates
The project uses **Husky** and **lint-staged** to ensure code quality:
- **Pre-commit:** Automatically runs `ruff` (linter + formatter) and the full `pytest` suite on every commit.

### Configuration
Copy `.env.example` to `.env` and fill the keys.

**Mandatory Keys (Core Operation):**
- `GEMINI_API_KEY`: Primary reasoning and fallback script generation.
- `GROQ_API_KEY`: High-speed Llama-4 reasoning for complex satire.
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`: Required for production persistence.
- `YOUTUBE_CLIENT_ID` / `SECRET` / `REFRESH_TOKEN`: Automated publishing.
- `NETLIFY_BUILD_HOOK`: Webhook URL for dashboard deployment.
- `VERCEL_DEPLOY_HOOK`: Webhook URL for dashboard deployment.

**Optional Keys (High-Fidelity TTS):**
- `CARTESIA_API_KEY` (Tier 1) / `KOKORO_API_KEY` (Tier 2).

## 🚀 Scripts Reference (`package.json`)

- `npm start`: Runs the local pipeline (SQLite + edge-tts).
- `npm run lint`: Runs `ruff check .` via the Python proxy.
- `npm run dry-run`: Production-style run with mocked AI responses.
- `npm run prod`: Full production broadcast (Supabase + Premium TTS + YouTube).
- `npm run verify`: Health check for APIs, DB, and local binaries.
- `npm test`: Runs the automated test suite (pytest).
- `npm run sync-config`: Manually force a metadata synchronization.

## 🚀 Detailed Pipeline Steps

### Step 1 — News Ingestion (`news_fetcher.py`)
Fetches up to 5 items from each RSS feed and 10 from HackerNews.
- **Tag-Aware Deduplication:** Items are blocked if they match an exact headline in history OR if they contain keywords from the **topic_tags** of the last 10 episodes. This prevents "zombie loops" where topics like 'NASA' or 'Ebola' repeat daily.

### Step 2b — AI Script Generation (`ai_client.py`)
Constructs a complex prompt containing the 20-item news feed and station memory. If the LLM returns truncated JSON, a recursive **JSON Healer** salvages completed segments.
- **Expansion Layer:** If segments are too short (<100 words), the system calls a dedicated expansion loop to lengthen them on the final attempt.
- **Validation:** Enforces a 100-word physical floor and verified `word_count` metadata (while asking for 130-160 words in the prompt as a soft anchor).

### Step 3 — TTS Synthesis (`tts_generator.py`)
- **Parallel Generation:** Narrates all 13 segments concurrently using a `ThreadPoolExecutor` (5 workers), reducing synthesis time from ~5 minutes to ~60 seconds.
- **Unified Master Engine:** Attempts the entire episode with one engine (Cartesia → Kokoro → Edge) to ensure vocal consistency. A **Quality Guard** rejects any audio with a WPM > 300.

### Step 4 — Audio Assembly & Mastering
Concatenates segments using Pydub and applies a **Loudness Normalization Pass** (Target: -14 LUFS) for professional streaming consistency.

### Step 5-7 — Visuals & Packaging
- **FFmpeg Optimization:** Compiles a pixel-perfect cover PNG and audio into an MP4 using the `veryfast` preset to accelerate compilation by ~60%.
- **Precision Clipping:** Uses the `-t` flag for exact millisecond alignment between audio and video tracks.

## 🔊 Sound Effects Reference

| SFX Key | Usage |
| :--- | :--- |
| `INTRO_THEME` | Show opening music |
| `OUTRO_THEME` | Show closing music |
| `APPLAUSE_OPEN` | Opening audience applause |
| `LAUGH_TRACK` | Audience laughter after a joke |
| `BAD_PUN_STING` | Trombone wah-wah after a terrible pun |
| `TRANSITION_STING`| Short sting between segments |
| `STREET_AMBIENT` | Background city noise for field reports |
| `SILENCE` | 2 seconds of dead air for gravity |

## 💾 Database Schema (`memory_log`)

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL | Primary key |
| `headline` | TEXT | AI-generated episode title |
| `original_headline`| TEXT | Headline of the primary news source |
| `audio_script` | JSON | Full dialogue array |
| `writer_model` | TEXT | LLM used for generation |
| `narrator_model` | TEXT | TTS engine used |
| `broadcast_duration`| INT | Total length in seconds |

## ⚖️ Stability & Quality Rules
1. **100-Word Floor:** Every segment must exceed 100 words (the prompt asks for 130-160 to ensure quality).
2. **Word Count Anchoring:** Every segment JSON must include a `word_count` key that helps anchor the model's focus on length.
3. **Best-Effort Expansion:** If a model under-delivers on length (<100 words), the system triggers a recursive expansion pass on the final attempt.
4. **Clash Protocol:** Characters are explicitly prompted to challenge each other's interpretations, breaking the "agreement loop" and ensuring adversarial social dynamics.
5. **Semantic Refresh:** Explicit ban on overused AI metaphors ("recursive loop", "deck chairs", "sinking ship", "void", "static").
6. **20 News Items:** Production runs ingest 20 news items to provide sufficient creative fuel.
7. **13 Segments:** Fixed show arc (Intro -> Main(9) -> Weatherbot -> Main -> Deep Dive -> Philosopher).

---
For a deep dive into the technical implementation, see [ARCHITECTURE.md](./ARCHITECTURE.md).
