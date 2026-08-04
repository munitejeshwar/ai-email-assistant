# ai_processing/reply_generator.py
#
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — DO NOT USE IN NEW CODE                            ║
# ║                                                                  ║
# ║  This module is a duplicate of drafts/reply_generator.py        ║
# ║  and will be deleted once all imports have been confirmed        ║
# ║  migrated to the canonical location.                            ║
# ║                                                                  ║
# ║  Migration path:                                                 ║
# ║    OLD: from ai_processing.reply_generator import generate_reply ║
# ║    NEW: from drafts.reply_generator import generate_reply        ║
# ╚══════════════════════════════════════════════════════════════════╝

import warnings

warnings.warn(
    "ai_processing.reply_generator is deprecated and will be removed. "
    "Import from drafts.reply_generator instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export the canonical implementation so any accidental import
# continues to work without silently running stale code.
from drafts.reply_generator import generate_reply  # noqa: F401, E402

__all__ = ["generate_reply"]
