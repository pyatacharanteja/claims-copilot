# Claims Intake Copilot

A Streamlit app that turns uploaded insurance claim documents into structured data, then checks that data against explicit business rules and flags problems for a human reviewer.

**Status:** working prototype, tested on two synthetic sample claims. It has not been validated on real-world documents.

## What it does
1. **Upload** a claim as a PDF, TXT file or image.
2. **Extract** text (PDFs and text files with `pypdf`; scanned or image claims with Gemini vision).
3. **Structure** the text into JSON with the Gemini API, using a fixed schema (policy number, claimant, incident and filing dates, claim type, claimed amount, policy limit, incident summary, supporting documents, adjuster notes).
4. **Validate** the result with a deterministic rules engine and show flags sorted by severity.
5. **Export** the extracted data as CSV or JSON.

## Design choice: AI extracts, rules decide
The language model only reads and structures the document. All decisions come from plain Python rules in `rules_engine.py`, so every flag can be traced and audited:

| Rule | Severity |
|---|---|
| Required field missing (policy number, claimant name, incident date, claim type, claimed amount) | High |
| Claimed amount exceeds policy limit | High |
| Filing date is before the incident date | High |
| Extraction failed or returned unusable data | High |
| No supporting documents mentioned | Medium |
| Claimed amount and limit can't be compared (non-numeric) | Medium |

## Tech stack
Python, Streamlit, Google Gemini API (`google-genai`), pypdf, pandas, Pillow

## Project structure
| File | Purpose |
|---|---|
| `app.py` | Streamlit interface: upload, results, flags, export |
| `extractor.py` | Text extraction and Gemini-based structured extraction, with error handling |
| `rules_engine.py` | Business rules applied to the extracted data |
| `sample_data/` | Two synthetic claims, one clean and one with issues |

## Run it locally
```bash
git clone https://github.com/pyatacharanteja/claims-copilot.git
cd claims-copilot
pip install -r requirements.txt
```

Add your Gemini API key to `.streamlit/secrets.toml`:
```toml
GEMINI_API_KEY = "your-key-here"
```

Then start the app and upload a file from `sample_data/`:
```bash
streamlit run app.py
```

## Limitations
- Tested only on two synthetic claims, so accuracy on messy real documents (handwriting, unusual layouts) is unknown.
- The extraction schema and rules are a starting point and would need adjusting with a real insurer's intake process.
- Extraction depends on the Gemini API, so it needs a valid key and is subject to rate limits.

## Possible next steps
- Add unit tests for the rules engine.
- Measure extraction accuracy on a labelled set of documents.
- Add a human review step that lets a reviewer correct fields before export.
