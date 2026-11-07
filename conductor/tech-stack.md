# Technology Stack

Echo FM utilizes a hybrid local/cloud stack designed for high availability and zero-token waste.

## Core Language & Runtime
- **Python:** Primary language for orchestration, fetching, and media processing.
- **Node.js (npm):** Used for task orchestration and pipeline management (via `package.json`).

## Artificial Intelligence & Synthesis
- **Google Gemini:** 3.5/3.1 series used for stable, high-quota script generation.
- **Groq:** Primary provider for high-tier models including **DeepSeek R1** (Reasoning), **Llama 3.3 70B**, and **Llama 4 Scout** (High Speed).
- **edge-tts:** Free TTS provider used across development, CI/CD, and production.

## Data Persistence & Infrastructure
- **Supabase:** Cloud database and storage for production episodes and artifacts.
- **Gate Checks:** Automated regression testing comparing new runs against the latest baseline episode.
- **SQLite:** Local database for development, allowing for "air-gapped" testing. The UI provides unified access to both Supabase and SQLite via dedicated `serve:supabase` and `serve:sqlite` scripts.
- **dotenv:** Management of environment profiles (local, production, etc.).

## Media & Distribution
- **FFmpeg:** The "engine" for audio concatenation and MP4 video compilation. Optimized with `-preset veryfast` for high-speed production.
- **Pydub:** High-level audio manipulation for multi-track mixing and acoustic effects.
- **Pillow (PIL):** Procedural generation of broadcast cover art and visuals.
- **YouTube Data API:** Automated publishing pipeline for the final broadcasts.

## Concurrency & Performance
- **Python Threading:** `ThreadPoolExecutor` utilized for parallelized TTS generation (5 workers) to maximize pipeline velocity.
