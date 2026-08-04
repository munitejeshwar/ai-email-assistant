# ai_processing/priority.py
#
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — DO NOT USE IN NEW CODE                            ║
# ║                                                                  ║
# ║  This module is a duplicate of ai_processing/priority_analyzer  ║
# ║  and will be deleted once all imports have been migrated.        ║
# ║                                                                  ║
# ║  Migration path:                                                 ║
# ║    OLD: from ai_processing.priority import analyze_priority      ║
# ║    NEW: from ai_processing.priority_analyzer import              ║
# ║             analyze_priority                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

import warnings

warnings.warn(
    "ai_processing.priority is deprecated and will be removed. "
    "Import from ai_processing.priority_analyzer instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export the canonical implementation so existing callers continue to
# work without modification until their imports are updated (Phase 0, Step 5).
from ai_processing.priority_analyzer import analyze_priority  # noqa: F401, E402

__all__ = ["analyze_priority"]