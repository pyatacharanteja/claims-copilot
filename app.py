"""
app.py (hardened)
Run with: streamlit run app.py --server.port 8080 --server.address 0.0.0.0

Key fixes from the first version:
  - A "Run self-test" button that checks the API connection BEFORE you
    upload anything — isolates "my API key/billing is broken" from
    "my document processing logic is broken."
  - Every step (read file, extract text, call API, run rules) is wrapped
    so a failure shows a clear red message in the UI instead of crashing
    the whole Streamlit process (which is what causes a 501/502 at the
    Replit proxy level — the process dies, so there's nothing to serve).
"""

import io
import json
import traceback

import pandas as pd
import streamlit as st

from extractor import check_api_connection, extract_structured_data, get_raw_text
from rules_engine import run_rules, severity_sort_key

st.set_page_config(page_title="Claims Intake Copilot", layout="centered")

st.title("Claims Intake Copilot (MVP)")
st.caption(
    "Upload a claim form (PDF, image, or text). This extracts the key fields "
    "and flags anything missing or inconsistent before it goes to an adjuster."
)

# ---------------------------------------------------------------------------
# Self-test panel — run this FIRST if anything seems broken.
# ---------------------------------------------------------------------------
with st.expander("🔧 Run self-test (check this first if something's broken)"):
    if st.button("Run self-test"):
        with st.spinner("Checking API connection..."):
            result = check_api_connection()
        if result["ok"]:
            st.success("API connection OK. Your key and billing are working.")
        else:
            st.error(f"API check failed: {result['error']}")
            st.info(
                "If this says 'Invalid or missing key' → recheck your Replit Secret "
                "named exactly ANTHROPIC_API_KEY.\n\n"
                "If this says 'network issue' → your API key is fine, this is likely "
                "a Replit/network problem, try again in a minute."
            )

st.divider()

uploaded_file = st.file_uploader(
    "Upload claim document", type=["pdf", "png", "jpg", "jpeg", "webp", "txt"]
)

if uploaded_file is not None:
    # --- Step 1: read raw text from the file ---
    raw_text = None
    with st.spinner("Reading document..."):
        try:
            raw_text = get_raw_text(uploaded_file)
        except ValueError as e:
            st.error(f"Could not read file: {e}")
        except Exception as e:
            st.error("Unexpected error while reading the file.")
            with st.expander("Technical details"):
                st.code(traceback.format_exc())

    if raw_text is not None:
        with st.expander("Raw extracted text (for debugging)"):
            st.text(raw_text[:3000] if raw_text.strip() else "(no text found)")

        if not raw_text.strip():
            st.warning("No text could be extracted from this document. Try a clearer scan or a different file.")
        else:
            # --- Step 2: structured extraction via Claude ---
            data = None
            with st.spinner("Extracting structured data..."):
                try:
                    data = extract_structured_data(raw_text)
                except Exception:
                    st.error("Unexpected error during extraction.")
                    with st.expander("Technical details"):
                        st.code(traceback.format_exc())

            if data is not None:
                if "error" in data:
                    st.error(f"Extraction issue: {data['error']}")
                    if "raw_output" in data:
                        with st.expander("Raw model output"):
                            st.text(data["raw_output"])
                else:
                    st.subheader("Extracted Data")
                    st.json(data)

                    # --- Step 3: rules engine ---
                    st.subheader("Flags")
                    try:
                        flags = run_rules(data)
                        flags_sorted = sorted(flags, key=severity_sort_key)
                        severity_style = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                        for flag in flags_sorted:
                            icon = severity_style.get(flag["severity"], "⚪")
                            st.write(f"{icon} **{flag['severity'].upper()}** — {flag['message']}")

                        # --- Step 4: export ---
                        st.subheader("Export")
                        export_row = dict(data)
                        export_row["flags"] = "; ".join(
                            f"[{f['severity']}] {f['message']}" for f in flags_sorted
                        )
                        df = pd.DataFrame([export_row])
                        csv_buffer = io.StringIO()
                        df.to_csv(csv_buffer, index=False)

                        st.download_button(
                            label="Download as CSV",
                            data=csv_buffer.getvalue(),
                            file_name="claim_intake_result.csv",
                            mime="text/csv",
                        )
                        st.download_button(
                            label="Download as JSON",
                            data=json.dumps(export_row, indent=2),
                            file_name="claim_intake_result.json",
                            mime="application/json",
                        )
                    except Exception:
                        st.error("Unexpected error while running rules/export.")
                        with st.expander("Technical details"):
                            st.code(traceback.format_exc())
else:
    st.info("Upload a document to get started. No sample? Use one from `sample_data/`.")
