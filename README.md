# Public Question Paper Maker v2

## Deploy to Streamlit Community Cloud
1. Create a GitHub repository.
2. Upload all files/folders from this package.
3. Create a Gemini API key.
4. In Streamlit Community Cloud choose Create app, select the repository, and use `streamlit_app.py` as the entrypoint.
5. Open App settings > Secrets and paste:
   GEMINI_API_KEY = "YOUR_REAL_KEY"
   GEMINI_MODEL = "gemini-2.5-flash"
6. Deploy/reboot and share the generated `.streamlit.app` URL.

Never upload your real API key to GitHub.

This public MVP generates up to four sets, 50 MCQs per set, descriptive questions, answer keys, proper model solutions, and DOCX downloads.
