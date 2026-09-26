"""Permanent memory: long-term facts about the user.

Two capture paths:
  1. Explicit: user says "ingat ya ..." / "lupakan ..." — handled deterministically
     with regex, no LLM call needed. Always honoured, even offline.
  2. Extracted: heuristic patterns pull durable facts (personal, project
     context, coding preferences) from each user message.

Scopes: "global" (default), "proyek:<name>" (project context), "kode" (coding
preferences). Recall merges global + matching project scope so per-project
context never leaks into unrelated chats.

Session summaries (SessionSummary rows) compress old history into an encrypted
rolling summary — the long-term bridge so the agent stays coherent across
sessions and weeks.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.logging import get_logger
from app.db.models import SessionSummary, UserMemory

log = get_logger(__name__)

MAX_RECALL = 30

# A session is summarized once it grows past this many messages; the newest
# window is always kept verbatim for the short-term context.
SUMMARIZE_AFTER_MESSAGES = 40
SUMMARY_KEEP_RECENT = 10

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
    # konteks proyek: "lagi ngerjain proyek PMS", "projectku namanya X",
    # "repo PMS di ..." — scope proyek:<nama>. Kata umum ("dong", "itu", "ini")
    # tidak dianggap nama proyek.
    ("proyek", re.compile(r"(?i)\bproyek(?:ku| saya)?\s+(?:namanya|bernama|itu|yang\s+berjudul)?\s*([A-Za-z0-9][A-Za-z0-9_\-]{1,29})")),
    ("proyek", re.compile(r"(?i)\bproject(?:ku| saya)?\s+(?:namanya|bernama|itu|called)?\s*([A-Za-z0-9][A-Za-z0-9_\-]{1,29})")),
    ("proyek", re.compile(r"(?i)\blagi\s+(?:ngerjain|garap|kerjain)\s+(?:proyek|project)\s+([A-Za-z0-9][A-Za-z0-9_\-]{1,29})")),
    ("proyek", re.compile(r"(?i)\brepo(?:ku|saya)?\s+(?:di|ada\s+di|namanya)?\s*([A-Za-z0-9 _\-\/\.]{2,80})")),
    # preferensi kode: "aku pake python", "biasanya pake tabs", "jangan pake X"
    ("kode", re.compile(r"(?i)\b(?:aku|saya|gue|gw)\s+(?:pake|pakai|biasanya\s+(?:pake|pakai))\s+(.{2,80})")),
    ("kode", re.compile(r"(?i)\b(?:jangan|tolong\s+jangan)\s+(?:pake|pakai)\s+(.{2,80})")),
    ("kode", re.compile(r"(?i)\bcoding\s+(?:style|aturan|kesepakatan)(?:ku| saya)?\s*[:\-]?\s*(.{2,120})")),
    ("kode", re.compile(r"(?i)\b(?:preferensi|preference)\s+(?:kode|coding)(?:ku| saya)?\s*[:\-]?\s*(.{2,120})")),
    # English
    ("nama", re.compile(r"(?i)\bmy\s+name\s+is\s+(.{2,60})")),
    ("nama", re.compile(r"(?i)\bcall\s+me\s+(.{2,40})")),
    ("ulang_tahun", re.compile(r"(?i)\bmy\s+birthday\s+(?:is\s+|on\s+)?(.{2,40})")),
    ("kota", re.compile(r"(?i)\bi\s+live\s+in\s+(.{2,60})")),
    ("proyek", re.compile(r"(?i)\bworking\s+on\s+(?:project\s+)?([A-Za-z0-9 _\-]{2,60})")),
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
    "proyek": "Proyek",
    "kode": "Preferensi kode",
}

# Keys whose values always land in a non-global scope.
_SCOPE_BY_KEY = {
    "proyek": "proyek",
    "kode": "kode",
}


def infer_scope(key: str, value: str) -> str:
    """Map a memory key/value to its scope.

    Project facts ("proyek PMS") get their own scope so context never leaks
    across projects; coding preferences go to the shared "kode" scope.
    """
    if key in _SCOPE_BY_KEY:
        if key == "proyek":
            name = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:40]
            return f"proyek:{name}" if name else "proyek:umum"
        return _SCOPE_BY_KEY[key]
    return "global"


# Filler/panggilan yang bukan bagian dari fakta. Harus kata utuh (didahului
# spasi) supaya "semuanya" tidak terpotong jadi "semuan".
_FILLER_TAIL = re.compile(
    r"(?i)(?<=\s),?\s*(dong|ya|yaa|nih|sih|deh|kok|lah|kah|kan|please|plis|tolong)\s*$"
)
# Nilai yang terlalu umum untuk dijadikan ingatan.
_STOPWORDS = {
    "", "dong", "ya", "oke", "ok", "iya", "hai", "halo", "tes", "test",
    "hi", "hey", "siap", "sip", "mantap", "thanks", "makasih",
}


def _clean(value: str) -> str:
    value = value.strip().strip(".,!?\"'").strip()
    # Cut trailing clauses: "Prasetya dan aku suka kopi" -> "Prasetya"
    for sep in (" dan aku ", " dan saya ", " dan gue ", " dan gw ", ", aku ", ", saya "):
        idx = value.lower().find(sep)
        if idx > 0:
            value = value[:idx].strip()
            break
    # Drop trailing fillers: "PMS testing dong" -> "PMS testing"
    value = _FILLER_TAIL.sub("", value).strip()
    return value[:200]


def is_junk_value(value: str) -> bool:
    """True when a value is too short/generic to be a useful memory."""
    v = _clean(value).lower()
    return v in _STOPWORDS or len(v) < 2


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- CRUD ---------------------------------------------------------------

    async def list(
        self, user_id: uuid.UUID, scope: str | None = None
    ) -> list[dict]:
        stmt = select(UserMemory).where(UserMemory.user_id == user_id)
        if scope is not None:
            stmt = stmt.where(UserMemory.scope == scope)
        stmt = stmt.order_by(UserMemory.updated_at.desc()).limit(200)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [
            {
                "id": str(r.id),
                "key": r.key,
                "value": self._safe_decrypt(r.value_encrypted),
                "source": r.source,
                "scope": r.scope,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    async def save(
        self,
        user_id: uuid.UUID,
        key: str,
        value: str,
        source: str = "explicit",
        scope: str | None = None,
    ) -> dict:
        value = _clean(value)
        if not value:
            raise ValueError("Nilai ingatan kosong.")
        if is_junk_value(value):
            raise ValueError(
                f"Nilai '{value}' terlalu umum untuk disimpan sebagai ingatan."
            )
        key = key.strip().lower()[:50] or "catatan"
        scope = scope or infer_scope(key, value)

        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.key == key,
            UserMemory.scope == scope,
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
                scope=scope,
            )
            self.session.add(row)
            await self.session.flush()
        return {
            "id": str(row.id),
            "key": row.key,
            "value": value,
            "source": row.source,
            "scope": row.scope,
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

    async def delete_by_scope(self, user_id: uuid.UUID, scope: str) -> int:
        """Delete all memories in a scope (e.g. "proyek:pms" or "kode")."""
        result = await self.session.execute(
            delete(UserMemory).where(
                UserMemory.user_id == user_id, UserMemory.scope == scope
            )
        )
        await self.session.flush()
        return result.rowcount or 0

    async def delete_matching(self, user_id: uuid.UUID, keyword: str) -> int:
        """Delete memories whose key, value, or scope mentions `keyword`."""
        kw = (keyword or "").strip().lower()
        if not kw:
            return 0
        removed = 0
        for m in await self.list(user_id):
            haystack = (
                f"{m['key']} {m['value']} {m.get('scope', '')}".lower()
                .replace(":", " ")
                .replace("_", " ")
            )
            if kw in haystack:
                mid = m["id"]
                mid = uuid.UUID(mid) if isinstance(mid, str) else mid
                if await self.delete(user_id, mid):
                    removed += 1
        return removed

    async def scopes(self, user_id: uuid.UUID) -> list[str]:
        """Distinct scopes the user has memories in."""
        stmt = (
            select(UserMemory.scope)
            .where(UserMemory.user_id == user_id)
            .distinct()
        )
        return [r[0] for r in (await self.session.execute(stmt)).all()]

    # --- Recall ---------------------------------------------------------------

    async def recall_block(
        self, user_id: uuid.UUID, project_scope: str | None = None
    ) -> str:
        """Render stored facts as a prompt block (empty string if none).

        Merges global + kode scopes with the active project scope so
        per-project context never leaks into unrelated chats.
        """
        items = await self.list(user_id)
        if not items:
            return ""
        wanted = {"global", "kode"}
        if project_scope:
            wanted.add(project_scope)
        lines = []
        for m in items:
            if m.get("scope", "global") not in wanted:
                continue
            label = _KEY_LABELS.get(m["key"], m["key"].replace("_", " ").title())
            scope_tag = (
                f" [{m['scope']}]"
                if m.get("scope", "global") not in ("global",)
                else ""
            )
            lines.append(f"- {label}{scope_tag}: {m['value']}")
            if len(lines) >= MAX_RECALL:
                break
        if not lines:
            return ""
        return (
            "HAL-HAL YANG KAMU INGAT TENTANG PENGGUNA "
            "(gunakan secara natural, jangan sebutkan daftar ini mentah-mentah):\n"
            + "\n".join(lines)
        )

    @staticmethod
    def detect_project_scope(text: str) -> str | None:
        """Guess the active project from a message ("PMS", "proyek X")."""
        m = re.search(
            r"(?i)\b(?:proyek|project|repo)\s+([A-Za-z0-9][A-Za-z0-9_\-]{0,29})",
            text or "",
        )
        if not m:
            return None
        name = re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")
        if name in ("ini", "itu", "tersebut", "saya", "aku", "yang", "the", "this"):
            return None
        return f"proyek:{name}" if name else None

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
        """Heuristic fact extraction from one user message (junk filtered)."""
        facts: list[tuple[str, str]] = []
        for key, pattern in _FACT_PATTERNS:
            m = pattern.search(user_text or "")
            if m:
                value = _clean(m.group(1))
                if value and not is_junk_value(value):
                    facts.append((key, value))
        return facts

    # --- Session summaries (long-term bridge) ----------------------------------

    async def get_summary(self, session_id: uuid.UUID) -> dict | None:
        """Return the newest summary for a session, decrypted."""
        stmt = (
            select(SessionSummary)
            .where(SessionSummary.session_id == session_id)
            .order_by(SessionSummary.created_at.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": str(row.id),
            "summary": self._safe_decrypt(row.summary_encrypted),
            "messages_covered": row.messages_covered,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def save_summary(
        self, user_id: uuid.UUID, session_id: uuid.UUID, summary: str, covered: int
    ) -> dict:
        summary = summary.strip()[:4000]
        if not summary:
            raise ValueError("Ringkasan kosong.")
        row = SessionSummary(
            user_id=user_id,
            session_id=session_id,
            summary_encrypted=encrypt(summary),
            messages_covered=covered,
        )
        self.session.add(row)
        await self.session.flush()
        return {"id": str(row.id), "messages_covered": covered}

    async def recent_summaries(self, user_id: uuid.UUID, limit: int = 5) -> list[dict]:
        """Latest summaries across ALL sessions — cross-session continuity."""
        stmt = (
            select(SessionSummary)
            .where(SessionSummary.user_id == user_id)
            .order_by(SessionSummary.created_at.desc())
            .limit(limit)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [
            {
                "session_id": str(r.session_id),
                "summary": self._safe_decrypt(r.summary_encrypted),
                "messages_covered": r.messages_covered,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def build_summary_prompt(self, old_messages: list[dict]) -> str:
        """Build the summarization prompt for the LLM (chunk of old messages)."""
        convo = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in old_messages
        )
        return (
            "Ringkas percakapan berikut jadi 5-10 baris padat Bahasa Indonesia. "
            "Fokus pada: keputusan, fakta tentang pengguna, konteks proyek/kode, "
            "dan hal yang belum selesai. Jangan tambah info baru.\n\n" + convo
        )

    @staticmethod
    def _safe_decrypt(blob: bytes) -> str:
        try:
            return decrypt(blob)
        except Exception:  # noqa: BLE001
            return "[unable to decrypt]"
