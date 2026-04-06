# CareGap AI

CareGap AI is a Streamlit app that reviews patient records, reconstructs a medical timeline, identifies potential care gaps and risks, assigns a risk level and score, and suggests follow-up actions.

## Features

- Paste patient records or upload `.txt` and `.pdf` files
- Extract PDF text with `PyPDF2`
- Analyze records with the OpenAI API
- View a structured dashboard with:
  - Timeline
  - Risks
  - Risk Level
  - Risk Score
  - Recommendations
- Try built-in high-risk and lower-risk demo patients without using API quota
- Download the analysis summary as `.txt`
- Download the patient timeline as `.csv`

## Requirements

- Python 3.10+
- An OpenAI API key with available billing/quota for live analysis

## Dependencies

- `streamlit>=1.43.0`
- `openai>=1.75.0`
- `PyPDF2>=3.0.1`

## Local Setup

1. Open PowerShell.
2. Move into the project folder:

```powershell
cd "C:\Users\britt\Desktop\CareGap AI\CareGap AI 2"
```

3. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

4. Set your OpenAI API key for the current shell session:

```powershell
$env:OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
```

5. Start the app:

```powershell
python -m streamlit run app.py
```

## Deployment

### Streamlit Community Cloud

1. Push `app.py` and `requirements.txt` to a GitHub repository.
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app and select your GitHub repo.
4. Set the main file path to `app.py`.
5. In Secrets / Advanced Settings, add:

```toml
OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
```

6. Deploy the app.

## Notes

- Demo buttons use built-in sample results and do not call the OpenAI API.
- Uploaded or pasted custom records do call the OpenAI API.
- Do not hardcode your API key in `app.py`.
- If you previously exposed API keys, revoke them and create fresh ones.

## Disclaimer

CareGap AI is an AI-assisted review tool for workflow support and care-gap screening. It is not a medical device and does not replace clinician judgment, diagnosis, or treatment planning.
