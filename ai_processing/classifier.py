# ai_processing/classifier.py
#
# Classifies an email into one of the defined categories.
#
# Public API (two functions, one shared LLM call):
#
#   classify_email(subject, body) -> str
#       Original interface. Returns the category label only (e.g. "IMPORTANT").
#       Backward compatible — existing callers in main.py and monitor.py
#       require no changes.
#
#   classify_email_detailed(subject, body) -> dict
#       Extended interface for the Decision Engine (Phase 1, Step 5) and
#       the Streamlit dashboard. Returns:
#           {
#             "category":               str,   # e.g. "IMPORTANT"
#             "ai_confidence_estimate": float,  # 0.0 – 1.0
#             "raw_response":           str    # LLM output, for diagnostics
#           }
#
# Both functions share _call_classifier() so only one API request is made
# regardless of which function is called.

import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# ---------------------------------------------------------------------------
# Valid output categories.
# Any LLM response not in this set is mapped to "UNKNOWN".
# ---------------------------------------------------------------------------
VALID_CATEGORIES = {"IMPORTANT", "PROMOTION", "SOCIAL", "SPAM", "UPDATES"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(subject: str, body: str) -> str:
    """
    Returns the classifier prompt.

    Design notes:
      - Categories are enumerated explicitly so the model cannot invent new ones.
      - The two-line output contract is stated once as an instruction and once
        as a concrete example to reduce format deviation.
      - temperature=0 (set at the call site) maximises determinism for
        reliable structured parsing.
      - The CONFIDENCE field is labelled as a self-assessed Model Confidence
        estimate, not a calibrated probability, per the project terminology.
    """
    return f"""You are an email classification system.

Classify the email below into EXACTLY ONE of these categories:
IMPORTANT | PROMOTION | SOCIAL | SPAM | UPDATES

Also rate your own confidence in this classification as a percentage (0 to 100).
This is a self-assessed Model Confidence estimate, not a calibrated probability.
100 = completely certain. 0 = guessing.

Respond in EXACTLY this two-line format — nothing else:
CATEGORY: <CATEGORY_NAME>
CONFIDENCE: <0-100>

Example of a correct response:
CATEGORY: IMPORTANT
CONFIDENCE: 82

EMAIL SUBJECT:
{subject}

EMAIL BODY:
{body[:2000]}
"""


def _parse_response(text: str) -> dict:
    """
    Parses the LLM's two-line structured output.

    Returns a dict with keys: category, ai_confidence_estimate, raw_response.
    On any parse failure, returns a safe fallback with UNKNOWN / 0.0 and
    the raw LLM text preserved for downstream diagnostics.
    """
    category = None
    confidence_raw = None

    for line in text.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip().upper()
        elif line.upper().startswith("CONFIDENCE:"):
            confidence_raw = line.split(":", 1)[1].strip()

    # Validate category
    if category not in VALID_CATEGORIES:
        logger.warning(
            "Classifier: unrecognised category '%s'. Falling back to UNKNOWN. "
            "Raw response: %r", category, text,
        )
        return {"category": "UNKNOWN", "ai_confidence_estimate": 0.0, "raw_response": text}

    # Validate and normalise confidence (0–100 int → 0.0–1.0 float)
    try:
        confidence_pct = float(confidence_raw)
        if not (0.0 <= confidence_pct <= 100.0):
            raise ValueError(f"Out of range: {confidence_pct}")
        confidence_float = round(confidence_pct / 100.0, 4)
    except (TypeError, ValueError):
        logger.warning(
            "Classifier: could not parse confidence value '%s'. Defaulting to 0.0. "
            "Raw response: %r", confidence_raw, text,
        )
        return {"category": category, "ai_confidence_estimate": 0.0, "raw_response": text}

    return {
        "category": category,
        "ai_confidence_estimate": confidence_float,
        "raw_response": text,
    }


def _call_classifier(subject: str, body: str) -> dict:
    """
    Makes the LLM API call and returns the parsed structured result.
    Both public functions delegate here — only one API request per call.
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": _build_prompt(subject, body)}],
        )
        raw_text = response.choices[0].message.content
        return _parse_response(raw_text)

    except Exception as exc:
        logger.error("Classifier API call failed: %s", exc)
        return {"category": "UNKNOWN", "ai_confidence_estimate": 0.0, "raw_response": ""}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_email(subject: str, body: str) -> str:
    """
    Classifies an email and returns the category label as a plain string.

    Backward-compatible interface used by main.py and monitor.py.
    Returns one of: IMPORTANT | PROMOTION | SOCIAL | SPAM | UPDATES | UNKNOWN.

    For the full structured result including AI Confidence Estimate,
    use classify_email_detailed() instead.
    """
    return _call_classifier(subject, body)["category"]


def classify_email_detailed(subject: str, body: str) -> dict:
    """
    Classifies an email and returns a structured result dict.

    Intended for the Decision Engine (ai_processing/decision_engine.py)
    and the Streamlit Approval Center dashboard.

    Returns:
        {
          "category":               str,   # e.g. "IMPORTANT"
          "ai_confidence_estimate": float,  # 0.0 – 1.0
          "raw_response":           str    # raw LLM output for diagnostics
        }

    On API failure or parse failure, returns safe fallback values:
        category="UNKNOWN", ai_confidence_estimate=0.0, raw_response="".
    """
    return _call_classifier(subject, body)