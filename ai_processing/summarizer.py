# ai_processing/summarizer.py
#
# Summarises an email into concise bullet points.
#
# Public API (two functions, one shared LLM call):
#
#   summarize_email(email_text) -> str
#       Original interface. Returns the bullet-point summary as a plain string.
#       Backward compatible — main.py and monitor.py require no changes.
#       Accepts the same argument as the original: either a plain string or the
#       full parsed email dict (both are embedded directly into the prompt).
#
#   summarize_email_detailed(email_text) -> dict
#       Extended interface for the Decision Engine and Streamlit dashboard.
#       Returns:
#           {
#             "summary":       str,   # bullet-point summary text
#             "quality_score": float, # 0.0 – 1.0; model's self-assessed
#                                     # summarisability rating (see note below)
#             "raw_response":  str    # raw LLM output for diagnostics
#           }
#
# quality_score note:
#   quality_score is the model's self-assessed estimate of how well the email
#   could be summarised (e.g. a clear, structured email scores higher than a
#   vague or very short one). It is an explainability aid and should not be
#   interpreted as an objective or statistically validated measure of summary
#   quality.

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
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(email_text) -> str:
    """
    Returns the summariser prompt.

    Design notes:
      - temperature=0 maximises determinism for reliable parsing.
      - The QUALITY_SCORE sentinel line acts as a clean boundary between the
        multi-line summary block and the scalar score field, allowing the
        parser to split on it without needing start/end section markers.
      - The quality score is defined as summarisability (how well-structured
        and summarisable the source email is), not summary accuracy.
      - The prompt instructs the model to place QUALITY_SCORE on the very
        last line to keep the parsing logic simple and robust.
    """
    return f"""You are an email summarisation assistant.

Summarise the email below in exactly 3 concise bullet points.
Each bullet point must begin with "•".

After the 3 bullet points, on a new line, provide your self-assessed
quality score for this summarisation on a scale of 0 to 100, where:
  100 = the email was clear and easy to summarise accurately
    0 = the email was too vague, sparse, or ambiguous to summarise well

This quality score reflects the summarisability of the email content,
not the accuracy of the summary itself. It is used for explainability only.

Respond in EXACTLY this format:
• <first bullet point>
• <second bullet point>
• <third bullet point>
QUALITY_SCORE: <0-100>

EMAIL:
{email_text}
"""


def _safe_fallback(raw_response: str = "") -> dict:
    """
    Returns a safe default result when the API call or parser fails.
    An empty summary string and quality_score=0.0 signal to downstream
    consumers that this result should be treated as unavailable.
    """
    return {
        "summary":       "",
        "quality_score": 0.0,
        "raw_response":  raw_response,
    }


def _parse_response(text: str) -> dict:
    """
    Parses the LLM's structured summary response.

    Strategy:
      - Find the last line that begins with "QUALITY_SCORE:" (case-insensitive).
      - Everything before that line is treated as the summary block.
      - The integer on the QUALITY_SCORE line is validated and normalised
        to a 0.0–1.0 float.
      - If no QUALITY_SCORE line is found, the full response is used as
        the summary and quality_score defaults to 0.0 (graceful degradation).
      - No exception is ever raised; failures return _safe_fallback().
    """
    lines = text.strip().splitlines()

    quality_score_float = 0.0
    quality_score_line_index = None

    # Scan lines in reverse — QUALITY_SCORE is always the last line.
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().upper().startswith("QUALITY_SCORE:"):
            quality_score_line_index = i
            raw_score = lines[i].split(":", 1)[1].strip()
            try:
                score = float(raw_score)
                if not (0.0 <= score <= 100.0):
                    raise ValueError(f"Out of range: {score}")
                quality_score_float = round(score / 100.0, 4)
            except (ValueError, TypeError):
                logger.warning(
                    "Summariser: could not parse QUALITY_SCORE '%s'. "
                    "Defaulting to 0.0. Raw response: %r", raw_score, text,
                )
            break  # found the sentinel; stop scanning

    # Extract summary lines (everything before the QUALITY_SCORE sentinel).
    if quality_score_line_index is not None:
        summary_lines = lines[:quality_score_line_index]
    else:
        # No sentinel found — treat entire response as summary (graceful degradation).
        logger.warning(
            "Summariser: QUALITY_SCORE sentinel not found. "
            "Using full response as summary. Raw response: %r", text,
        )
        summary_lines = lines

    summary = "\n".join(line for line in summary_lines if line.strip())

    if not summary:
        logger.warning(
            "Summariser: parsed summary is empty. Raw response: %r", text,
        )
        return _safe_fallback(text)

    return {
        "summary":       summary,
        "quality_score": quality_score_float,
        "raw_response":  text,
    }


def _call_summarizer(email_text) -> dict:
    """
    Makes the LLM API call and returns the parsed structured result.
    Both public functions delegate here — only one API request per call.
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": _build_prompt(email_text)}],
        )
        raw_text = response.choices[0].message.content
        return _parse_response(raw_text)

    except Exception as exc:
        logger.error("Summariser API call failed: %s", exc)
        return _safe_fallback()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_email(email_text) -> str:
    """
    Summarises an email and returns the bullet-point summary as a plain string.

    Backward-compatible interface used by main.py and monitor.py.
    Accepts the same argument type as the original implementation: a plain
    string or the full parsed email dict (both are embedded into the prompt).

    Returns the summary text (3 bullet points), or an empty string on failure.

    For the full structured result including quality_score and raw_response,
    use summarize_email_detailed() instead.
    """
    return _call_summarizer(email_text)["summary"]


def summarize_email_detailed(email_text) -> dict:
    """
    Summarises an email and returns a full structured result dict.

    Intended for the Decision Engine (ai_processing/decision_engine.py)
    and the Streamlit Approval Center dashboard.

    Returns:
        {
          "summary":       str,   # 3 bullet-point summary (plain text)
          "quality_score": float, # 0.0 – 1.0; model's self-assessed estimate
                                  # of how well the email could be summarised.
                                  # This is an explainability aid and should not
                                  # be interpreted as an objective or statistically
                                  # validated measure of summary quality.
          "raw_response":  str    # raw LLM output for diagnostics
        }

    On API or parse failure, returns safe fallback values:
        summary="", quality_score=0.0, raw_response="".
    """
    return _call_summarizer(email_text)