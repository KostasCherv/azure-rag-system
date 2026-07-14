# Promo video

This isolated Remotion project turns a real Playwright walkthrough into portfolio-ready media.

## Capture and render

Install `ffmpeg`, start the API and a production UI build as described in the repository README, and make sure `/ready` is healthy. Production mode avoids recording Next.js development chrome.

```bash
cd ui
npm run build
npm run start
```

In another shell:

```bash
cd video
npm ci
npm run capture
npm run render
```

Outputs are written to `assets/promo/`. The MP4 is the portfolio master. Use `npm run render:webm` for the GitHub README and `npm run render:gif` only when a platform cannot embed video.

The capture is deterministic and fails with a diagnostic screenshot under `output/playwright/promo/`. It records readiness, a corpus-derived suggested question, a grounded answer, a contextual follow-up, and an inline citation click. Local capture automatically uses `local-development-user`, which must own the indexed sample documents. `DEMO_BASE_URL` can target an authenticated deployed UI; set `DEMO_USER_ID` when its indexed corpus belongs to another identity.

No narration or music is baked in so the video works when GitHub autoplays it muted. Remotion Studio can be used to refine timing and copy:

```bash
npm run studio
```
