"""Tests for direct GitHub repo reading (no web search involved)."""

from __future__ import annotations

import base64

import pytest
import respx
from httpx import Response

from app.services.agent.tools import web_management


class TestParseRepo:
    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            ("owner/repo", ("owner", "repo")),
            ("https://github.com/owner/repo", ("owner", "repo")),
            ("https://github.com/owner/repo.git", ("owner", "repo")),
            ("https://github.com/owner/repo/tree/main/src", ("owner", "repo")),
            ("git@github.com:owner/repo.git", ("owner", "repo")),
            ("Prasetya1721/coba-kayak-hermes", ("Prasetya1721", "coba-kayak-hermes")),
        ],
    )
    def test_parse(self, ref, expected):
        assert web_management.parse_repo(ref) == expected

    def test_parse_invalid(self):
        with pytest.raises(web_management.WebManagementError):
            web_management.parse_repo("")


class TestGithubRead:
    @pytest.mark.asyncio
    async def test_list_files(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "ghp_test")
        payload = [
            {"name": "src", "type": "dir", "size": 0, "path": "src"},
            {"name": "README.md", "type": "file", "size": 120, "path": "README.md"},
        ]
        with respx.mock:
            respx.get("https://api.github.com/repos/o/r/contents/").mock(
                return_value=Response(200, json=payload)
            )
            out = await web_management.github_list_files("o", "r")
        names = [e["name"] for e in out["entries"]]
        assert names == ["src", "README.md"]  # dirs first

    @pytest.mark.asyncio
    async def test_read_file_decodes_base64(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "ghp_test")
        content = base64.b64encode(b"def hello():\n    return 42\n").decode()
        payload = {
            "path": "main.py",
            "size": 27,
            "sha": "abc",
            "encoding": "base64",
            "content": content,
        }
        with respx.mock:
            respx.get("https://api.github.com/repos/o/r/contents/main.py").mock(
                return_value=Response(200, json=payload)
            )
            out = await web_management.github_read_file("o", "r", "main.py")
        assert "def hello()" in out["content"]
        assert out["truncated"] is False

    @pytest.mark.asyncio
    async def test_read_file_rejects_binary(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "ghp_test")
        with pytest.raises(web_management.WebManagementError, match="biner"):
            await web_management.github_read_file("o", "r", "logo.png")

    @pytest.mark.asyncio
    async def test_search_code(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "ghp_test")
        payload = {
            "total_count": 2,
            "items": [
                {"path": "src/a.py", "html_url": "u1"},
                {"path": "src/b.py", "html_url": "u2"},
            ],
        }
        with respx.mock:
            respx.get("https://api.github.com/search/code").mock(
                return_value=Response(200, json=payload)
            )
            out = await web_management.github_search_code("o", "r", "hello")
        assert out["total"] == 2
        assert out["matches"][0]["path"] == "src/a.py"

    @pytest.mark.asyncio
    async def test_list_commits(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "ghp_test")
        payload = [
            {
                "sha": "abcdef123456",
                "commit": {
                    "message": "feat: something\n\nbody",
                    "author": {"name": "Budi", "date": "2026-01-01T00:00:00Z"},
                },
            }
        ]
        with respx.mock:
            respx.get("https://api.github.com/repos/o/r/commits").mock(
                return_value=Response(200, json=payload)
            )
            out = await web_management.github_list_commits("o", "r")
        assert out["commits"][0]["sha"] == "abcdef12"
        assert out["commits"][0]["message"] == "feat: something"

    @pytest.mark.asyncio
    async def test_no_token_errors(self, monkeypatch):
        monkeypatch.setattr(web_management.settings, "github_token", "")
        with pytest.raises(web_management.WebManagementError, match="GITHUB_TOKEN"):
            await web_management.github_list_files("o", "r")


class TestGithubTool:
    @pytest.mark.asyncio
    async def test_tool_explains_missing_token(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        # No token resolver, no env token.
        monkeypatch.setattr(registry.settings, "github_token", "")
        monkeypatch.setattr(registry, "_token_resolver", None)
        out = await registry._github_impl("list_files", "owner/repo")
        assert "token" in out.lower()

    @pytest.mark.asyncio
    async def test_tool_uses_user_token(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        monkeypatch.setattr(registry.settings, "github_token", "")

        async def fake_token() -> str:
            return "ghp_user"

        monkeypatch.setattr(registry, "_token_resolver", fake_token)
        seen: dict = {}

        async def fake_list(owner, repo, path="", *, branch=None, token=None):
            seen["token"] = token
            return {"entries": []}

        monkeypatch.setattr(registry.web_management, "github_list_files", fake_list)
        out = await registry._github_impl("list_files", "o/r")
        assert seen["token"] == "ghp_user"
        assert "entries" in out

    def test_github_tool_always_registered(self):
        from app.services.agent.tool_registry import build_agent_tools

        names = [t.name for t in build_agent_tools()]
        assert "manage_github" in names
