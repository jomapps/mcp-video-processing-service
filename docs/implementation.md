# mcp-video-processing-service

## Service overview and purpose
A standalone processing service focused on basic video editing and assembly pipelines: trimming, concatenation, overlays, and scene stitching for previews. Intended to run as CPU-only worker(s) for MVP.

## Technical requirements and dependencies
- Language: Python 3.11+
- Orchestration: FastAPI control plane + Celery workers
- Media tools: FFmpeg, FFprobe (installed in container)
- Storage: PayloadCMS Media (pull/push via signed URLs or direct API)
- Messaging: Redis for Celery broker/result

## API endpoints and interfaces
- HTTP:
  - POST `/jobs/concat` { inputs[], audioTrack?, outputFormat } → { jobId }
  - POST `/jobs/overlay` { input, overlays[], outputFormat } → { jobId }
  - GET `/jobs/{jobId}` → status/progress/result mediaId
  - GET `/health` → { ok: true }
- Queue contracts (Celery tasks): `video.concat`, `video.overlay`

## Database schema (if applicable)
Store job metadata in CMS or lightweight internal store:
- videoJobs: { jobId, type, params, status, progress, resultMediaId, createdAt }

## Integration points with PayloadCMS
- Inputs addressed by PayloadCMS Media IDs only (no external URLs)
- Output upload back to Media with metadata: { jobId, operation, inputs[], durationMs, codecSummary }
- Job status surfaced to UI via WebSocket events

## Step-by-step implementation guide
1. Container with FFmpeg + Python deps
2. FastAPI routes for job submission/status
3. Celery tasks implementing FFmpeg pipelines
4. Media download/upload helpers (single-attempt IO; surface errors clearly)
5. Emit progress; finalize with media upload and metadata update

## Testing strategy
- Unit: FFmpeg command builders
- Integration: concat small sample clips; verify duration and streams
- Regression: overlay positioning and alpha correctness

## Deployment considerations
- CPU-only (MVP); ensure codecs present (x264/x265, aac)
- Isolate worker autoscaling independent of API nodes
- Mount temp storage; set size limits



## Platform constraints and assumptions
- Single source of truth: PayloadCMS Media — both inputs and outputs are addressed via CMS; inputs must be Media IDs only (no external URLs); store outputs back with metadata
- No auth/roles yet (MVP); align later with bearer token standard
- No retries/fallbacks/mocks — return best possible error message; include ffmpeg stderr summary when safe
- FFmpeg/FFprobe available in container; CPU-only (MVP); no GPU usage
- Default output resolution: HD 1280x720; no hard limits on inputs/duration/output size (MVP)
- Temp storage: container-local /tmp; cleanup per job

## Error handling and observability
- Structured JSON logs for every job with fields: { requestId, jobId, operation, inputs[], startedAt, finishedAt, durationMs, ffmpegExitCode, status, message }
- Propagate orchestrator trace metadata (traceId, step) if provided
- Map failures to HTTP 4xx (validation) / 5xx (processing) with actionable messages
- Emit progress updates: { percent, currentStep, message, updatedAt }

## Local development & testing
- Install ffmpeg/ffprobe locally; run FastAPI + Celery with Redis
- Provide small sample clips and overlay fixtures under tests assets
- Unit tests focus on command builders; integration tests run short pipelines (<10s) to keep CI fast

## Confirmed defaults (MVP)
- Operations: concat, trim, overlay (image/text), audio mixdown; no subtitles; no transitions; CPU-only
- Execution model: Asynchronous jobs via Celery; HTTP returns { jobId }; progress fields { percent, currentStep, message, updatedAt }
- Inputs/Outputs: Inputs must be PayloadCMS Media IDs only; Outputs saved to PayloadCMS Media with metadata { jobId, operation, inputs[], durationMs, codecSummary }
- Output format: MP4 (H.264 + AAC); CRF 20-23; Stereo 48kHz
- Resolution: HD 1280x720; no hard limits on inputs/duration/output size
- Temp storage: container-local /tmp; cleanup per job
