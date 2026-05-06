from __future__ import annotations

import re

REPLACEMENT_CHAR = "\ufffd"
MOJIBAKE_RE = re.compile(r"(?:Γƒ.|Γ‚.|Γ.|Γ.|ΓΆβ‚¬.|ΓΆβ‚¬Ε“|ΓΆβ‚¬β„Ά|ΓΆβ‚¬\x9d)")
C1_CONTROL_RE = re.compile(r"[\u0080-\u009f]")
QUESTION_RUN_RE = re.compile(r"\?{3,}")


def detect_text_issues(text: str) -> list[str]:
    issues: list[str] = []
    if not text:
        return issues
    if REPLACEMENT_CHAR in text:
        issues.append("replacement_character")
    if C1_CONTROL_RE.search(text):
        issues.append("c1_control_character")
    if MOJIBAKE_RE.search(text):
        issues.append("mojibake_pattern")
    if QUESTION_RUN_RE.search(text) and "http" not in text:
        issues.append("question_mark_run")
    return issues
