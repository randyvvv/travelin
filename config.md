PROJECT_ID=sosro-511617
STORAGE_BUCKET=sosro-511617.firebasestorage.app

firebaseConfig = {
  apiKey: "AIzaSyDMkbABf2y0p84vupOEGLmFRbV0xs1oSx8",
  authDomain: "sosro-511617.firebaseapp.com",
  projectId: "sosro-511617",
  storageBucket: "sosro-511617.firebasestorage.app",
  messagingSenderId: "345197313622",
  appId: "1:345197313622:web:cf74c66f3f8f5c594445f7",
  measurementId: "G-BWSNHHV35Y"
};

MAPS_BROWSER_KEY=AIzaSyAVq8JHH9OJoEL5hHElCD5YsGjO8IcaICw
MAP_ID=2579b4bcbb617d9e9e69851b

<!-- SMOKE TEST -->
PS D:\Code\works\hackaton\ai-builder> uv run --project api python scripts/smoke_gemini.py
Using CPython 3.12.0 interpreter at: C:\Program Files\Python312\python.exe
Creating virtual environment at: api\.venv
    Updated https://github.com/google-agentic-commerce/AP2.git (e1ea56db72a6385bce3e5c1112b3a56ce60acb43)
      Built ap2 @ git+https://github.com/google-agentic-commerce/AP2.git@e1ea56db72a6385bce3e5c1112b3a56ce60acb43
░░░░░░░░░░░░░░░░░░░░ [0/83] Installing wheels...warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 83 packages in 5.19s
project=sosro-511617 location=global fast=gemini-3.8-flash planner=gemini-4-argon

SKIP  video extraction (pass --video gs://...)
PASS  structured output (18.5s): ['Kraton Yogyakarta', 'Taman Sari']
PASS  maps grounding (13.6s): [('Water Castle of Royal Jogjakarta - Google Maps', 'ChIJya-Z3pNXei4R-ceM3J_doVA'), ('Taman SariTourist Village - Google Maps', 'ChIJK8_C0JNXei4RE74coPghaic'), ('Review of Water Castle of Royal Jogjakarta - Google Maps', 'ChIJya-Z3pNXei4R-ceM3J_doVA')]
PASS  planner model (2.1s): ready