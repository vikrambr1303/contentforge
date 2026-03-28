# ContentForge

ContentForge is a full-stack application for **topic-driven social content**: it generates **quotes** (via a local LLM), **vertical images** (Stable Diffusion or Unsplash), **composites** quote text onto the image, optionally **renders a short video** (Ken Burns–style), and can **post** to configured platforms through a plugin layer.

This README is written for **full-stack developers** who need to run, extend, or debug the system—especially the **async generation pipeline** (API → DB → Celery → files on disk).

---

## Architecture

```mermaid
flowchart LR
  subgraph client [Browser]
    UI[React + Vite]
  end
  subgraph compose [Docker Compose]
    FE[frontend :5173]
    API[backend FastAPI :8000]
    W[Celery worker]
    R[Redis]
    DB[(MySQL 8)]
    OL[Ollama]
  end
  UI --> FE
  FE -->|"/api proxy"| API
  API --> DB
  API -->|enqueue| R
  W --> R
  W --> DB
  W --> OL
  W -->|read/write| DATA[./data volume]
  W -->|optional SD weights| SD[/models mount/]
```

| Service | Role |
|--------|------|
| **frontend** | React SPA; Vite dev server proxies `/api` and `/health` to the backend (in Compose: `http://backend:8000`). |
| **backend** | FastAPI: CRUD, settings, generation triggers, static file routes for content images/videos. **Does not** run heavy image generation. |
| **worker** | Same Python image as backend; runs **Celery** with `concurrency=1` so only one generation task loads SD/RAM at a time. |
| **redis** | Celery broker and result backend. |
| **db** | MySQL: topics, content items, generation jobs, app settings, platform accounts, post history. |
| **ollama** | Local LLM HTTP API (`/api/generate`) for quotes, SD prompt enrichment, stock-photo search phrases, and social captions. |

---

## Tech stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Celery 5, httpx, Pillow, diffusers/torch (in worker), MoviePy (video).
- **Frontend:** React, React Router, Vite, Tailwind-style utility classes (`cf-*`), axios.
- **Infra:** Docker Compose; optional `docker-compose.gpu.yml` for NVIDIA hosts.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `contentforge/` | Backend + worker code (single package: `main.py`, `api/`, `models/`, `tasks/`, `services/`, `alembic/`). |
| `frontend/` | Vite + React UI. |
| `docker-compose.yml` | Default stack (CPU-friendly SD; Ollama CPU). |
| `docker-compose.gpu.yml` | Optional overlay for GPU (Linux + NVIDIA). |
| `data/` | Runtime user data (mounted to `/app/data` in containers): `images/`, `backgrounds/`, `videos/`, `topic_refs/`. |
| `models/sd15/` | Optional host mount for Stable Diffusion 1.5 diffusers weights (read-only in worker). |
| `.env` | Secrets and URLs (not committed). See `.env.example`. |

---

## Quick start (Docker)

1. **Copy environment file**

   ```bash
   cp .env.example .env
   ```

   Edit MySQL passwords, `SECRET_KEY`, and any optional keys (e.g. `UNSPLASH_ACCESS_KEY`).

2. **Stable Diffusion weights (optional, for `background_source = diffusers`)**

   The worker expects a **diffusers** layout at the path stored in **Settings → Diffusers model path** (default in DB is often `/models/stable-diffusion`). The compose file mounts `./models/sd15` at `/models/sd15`; point Settings to that path or adjust the mount.

3. **Pull an Ollama model** (e.g. on first run)

   ```bash
   docker compose exec ollama ollama pull llama3.2
   ```

   Match the model name to **Settings → Ollama model**.

4. **Start stack**

   ```bash
   docker compose up -d --build
   ```

5. **Run migrations** (idempotent)

   ```bash
   docker compose exec backend alembic upgrade head
   ```

6. **Open the app**

   - UI: `http://localhost:5173`
   - API: `http://localhost:8000`
   - Health: `http://localhost:8000/health`

---

## Environment variables

Loaded from `.env` into **backend** and **worker** (`env_file` in Compose). Names map to `contentforge/config.py` (`pydantic-settings`).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLAlchemy URL (MySQL in Docker: host `db`). |
| `SECRET_KEY` | App secret (e.g. credential encryption helpers). |
| `DATA_DIR` | Filesystem root for media; default `/app/data` in containers. |
| `OLLAMA_BASE_URL` | e.g. `http://ollama:11434` in Compose. |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis URLs. |
| `PUBLIC_BASE_URL` | Optional; used when a platform needs to fetch public media URLs. |
| `UNSPLASH_ACCESS_KEY` | Required if **Settings → Background source** is **Unsplash**. |
| `SD_INFERENCE_STEPS_GPU` | More steps on CUDA (worker). |
| `FORCE_SD_CPU` | Force CPU even if GPU visible (debug). |

MySQL variables (`MYSQL_*`) are for the **db** service image; `DATABASE_URL` must align with them.

---

## Database and migrations

- **Alembic** lives under `contentforge/alembic/`. Revisions include initial schema, job progress, topic style reference, generation retry limit, and background source.
- Always run `alembic upgrade head` after pulling migrations.
- Singleton **`app_settings`** row (`id = 1`) holds Ollama model name, diffusers path, default image style, caption CTA, retry limit, and **`background_source`** (`diffusers` | `unsplash`).

---

## Generation pipeline (deep dive)

Generation is **asynchronous**: the API creates DB rows and enqueues **Celery tasks**. The UI polls **`GET /api/jobs/{id}`** for `status`, `progress_percent`, `stage`, and errors.

### Core entities

- **`ContentItem`** — One piece of content: `quote_text`, `quote_author`, paths under `data_dir` for `background_path`, `image_path` (composed), optional `video_path`, `status` (`draft` | `approved` | `rejected` | `posted`), `generation_model` (Ollama), `image_model` (diffusers path or `"unsplash"`).
- **`GenerationJob`** — Tracks one run: `job_type`, `status` (`queued` → `running` → `done` | `failed`), `progress_percent`, `stage`, `error_message`, links to `topic_id` and `content_item_id`.

### Entry points (API)

| Endpoint | Celery task | `job_type` | What it does |
|----------|-------------|------------|----------------|
| `POST /api/generate` | `run_full_generation` | `full` | Quote → background → composite → optional video. |
| `POST /api/generate/quote` | `run_quote_only` | `quote` | Quote (and mood) only; no image. |
| `POST /api/generate/image` | `run_image_only` | `image` | Image pipeline for an **existing** item that already has `quote_text`. |

Batch generate creates **N** content items and **N** jobs in one request (`count` in body).

### Full generation sequence (`run_full_generation`)

High-level flow:

```mermaid
sequenceDiagram
  participant API as FastAPI
  participant DB as MySQL
  participant Q as Redis/Celery
  participant W as Worker
  participant O as Ollama
  participant SD as SD or Unsplash
  participant FS as data/

  API->>DB: ContentItem + GenerationJob (queued)
  API->>Q: run_full_generation.delay(job_id)
  W->>DB: job running, stages
  W->>O: generate_quote_sync
  W->>DB: save quote, mood
  W->>O: enrich_sd_prompt_sync
  alt background_source diffusers
    W->>SD: generate_background (txt2img or img2img)
  else background_source unsplash
    W->>O: stock_photo_search_query_sync
    W->>SD: Unsplash HTTP + crop JPEG
  end
  W->>FS: backgrounds/{id}_background.jpg
  W->>FS: composite_quote → images/{id}_composed.jpg
  opt include_video
    W->>FS: videos/{id}.mp4
  end
  W->>DB: job done, paths on item
```

**Step-by-step:**

1. **Job lifecycle** — Job marked `running`; `stage` strings update throughout (e.g. “Writing quote”, “Refining image prompt”, “Generating background”, “Compositing text”, “Rendering video”, “Complete”).

2. **Quote** — `llm_service.generate_quote_sync(topic, ollama_model)` calls Ollama with JSON output: quote, author, mood. Stored on `ContentItem`; `generation_model` set to the Ollama model name.

3. **Prompt package** — `_prepare_background_prompts()` calls `enrich_sd_prompt_sync()` so Ollama returns a structured `visual` fragment (and optional `negative_extra`) for **abstract, no-people** backgrounds. If enrichment fails, the worker falls back to `topic.image_style` + mood template (still SD-oriented rules).

4. **Background file** — `_produce_background()` branches on **`app_settings.background_source`**:
   - **`diffusers`** — `image_service.generate_background()`: loads **StableDiffusionPipeline** or **StableDiffusionImg2ImgPipeline** if the topic has a **style reference** (`topic_refs/...` under `data_dir`). Progress callbacks map diffusion steps into `progress_percent` (roughly 26–86% for full job). Output: `backgrounds/{content_id}_background.jpg` (default dimensions 1080×1920 portrait). On failure (missing model, etc.), a **gradient placeholder** may be written (see `image_service`).
   - **`unsplash`** — Requires `UNSPLASH_ACCESS_KEY`. Ollama produces a short **stock search query** (`stock_photo_search_query_sync`). The worker searches Unsplash (portrait), picks a result, triggers download tracking, fetches the image, **cover-crops** to target size, saves the same relative `backgrounds/...` path. `ContentItem.image_model` is set to `"unsplash"`.

5. **Composite** — `image_service.composite_quote()` draws a **center-weighted scrim** and **vertically centered** quote + author text (DejaVu fonts in container), writes `images/{id}_composed.jpg`.

6. **Video (optional)** — If `include_video` is true, `video_service.make_ken_burns_video()` builds `videos/{id}.mp4` from the composed image.

7. **Completion** — Job `status = done`, `progress_percent = 100`, `completed_at` set.

### Quote-only and image-only

- **Quote-only** — Same quote generation; updates item; no SD/Unsplash/composite/video.
- **Image-only** — Assumes `quote_text` exists; uses a placeholder mood (`contemplative`) in code for prompt path; otherwise same background + composite flow as full (no new quote).

### Retries vs worker crashes

- **`generation_retry_limit`** (Settings, 0–10): on **normal Python exceptions** inside the task, the worker can **retry** the same logical job up to `limit + 1` total attempts, with `stage` like “Retry 2/3”.
- **Worker process death** (e.g. **SIGKILL** from OOM during SD) is **not** a clean retry: Celery’s `task_failure` handler (`tasks/celery_app.py`) marks the `GenerationJob` **`failed`** if it was still non-terminal, with a message that often mentions memory. **`task_acks_late`** and **`task_reject_on_worker_lost`** reduce silent loss of tasks; the job row still reflects failure for the UI.

### Posting (separate from generation)

`tasks.post_content.post_to_platform` builds a caption via `generate_caption_sync` (Ollama + topic + quote + CTA), then calls a **platform plugin** with the video or image path. Not part of the “generation pipeline” above but uses the same `data_dir` files.

---

## API surface (overview)

All JSON routers are mounted under **`/api`** (see `main.py`):

| Prefix | Concern |
|--------|---------|
| `/api/topics` | Topics CRUD, optional per-topic style reference image upload. |
| `/api/content` | List/get/patch/delete content; serve binary image/video; batch zip. |
| `/api/generate` | Trigger full / quote / image generation (see above). |
| `/api/jobs` | Job status polling. |
| `/api/settings` | App settings get/patch. |
| `/api/llm` | e.g. list Ollama models for the Settings UI. |
| `/api/platforms`, `/api/accounts`, `/api/post`, `/api/post-history` | Social integrations. |

Unauthenticated in default dev layout; tighten before production.

---

## Local frontend development (without Docker for UI)

If you run `npm run dev` on the host, point the Vite proxy at a reachable backend (e.g. change `vite.config.js` `target` to `http://127.0.0.1:8000` when the API is exposed from Docker on port 8000).

---

## Operational notes

- **Memory** — SD **img2img** + VAE decode is heavy on **CPU Docker**; the worker uses reduced inference resolution on CPU and `shm_size: 4gb` to mitigate OOM. Prefer **GPU compose** on Linux when possible.
- **Concurrency** — Worker **`--concurrency=1`**: raising it without enough RAM can spawn multiple SD loads and trigger SIGKILL.
- **Unsplash** — Respect [Unsplash API guidelines](https://help.unsplash.com/en/articles/2511315-guideline-attribution) and photographer attribution for public posts.
- **Plugins** — `contentforge/plugins/` is loaded at startup (`load_plugins()`); posting behavior is extensible per platform.

---

## Optional GPU stack

On a suitable Linux host with NVIDIA drivers:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

(Adjust paths and device requests per your `docker-compose.gpu.yml`.)

---

## License

If you add a license file, reference it here. Until then, treat the repo as private/unlicensed unless stated otherwise by the author.
