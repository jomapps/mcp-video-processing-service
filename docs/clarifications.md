# Clarification Questions — mcp-video-processing-service

Last Updated: 2025-09-29
Status: Resolved items recorded; no open questions

## Resolved decisions (2025-09-29)
1) Final MVP operation set and limits
- Operations IN: concat, trim, overlay (image/text), audio mixdown
- Operations OUT (MVP): subtitles (any), transitions
- Limits: no explicit limits on inputs, duration, or output size for MVP
- Resolution default: HD 1280x720 (not Full HD)
- GPU: CPU-only (no GPU usage in MVP)

2) Execution model and progress fields
- Model: Asynchronous jobs via Celery
- HTTP: returns { jobId } on submit; UI polls GET /jobs/{jobId}
- Progress fields: { percent [0-100], currentStep, message, updatedAt }

3) Subtitles, transitions beyond crossfade, GPU expectations
- Not included for MVP (deferred)


4) Inputs/Outputs and metadata
- Inputs: PayloadCMS Media IDs only (no external URLs)
- Outputs: Saved to PayloadCMS Media with metadata { jobId, operation, inputs[], durationMs, codecSummary }

5) Codec and container defaults
- MP4 (H.264 + AAC); CRF 20–23; Stereo 48kHz

6) Temp storage policy
- Container-local /tmp; cleanup per job

---

## Open questions
- None at this time

## Context (platform-wide defaults applied here)
- Source of truth: PayloadCMS (Media collection) — outputs saved back with public URLs via Cloudflare R2
- No auth/roles yet; future bearer-token alignment
- No retries/fallbacks/mocks; return best possible error message
- FFmpeg and FFprobe available in the environment

