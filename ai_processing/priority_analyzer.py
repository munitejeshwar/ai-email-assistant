# ai_processing/priority_analyzer.py
#
# Analyses email priority and returns structured XAI fields.
#
# Public API (two functions, one shared LLM call):
#
#   analyze_priority(subject, body) -> str
#       Original interface. Returns a plain string in the legacy format:
#           PRIORITY: X/10
#           URGENCY: LOW/MEDIUM/HIGH
#           ACTION: YES/NO
#       Backward compatible — main.py and monitor.py require no changes.
#
#   analyze_priority_detailed(subject, body) -> dict
#       Extended interface for the Decision Engine and Streamlit dashboard.
#       Returns:
#           {
#             "priority":               str,   # legacy string (same as analyze_priority())
#             "priority_score":         int,   # 1–10
#             "urgency":                str,   # "LOW" | "MEDIUM" | "HIGH"
#             "action_required":        bool,  # True if action is needed
#             "risk_level":             str,   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
#             "reasoning":              str,   # one-sentence AI explanation
#             "ai_confidence_estimate": float, # 0.0 – 1.0
#             "raw_response":           str    # raw LLM output for diagnostics
#           }
#
# Model note:
#   Changed from openai/gpt-oss-20b:free to openai/gpt-4o-mini.
#   Reason: free-tier models have inconsistent adherence to strict multi-line
#   output contracts, which the structured parser depends on. gpt-4o-mini is
#   the project standard, cost-effective, and improves reproducibility for
#   the IEEE/Springer paper.

import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# ---------------------------------------------------------------------------
# Valid field values for strict validation.
# ---------------------------------------------------------------------------
VALID_URGENCY    = {"LOW", "MEDIUM", "HIGH"}
VALID_RISK_LEVEL = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_ACTION     = {"YES", "NO"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(subject: str, body: str) -> str:
    """
    Returns the priority analysis prompt.

    Design notes:
      - temperature=0 (set at call site) maximises determinism.
      - Six output fields are requested in a strict prefix format so the
        parser can match lines independently of order.
      - CONFIDENCE is labelled as a self-assessed Model Confidence estimate,
        consistent with the project's AI Confidence Estimate terminology.
      - REASONING is capped at one sentence to keep the output concise and
        parseable without multi-line handling.
    """
    return f"""You are an AI email priority analyser.

Analyse the email below and respond in EXACTLY this six-line format — nothing else:
PRIORITY_SCORE: <integer 1-10>
URGENCY: <LOW|MEDIUM|HIGH>
ACTION: <YES|NO>
RISK_LEVEL: <LOW|MEDIUM|HIGH|CRITICAL>
CONFIDENCE: <integer 0-100>
REASONING: <one concise sentence explaining your assessment>

Field definitions:
  PRIORITY_SCORE : overall importance of this email (1 = lowest, 10 = highest)
  URGENCY        : how time-sensitive a response is
  ACTION         : does the recipient need to take action?
  RISK_LEVEL     : potential negative consequence if ignored
  CONFIDENCE     : your self-assessed Model Confidence estimate (not a calibrated probability)
  REASONING      : brief rationale (one sentence only)

Example of a correct response:
PRIORITY_SCORE: 8
URGENCY: HIGH
ACTION: YES
RISK_LEVEL: MEDIUM
CONFIDENCE: 85
REASONING: The email contains a deadline-sensitive contract approval request.

EMAIL SUBJECT:
{subject}

EMAIL BODY:
{body[:3000]}
"""


def _safe_fallback(raw_response: str = "") -> dict:
    """
    Returns a safe default result used whenever parsing or the API call fails.
    priority_score=0 and urgency=UNKNOWN signal to downstream consumers that
    this result should not be used for filtering or sorting.
    """
    return {
        "priority":               "PRIORITY: 0/10\nURGENCY: UNKNOWN\nACTION: NO",
        "priority_score":         0,
        "urgency":                "UNKNOWN",
        "action_required":        False,
        "risk_level":             "UNKNOWN",
        "reasoning":              "",
        "ai_confidence_estimate": 0.0,
        "raw_response":           raw_response,
    }


def _parse_response(text: str) -> dict:
    """
    Parses the LLM's six-line structured output into a result dict.

    Parsing rules:
      - Lines are matched by prefix; order is not assumed.
      - Each field is validated against its allowed value set.
      - PRIORITY_SCORE is clamped to 1–10; values outside this range
        trigger a warning and fall back to 0.
      - CONFIDENCE (0–100 int) is normalised to a 0.0–1.0 float.
      - REASONING is accepted as-is (free text, one line).
      - Any validation failure returns _safe_fallback() — no exception raised.
    """
    fields = {}

    for line in text.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().upper()] = value.strip()

    # --- PRIORITY_SCORE ---
    try:
        score = int(fields.get("PRIORITY_SCORE", "0"))
        if not (1 <= score <= 10):
            raise ValueError(f"Out of range: {score}")
    except (ValueError, TypeError):
        logger.warning(
            "Priority analyser: invalid PRIORITY_SCORE '%s'. "
            "Raw response: %r", fields.get("PRIORITY_SCORE"), text,
        )
        return _safe_fallback(text)

    # --- URGENCY ---
    urgency = fields.get("URGENCY", "").upper()
    if urgency not in VALID_URGENCY:
        logger.warning(
            "Priority analyser: unrecognised URGENCY '%s'. Raw response: %r",
            urgency, text,
        )
        return _safe_fallback(text)

    # --- ACTION ---
    action_raw = fields.get("ACTION", "NO").upper()
    if action_raw not in VALID_ACTION:
        logger.warning(
            "Priority analyser: unrecognised ACTION '%s'. Raw response: %r",
            action_raw, text,
        )
        return _safe_fallback(text)
    action_required = action_raw == "YES"

    # --- RISK_LEVEL ---
    risk_level = fields.get("RISK_LEVEL", "").upper()
    if risk_level not in VALID_RISK_LEVEL:
        logger.warning(
            "Priority analyser: unrecognised RISK_LEVEL '%s'. Raw response: %r",
            risk_level, text,
        )
        return _safe_fallback(text)

    # --- CONFIDENCE ---
    try:
        confidence_pct = float(fields.get("CONFIDENCE", "0"))
        if not (0.0 <= confidence_pct <= 100.0):
            raise ValueError(f"Out of range: {confidence_pct}")
        confidence_float = round(confidence_pct / 100.0, 4)
    except (ValueError, TypeError):
        logger.warning(
            "Priority analyser: could not parse CONFIDENCE '%s'. "
            "Defaulting to 0.0. Raw response: %r",
            fields.get("CONFIDENCE"), text,
        )
        confidence_float = 0.0

    # --- REASONING ---
    reasoning = fields.get("REASONING", "")

    # Reconstruct the legacy string so analyze_priority() can return it unchanged.
    legacy_string = (
        f"PRIORITY: {score}/10\n"
        f"URGENCY: {urgency}\n"
        f"ACTION: {'YES' if action_required else 'NO'}"
    )

    return {
        "priority":               legacy_string,
        "priority_score":         score,
        "urgency":                urgency,
        "action_required":        action_required,
        "risk_level":             risk_level,
        "reasoning":              reasoning,
        "ai_confidence_estimate": confidence_float,
        "raw_response":           text,
    }


def _call_analyzer(subject: str, body: str) -> dict:
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
        logger.error("Priority analyser API call failed: %s", exc)
        return _safe_fallback()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_priority(subject: str, body: str) -> str:
    """
    Analyses email priority and returns a plain string in the legacy format.

    Backward-compatible interface used by main.py and monitor.py.
    Returns a string formatted as:
        PRIORITY: X/10
        URGENCY: LOW/MEDIUM/HIGH
        ACTION: YES/NO

    For the full structured result including risk level, reasoning, and
    AI Confidence Estimate, use analyze_priority_detailed() instead.
    """
    return _call_analyzer(subject, body)["priority"]


def analyze_priority_detailed(subject: str, body: str) -> dict:
    """
    Analyses email priority and returns a full structured result dict.

    Intended for the Decision Engine (ai_processing/decision_engine.py)
    and the Streamlit Approval Center dashboard.

    Returns:
        {
          "priority":               str,   # legacy format string
          "priority_score":         int,   # 1–10 (0 on failure)
          "urgency":                str,   # "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN"
          "action_required":        bool,
          "risk_level":             str,   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN"
          "reasoning":              str,   # one-sentence AI rationale
          "ai_confidence_estimate": float, # 0.0 – 1.0
          "raw_response":           str    # raw LLM output for diagnostics
        }

    On API or parse failure, returns safe fallback values with
    priority_score=0 and urgency="UNKNOWN".
    """
    return _call_analyzer(subject, body)