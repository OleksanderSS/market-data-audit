"""Known answers for the nightly gate script (REGISTER #380).

Each case builds a stamp whose verdict is known, renders the report, and asks
the SessionStart hook -- the only reader of the report -- what it sees. The
hook must name the same verdict the script wrote, for every verdict: a green
that the hook reads as red, or a red it reads as green, is the whole failure.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "maintenance" / f"{name}.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ng = _load("nightly_gate")
hook = _load("is_last_nights_report_there")

TODAY = dt.date(2026, 9, 19)
GREEN = {"finished": "2026-09-19T04:01:00", "green": True, "reasons": [],
         "contracts": {"passed": 695, "failed": 0, "skipped": 1, "error": 0},
         "contracts_failed_lines": [], "ratchet_exit": 0,
         "ratchet_tail": ["ratchet: 0 new"], "ratchet_failures": []}
RED = {**GREEN, "green": False, "reasons": ["tests/contracts: 1 failed, 0 errors"],
       "contracts": {"passed": 694, "failed": 1, "skipped": 1, "error": 0},
       "contracts_failed_lines": ["FAILED tests/contracts/test_x.py::test_y - assert 1 == 2"]}
PREV_GREEN = ("2026-09-18.md", "HEAD: abc1234\nContracts: 695 passed / 1 skipped\nВердикт: ЗЕЛЕНЕ\n")


def _render(**kw):
    base = dict(today=TODAY, head="abc1234", dirty=[], stamp=GREEN, gate_exit=0,
                wiki_line="live titles checked: 95 — чисто", busy=[], previous=PREV_GREEN)
    base.update(kw)
    return ng.render(**base)


CASES = {
    "green": (dict(), "ЗЕЛЕНЕ"),
    "red contract": (dict(stamp=RED, gate_exit=1), "ЧЕРВОНЕ"),
    "stale stamp": (dict(stamp={**GREEN, "finished": "2026-09-18T04:00:00"}), "НЕ ВИМІРЯНО"),
    "no summary": (dict(stamp={**GREEN, "contracts": None, "green": False}), "НЕ ВИМІРЯНО"),
    "gate timed out": (dict(gate_exit=None), "НЕ ВИМІРЯНО"),
    "no stamp": (dict(stamp=None), "НЕ ВИМІРЯНО"),
    "killed step": (dict(stamp={**RED, "reasons": ["unit_failure_ratchet hung and was killed: NOT MEASURED"]},
                         gate_exit=1), "НЕ ВИМІРЯНО"),
    "rebuild refused": (dict(stamp=None, gate_exit=2), "ПРОПУЩЕНО"),
    "heavy run alive": (dict(busy=["pid 1: python -m pytest tests/unit"]), "ПРОПУЩЕНО"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_the_hook_reads_the_verdict_the_script_wrote(name, tmp_path):
    kw, want = CASES[name]
    text = _render(**kw)
    assert text.rstrip().endswith(f"Вердикт: {want}")
    (tmp_path / f"{TODAY.isoformat()}.md").write_text(text, encoding="utf-8")
    ok, message = hook.check(tmp_path, dt.datetime(2026, 9, 19, 9, 0))
    assert ok == (want == "ЗЕЛЕНЕ")
    assert want in message


@pytest.mark.parametrize("now, report_day, due", [
    (dt.datetime(2026, 9, 19, 17, 53), "2026-09-19", "2026-09-20"),  # evening: tonight's report is tomorrow's
    (dt.datetime(2026, 9, 19, 4, 30), "2026-09-19", "2026-09-20"),
    (dt.datetime(2026, 9, 20, 3, 0), "2026-09-19", "2026-09-20"),    # before 04:30: still due today
])
def test_the_hook_says_when_the_next_report_is_due(now, report_day, due, tmp_path):
    (tmp_path / f"{report_day}.md").write_text(_render(), encoding="utf-8")
    ok, message = hook.check(tmp_path, now, count=lambda head: None)
    assert ok and f"Наступний звіт — після 04:30 {due}" in message
    assert "HEAD звіту" not in message and "покриває" not in message


@pytest.mark.parametrize("n, want, not_want", [
    (0, "Звіт покриває поточний HEAD (abc1234)", "ще не йшли"),
    (13, "Після HEAD звіту (abc1234) комітів: 13", "покриває"),
])
def test_the_hook_says_whether_the_report_saw_the_current_commits(n, want, not_want, tmp_path):
    (tmp_path / f"{TODAY.isoformat()}.md").write_text(_render(), encoding="utf-8")
    asked = []
    ok, message = hook.check(tmp_path, dt.datetime(2026, 9, 19, 9, 0), count=lambda head: asked.append(head) or n)
    assert asked == ["abc1234"] and want in message and not_want not in message
    # the report itself travels in a green message too, so no session opens the file to read it
    assert "Contracts: 695 passed" in message


def test_a_red_night_names_the_new_red_against_a_green_night():
    text = _render(stamp=RED, gate_exit=1)
    assert "tests/contracts/test_x.py::test_y" in text
    assert "нові червоні 1, полагодились 0" in text
    # a red report after a green night: the only verdict word is on the verdict line
    assert text.count("ЗЕЛЕНЕ") == 0


def test_a_healed_test_is_counted_from_the_previous_report():
    prev = ("2026-09-18.md", _render(stamp=RED, gate_exit=1))
    text = _render(previous=prev)
    assert "нові червоні 0, полагодились 1" in text


def test_only_the_known_flaky_test_is_said_so():
    flaky = {**RED, "contracts_failed_lines": [f"FAILED tests/contracts/{ng.KNOWN_FLAKY} - x"]}
    assert "лише #376" in _render(stamp=flaky, gate_exit=1)
    assert "лише #376" not in _render(stamp=RED, gate_exit=1)


def test_a_dirty_tree_is_the_first_line_after_the_title():
    text = _render(dirty=[" M src/a.py", "?? tests/b.py"])
    assert text.splitlines()[2].startswith("ДЕРЕВО БРУДНЕ: 2 файлів")


def test_the_previous_report_is_the_latest_earlier_one(tmp_path):
    for day in ("2026-09-16", "2026-09-17", "2026-09-19", "2026-09-20"):
        (tmp_path / f"{day}.md").write_text("x", encoding="utf-8")
    assert ng.previous_report(tmp_path, TODAY).name == "2026-09-17.md"


# --------------------------------------------------------- tests/dean_os (18.09)
# Summary lines in the shape pytest -q prints them; the first is the real one
# measured on 18.09 after #403.
DEAN_GREEN_OUT = "....\n1290 passed, 304 skipped, 6 xfailed in 410.33s (0:06:50)\n"
DEAN_RED_OUT = ("....\nFAILED tests/dean_os/test_a.py::test_b - assert 0\n"
                "ERROR tests/dean_os/test_c.py::test_d - ImportError\n"
                "1 failed, 1288 passed, 304 skipped, 6 xfailed, 1 error in 401.0s\n")


def test_the_dean_os_summary_is_read_to_the_count():
    d = ng.dean_os_result(DEAN_GREEN_OUT, timed_out=False)
    assert (d["passed"], d["failed"], d["skipped"], d["xfailed"], d["error"]) == (1290, 0, 304, 6, 0)
    assert d["seconds"] == 410.33 and d["measured"]
    r = ng.dean_os_result(DEAN_RED_OUT, timed_out=False)
    assert (r["failed"], r["error"], r["passed"]) == (1, 1, 1288)
    assert r["failed_names"] == ["FAILED tests/dean_os/test_a.py::test_b",
                                 "ERROR tests/dean_os/test_c.py::test_d"]
    assert not ng.dean_os_result("....\n", timed_out=False)["measured"]
    assert not ng.dean_os_result(DEAN_GREEN_OUT, timed_out=True)["measured"]


DEAN_CASES = {
    "gate green, dean_os green": (dict(), DEAN_GREEN_OUT, False, "ЗЕЛЕНЕ"),
    "gate green, dean_os red": (dict(), DEAN_RED_OUT, False, "ЧЕРВОНЕ"),
    "gate green, dean_os hung": (dict(), "", True, "НЕ ВИМІРЯНО"),
    "gate green, dean_os no summary": (dict(), "Traceback\n", False, "НЕ ВИМІРЯНО"),
    "gate red, dean_os green": (dict(stamp=RED, gate_exit=1), DEAN_GREEN_OUT, False, "ЧЕРВОНЕ"),
    "gate red, dean_os hung": (dict(stamp=RED, gate_exit=1), "", True, "ЧЕРВОНЕ"),
}


@pytest.mark.parametrize("name", list(DEAN_CASES))
def test_the_hook_reads_dean_os_through_the_verdict(name, tmp_path):
    kw, out, timed_out, want = DEAN_CASES[name]
    text = _render(dean=ng.dean_os_result(out, timed_out), **kw)
    assert text.rstrip().endswith(f"Вердикт: {want}")
    # the dean_os line itself carries no verdict word the hook could pick up
    line = next(ln for ln in text.splitlines() if ln.startswith("tests/dean_os:"))
    assert not any(v in line for v in hook.VERDICTS)
    (tmp_path / f"{TODAY.isoformat()}.md").write_text(text, encoding="utf-8")
    ok, message = hook.check(tmp_path, dt.datetime(2026, 9, 19, 9, 0))
    assert ok == (want == "ЗЕЛЕНЕ") and want in message


def test_a_dean_os_red_is_named_and_compared_with_the_night_before():
    text = _render(dean=ng.dean_os_result(DEAN_RED_OUT, False))
    assert "tests/dean_os: 1288 passed / 1 failed / 1 error / 304 skipped / 6 xfail, 401 с" in text
    assert "- FAILED tests/dean_os/test_a.py::test_b" in text
    assert "нові червоні 2, полагодились 0" in text


# ------------------------------------------------ dying-name capture (#434)

CAPTURE_OUT = """skipped as fetch-day stamps: 2026-09-18 (597)
delisted list 9,513 rows; stocks dead in the last 60 days and not yet captured: 62
   CELUW      died 2026-07-23  real bars  56  last real 2026-07-17  ok
   VIP        died 2026-07-23  real bars 100  last real 2026-09-18  STILL TRADING -- the delisting flag is probably wrong
   WAVS       died 2026-07-28  real bars   0  last real -  padding only
   SKYT       died 2026-07-31  real bars  99  last real 2026-07-30  ok
budget reached; 49 left for the next run
manifest data/dead_name_prices/manifest.csv: 13 names
"""


def test_the_capture_is_read_to_the_count():
    line = ng.capture_line(CAPTURE_OUT, False, 0)
    assert line == "зібрано 2, досі торгуються 1, лише заповнення 1, у черзі 49"


def test_a_refused_capture_says_so_and_nothing_is_lost():
    out = CAPTURE_OUT.replace("budget reached; 49 left for the next run",
                              "   KORE       REFUSED ('{Information: rate limit}') -- stopping")
    assert "відмова API" in ng.capture_line(out, False, 0)


@pytest.mark.parametrize("out, timed_out, code, want", [
    ("delisted list 9,513 rows; stocks dead in the last 60 days and not yet captured: 0\n",
     False, 0, "нових смертей за 60 днів немає"),
    ("REFUSED: the delisted list came back as '{}'\n", False, 1,
     "не зібрано: REFUSED: the delisted list came back as '{}'"),
    ("", True, None, "не завершився за 600 с"),
])
def test_every_way_the_capture_ends_has_its_own_words(out, timed_out, code, want):
    assert ng.capture_line(out, timed_out, code) == want


@pytest.mark.parametrize("name", list(CASES))
def test_the_capture_line_never_moves_the_verdict(name, tmp_path):
    """The hook takes the first verdict word anywhere; the capture line must
    carry none, on a skipped night as well -- the capture runs even then."""
    kw, want = CASES[name]
    for capture in (ng.capture_line(CAPTURE_OUT, False, 0), "не зібрано: x", "не запускався"):
        text = _render(capture=capture, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Ціни мертвих імен"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")



# ------------------------------------------------ 22.09: the night that measured nothing (#453)
# The real 22.09 report printed `Contracts: 774 passed` from a stamp finished
# 21.09 13:15 and counted "полагодились 1" from it; the run started 05:43, not
# 03:35, and resumed at 09:10 after the machine slept.
STALE = {**GREEN, "finished": "2026-09-18T13:15:29", "head": "213602fb415cedd7",
         "contracts": {"passed": 774, "failed": 0, "skipped": 1, "error": 0}}


def test_an_old_stamps_numbers_are_marked_old_and_not_compared():
    text = _render(stamp=STALE, gate_exit=1, previous=("2026-09-18.md", _render(stamp=RED, gate_exit=1)))
    line = next(ln for ln in text.splitlines() if ln.startswith("Contracts"))
    assert line.startswith("Contracts (СТАРИЙ штамп") and "2026-09-18T13:15:29" in line
    assert "213602fb" in line and line.endswith("774 passed / 1 skipped / 0 failed / 0 error")
    assert next(ln for ln in text.splitlines() if ln.startswith("Храповик")).startswith("Храповик (СТАРИЙ")
    assert "не порівнювалось" in text and "полагодились" not in text
    assert text.rstrip().endswith("Вердикт: НЕ ВИМІРЯНО")
    # the next night must not read the old count as a real one
    assert ng.parse_report(text)["passed"] is None


def test_a_fresh_stamp_carries_no_old_mark():
    assert "СТАРИЙ" not in _render()


@pytest.mark.parametrize("start, end, want, notes", [
    ((3, 35), (4, 12), "Час: старт 03:35, кінець 04:12 (0 год 37 хв)", 0),
    ((5, 43), (9, 14), "Час: старт 05:43, кінець 09:14 (3 год 31 хв)", 2),
])
def test_the_report_says_when_the_run_really_happened(start, end, want, notes):
    s = dt.datetime.combine(TODAY, dt.time(*start))
    e = dt.datetime.combine(TODAY, dt.time(*end))
    text = _render(started=s, finished=e)
    line = next(ln for ln in text.splitlines() if ln.startswith("Час:"))
    assert line.startswith(want)
    assert line.count(";") == notes
    assert not any(v in line for v in hook.VERDICTS)
    assert text.rstrip().endswith("Вердикт: ЗЕЛЕНЕ")


# ------------------------------------------------ #456: what the machine ran on
MAINS, LOW = {"plugged": True, "percent": 100}, {"plugged": False, "percent": 12}


@pytest.mark.parametrize("start, end, want", [
    (MAINS, MAINS, "Живлення: мережа 100% → мережа 100%"),
    ({"plugged": False, "percent": 61}, LOW,
     "Живлення: батарея 61% → батарея 12% — на батареї машина засинає"),
    (MAINS, LOW, "Живлення: мережа 100% → батарея 12% — "),   # the grid went down mid-run
    (None, None, "Живлення: невідомо → невідомо"),
])
def test_the_report_says_what_the_machine_ran_on(start, end, want):
    line = ng.power_line(start, end)
    assert line.startswith(want)
    assert ("#453" in line) == (LOW in (start, end) or start == {"plugged": False, "percent": 61})
    assert not any(v in line for v in hook.VERDICTS)


@pytest.mark.parametrize("name", list(CASES))
def test_the_power_line_is_printed_and_never_moves_the_verdict(name):
    kw, want = CASES[name]
    s = dt.datetime.combine(TODAY, dt.time(3, 35))
    text = _render(power=ng.power_line(MAINS, LOW), started=s, finished=s, **kw)
    lines = text.splitlines()
    i = next(i for i, ln in enumerate(lines) if ln.startswith("Живлення:"))
    assert lines[i - 1].startswith("Час:")   # beside the time, on a skipped night too
    assert text.rstrip().endswith(f"Вердикт: {want}")


def test_reading_the_battery_never_raises(monkeypatch):
    import psutil

    monkeypatch.setattr(psutil, "sensors_battery", lambda: None)
    assert ng.read_power() is None
    monkeypatch.setattr(psutil, "sensors_battery", lambda: (_ for _ in ()).throw(OSError("no ACPI")))
    assert ng.read_power() is None
    from types import SimpleNamespace

    monkeypatch.setattr(psutil, "sensors_battery",
                        lambda: SimpleNamespace(percent=72.6, secsleft=1, power_plugged=False))
    assert ng.read_power() == {"plugged": False, "percent": 73}


PYTHONW = Path(sys.executable).with_name("pythonw.exe")


@pytest.mark.skipif(sys.platform != "win32" or not PYTHONW.is_file(),
                    reason="console windows are a Windows thing")
def test_a_bounded_child_of_pythonw_gets_no_visible_console(tmp_path):
    """22.09: the nightly run is pythonw.exe, and every step it started opened
    a VISIBLE console a person could close; the contracts pytest died with
    abort at 09:14. Reproduced in the real shape -- pythonw -> run_bounded ->
    python.exe -- because a console-less pytest parent passes either way."""
    out = tmp_path / "probe.txt"
    probe = ("import ctypes; k=ctypes.windll.kernel32; u=ctypes.windll.user32; "
             "h=k.GetConsoleWindow(); print(bool(h and u.IsWindowVisible(h)))")
    driver = tmp_path / "driver.py"
    driver.write_text("\n".join([
        "import sys",
        f"sys.path.insert(0, {str(ROOT / 'scripts' / 'maintenance')!r})",
        "from _bounded_run import run_bounded",
        f"r = run_bounded([{sys.executable!r}, '-c', {probe!r}], cwd='.', timeout_s=60)",
        f"open({str(out)!r}, 'w').write(f'{{r.returncode}} {{r.stdout.strip()}}')",
    ]) + "\n", encoding="utf-8")
    subprocess.run([str(PYTHONW), str(driver)], timeout=90, check=True)
    assert out.read_text() == "0 False"


# ------------------------------------------------ forward journal (#482)
JOURNAL_OUT = ("journal: forecast 2026-09-29 names 498, missed 0, resolved files 2; "
               "chain 0a1b2c3d4e5f (41 links)\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (JOURNAL_OUT, False, 0, "forecast 2026-09-29 names 498"),
    ("journal: CHAIN BROKEN, nothing written: link 3: x changed\n", False, 2, "ЛАНЦЮГ ХЕШІВ ПОШКОДЖЕНО"),
    ("Traceback ...\nConnectionError: no route\n", False, 1, "не записано: ConnectionError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_journal_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.journal_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_journal_line_never_moves_the_verdict(name):
    """Same rule as the capture: the journal runs on skipped nights too."""
    kw, want = CASES[name]
    for journal in (ng.journal_line(JOURNAL_OUT, False, 0),
                    ng.journal_line("journal: CHAIN BROKEN\n", False, 2),
                    ng.journal_line("", True, None), "не запускався"):
        text = _render(journal=journal, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Журнал уперед"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


# ------------------------------------------------ #489: the raw news capture
NEWS_OUT = ("yahoo 7000 rows, 480/503 names (900 s)\nrss 400 rows, 20/26 feeds, failed 6 (20 s)\n"
            "news: 7400 rows, 7300 articles, new 5100; yahoo 7000 rows, 480/503 names (900 s); "
            "rss 400 rows, 20/26 feeds, failed 6 (20 s); 920 s -> data\\news_capture\\x.parquet\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (NEWS_OUT, False, 0, "7400 rows, 7300 articles, new 5100"),
    ("news: 0 rows, 0 articles, new 0; -> nothing written\n", False, 1, "не зібрано: news: 0 rows"),
    ("Traceback ...\nFileNotFoundError: no universe snapshot\n", False, 1, "не зібрано: FileNotFoundError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_news_capture_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.news_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_news_line_never_moves_the_verdict(name):
    """Same rule as the capture and the journal: a failed news night is data lost,
    not a red gate."""
    kw, want = CASES[name]
    for news in (ng.news_line(NEWS_OUT, False, 0), ng.news_line("", True, None),
                 ng.news_line("Traceback\nboom\n", False, 1), "не запускався"):
        text = _render(news=news, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Новини (#489)"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


# ------------------------------------------------ #489б: the option snapshot
OPTIONS_OUT = ("options: 498/503 names, 240000 contracts, 3.0 expirations per name, no chain 3, "
               "failed 2; 380 s -> data\\options_capture\\x.parquet\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (OPTIONS_OUT, False, 0, "498/503 names, 240000 contracts"),
    ("options: 0/503 names, 0 contracts -> nothing written\n", False, 1, "не зібрано: options: 0/503"),
    ("Traceback ...\nImportError: yfinance\n", False, 1, "не зібрано: ImportError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_option_snapshot_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.options_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_options_line_never_moves_the_verdict(name):
    kw, want = CASES[name]
    for options in (ng.options_line(OPTIONS_OUT, False, 0), ng.options_line("", True, None),
                    ng.options_line("Traceback\nboom\n", False, 1), "не запускався"):
        text = _render(options=options, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Опціони (#489б)"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


# ------------------------------------------------ #489в: the analyst snapshot
ANALYSTS_OUT = ("analysts: 500/503 names, 68000 rows, firm actions 2400 in 30 d; tables missing "
                "(! = error): earnings_history 3; nothing 3, failed 0; 250 s -> data\\analyst_capture\\x.parquet\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (ANALYSTS_OUT, False, 0, "500/503 names, 68000 rows"),
    ("analysts: 0/503 names, 0 rows -> nothing written\n", False, 1, "не зібрано: analysts: 0/503"),
    ("Traceback ...\nImportError: yfinance\n", False, 1, "не зібрано: ImportError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_analyst_snapshot_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.analysts_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_analysts_line_never_moves_the_verdict(name):
    kw, want = CASES[name]
    for analysts in (ng.analysts_line(ANALYSTS_OUT, False, 0), ng.analysts_line("", True, None),
                     ng.analysts_line("Traceback\nboom\n", False, 1), "не запускався"):
        text = _render(analysts=analysts, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Аналітики (#489в)"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


# ------------------------------------------------ #501: the Reddit capture
REDDIT_OUT = ("pages: stocks 100 over 261 h; wallstreetbets 100 over 164 h\n"
              "reddit: 4/4 subreddits, 400 posts, new 120, gap 0, undated 0, failed 0; "
              "250 s -> data\\reddit_capture\\x.parquet\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (REDDIT_OUT, False, 0, "4/4 subreddits, 400 posts, new 120, gap 0"),
    ("failed: stocks:HTTP 429 twice\nreddit: 0/4 subreddits, 0 posts -> nothing written\n", False, 1,
     "не зібрано: reddit: 0/4"),
    ("Traceback ...\nImportError: feedparser\n", False, 1, "не зібрано: ImportError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_reddit_capture_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.reddit_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_reddit_line_never_moves_the_verdict(name):
    kw, want = CASES[name]
    for reddit in (ng.reddit_line(REDDIT_OUT, False, 0), ng.reddit_line("", True, None),
                   ng.reddit_line("Traceback\nboom\n", False, 1), "не запускався"):
        text = _render(reddit=reddit, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Reddit (#501)"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


# ------------------------------------------------ #513: the job-postings capture
JOBS_OUT = ("jobs: 19/19 names, postings 15653, capped 1, robots 0, failed 0; "
            "82 s -> data\\job_postings_capture\\x.parquet\n")


@pytest.mark.parametrize("out, timed_out, code, start", [
    (JOBS_OUT, False, 0, "19/19 names, postings 15653, capped 1"),
    ("failed: ADI:HTTP 403\njobs: 0/19 names, postings 0 -> nothing written\n", False, 1,
     "не зібрано: jobs: 0/19"),
    ("Traceback ...\nFileNotFoundError: job_board_keys.csv\n", False, 1,
     "не зібрано: FileNotFoundError"),
    ("", True, None, "не завершився"),
])
def test_every_way_the_jobs_capture_ends_has_its_own_words(out, timed_out, code, start):
    assert ng.jobs_line(out, timed_out, code).startswith(start)


@pytest.mark.parametrize("name", list(CASES))
def test_the_jobs_line_never_moves_the_verdict(name):
    kw, want = CASES[name]
    for jobs in (ng.jobs_line(JOBS_OUT, False, 0), ng.jobs_line("", True, None),
                 ng.jobs_line("Traceback\nboom\n", False, 1), "не запускався"):
        text = _render(jobs=jobs, **kw)
        line = next(ln for ln in text.splitlines() if ln.startswith("Вакансії (#513)"))
        assert not any(v in line for v in hook.VERDICTS)
        assert text.rstrip().endswith(f"Вердикт: {want}")


def test_a_second_nightly_copy_is_seen_and_a_dry_run_is_not():
    """03.10: a manual run and the scheduler's catch-up ran side by side, every
    source was asked twice, and neither copy saw the other."""
    procs = [
        (10, "python scripts/maintenance/nightly_gate.py"),                # me
        (11, r"pythonw.exe D:\trading_project\scripts\maintenance\nightly_gate.py"),
        (12, "python scripts/maintenance/nightly_gate.py --dry-run"),      # a look
        (13, "python scripts/maintenance/commit_gate.py run"),             # not a copy
    ]
    assert ng.other_copies(procs, skip={10}) == [11]
    assert ng.other_copies(procs[:1] + procs[2:], skip={10}) == [], "alone: no copy"
