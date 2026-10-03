"""No value from the local `.env` sits in any file git tracks (#538).

The repository is public. On 03.10 the live NewsAPI key was found in a test
fixture (`test_newsapi_respects_its_allowance.py`, two lines), the live FRED
key in a committed rebuild log, and two Hugging Face tokens in older reports.
The keys were rotated; this test stops the next one before it is pushed.

Known answers: a planted value must be found in a planted file, and a file
without it must not be. Failure messages name the KEY and the FILE, never the
value. Without a `.env` (CI) the repository check skips; the control does not.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MIN_LEN = 16  # shorter values (flags, ports, model names) are not secrets


def _env_values(env_path: Path) -> dict[str, str]:
    values = {}
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if len(value) >= MIN_LEN:
            values[key.strip()] = value
    return values


def _files_holding(values: dict[str, str], paths: list[Path]) -> list[tuple[str, str]]:
    needles = {key: value.encode("utf-8") for key, value in values.items()}
    hits = []
    for path in paths:
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        hits.extend((key, str(path)) for key, needle in needles.items() if needle in blob)
    return hits


def test_the_control_finds_a_planted_value_and_only_there(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PLANTED_KEY=0123456789abcdef0123456789abcdef\nSHORT=abc\n", encoding="utf-8")
    holding = tmp_path / "holding.py"
    holding.write_text('key = "0123456789abcdef0123456789abcdef"\n', encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text('key = os.environ["PLANTED_KEY"]\n', encoding="utf-8")

    values = _env_values(env)
    assert list(values) == ["PLANTED_KEY"]
    assert _files_holding(values, [holding, clean]) == [("PLANTED_KEY", str(holding))]


def test_no_env_value_is_in_a_tracked_file():
    env = REPO / ".env"
    if not env.exists():
        pytest.skip("no local .env (CI)")
    values = _env_values(env)
    if not values:
        pytest.skip(".env holds no value long enough to be a secret")
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    paths = [REPO / name for name in listed.decode("utf-8").split("\0") if name]
    hits = _files_holding(values, paths)
    assert not hits, "keys from .env found in tracked files (names only): " + "; ".join(
        f"{key} in {Path(path).relative_to(REPO)}" for key, path in hits)
