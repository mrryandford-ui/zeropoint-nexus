"""
Unit tests — KaliRunner wrappers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from zeropoint.pentest.kali_runner import KaliRunner, ScanResult


def _scan(tool: str, target: str, stdout: str, rc: int = 0) -> ScanResult:
    now = datetime.now(timezone.utc)
    return ScanResult(
        tool=tool,
        target=target,
        args=[],
        stdout=stdout,
        stderr="",
        returncode=rc,
        started_at=now,
        finished_at=now,
    )


@pytest.mark.asyncio
async def test_metasploit_modules_parses_results(tmp_path, monkeypatch):
    runner = KaliRunner(output_dir=tmp_path)

    async def fake_run(tool, args, target, timeout=300):
        return _scan(
            tool,
            target,
            "exploit/linux/http/sample excellent Sample exploit module\n"
            "auxiliary/scanner/http/http_version normal HTTP version scanner\n",
            0,
        )

    monkeypatch.setattr(runner, "_run", fake_run)
    result = await runner.metasploit_modules(query="type:exploit", authorized=True)
    assert result.parsed["count"] >= 2
    assert result.parsed["matches"][0]["module"].startswith("exploit/")


@pytest.mark.asyncio
async def test_hashcat_crack_parses_show(tmp_path, monkeypatch):
    runner = KaliRunner(output_dir=tmp_path)
    hashes = tmp_path / "hashes.txt"
    hashes.write_text("d41d8cd98f00b204e9800998ecf8427e")

    async def fake_run(tool, args, target, timeout=300):
        if "--show" in args:
            return _scan(tool, target, "d41d8cd98f00b204e9800998ecf8427e:plaintext\n", 0)
        return _scan(tool, target, "", 0)

    monkeypatch.setattr(runner, "_run", fake_run)
    result = await runner.hashcat_crack(
        hash_file=str(hashes),
        mode=0,
        wordlist=str(hashes),
        authorized=True,
    )
    assert result.parsed["count"] == 1
    assert result.parsed["cracked"][0]["plaintext"] == "plaintext"


@pytest.mark.asyncio
async def test_john_crack_parses_show(tmp_path, monkeypatch):
    runner = KaliRunner(output_dir=tmp_path)
    hashes = tmp_path / "john.txt"
    hashes.write_text("user:$1$abc$xyz")

    async def fake_run(tool, args, target, timeout=300):
        if "--show" in args:
            return _scan(tool, target, "user:password\n1 password hash cracked, 0 left\n", 0)
        return _scan(tool, target, "", 0)

    monkeypatch.setattr(runner, "_run", fake_run)
    result = await runner.john_crack(
        hash_file=str(hashes),
        authorized=True,
    )
    assert result.parsed["count"] == 1
    assert result.parsed["cracked"][0]["user"] == "user"


@pytest.mark.asyncio
async def test_hashcat_requires_authorized(tmp_path):
    runner = KaliRunner(output_dir=tmp_path)
    hashes = tmp_path / "hashes.txt"
    hashes.write_text("d41d8cd98f00b204e9800998ecf8427e")
    with pytest.raises(PermissionError):
        await runner.hashcat_crack(hash_file=str(hashes), mode=0, wordlist=str(hashes), authorized=False)

