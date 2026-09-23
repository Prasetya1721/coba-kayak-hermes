"""Sensitive-data detection and masking (PRD §7.1).

This module is intentionally dependency-free and pure so it can be reused by
HTTP middleware, logging, AI-tool inputs, and tests.

Guarantees:
  * Credit card numbers are masked preserving the last 4 digits.
  * Indonesian NIK (16 digits) is masked, preserving the last 4 digits.
  * Passwords / secrets / tokens are fully redacted.
  * Medical / health keywords are flagged so callers can decide to withhold.
  * Scrubbing is deterministic and idempotent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MASK = "[REDACTED]"

# --- Patterns -----------------------------------------------------------------

# 13-19 digit card numbers, optionally separated by spaces or dashes.
# Must start and end with a digit so trailing separators are not consumed.
# A Luhn check is applied afterwards to avoid masking arbitrary long numbers.
_CC_CANDIDATE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")

_NIK = re.compile(r"\b\d{16}\b")

# key = value / key: value assignments for secret-ish keys.
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|pass|secret|token|api[_-]?key|apikey|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret|private[_-]?key|auth|credential|pin|otp"
    r")\b\s*[:=]\s*(['\"]?)([^\s'\"&,;]+)\2"
)

# Bearer / basic authorization headers.
_AUTH_HEADER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}")

# PEM private keys.
_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)

# Email: partial mask keeping first char + domain.
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")

# Indonesian phone numbers (+62 / 08xx).
_PHONE_ID = re.compile(r"(?<!\d)(?:\+62|62|0)8\d{1,3}[\s-]?\d{3,4}[\s-]?\d{3,5}(?!\d)")

# Medical / health indicators (flagged, not auto-masked by default).
_MEDICAL_TERMS = re.compile(
    r"(?i)\b("
    r"diagnosis|diagnosa|resep|obat|dosis|hiv|aids|kanker|cancer|diabetes|"
    r"hipertensi|asma|tuberkulosis|tbc|kolesterol|hasil lab|rekam medis|"
    r"riwayat penyakit|alergi|kehamilan|psikologi|psikiater|depresi"
    r")\b"
)


@dataclass
class ScrubResult:
    """Outcome of scrubbing a single string."""

    original: str
    scrubbed: str
    detections: list[str] = field(default_factory=list)
    medical_flag: bool = False

    @property
    def changed(self) -> bool:
        return self.original != self.scrubbed


def _luhn_ok(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 13:
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _mask_keep_last4(value: str, keep: int = 4) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) <= keep:
        return "*" * len(digits)
    masked = "*" * (len(digits) - keep) + digits[-keep:]
    # Preserve the original grouping flavour when separators were used.
    if "-" in value:
        return f"****-****-****-{digits[-keep:]}"
    return masked


def scrub_text(text: str, *, flag_medical: bool = True) -> str:
    """Return `text` with sensitive substrings masked.

    Idempotent: scrubbing an already-scrubbed string is a no-op.
    """
    if not text:
        return text

    result = text

    result = _PEM.sub(MASK, result)
    result = _AUTH_HEADER.sub(lambda m: f"{m.group(1)} {MASK}", result)
    result = _SECRET_ASSIGNMENT.sub(
        lambda m: f"{m.group(1)}{m.group(2) or ''}{MASK}{m.group(2) or ''}", result
    )

    def _cc_sub(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if _luhn_ok(digits):
            return _mask_keep_last4(raw)
        return raw

    result = _CC_CANDIDATE.sub(_cc_sub, result)
    result = _NIK.sub(lambda m: _mask_keep_last4(m.group(0)), result)
    result = _PHONE_ID.sub(lambda m: _mask_keep_last4(m.group(0)), result)
    result = _EMAIL.sub(lambda m: f"{m.group(1)}***{m.group(2)}", result)

    _ = flag_medical  # reserved: medical masking policy is owned by callers
    return result


def scrub_text_detailed(text: str) -> ScrubResult:
    """Like `scrub_text` but reports which categories were detected."""
    if not text:
        return ScrubResult(original=text, scrubbed=text)

    detections: list[str] = []
    if _PEM.search(text):
        detections.append("private_key")
    if _AUTH_HEADER.search(text):
        detections.append("auth_header")
    if _SECRET_ASSIGNMENT.search(text):
        detections.append("secret_assignment")
    if any(_luhn_ok(re.sub(r"\D", "", m.group(0))) for m in _CC_CANDIDATE.finditer(text)):
        detections.append("credit_card")
    if _NIK.search(text):
        detections.append("nik")
    if _PHONE_ID.search(text):
        detections.append("phone_id")
    if _EMAIL.search(text):
        detections.append("email")

    medical = bool(_MEDICAL_TERMS.search(text))
    return ScrubResult(
        original=text,
        scrubbed=scrub_text(text),
        detections=detections,
        medical_flag=medical,
    )


def scrub_value(value: Any) -> Any:
    """Recursively scrub strings inside dict/list structures."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: scrub_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_value(v) for v in value]
    return value


def contains_medical(text: str) -> bool:
    return bool(_MEDICAL_TERMS.search(text or ""))
