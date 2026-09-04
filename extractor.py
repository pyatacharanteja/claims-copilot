"""
extractor.py

Gemini-powered insurance claims extraction.

This module:
  1. Reads the Gemini API key securely from Streamlit Secrets.
  2. Extracts text from PDFs and TXT files.
  3. Uses Gemini vision for scanned/image claim documents.
  4. Extracts structured claim data as JSON.
  5. Includes a self-test API connection check.
  6. Returns clear errors instead of crashing the Streamlit app.
"""

import json
import time
from io import BytesIO

import streamlit as st
from google import genai
from google.genai import types
from pypdf import PdfReader


# Gemini model
MODEL = "gemini-3.6-flash"

_client = None


def get_client():
    """Create the Gemini client using Streamlit Secrets."""
    global _client

    if _client is None:
        api_key = st.secrets.get("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing from Streamlit Secrets."
            )

        _client = genai.Client(api_key=api_key)

    return _client


def check_api_connection() -> dict:
    """
    Cheap, fast call to confirm the Gemini API key and connection work.

    Returns:
        {"ok": True}

    or:

        {"ok": False, "error": "..."}
    """
    try:
        client = get_client()

        response = client.models.generate_content(
            model=MODEL,
            contents="Reply with just: ok",
            config=types.GenerateContentConfig(
                max_output_tokens=10,
            ),
        )

        if response.text:
            return {"ok": True}

        return {
            "ok": False,
            "error": "Gemini returned an empty response.",
        }

    except Exception as e:
        error_text = str(e)

        if "API key" in error_text or "401" in error_text or "403" in error_text:
            return {
                "ok": False,
                "error": "Gemini authentication failed. Check GEMINI_API_KEY in Streamlit Secrets.",
            }

        if "429" in error_text or "quota" in error_text.lower():
            return {
                "ok": False,
                "error": "Gemini API quota/rate limit reached. Please try again later.",
            }

        return {
            "ok": False,
            "error": f"Gemini API error: {error_text}",
        }


# ---------------------------------------------------------------------------
# Extraction schema
# ---------------------------------------------------------------------------

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "policy_number": {
            "type": ["string", "null"],
            "description": "Insurance policy number, if present.",
        },
        "claimant_name": {
            "type": ["string", "null"],
            "description": "Name of the claimant, if present.",
        },
        "date_of_incident": {
            "type": ["string", "null"],
            "description": "Date of incident in YYYY-MM-DD format, if present.",
        },
        "date_filed": {
            "type": ["string", "null"],
            "description": "Date the claim was filed in YYYY-MM-DD format, if present.",
        },
        "claim_type": {
            "type": ["string", "null"],
            "description": "Type of claim such as auto, property, liability, etc.",
        },
        "claimed_amount": {
            "type": ["number", "null"],
            "description": "Amount claimed, if present.",
        },
        "policy_limit": {
            "type": ["number", "null"],
            "description": "Policy coverage limit, if present.",
        },
        "description_of_incident": {
            "type": ["string", "null"],
            "description": "One or two sentence summary of the incident.",
        },
        "supporting_documents_mentioned": {
            "type": "array",
            "items": {
                "type": "string",
            },
            "description": "Supporting documents mentioned in the claim.",
        },
        "adjuster_notes": {
            "type": ["string", "null"],
            "description": "Adjuster notes, if present.",
        },
    },
    "required": [
        "policy_number",
        "claimant_name",
        "date_of_incident",
        "date_filed",
        "claim_type",
        "claimed_amount",
        "policy_limit",
        "description_of_incident",
        "supporting_documents_mentioned",
        "adjuster_notes",
    ],
}


SYSTEM_PROMPT = f"""
You are an intake assistant for an insurance agency.

You will be given the raw text of an insurance claim form or related document.

Extract the following fields:

{json.dumps(EXTRACTION_SCHEMA, indent=2)}

Rules:
- Return ONLY valid JSON.
- Do not include markdown.
- Do not include explanations or commentary.
- If a field is not present, return null.
- For supporting_documents_mentioned, return an empty list if none are mentioned.
- Do not guess or invent information.
- Only extract information supported by the document.
- Normalize dates to YYYY-MM-DD whenever possible.
- Keep the incident description concise.
"""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract selectable text from a PDF."""
    try:
        reader = PdfReader(BytesIO(file_bytes))

        text = [
            page.extract_text() or ""
            for page in reader.pages
        ]

        return "\n".join(text).strip()

    except Exception as e:
        raise ValueError(f"Could not parse PDF: {e}")


def extract_text_from_image(
    file_bytes: bytes,
    media_type: str
) -> str:
    """
    Use Gemini vision to read text from a scanned claim document.
    """

    try:
        client = get_client()

        image_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=media_type,
        )

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                image_part,
                """
Transcribe all visible text from this insurance claim document.

Read the document carefully and reproduce all visible text as accurately
and completely as possible.

Do not summarize.
Do not interpret the information.
Just return the visible text.
""",
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=3000,
            ),
        )

        if not response.text:
            raise ValueError(
                "Gemini returned no text from the image."
            )

        return response.text.strip()

    except Exception as e:
        raise ValueError(
            f"Could not read the document image with Gemini: {e}"
        )


def get_raw_text(uploaded_file) -> str:
    """
    Dispatch based on file type.
    """

    name = uploaded_file.name.lower()
    file_bytes = uploaded_file.read()

    if len(file_bytes) == 0:
        raise ValueError(
            "The uploaded file is empty (0 bytes)."
        )

    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)

    elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):

        if name.endswith(".png"):
            media_type = "image/png"
        elif name.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"

        return extract_text_from_image(
            file_bytes,
            media_type
        )

    elif name.endswith(".txt"):

        try:
            return file_bytes.decode(
                "utf-8",
                errors="ignore"
            )

        except Exception as e:
            raise ValueError(
                f"Could not read text file: {e}"
            )

    else:
        raise ValueError(
            f"Unsupported file type: {name}. "
            "Use PDF, PNG, JPG, WEBP, or TXT."
        )


def extract_structured_data(
    raw_text: str,
    max_retries: int = 1
) -> dict:
    """
    Send document text to Gemini and return structured JSON.

    Retries once on transient errors.
    Never raises an exception to the Streamlit UI.
    """

    if not raw_text or not raw_text.strip():
        return {
            "error": "No text was extracted from the document to analyze."
        }

    last_error = None

    for attempt in range(max_retries + 1):

        try:
            client = get_client()

            prompt = f"""
{SYSTEM_PROMPT}

DOCUMENT TEXT:
----------------
{raw_text}
----------------

Extract the claim information from the document.
"""

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=2000,
                    response_mime_type="application/json",
                    response_schema=EXTRACTION_SCHEMA,
                ),
            )

            raw_output = response.text.strip()

            if not raw_output:
                return {
                    "error": "Gemini returned an empty response."
                }

            # Parse Gemini's structured JSON response.
            result = json.loads(raw_output)

            return result

        except Exception as e:

            error_text = str(e)

            # Authentication errors
            if (
                "API key" in error_text
                or "401" in error_text
                or "403" in error_text
                or "authentication" in error_text.lower()
            ):
                return {
                    "error": (
                        "Gemini authentication failed — "
                        "check GEMINI_API_KEY in Streamlit Secrets."
                    )
                }

            # Quota / rate-limit errors
            if (
                "429" in error_text
                or "quota" in error_text.lower()
                or "rate limit" in error_text.lower()
            ):
                return {
                    "error": (
                        "Gemini API quota or rate limit reached. "
                        "Please try again later."
                    )
                }

            # JSON parsing error
            if isinstance(e, json.JSONDecodeError):
                return {
                    "error": "Gemini did not return valid JSON.",
                    "raw_output": raw_output
                    if "raw_output" in locals()
                    else "",
                }

            last_error = f"Gemini API error: {error_text}"

            if attempt < max_retries:
                time.sleep(1)
                continue

            break

    return {
        "error": last_error or "Extraction failed after retry."
    }
