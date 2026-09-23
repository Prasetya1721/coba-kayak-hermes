"""Seed built-in command templates (starter set for beginners, PRD §6)."""

from __future__ import annotations

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import CommandTemplate
from app.db.session import SessionLocal

log = get_logger(__name__)

BUILTIN_TEMPLATES: list[dict[str, str]] = [
    {
        "title": "Buat landing page sederhana",
        "description": "Minta Hermes membuat halaman landing HTML/CSS satu file.",
        "command_pattern": (
            "Buatkan landing page sederhana untuk produk bernama {nama_produk} "
            "dengan hero, fitur, dan CTA. Simpan sebagai file HTML."
        ),
        "category": "web",
    },
    {
        "title": "Cek uptime website saya",
        "description": "Periksa apakah situs merespons dan ukur waktu balas.",
        "command_pattern": "Cek uptime website {url} dan beri tahu saya statusnya.",
        "category": "web",
    },
    {
        "title": "Ingatkan meeting besok jam 10",
        "description": "Buat pengingat sekali jalan via Telegram/WhatsApp.",
        "command_pattern": (
            "Ingatkan saya meeting besok jam {jam} tentang {topik}."
        ),
        "category": "notification",
    },
    {
        "title": "Cek status server",
        "description": "Jalankan pemeriksaan ringan pada server via SSH (whitelisted).",
        "command_pattern": "Cek status server {host} dan laporkan uptime serta disk.",
        "category": "device",
    },
    {
        "title": "Rangkum berita terbaru AI",
        "description": "Cari dan rangkum 5 berita AI terbaru dari web.",
        "command_pattern": "Cari 5 berita terbaru tentang {topik} dan rangkum singkat.",
        "category": "search",
    },
    {
        "title": "Deploy website ke Vercel",
        "description": "Trigger deployment ulang project di Vercel.",
        "command_pattern": "Deploy ulang project Vercel {project} dari branch main.",
        "category": "web",
    },
    {
        "title": "Commit perubahan ke GitHub",
        "description": "Push satu file ke repository GitHub.",
        "command_pattern": (
            "Commit file {path} ke repo {owner}/{repo} dengan pesan '{pesan}'."
        ),
        "category": "web",
    },
    {
        "title": "Jadwalkan pengingat harian",
        "description": "Notifikasi berulang setiap hari pada jam tertentu.",
        "command_pattern": "Kirim pengingat setiap hari jam {jam}: {pesan}.",
        "category": "notification",
    },
]


async def seed_builtin_templates() -> int:
    """Insert built-in templates if they are not present yet."""
    async with SessionLocal() as db:
        existing = await db.execute(
            select(CommandTemplate.title).where(CommandTemplate.is_builtin.is_(True))
        )
        titles = {row[0] for row in existing.all()}

        added = 0
        for tpl in BUILTIN_TEMPLATES:
            if tpl["title"] in titles:
                continue
            db.add(
                CommandTemplate(
                    user_id=None,
                    title=tpl["title"],
                    description=tpl["description"],
                    command_pattern=tpl["command_pattern"],
                    category=tpl["category"],
                    is_builtin=True,
                )
            )
            added += 1
        if added:
            await db.commit()
            log.info("seeded_builtin_templates", count=added)
        return added
