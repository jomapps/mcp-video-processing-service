# mcp-video-processing-service

## Service overview and purpose
A standalone processing service focused on basic video editing and assembly pipelines: trimming, concatenation, overlays, subtitles burn-in, and scene stitching for previews. Intended to run as CPU/GPU capable worker(s).

## Technical requirements and dependencies
- Language: Python 3.11+
- Orchestration: FastAPI control plane + Celery workers
- Media tools: FFmpeg, FFprobe (installed in container)
- Storage: PayloadCMS Media (pull/push via signed URLs or direct API)
- Messaging: Redis for Celery broker/result

## API endpoints and interfaces
- HTTP:
  - POST `/jobs/concat` { inputs[], transitions?, audioTrack?, outputFormat } → { jobId }
  - POST `/jobs/overlay` { input, overlays[], outputFormat } → { jobId }
  - POST `/jobs/subtitles` { input, subs, burnIn?, outputFormat } → { jobId }
  - GET `/jobs/{jobId}` → status/progress/result mediaId
  - GET `/health` → { ok: true }
- Queue contracts (Celery tasks): `video.concat`, `video.overlay`, `video.subtitles`

## Database schema (if applicable)
Store job metadata in CMS or lightweight internal store:
- videoJobs: { jobId, type, params, status, progress, resultMediaId, createdAt }

## Integration points with PayloadCMS
- Input discovery via Media collection IDs
- Output upload back to Media with metadata: { jobId, operation }
- Job status surfaced to UI via WebSocket events

## Step-by-step implementation guide
1. Container with FFmpeg + Python deps
2. FastAPI routes for job submission/status
3. Celery tasks implementing FFmpeg pipelines
4. Media download/upload helpers with retry-limited IO
5. Emit progress; finalize with media upload and metadata update

## Testing strategy
- Unit: FFmpeg command builders
- Integration: concat small sample clips; verify duration and streams
- Regression: subtitle burn-in correctness

## Deployment considerations
- GPU optional; ensure codecs present (x264/x265, aac)
- Isolate worker autoscaling independent of API nodes
- Mount temp storage; set size limits

