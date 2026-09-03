"""
rules_engine.py
Takes the structured data extracted from a document and applies hardcoded
business rules on top of it — the part an LLM alone shouldn't be trusted
to do reliably (limits, required fields, thresholds).

This is deliberately simple and explicit. As you learn the real rules a
specific agency uses, you add them here as plain Python — no need for a
rules DSL or config system at MVP stage.
"""

REQUIRED_FIELDS = [
    "policy_number",
    "claimant_name",
    "date_of_incident",
    "claim_type",
    "claimed_amount",
]


def run_rules(data: dict) -> list[dict]:
    """
    Returns a list of flags. Each flag is:
      {"severity": "high" | "medium" | "low", "message": str}
    """
    flags = []

    if "error" in data:
        return [{"severity": "high", "message": "Extraction failed — document could not be parsed into structured data."}]

    # Rule 1: required fields present
    for field in REQUIRED_FIELDS:
        if not data.get(field):
            flags.append({
                "severity": "high",
                "message": f"Missing required field: '{field}'. Cannot process claim without this."
            })

    # Rule 2: claimed amount vs policy limit
    claimed = data.get("claimed_amount")
    limit = data.get("policy_limit")
    if claimed is not None and limit is not None:
        try:
            if float(claimed) > float(limit):
                flags.append({
                    "severity": "high",
                    "message": f"Claimed amount (${claimed:,.2f}) exceeds policy limit (${limit:,.2f})."
                })
        except (ValueError, TypeError):
            flags.append({"severity": "medium", "message": "Could not compare claimed amount to policy limit (non-numeric values)."})

    # Rule 3: supporting documentation
    docs = data.get("supporting_documents_mentioned") or []
    if len(docs) == 0:
        flags.append({
            "severity": "medium",
            "message": "No supporting documents (photos, reports, etc.) mentioned in the claim."
        })

    # Rule 4: date sanity check (filed before incident = red flag)
    date_incident = data.get("date_of_incident")
    date_filed = data.get("date_filed")
    if date_incident and date_filed and date_filed < date_incident:
        flags.append({
            "severity": "high",
            "message": f"Filing date ({date_filed}) is before incident date ({date_incident}) — possible data error or fraud flag."
        })

    # Rule 5: no flags at all = clean claim
    if not flags:
        flags.append({"severity": "low", "message": "No issues detected. Claim appears complete."})

    return flags


def severity_sort_key(flag: dict) -> int:
    order = {"high": 0, "medium": 1, "low": 2}
    return order.get(flag.get("severity", "low"), 3)
