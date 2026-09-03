# Claims Intake Copilot — MVP

A minimal, working version of the pipeline discussed: upload a document →
extract structured data with Claude → run business rules → flag issues →
export the result. Built around insurance claims intake, but the extraction
schema and rules are the only two things you need to change to point this
at a different niche (legal intake, real estate transaction docs, etc.).

## What's actually in here

- `extractor.py` — pulls text out of PDFs/images, then calls Claude to turn
  raw text into structured JSON matching a schema you define.
- `rules_engine.py` — hardcoded, explicit business rules (missing fields,
  amount vs. limit, date sanity checks). No AI here on purpose — this is
  the part that should be deterministic and auditable.
- `app.py` — the Streamlit UI: upload, view extracted data, view flags,
  export as CSV/JSON.
- `sample_data/` — two synthetic sample claims (one clean, one with issues)
  so you can test without needing a real document yet.

## Setup (5 minutes)

```bash
cd claims-copilot
pip install -r requirements.txt

# Set your API key (get one at console.anthropic.com)
export ANTHROPIC_API_KEY="sk-ant-..."

streamlit run app.py
```

This opens a browser tab at `localhost:8501`. Upload one of the files in
`sample_data/` to see it work end-to-end, or upload a real document.

## What I could NOT do for you

I built the scaffold and verified the logic works (rules engine tested
against both a clean and a flagged sample — see terminal output). What I
can't do from here:

- **Talk to real people in the industry.** You still need to find 3-5
  people (insurance agents, paralegals, whoever fits the niche you pick)
  and get their actual intake documents. The schema in `extractor.py`
  is my best guess at relevant fields — it will be wrong in places until
  a real document corrects it.
- **Validate against real documents.** The synthetic samples prove the
  pipeline runs; they don't prove the extraction prompt handles messy
  real-world handwriting, inconsistent formats, or industry jargon. Test
  with real docs before trusting the output.
- **Get you a paying customer.** That's a conversation, not code.

## How to adapt this to a different niche

1. Edit `EXTRACTION_SCHEMA` and `SYSTEM_PROMPT` in `extractor.py` — change
   the fields to whatever matters for your chosen workflow (lease terms
   for real estate, case details for legal intake, etc.).
2. Edit `REQUIRED_FIELDS` and the rule functions in `rules_engine.py` to
   match the real business logic for that industry.
3. Everything else (upload flow, flagging UI, export) stays the same.

## Immediate next steps (in priority order)

1. Run this against 3-5 real documents from someone in the target
   industry — even a smartphone photo of a paper form.
2. Sit with them while they try it. Note where the extracted data is
   wrong or where a flag doesn't make sense to them.
3. Fix the schema/rules based on what you saw, not what you assume.
4. Ask if they'd pay a small monthly fee for this. Their actual answer
   (not a hypothetical one) is the real validation.

## Known limitations at this stage

- No auth/login — single-user local tool only.
- No database — nothing is saved between sessions (add this once you
  know what "saved" should even mean for the real user).
- No CRM/email integration — manual upload only.
- Image OCR relies on Claude's vision, which is good but not
  specialized OCR — very poor scans may need a dedicated OCR step later.
