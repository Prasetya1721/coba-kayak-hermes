"""Permanent memory: long-term facts about the user.

Two capture paths:
  1. Explicit: user says "ingat ya ..." / "lupakan ..." — handled deterministically
     with regex, no LLM call needed. Always honoured, even offline.
  2. Extracted: after each assistant turn, a cheap LLM pass pulls durable facts
     ("nama saya X", "ulang tahun ...", "punya server ...") from the message pair.

Both store AES-256-GCM ciphertext via the shared crypto module. Recall injects
decrypted facts into the system prompt of every turn (bounded: latest 30).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.logging import get_logger
from app.db.models import UserMemory

log = get_logger(__name__)

MAX_RECALL = 30

# "ingat ya ...", "ingat-ingat ...", "tolong ingat ..."
_REMEMBER = re.compile(
    r"(?i)\b(?:tolong\s+)?ingat(?:-ingat|kan)?(?:\s+ya|\s+dong|\s+nih)?[,:]?\s+(.+)$"
)
# "lupakan ...", "lupa aja ...", "hapus ingatan tentang ..."
_FORGET = re.compile(r"(?i)\blup(?:akan|a(?:in| aja)?)\b(?:\s+tentang)?\s*(.+)?$")

# Heuristics for auto-extraction (Indonesian + English).
_FACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # "nama saya X", "namaku X", "nama gue X"
    ("nama", re.compile(r"(?i)\bnamaku\s+(.{2,60})")),
    ("nama", re.compile(r"(?i)\bnama\s+(?:saya|aku|gue|gw|ku)\s+(?:adalah\s+|itu\s+)?(.{2,60})")),
    ("nama", re.compile(r"(?i)\bpanggil\s+(?:saya|aku|gue|gw)\s+(?:dengan\s+)?(.{2,40})")),
    # "ulang tahunku X", "ultahku X"
    ("ulang_tahun", re.compile(r"(?i)\b(?:ulang\s+tahun|ultah)ku\s+(?:tanggal\s+|pada\s+)?(.{2,40})")),
    ("ulang_tahun", re.compile(r"(?i)\bulang\s+tahun\s+(?:saya|aku|gue|gw)\s+(?:tanggal\s+)?(.{2,40})")),
    # "aku tinggal di X", "aku dari X"
    ("kota", re.compile(r"(?i)\b(?:tinggal|berada|domisili)\s+di\s+(.{2,60})")),
    ("kota", re.compile(r"(?i)\baku\s+(?:orang|dari)\s+(.{2,40})")),
    # pekerjaan
    ("pekerjaan", re.compile(r"(?i)\b(?:aku|saya|gue|gw)\s+(?:bekerja\s+sebagai|kerja\s+sebagai|kerja\s+di|profesiku|profesinya)\s+(.{2,60})")),
    # preferensi (suka / nggak suka)
    ("preferensi", re.compile(r"(?i)\b(?:aku|saya|gue|gw)\s+(?:nggak|gak|tidak)\s+suka\s+(.{2,80})")),
    ("preferensi", re.compile(r"(?i)\b(?:aku|saya|gue|gw)\s+suka\s+(.{2,80})")),
    ("preferensi", re.compile(r"(?i)\b(?:kesukaanku|favoritku)\s+(?:adalah\s+)?(.{2,80})")),
    # perangkat
    ("perangkat", re.compile(r"(?i)\b(?:server|vps|komputer|laptop|hp)\s+(?:ku|saya|aku|gue|gw)\s*(?:di|ip|dengan|adalah|bernama)?\s*([\w.\-:]{3,80})")),
    # English
    ("nama", re.compile(r"(?i)\bmy\s+name\s+is\s+(.{2,60})")),
    ("nama", re.compile(r"(?i)\bcall\s+me\s+(.{2,40})")),
    ("ulang_tahun", re.compile(r"(?i)\bmy\s+birthday\s+(?:is\s+|on\s+)?(.{2,40})")),
    ("kota", re.compile(r"(?i)\bi\s+live\s+in\s+(.{2,60})")),
]

_KEY_LABELS = {
    "nama": "Nama",
    "name": "Nama",
    "ulang_tahun": "Ulang tahun",
    "birthday": "Ulang tahun",
    "kota": "Kota",
    "pekerjaan": "Pekerjaan",
    "preferensi": "Suka/tidak suka",
    "perangkat": "Perangkat",
}


def _clean(value: str) -> str:
    value = value.strip().strip(".,!?\"'").strip()
    # Cut trailing clauses: "Prasetya dan aku suka kopi" -> "Prasetya"
    for sep in (" dan aku ", " dan saya ", " dan gue ", " dan gw ", ", aku ", ", saya "):
        idx = value.lower().find(sep)
        if idx > 0:
            value = value[:idx].strip()
            break
    return value[:200]


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- CRUD ---------------------------------------------------------------

    async def list(self, user_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.updated_at.desc())
            .limit(200)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [
            {
                "id": str(r.id),
                "key": r.key,
                "value": self._safe_decrypt(r.value_encrypted),
                "source": r.source,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    async def save(
        self, user_id: uuid.UUID, key: str, value: str, source: str = "explicit"
    ) -> dict:
        value = _clean(value)
        if not value:
            raise ValueError("Nilai ingatan kosong.")
        key = key.strip().lower()[:50] or "catatan"

        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id, UserMemory.key == key
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.value_encrypted = encrypt(value)
            existing.source = source
            await self.session.flush()
            row = existing
        else:
            row = UserMemory(
                user_id=user_id,
                key=key,
                value_encrypted=encrypt(value),
                source=source,
            )
            self.session.add(row)
            await self.session.flush()
        return {
            "id": str(row.id),
            "key": row.key,
            "value": value,
            "source": row.source,
        }

    async def delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(UserMemory).where(
                UserMemory.id == memory_id, UserMemory.user_id == user_id
            )
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def delete_by_key(self, user_id: uuid.UUID, key: str) -> int:
        result = await self.session.execute(
            delete(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.key == key.strip().lower(),
            )
        )
        await self.session.flush()
        return result.rowcount or 0

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(UserMemory).where(UserMemory.user_id == user_id)
        )
        return result.rowcount or 0

    # --- Recall ---------------------------------------------------------------

    async def recall_block(self, user_id: uuid.UUID) -> str:
        """Render stored facts as a prompt block (empty string if none)."""
        items = await self.list(user_id)
        if not items:
            return ""
        lines = []
        for m in items[:MAX_RECALL]:
            label = _KEY_LABELS.get(m["key"], m["key"].replace("_", " ").title())
            lines.append(f"- {label}: {m['value']}")
        return (
            "HAL-HAL YANG KAMU INGAT TENTANG PENGGUNA "
            "(gunakan secara natural, jangan sebutkan daftar ini mentah-mentah):\n"
            + "\n".join(lines)
        )

    # --- Capture ---------------------------------------------------------------

    def parse_explicit_command(self, text: str) -> dict | None:
        """Return {action, value} for ingat/lupakan, else None."""
        m = _REMEMBER.search(text or "")
        if m and _clean(m.group(1)):
            return {"action": "remember", "value": _clean(m.group(1))}
        m = _FORGET.search(text or "")
        if m:
            return {"action": "forget", "value": _clean(m.group(1) or "")}
        return None

    def extract_facts(self, user_text: str) -> list[tuple[str, str]]:
        """Heuristic fact extraction from one user message."""
        facts: list[tuple[str, str]] = []
        for key, pattern in _FACT_PATTERNS:
            m = pattern.search(user_text or "")
            if m:
                value = _clean(m.group(1))
                if value and len(value) >= 2:
                    facts.append((key, value))
        return facts

    @staticmethod
    def _safe_decrypt(blob: bytes) -> str:
        try:
            return decrypt(blob)
        except Exception:  # noqa: BLE001
            return "[unable to decrypt]"
