# Question Paper Maker — Public Web v2.2 Fast

This version improves the public Streamlit app by:

- caching syllabus/reference extraction so uploaded PDFs are not reparsed on every rerun
- adding `fonttools` for PDFs with embedded CFF/Type1 fonts
- suppressing repetitive pypdf font warnings in app logs
- selecting only unit-relevant reference excerpts for each AI request
- defaulting to one-set-at-a-time generation
- showing unit-by-unit generation progress
- preserving completed sets if a later set fails
- retrying temporary Gemini 429/5xx/network failures automatically
- using `gemini-3.6-flash` as the default model
- retaining uploaded Word-template export for question paper, MCQ key, and scheme/solution

## Update an existing Streamlit Community Cloud app

1. Replace `streamlit_app.py` in your GitHub repository with this version.
2. Replace `requirements.txt` with this version.
3. Commit the changes. Streamlit should redeploy automatically.
4. In Streamlit app Secrets, keep your existing API key and set:

```toml
GEMINI_API_KEY = "YOUR_REAL_KEY"
GEMINI_MODEL = "gemini-3.6-flash"
```

Do not commit your real API key to GitHub.

## Recommended use

Set **Target number of sets = 1** and click **Generate Next Set**. After reviewing Set 1, increase the target to 2/3/4 and click **Generate Next Set** again. Completed sets stay in the current Streamlit session.
