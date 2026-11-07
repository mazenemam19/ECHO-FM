# System Architecture — Echo FM

Echo FM is an **autonomous, serverless media pipeline**. It is engineered to operate with zero persistent server overhead, utilizing discrete cloud services and high-tier AI reasoning to produce professional satirical radio broadcasts on a periodic schedule.

## 🛰️ Detailed Data Flow (High-Fidelity Pipeline)

Echo FM utilizes a multi-phase, state-aware production loop. Every stage is designed for maximum resilience and data integrity.

```mermaid
flowchart TD
    %% Trigger
    GHA(("GitHub Actions CRON")) --> S1

    %% Phase 1
    subgraph P1 ["Phase 1: Persistence & Engagement"]
        S1["Step 1: Initialize DB Client<br/>(db_client.py)"] --> S0
        S0["Step 0: Engagement Sync<br/>(publisher.py)"]
        YT_DATA(["YouTube Data API v3"]) <--> S0
        S0 -.-> DB[(SQLite / Supabase)]
    end

    %% Phase 2
    subgraph P2 ["Phase 2: Intelligence & Synthesis"]
        S0 --> S2["Step 2: Fetch News & Memory<br/>(news_fetcher.py)"]
        S2 --> S2b["Step 2b: AI Script Generation<br/>(ai_client.py)"]
        
        RSS(["RSS: BBC, Guardian, etc."]) --> S2
        DB --> S2
        
        subgraph AI ["Smart Router Logic"]
            LLM_Q{"Model Queue"} -->|SDK Dispatch| LLM_CALL["Gemini / Groq SDK"]
            LLM_CALL --> JSON_HEAL{"JSON Healer"}
            JSON_HEAL -->|Success| EXP["Expansion Layer<br/>(Optional)"]
            EXP --> VAL{"Quality Validator"}
            JSON_HEAL -->|Fail| LLM_Q
            VAL -->|Fail| LLM_Q
        end
        S2b --> AI
    end

    %% Phase 3
    subgraph P3 ["Phase 3: Production Studio"]
        AI --> S3["Step 3: Unified Master TTS<br/>(tts_generator.py)"]
        
        TTS(["Edge-TTS Standard<br/>(free, retried)"])
        S3 --> TTS
        
        TTS --> S4["Step 4: SFX Mixing & LUFS Mastering<br/>(pydub)"]
        SFX_DIR[("sfx/*.mp3")] --> S4
        S4 --> S5["Step 5: Duration & Quality Gate"]
    end

    %% Phase 4
    subgraph P4 ["Phase 4: Visuals & Packaging"]
        S5 --> S6["Step 6: Pixel-Perfect Cover Art<br/>(Pillow)"]
        S6 --> S7["Step 7: MP4 Video Compilation<br/>(FFmpeg)"]
    end

    %% Phase 5
    subgraph P5 ["Phase 5: Global Distribution"]
        S7 --> S8["Step 8: Automated YT Publication"]
        S8 --> S9["Step 9: Database Persistence"]
        S9 --> S10["Step 10: Static Config Sync"]
        
        S8 --> YT_SVC(["YouTube Studio"])
        S9 -.-> DB
    end

    %% Phase 6
    subgraph P6 ["Phase 6: Deployment & UI"]
        S10 --> CLEAN["Artifact Cleanup"]
        CLEAN --> S11["Step 11: Self-Assessment"]
        S11 -->|SUCCESS| HOOK(["Netlify Build Hook"])
        HOOK --> WEB["Station Dashboard Rebuild"]
        
        DB -.->|Metadata| CONFIG[/"config.json"/]
        CONFIG -.->|Load time| WEB
    end
```

## 🏗️ Shape Legend

| Shape | Mermaid Syntax | Meaning |
| :--- | :--- | :--- |
| Cylinder | `[(text)]` | Persistent data store |
| Diamond | `{text}` | Decision / Gate Check |
| Stadium | `(["text"])` | External API or Service |
| Parallelogram| `[/"text"/]` | Data artifact / File on disk |
| Rectangle | `[text]` | General processing node |

## 🧠 Technical Design Principles

### 1. Unified Master Engine (Narration Consistency)
Echo FM maintains vocal consistency by selecting **Edge-TTS** as the single master engine for each broadcast. Transient synthesis failures are retried with exponential backoff before the segment is treated as failed.

### 2. Resilience & Retry Logic
The system is designed to "fail forward" through multiple layers:
- **AI Synthesis Retry:** If the primary LLM fails validation, the system retries once more. If both fail, it moves to the next model in the prioritized **Smart Router** queue.
- **Recursive Expansion Layer:** If a model returns high-quality content but fails the 100-word floor on the final attempt, the system triggers a targeted expansion pass using the same model to lengthen the segment while preserving tone.
- **JSON Healer & Anchoring:** A custom brace-walking algorithm repairs truncated JSON. Every segment includes a `word_count` metadata key that the model must self-report, anchoring its attention on length (aiming for 130-160 words) while validating against a 100-word stable floor.
- **Edge-TTS Retry:** Each Edge-TTS request is retried with exponential backoff before the pipeline reports a failure.

### 3. Audio Engineering (The Mixer)
The `tts_generator.py` and `main.py` collaborate to produce radio-quality audio:
- **Parallel TTS Generation:** The station uses a `ThreadPoolExecutor` (5 workers) to narrate all 13 segments concurrently. This reduces the Studio Phase duration from ~5 minutes to ~60 seconds.
- **SFX Priority:** Scripts define `sfx_pre` and `sfx_post` (stings, applause, laugh tracks) which are mixed with precision timing.
- **Atmospheric Looping:** Field reports automatically trigger a `-22dB STREET_AMBIENT` loop mixed behind the narrator.
- **Mastering:** The final assembly undergoes a **Loudness Normalization Pass** (Target: -14 LUFS) to ensure professional streaming volume consistency.
- **Duration Gate:** All broadcasts are capped at **14.8 minutes (888s)** to stay within the 15-minute high-fidelity threshold. FFmpeg uses the `-t` flag for exact millisecond clipping between audio and video, and the `-preset veryfast` flag to accelerate compilation by ~60%.

### 4. Identity & State Awareness
To prevent "Identity Mirroring" (where a character addresses others by their own name), the station uses:
- **Spatial Grounding:** Personas are assigned physical locations (Studio, Field, Library) to anchor their conversational distance.
- **Gender Anchoring:** Explicit (Male/Female) markers in the prompt provide a logical mismatch check for the AI's attention mechanism.
- **Narrative Memory:** The station persists a detailed `summary` of the full narrative arc of each episode, allowing the AI to maintain continuity across production runs.

## 🌐 Behavioral Divergence (Local vs Production)

The system behavior is strictly controlled by the `--env` flag:

| Feature | Local Development (`--env local`) | Production Broadcast (`--env production`) |
| :--- | :--- | :--- |
| **Database** | SQLite (`ai_radio_dev.db`) | Supabase Cloud |
| **AI News Context** | Filtered / Cached Headlines | 20+ Real-time Global Headlines |
| **TTS Engine** | Standard `edge-tts` (Free) | Standard `edge-tts` (Free) |
| **Cover Art** | FFmpeg simple color | Pixel-Perfect Pillow (PIL) Overlays |
| **Publishing** | `output/` folder only | YouTube Data API v3 |
| **UI Updates** | Local `config.json` sync | Netlify Webhook Rebuild |

## 🔗 Serverless UI Synchronization
The app is 100% serverless. The UI is a static frontend refreshed via webhooks:
1. **Telemetry Loop:** Every production run starts with **Step 0: YouTube Engagement Sync**. The system fetches real-time metrics for all previous broadcasts, ensuring the dashboard stats are updated by the start of the next run.
2. **Pipeline Completion:** Once the MP4 is uploaded and the DB record is saved, `sync_config.py` runs.
3. **Build Hook:** The pipeline sends a POST request to a **Netlify Build Hook**.
4. **Redeploy:** Netlify re-clones the repo, fetches the latest metadata, and redeploys the **Station Control** UI with the new broadcast visible instantly.
