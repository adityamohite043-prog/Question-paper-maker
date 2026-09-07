# Question Paper Maker Public Web v2.3 Resilient

## What changed
- Gemini Interactions API (`/v1beta/interactions`)
- Default model: `gemini-3.8-flash`
- Low thinking level for lower latency
- Automatic retry for 429/500/502/503/504: 5s, 15s, 30s
- Every completed unit is saved in Streamlit session state
- If a later unit fails, click **Generate Next Set** again and generation resumes from the failed unit
- Optional fallback model can be configured by the site owner
- Cached PDF/DOCX extraction and relevant-reference selection retained
- Template-based question paper, MCQ key, and scheme/solution export retained

## Streamlit Secrets
```toml
GEMINI_API_KEY = "YOUR_REAL_KEY"
GEMINI_MODEL = "gemini-3.8-flash"
```

Optional fallback (only use a model you have verified is available to your project):
```toml
GEMINI_FALLBACK_MODEL = "verified-model-id"
```

## Deploy
Replace `streamlit_app.py` and `requirements.txt` in your GitHub repository, commit, and let Streamlit redeploy.
