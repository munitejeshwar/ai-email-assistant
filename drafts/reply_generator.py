# drafts/reply_generator.py
#
# Generates an AI draft reply to an email.
#
# Public API (two functions, one shared LLM call):
#
#   generate_reply(sender, subject, body) -> str
#       Original interface. Returns the draft reply as a plain string.
#       Backward compatible — main.py requires no changes.
#
#   generate_reply_detailed(sender, subject, body) -> dict
#       Extended interface for the Decision Engine and Streamlit dashboard.
#       Returns:
#           {
#             "draft_reply":           str,   # the generated reply text
#             "suggested_tone":        str,   # e.g. "Casual", "Professional"
#             "reply_rationale":       str,   # one-sentence explanation of why
#                                            # this reply was generated
#             "ai_confidence_estimate": float, # 0.0 – 1.0
#                                            # (see note below)
#             "raw_response":          str    # raw LLM output for diagnostics
#           }
#
# ai_confidence_estimate note:
#   This is the model's self-reported estimate of how appropriate and
#   contextually accurate the generated reply is for the given email.
#   It is an explainability aid intended for display in the Approval Center
#   and should not be interpreted as a calibrated probability or an
#   objective measure of reply quality. The human reviewer retains full
#   authority to edit or reject the draft regardless of this score.
#
# Canonical location: drafts/reply_generator.py
# Deprecated duplicate: ai_processing/reply_generator.py (shim only)

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
# Valid tone values.
# Any LLM response that does not match one of these is stored as-is with
# a warning — tone is informational, so an unrecognised value does not
# trigger a full fallback.
# ---------------------------------------------------------------------------
VALID_TONES = {
    "Casual", "Professional", "Formal",
    "Empathetic", "Concise", "Apologetic", "Enthusiastic",
}

# Sentinel that separates structured metadata from the multi-line reply body.
REPLY_DELIMITER = "---REPLY---"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(sender: str, subject: str, body: str) -> str:
    """
    Returns the reply generation prompt.

    Design notes:
      - temperature=0 maximises determinism for reliable structured parsing.
      - The prompt preserves the original Muni assistant persona and rules
        verbatim to ensure generate_reply() returns the same style of reply
        as the original implementation.
      - Three metadata fields (TONE, CONFIDENCE, RATIONALE) appear before
        the REPLY_DELIMITER sentinel so they can be parsed as single-line
        prefix fields.
      - The reply body follows the sentinel and may span multiple lines.
      - CONFIDENCE is explicitly labelled as a self-assessed Model Confidence
        estimate, not a calibrated probability, per project terminology.
    """
    return f"""You are Muni's personal AI email assistant.

Generate a SHORT, natural, human-like email reply following ALL rules below.

REPLY RULES:
- Reply as Muni's AI assistant
- Sound natural and friendly
- Keep under 5 sentences
- Never sound robotic or use corporate language
- Reply casually if the message is friend-like
- Never use placeholders like [Your Name]
- If someone asks for contact details, Instagram, or social media, include:
    Instagram: @muni_tejeshwar
- Always include: "Thank you for contacting Muni. This AI assistant received
  your email successfully. Muni will respond shortly."

Before the reply, provide three metadata fields on separate lines:
TONE: <one word or short phrase describing the tone — e.g. Casual, Professional, Empathetic>
CONFIDENCE: <integer 0-100; your self-assessed Model Confidence estimate that this reply
             is appropriate and contextually accurate for the given email.
             This is an explainability aid, not a calibrated probability.>
RATIONALE: <one concise sentence explaining why you chose this tone and approach>

Then write EXACTLY the following delimiter on its own line:
{REPLY_DELIMITER}

Then write the reply text (may be multiple lines).

Example format:
TONE: Casual
CONFIDENCE: 82
RATIONALE: The email is an informal greeting from a friend, so a warm casual reply is most appropriate.
{REPLY_DELIMITER}
Hey! Thanks for reaching out — really appreciate it. Muni will get back to you soon!
Thank you for contacting Muni. This AI assistant received your email successfully. Muni will respond shortly.

EMAIL DETAILS:

FROM:
{sender}

SUBJECT:
{subject}

BODY:
{body}
"""


def _safe_fallback(raw_response: str = "") -> dict:
    """
    Returns a safe default result when the API call or parser fails.
    draft_reply="" signals to downstream consumers that generation failed.
    """
    return {
        "draft_reply":           "",
        "suggested_tone":        "Unknown",
        "reply_rationale":       "",
        "ai_confidence_estimate": 0.0,
        "raw_response":          raw_response,
    }


def _parse_response(text: str) -> dict:
    """
    Parses the LLM's structured reply response.

    Strategy:
      - Split the response on the REPLY_DELIMITER sentinel.
      - Everything before the delimiter is parsed as single-line prefix
        fields (TONE, CONFIDENCE, RATIONALE).
      - Everything after the delimiter is the reply body (may be multi-line).
      - If the delimiter is absent, the full response is treated as the
        reply body and metadata defaults are applied (graceful degradation).
      - CONFIDENCE is validated as 0–100 and normalised to 0.0–1.0.
      - An unrecognised TONE is accepted with a warning (non-fatal).
      - No exception is raised on failure; _safe_fallback() is returned.
    """
    # Split on delimiter
    if REPLY_DELIMITER in text:
        meta_block, _, reply_block = text.partition(REPLY_DELIMITER)
    else:
        logger.warning(
            "Reply generator: delimiter '%s' not found. "
            "Using full response as reply. Raw response: %r",
            REPLY_DELIMITER, text,
        )
        # Graceful degradation — return the full text as the reply.
        return {
            "draft_reply":           text.strip(),
            "suggested_tone":        "Unknown",
            "reply_rationale":       "",
            "ai_confidence_estimate": 0.0,
            "raw_response":          text,
        }

    # --- Parse metadata fields ---
    meta_fields = {}
    for line in meta_block.strip().splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            meta_fields[key.strip().upper()] = value.strip()

    # TONE
    suggested_tone = meta_fields.get("TONE", "Unknown")
    if suggested_tone not in VALID_TONES:
        logger.warning(
            "Reply generator: unrecognised TONE '%s'. Storing as-is.", suggested_tone,
        )

    # CONFIDENCE
    try:
        confidence_pct = float(meta_fields.get("CONFIDENCE", "0"))
        if not (0.0 <= confidence_pct <= 100.0):
            raise ValueError(f"Out of range: {confidence_pct}")
        confidence_float = round(confidence_pct / 100.0, 4)
    except (ValueError, TypeError):
        logger.warning(
            "Reply generator: could not parse CONFIDENCE '%s'. Defaulting to 0.0.",
            meta_fields.get("CONFIDENCE"),
        )
        confidence_float = 0.0

    # RATIONALE
    reply_rationale = meta_fields.get("RATIONALE", "")

    # --- Parse reply body ---
    draft_reply = reply_block.strip()
    if not draft_reply:
        logger.warning(
            "Reply generator: reply body is empty after delimiter. "
            "Raw response: %r", text,
        )
        return _safe_fallback(text)

    return {
        "draft_reply":           draft_reply,
        "suggested_tone":        suggested_tone,
        "reply_rationale":       reply_rationale,
        "ai_confidence_estimate": confidence_float,
        "raw_response":          text,
    }


def _call_reply_generator(sender: str, subject: str, body: str) -> dict:
    """
    Makes the LLM API call and returns the parsed structured result.
    Both public functions delegate here — only one API request per call.
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": _build_prompt(sender, subject, body)}],
        )
        raw_text = response.choices[0].message.content
        return _parse_response(raw_text)

    except Exception as exc:
        logger.error("Reply generator API call failed: %s", exc)
        return _safe_fallback()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_reply(sender: str, subject: str, body: str) -> str:
    """
    Generates an AI draft reply and returns it as a plain string.

    Backward-compatible interface used by main.py.
    Returns the reply text only, with no metadata fields.

    For the full structured result including suggested tone, rationale,
    and AI Confidence Estimate, use generate_reply_detailed() instead.
    """
    return _call_reply_generator(sender, subject, body)["draft_reply"]


def generate_reply_detailed(sender: str, subject: str, body: str) -> dict:
    """
    Generates an AI draft reply and returns a full structured result dict.

    Intended for the Decision Engine (ai_processing/decision_engine.py)
    and the Streamlit Approval Center dashboard.

    Returns:
        {
          "draft_reply":           str,   # the generated reply text
          "suggested_tone":        str,   # e.g. "Casual", "Professional"
          "reply_rationale":       str,   # one-sentence generation rationale
          "ai_confidence_estimate": float, # 0.0 – 1.0
                                          # This is the model's self-reported
                                          # estimate of how appropriate the reply
                                          # is for the given email context.
                                          # It is an explainability aid and should
                                          # not be interpreted as a calibrated
                                          # probability or objective quality metric.
                                          # Human review and approval remains
                                          # mandatory regardless of this score.
          "raw_response":          str    # raw LLM output for diagnostics
        }

    On API or parse failure, returns safe fallback values:
        draft_reply="", suggested_tone="Unknown",
        reply_rationale="", ai_confidence_estimate=0.0.
    """
    return _call_reply_generator(sender, subject, body)
