"""
extractor.py (hardened)

Key fixes from the first version:
  1. The Anthropic client is no longer created at import time. Before, if
     ANTHROPIC_API_KEY was missing or empty when the app started, the whole
     app would crash on startup — which is exactly what produces a blank
     501/502 from Replit's proxy (app never came up, so there's nothing to
     route to).
  2. Every external call (API, file parsing) is wrapped so failures return
     a clear error dict instead of raising and killing the app.
  3. Added a short retry on transient API errors, since flaky network blips
     otherwise look identical to "the app is broken."
  4. Added a standalone check_api_connection() used by the self-test panel
     in app.py, so you can verify the API key works BEFORE uploading a doc.
"""

import base64
import json
import time
from io import BytesIO

from anthropic import Anthropic, APIConnectionError, APIStatusError, AuthenticationError
from pypdf import PdfReader

MODEL = "claude-sonnet-4-6"

_client = None


def get_client():
    """Create the Anthropic client lazily, on first real use — not at import time."""
    global _client
    if _client is None:
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from environment
    return _client


def check_api_connection() -> dict:
    """
    Cheap, fast call to confirm the API key + network actually work.
    Returns {"ok": True} or {"ok": False, "error": "..."} — never raises.
    """
    try:
        client = get_client()
        client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with just: ok"}],
        )
        return {"ok": True}
    except AuthenticationError:
        return {"ok": False, "error": "Invalid or missing ANTHROPIC_API_KEY. Check your Replit Secret."}
    except APIConnectionError:
        return {"ok": False, "error": "Could not reach the Anthropic API (network issue)."}
    except APIStatusError as e:
        return {"ok": False, "error": f"API returned an error: {e.status_code} — {e.message}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


# ---------------------------------------------------------------------------
# Extraction schema — customize per industry
# ---------------------------------------------------------------------------
EXTRACTION_SCHEMA = {
    "policy_number": "string or null",
    "claimant_name": "string or null",
    "date_of_incident": "string (YYYY-MM-DD) or null",
    "date_filed": "string (YYYY-MM-DD) or null",
    "claim_type": "string, e.g. 'auto', 'property', 'liability', or null",
    "claimed_amount": "number or null",
    "policy_limit": "number or null",
    "description_of_incident": "string, 1-2 sentence summary or null",
    "supporting_documents_mentioned": "list of strings, e.g. ['photos', 'police report']",
    "adjuster_notes": "string or null",
}

SYSTEM_PROMPT = f"""You are an intake assistant for an insurance agency.
You will be given the raw text of a claim form or related document.
Extract the following fields as JSON, matching this schema exactly:

{json.dumps(EXTRACTION_SCHEMA, indent=2)}

Rules:
- Return ONLY valid JSON. No preamble, no markdown code fences, no commentary.
- If a field isn't present in the text, use null (or an empty list for list fields).
- Do not guess or invent values that aren't supported by the text.
- Dates should be normalized to YYYY-MM-DD where possible.
"""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(file_bytes))
        text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(text).strip()
    except Exception as e:
        raise ValueError(f"Could not parse PDF: {e}")


def extract_text_from_image(file_bytes: bytes, media_type: str) -> str:
    """Uses Claude's vision to read an image (e.g. a scanned form) directly."""
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": "Transcribe all visible text from this document image, "
                                "as plainly and completely as possible.",
                    },
                ],
            }
        ],
    )
    return response.content[0].text.strip()


def get_raw_text(uploaded_file) -> str:
    """Dispatch based on file type. Raises ValueError with a clear message on failure."""
    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.read()

    if len(file_bytes) == 0:
        raise ValueError("The uploaded file is empty (0 bytes).")

    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        media_type = "image/png" if name.endswith(".png") else "image/jpeg"
        return extract_text_from_image(file_bytes, media_type)
    elif name.endswith(".txt"):
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception as e:
            raise ValueError(f"Could not read text file: {e}")
    else:
        raise ValueError(f"Unsupported file type: {name}. Use PDF, PNG, JPG, or TXT.")


def extract_structured_data(raw_text: str, max_retries: int = 1) -> dict:
    """
    Send raw document text to Claude and get back structured JSON.
    Retries once on transient connection errors. Never raises — always
    returns a dict, with an "error" key set on failure so the UI can show
    a real message instead of crashing.
    """
    if not raw_text or not raw_text.strip():
        return {"error": "No text was extracted from the document to analyze."}

    last_error = None
    raw_output = ""
    for attempt in range(max_retries + 1):
        try:
            client = get_client()
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": raw_text}],
            )
            raw_output = response.content[0].text.strip()

            if raw_output.startswith("```"):
                raw_output = raw_output.strip("`")
                if raw_output.lower().startswith("json"):
                    raw_output = raw_output[4:].strip()

            return json.loads(raw_output)

        except AuthenticationError:
            return {"error": "Authentication failed — check ANTHROPIC_API_KEY in Replit Secrets."}
        except APIConnectionError as e:
            last_error = f"Network error contacting the API: {e}"
            time.sleep(1)
            continue
        except APIStatusError as e:
            return {"error": f"API error {e.status_code}: {e.message}"}
        except json.JSONDecodeError:
            return {"error": "Model did not return valid JSON.", "raw_output": raw_output}
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            break

    return {"error": last_error or "Extraction failed after retry."}
