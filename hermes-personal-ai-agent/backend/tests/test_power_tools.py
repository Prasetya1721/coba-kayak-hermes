"""Tests for scoped memory, repo sandbox, and code-exec safety."""

from __future__ import annotations

import os
import tempfile

import pytest

from app.services.memory_service import MemoryService


def _service():
    from unittest.mock import AsyncMock

    return MemoryService(AsyncMock())


class TestScope:
    def test_infer_scope_proyek(self):
        from app.services.memory_service import infer_scope

        assert infer_scope("proyek", "PMS") == "proyek:pms"
        assert infer_scope("kode", "pake python") == "kode"
        assert infer_scope("nama", "Budi") == "global"
        assert infer_scope("preferensi", "kopi") == "global"

    def test_detect_project_scope(self):
        assert MemoryService.detect_project_scope("lagi ngerjain proyek PMS nih") == "proyek:pms"
        assert MemoryService.detect_project_scope("repo PMS error") == "proyek:pms"
        assert MemoryService.detect_project_scope("halo apa kabar") is None

    def test_extract_project_facts(self):
        facts = _service().extract_facts("lagi ngerjain proyek PMS buat kantor")
        assert ("proyek", "PMS buat kantor") in facts or any(
            k == "proyek" for k, _ in facts
        )

    def test_extract_code_prefs(self):
        facts = _service().extract_facts("aku biasanya pake python buat scripting")
        assert any(k == "kode" for k, _ in facts)
        facts2 = _service().extract_facts("jangan pake tabs ya")
        assert any(k == "kode" for k, _ in facts2)


class TestRepoJail:
    def test_resolve_inside_root(self, monkeypatch, tmp_path):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            repo.settings, "repo_roots", str(tmp_path), raising=False
        )
        # monkeypatch the property source instead
        monkeypatch.setattr(
            type(repo.settings),
            "repo_roots_list",
            property(lambda self: [str(tmp_path)]),
        )
        (tmp_path / "a.py").write_text("print('hi')")
        assert "hi" in repo.read_file("a.py")

    def test_dotdot_escape_refused(self, monkeypatch, tmp_path):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            type(repo.settings),
            "repo_roots_list",
            property(lambda self: [str(tmp_path)]),
        )
        with pytest.raises(repo.RepoAccessError):
            repo.read_file("../../secret.txt")

    def test_absolute_outside_refused(self, monkeypatch, tmp_path):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            type(repo.settings),
            "repo_roots_list",
            property(lambda self: [str(tmp_path)]),
        )
        outside = os.path.join(tempfile.gettempdir(), "outside_hermes_test.txt")
        with open(outside, "w") as fh:
            fh.write("x")
        try:
            with pytest.raises(repo.RepoAccessError):
                repo.read_file(outside)
        finally:
            os.remove(outside)

    def test_binary_refused(self, monkeypatch, tmp_path):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            type(repo.settings),
            "repo_roots_list",
            property(lambda self: [str(tmp_path)]),
        )
        (tmp_path / "img.png").write_bytes(b"\x89PNG\x00\x01\x02")
        with pytest.raises(repo.RepoAccessError):
            repo.read_file("img.png")

    def test_search_code(self, monkeypatch, tmp_path):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            type(repo.settings),
            "repo_roots_list",
            property(lambda self: [str(tmp_path)]),
        )
        (tmp_path / "main.py").write_text("def hello():\n    pass\n")
        out = repo.search_code("hello", ext=".py")
        assert "main.py:1" in out

    def test_no_roots_configured(self, monkeypatch):
        from app.services.agent.tools import repo

        monkeypatch.setattr(
            type(repo.settings), "repo_roots_list", property(lambda self: [])
        )
        with pytest.raises(repo.RepoAccessError, match="REPO_ROOTS"):
            repo.read_file("a.py")


class TestCodeExec:
    def test_disabled_by_default(self, monkeypatch):
        import asyncio

        from app.services.agent.tools import code_exec

        monkeypatch.setattr(code_exec.settings, "code_exec_enabled", False)
        out = asyncio.get_event_loop().run_until_complete(
            _run(code_exec, "print(1)")
        )
        assert "MATI" in out

    def test_blocked_patterns_rejected(self, monkeypatch):
        from app.services.agent.tools import code_exec

        monkeypatch.setattr(code_exec.settings, "code_exec_enabled", True)
        for bad in [
            "import os; os.system('ls')",
            "import subprocess; subprocess.run(['ls'])",
            "import socket",
            "eval('1')",
            "open('x','w').write('y')",
        ]:
            with pytest.raises(code_exec.CodeExecError):
                code_exec.validate_code("python", bad)

    def test_bad_language_rejected(self, monkeypatch):
        from app.services.agent.tools import code_exec

        monkeypatch.setattr(code_exec.settings, "code_exec_enabled", True)
        monkeypatch.setattr(
            code_exec.settings, "code_exec_languages", "python", raising=False
        )
        with pytest.raises(code_exec.CodeExecError):
            code_exec.validate_code("ruby", "puts 1")

    @pytest.mark.asyncio
    async def test_run_safe_python(self, monkeypatch):
        from app.services.agent.tools import code_exec

        monkeypatch.setattr(code_exec.settings, "code_exec_enabled", True)
        monkeypatch.setattr(
            code_exec.settings, "code_exec_languages", "python", raising=False
        )
        out = await code_exec.run_code(
            language="python", code="print(40 + 2)"
        )
        assert "[exit 0]" in out
        assert "42" in out


async def _run(code_exec, code: str) -> str:
    try:
        return await code_exec.run_code(language="python", code=code)
    except code_exec.CodeExecError as exc:
        return f"Nggak bisa jalanin: {exc}"
