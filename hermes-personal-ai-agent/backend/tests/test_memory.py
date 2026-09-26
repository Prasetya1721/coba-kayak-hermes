"""Tests for permanent memory: parsing, extraction, recall, and explicit commands."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.memory_service import MemoryService


def _service() -> MemoryService:
    return MemoryService(AsyncMock())


class TestExplicitCommands:
    def test_remember_basic(self):
        cmd = _service().parse_explicit_command("ingat ya, namaku Budi")
        assert cmd == {"action": "remember", "value": "namaku Budi"}

    def test_remember_variants(self):
        assert _service().parse_explicit_command("tolong ingat ulang tahunku 5 Mei") == {
            "action": "remember",
            "value": "ulang tahunku 5 Mei",
        }
        assert _service().parse_explicit_command("ingat-ingat dong aku suka teh") == {
            "action": "remember",
            "value": "aku suka teh",
        }

    def test_forget(self):
        cmd = _service().parse_explicit_command("lupakan ulang tahunku")
        assert cmd is not None and cmd["action"] == "forget"

    def test_forget_all(self):
        cmd = _service().parse_explicit_command("lupakan semuanya")
        assert cmd is not None and cmd["value"] == "semuanya"

    def test_no_command(self):
        assert _service().parse_explicit_command("halo apa kabar?") is None


class TestFactExtraction:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("namaku Budi Santoso", [("nama", "Budi Santoso")]),
            ("nama saya adalah Siti", [("nama", "Siti")]),
            ("panggil aku Udin", [("nama", "Udin")]),
            ("ultahku 5 Mei", [("ulang_tahun", "5 Mei")]),
            ("aku tinggal di Bandung", [("kota", "Bandung")]),
            ("aku kerja sebagai designer", [("pekerjaan", "designer")]),
            ("aku suka kopi tubruk", [("preferensi", "kopi tubruk")]),
            ("aku nggak suka pedas", [("preferensi", "pedas")]),
            ("favoritku warna biru", [("preferensi", "warna biru")]),
            ("my name is Alex", [("nama", "Alex")]),
            ("halo apa kabar", []),
        ],
    )
    def test_extract(self, text, expected):
        facts = _service().extract_facts(text)
        assert facts == expected

    def test_trailing_clause_is_cut(self):
        facts = _service().extract_facts("namaku Budi dan aku suka kopi")
        assert facts[0] == ("nama", "Budi")

    def test_trailing_filler_word_dropped(self):
        from app.services.memory_service import _clean

        assert _clean("PMS testing dong") == "PMS testing"
        # "semuanya" must NOT be truncated to "semuan".
        assert _clean("semuanya") == "semuanya"

    def test_junk_values_rejected(self):
        from app.services.memory_service import is_junk_value

        assert is_junk_value("dong") is True
        assert is_junk_value("ya") is True
        assert is_junk_value("oke") is True
        assert is_junk_value("PMS testing") is False

    def test_junk_not_extracted(self):
        # A message of only filler must produce no facts.
        assert _service().extract_facts("dong aja ya") == []


class TestForgetTool:
    @pytest.mark.asyncio
    async def test_forget_impl_without_context(self):
        from app.services.agent import tool_registry as registry

        out = await registry._forget_impl("dong")
        assert "tidak tersedia" in out

    @pytest.mark.asyncio
    async def test_forget_impl_deletes_matching(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        calls: list[str] = []

        class _Svc:
            async def delete_by_scope(self, user_id, scope):
                calls.append(f"scope:{scope}")
                return 0

            async def delete_by_key(self, user_id, key):
                calls.append(f"key:{key}")
                return 0

            async def list(self, user_id):
                return [
                    {"id": "11111111-1111-1111-1111-111111111111", "key": "proyek", "value": "dong", "scope": "proyek:dong"},
                    {"id": "22222222-2222-2222-2222-222222222222", "key": "kota", "value": "Bandung", "scope": "global"},
                ]

            async def delete(self, user_id, memory_id):
                calls.append(f"del:{str(memory_id)[:4]}")
                return True

        registry.set_memory_service(_Svc(), "00000000-0000-0000-0000-000000000000")
        try:
            out = await registry._forget_impl("dong")
        finally:
            registry.set_memory_service(None)
        assert "udah aku lupain" in out
        assert any(c.startswith("del:") for c in calls)

    @pytest.mark.asyncio
    async def test_remember_with_scope(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        captured: dict = {}

        class _Svc:
            async def save(self, user_id, key, value, scope=None):
                captured["scope"] = scope
                return {"key": key, "value": value, "scope": scope or "global"}

            async def list(self, user_id):
                return []

        registry.set_memory_service(_Svc(), "00000000-0000-0000-0000-000000000000")
        try:
            out = await registry._remember_impl("proyek", "PMS", scope="proyek:pms")
        finally:
            registry.set_memory_service(None)
        assert captured["scope"] == "proyek:pms"
        assert "[proyek:pms]" in out


class TestMemoryService:
    @pytest.mark.asyncio
    async def test_save_and_list_roundtrip(self):
        from app.services.memory_service import UserMemory

        store: dict = {}

        class _FakeResult:
            def scalars(self):
                class _S:
                    def all(self_inner):
                        return list(store.values())

                return _S()

            def scalar_one_or_none(self):
                return None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult())
        svc = MemoryService(db)
        saved = await svc.save(__import__("uuid").uuid4(), "nama", "Budi")
        assert saved["key"] == "nama"
        assert saved["value"] == "Budi"
        # value must be encrypted at rest, never plaintext
        row: UserMemory = db.add.call_args[0][0]
        assert b"Budi" not in row.value_encrypted

    def test_remember_impl_without_context(self):
        import asyncio

        from app.services.agent import tool_registry as registry

        out = asyncio.get_event_loop().run_until_complete(
            registry._remember_impl("nama", "Budi")
        )
        assert "tidak tersedia" in out

    def test_recall_impl_without_context(self):
        import asyncio

        from app.services.agent import tool_registry as registry

        out = asyncio.get_event_loop().run_until_complete(
            registry._recall_impl(None)
        )
        assert "tidak tersedia" in out
