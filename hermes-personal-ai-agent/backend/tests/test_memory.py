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
