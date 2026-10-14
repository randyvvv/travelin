# Sample media

Demo media is stored in Cloud Storage, not in git. Keep local copies in `reels/` and `receipts/` (both git-ignored) and upload them to the project bucket:

```bash
gcloud storage cp samples/reels/*.mp4 gs://<bucket>/samples/reels/
gcloud storage cp samples/receipts/*.jpg gs://<bucket>/samples/receipts/
```

## What to collect

- **3 travel reels** (30–60 s, MP4) for the demo destination. Each should name places clearly: on-screen text, captions, or speech. Include at least one place that will fail verification, so the demo can show a dropped place.
- **2 receipt photos** from a restaurant or café, with item lines, tax, and service charge.

## Sources

Use only media you recorded yourself or have permission to use. Record each file here.

| File | Source | Permission |
|---|---|---|
| reels/reel-1.mp4 | | |
| reels/reel-2.mp4 | | |
| reels/reel-3.mp4 | | |
| receipts/receipt-1.jpg | | |
| receipts/receipt-2.jpg | | |
