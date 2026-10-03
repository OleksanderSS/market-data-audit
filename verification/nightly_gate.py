"""The nightly gate as a script, run by Windows Task Scheduler. (REGISTER #380)

WHY NOT A CLAUDE SESSION ANY MORE, 18.09. The scheduled Claude task
`trading-nightly-gate` fired three times (15-17.09) and wrote a report 0 times
by itself. 17.09 its first and only action was a `Read` outside the project,
which waits for a permission nobody grants at 03:35; the session ended with
nothing. 18.09 the PC was on all night and no session started at all. Nothing
in the job needs judgement: run the gate, read its stamp, write sixteen lines,
compare with the night before. A model in that loop adds three ways to fail
silently (the app must be open, any permission prompt kills it, the prompt can
be misread) and no capability.

Same steps as the task's prompt, same report file, so the SessionStart hook
(`is_last_nights_report_there.py`) reads it unchanged:

  1. a heavy python run is alive (pytest, rebuild, pipeline, run_, commit_gate)
     -> ПРОПУЩЕНО, with the command lines; nothing is started;
  2. HEAD and uncommitted files under src/ tests/;
  3. `commit_gate.py run`, output kept beside the report as YYYY-MM-DD.log;
  3b. the wiki-map check (#373), its own line, never changes the verdict;
  3c. `pytest tests/dean_os` (owner, 18.09), its own line -- the gate never
      runs this folder, so six reds sat unseen until #403. Unlike the wiki,
      it DOES reach the verdict: a red or unfinished dean_os under a green
      gate is ЧЕРВОНЕ / НЕ ВИМІРЯНО, because the hook reads only the verdict;
  3d. prices of names that died in the last 60 days (#434, owner 21.09), its
      own line, never changes the verdict, and runs even when step 1 skips
      the gate: it is network-light, and each night a dead name's last real
      bars are closer to gone (#289: Yahoo 1 bar a month after WBS died,
      Alpha Vantage still 99);
  3e. the forward journal (#461, #482, owner 29.09): tonight's dated
      probabilities, resolutions of old ones, the hash chain's head -- its
      own line, never changes the verdict, runs even when step 1 skips the
      gate: a night without it is a day lost for good, not a day late;
  4. the stamp: `finished` must be today, `contracts` null is NOT MEASURED;
  5. the report, compared with the latest earlier one.

The verdict word appears ONLY on the `Вердикт:` line: the hook takes the first
verdict word found anywhere, bad ones first.

    python scripts/maintenance/nightly_gate.py            # the real run
    python scripts/maintenance/nightly_gate.py --dry-run  # step 1-2 only, prints
Known answers: tests/unit/test_nightly_gate_report.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bounded_run import STEP_LIMIT_S, run_bounded  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path.home() / "trading_nightly"
HEAVY = ("pytest", "rebuild", "pipeline", "run_", "commit_gate")
WIKI = "scripts/diagnostics/does_each_declared_article_still_resolve_to_itself_373.py"
DEAN_OS_LIMIT_S = 40 * 60  # 410 s on 18.09; x6 before it counts as hung
CAPTURE = "scripts/data/capture_dying_names_prices.py"
CAPTURE_BUDGET = 12      # of Alpha Vantage's 25 free requests a day
JOURNAL = "scripts/journal/forward_journal.py"
JOURNAL_LIMIT_S = 1200   # ~520 names x 3 months from Yahoo, then pure numpy
CAPTURE_LIMIT_S = 600    # 12 requests 15 s apart is ~4 min
NEWS = "scripts/data/capture_news_nightly.py"
NEWS_LIMIT_S = 3600      # 29.09: Yahoo 503 names 378 s; Google 20 names 29 s (-> ~12 min for 503);
                         # 125 dictionary words 196 s; feeds 39 s -> ~23 min; x1.6 for a slow net
OPTIONS = "scripts/data/capture_options_nightly.py"
OPTIONS_LIMIT_S = 1200   # 503 names took 150 s on 29.09; x8 for Yahoo throttling
ANALYSTS = "scripts/data/capture_analyst_nightly.py"
ANALYSTS_LIMIT_S = 1800  # 10 names 5 s on 29.09 -> ~4 min for 503; x7 for Yahoo throttling
REDDIT = "scripts/data/capture_reddit_nightly.py"
REDDIT_LIMIT_S = 1200    # 4 subreddits 60 s apart, 2 of them 70 s on 30.09; + a 120 s retry each; x2
JOBS = "scripts/data/capture_job_postings_nightly.py"
JOBS_LIMIT_S = 2400      # 19 names 82 s on 02.10 (~4.3 s a name) -> ~18 min for 250 names; x2.2
SCHEDULED = dt.time(3, 35)  # the Task Scheduler trigger of trading-nightly-gate
LONG_RUN_MIN = 180          # 34-36 min gate + 5 dean_os + 4 capture + 3 journal + 23 news + 3 options
                            # + 4 analysts + 4 reddit (+ 2 jobs, 19 names on 02.10); x2.2
KNOWN_FLAKY = ("test_identity_columns_are_not_features.py::"
               "test_a_dropped_categorical_always_has_a_numeric_counterpart")


def _console_python() -> str:
    """python.exe even when this script runs under pythonw.exe (no console window):
    the gate's own children use sys.executable and must have real std streams."""
    exe = Path(sys.executable)
    twin = exe.with_name("python.exe")
    return str(twin if exe.name.lower() == "pythonw.exe" and twin.is_file() else exe)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=60).stdout


def heavy_processes(own_pid: int) -> list[str]:
    import psutil

    skip = {own_pid, *(p.pid for p in psutil.Process(own_pid).parents())}
    found = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] in skip or "python" not in (proc.info["name"] or "").lower():
            continue
        line = " ".join(proc.info.get("cmdline") or [])
        if any(word in line for word in HEAVY) and "nightly_gate.py" not in line:
            found.append(f"pid {proc.info['pid']}: {line[:160]}")
    return found


def other_copies(procs: list[tuple[int, str]], skip: set[int]) -> list[int]:
    """Pids of OTHER running nightly_gate.py copies (pure, for the test).

    03.10: power came back at 06:36, I started this script by hand at 06:40,
    and the scheduler started its own missed-run catch-up at 06:45. The two ran
    side by side -- every source asked twice, the second copy's options capture
    got 41 of 503 names and its analysts capture 1 of 503 -- and neither saw
    the other, because `heavy_processes` skips "nightly_gate.py" on purpose.
    A `--dry-run` is a look, not a run, and is not counted.
    """
    return [pid for pid, line in procs
            if pid not in skip and "nightly_gate.py" in line and "--dry-run" not in line]


def running_copies(own_pid: int) -> list[int]:
    import psutil

    skip = {own_pid, *(p.pid for p in psutil.Process(own_pid).parents())}
    procs = [(p.info["pid"], " ".join(p.info.get("cmdline") or []))
             for p in psutil.process_iter(["pid", "name", "cmdline"])
             if "python" in (p.info["name"] or "").lower()]
    return other_copies(procs, skip)


# ---------------------------------------------------------------- pure part

_COUNT = re.compile(r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?)")


def dean_os_result(stdout: str, timed_out: bool) -> dict:
    """The last pytest summary line of `tests/dean_os`, as counts.

    `measured` is False when the run was killed or printed no summary: a
    missing count is not a zero (the lesson of 17.09, a grep that found
    nothing read as a dead path)."""
    lines = stdout.splitlines()
    summary = next((ln for ln in reversed(lines)
                    if _COUNT.search(ln) and re.search(r" in [\d.]+s", ln)), "")
    counts = {k: 0 for k in ("passed", "failed", "skipped", "xfailed", "xpassed", "error")}
    for n, kind in _COUNT.findall(summary):
        counts["error" if kind.startswith("error") else kind] += int(n)
    secs = re.search(r" in ([\d.]+)s", summary)
    failed = [ln.split(" - ")[0].strip() for ln in lines
              if ln.startswith(("FAILED ", "ERROR "))]
    return {**counts, "seconds": float(secs.group(1)) if secs else None,
            "failed_names": failed, "measured": bool(summary) and not timed_out,
            "timed_out": timed_out}


def dean_os_line(d: dict | None) -> str:
    """Never contains a verdict word: the hook takes the first one it finds."""
    if d is None:
        return "tests/dean_os: не запускалась"
    if d["timed_out"]:
        return f"tests/dean_os: не добігла за {DEAN_OS_LIMIT_S // 60} хв, дерево процесів убито"
    if not d["measured"]:
        return "tests/dean_os: підсумку pytest немає"
    return (f"tests/dean_os: {d['passed']} passed / {d['failed']} failed / {d['error']} error / "
            f"{d['skipped']} skipped / {d['xfailed']} xfail, {d['seconds']:.0f} с")

def journal_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the forward journal (#482). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {JOURNAL_LIMIT_S} с — день прогнозу втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("journal:")), None)
    if returncode == 0 and last:
        return last.removeprefix("journal:").strip()
    if returncode == 2:
        return "ЛАНЦЮГ ХЕШІВ ПОШКОДЖЕНО, нічого не записано: " + (last or "")[:160]
    return "не записано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def news_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the raw news capture (#489). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {NEWS_LIMIT_S} с — ніч новин втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("news:")), None)
    if returncode == 0 and last:
        return last.removeprefix("news:").strip()[:300]
    return "не зібрано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def options_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the option snapshot (#489б). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {OPTIONS_LIMIT_S} с — ніч опціонів втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("options:")), None)
    if returncode == 0 and last:
        return last.removeprefix("options:").strip()[:300]
    return "не зібрано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def analysts_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the analyst snapshot (#489в). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {ANALYSTS_LIMIT_S} с — ніч оцінок аналітиків втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("analysts:")), None)
    if returncode == 0 and last:
        return last.removeprefix("analysts:").strip()[:300]
    return "не зібрано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def reddit_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the Reddit capture (#501). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {REDDIT_LIMIT_S} с — ніч Reddit втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("reddit:")), None)
    if returncode == 0 and last:
        return last.removeprefix("reddit:").strip()[:300]
    return "не зібрано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def jobs_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the job-postings capture (#513). Never a verdict word."""
    out = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {JOBS_LIMIT_S} с — ніч вакансій втрачено"
    last = next((ln for ln in reversed(out) if ln.startswith("jobs:")), None)
    if returncode == 0 and last:
        return last.removeprefix("jobs:").strip()[:300]
    return "не зібрано: " + ((last or (out[-1] if out else "без виводу"))[:160])


def capture_line(stdout: str, timed_out: bool, returncode: int | None) -> str:
    """One line from the dying-name capture. Never a verdict word: the hook
    takes the first one found anywhere in the report."""
    out = [ln for ln in stdout.splitlines() if ln.strip()]
    if timed_out:
        return f"не завершився за {CAPTURE_LIMIT_S} с"
    if returncode != 0:
        return "не зібрано: " + (out[-1].strip()[:120] if out else "без виводу")
    died = [ln for ln in out if " died " in ln]
    ok = sum(ln.rstrip().endswith(" ok") for ln in died)
    alive = sum("STILL TRADING" in ln for ln in died)
    padding = sum(ln.rstrip().endswith("padding only") for ln in died)
    refused = any("REFUSED" in ln for ln in out)
    left = next((int(m.group(1)) for ln in out
                 if (m := re.search(r"budget reached; (\d+) left", ln))), 0)
    found = next((int(m.group(1)) for ln in out
                  if (m := re.search(r"not yet captured: (\d+)", ln))), None)
    if found == 0:
        return "нових смертей за 60 днів немає"
    parts = [f"зібрано {ok}", f"досі торгуються {alive}", f"лише заповнення {padding}"]
    if refused:
        parts.append("відмова API, решта наступної ночі")
    if left:
        parts.append(f"у черзі {left}")
    return ", ".join(parts)


def verdict(stamp: dict | None, today: dt.date, gate_exit: int | None,
            dean: dict | None = None) -> tuple[str, str]:
    """(verdict word, why). Everything that is not a measured green is said."""
    word, why = _gate_verdict(stamp, today, gate_exit)
    if word not in ("ЗЕЛЕНЕ", "ЧЕРВОНЕ") or dean is None:
        return word, why
    if dean["measured"] and (dean["failed"] or dean["error"] or dean["xpassed"]):
        extra = f"tests/dean_os: {dean['failed']} failed, {dean['error']} error"
        return "ЧЕРВОНЕ", "; ".join(x for x in (why, extra) if x)
    if word == "ЗЕЛЕНЕ" and not dean["measured"]:
        return "НЕ ВИМІРЯНО", "tests/dean_os не дала підсумку"
    return word, why


def _gate_verdict(stamp: dict | None, today: dt.date, gate_exit: int | None) -> tuple[str, str]:
    if gate_exit == 2:
        return "ПРОПУЩЕНО", "ворота відмовились: іде перезбірка"
    if gate_exit is None:
        return "НЕ ВИМІРЯНО", "ворота не завершились у межах часу"
    if not stamp:
        return "НЕ ВИМІРЯНО", "штампа воріт немає"
    finished = str(stamp.get("finished") or "")
    if not finished.startswith(today.isoformat()):
        return "НЕ ВИМІРЯНО", f"штамп старий (finished {finished or '—'})"
    if stamp.get("contracts") is None:
        return "НЕ ВИМІРЯНО", "контракти не надрукували підсумку"
    if any("NOT MEASURED" in r for r in stamp.get("reasons") or []):
        return "НЕ ВИМІРЯНО", "; ".join(stamp["reasons"])
    if stamp.get("green"):
        return "ЗЕЛЕНЕ", ""
    return "ЧЕРВОНЕ", "; ".join(stamp.get("reasons") or [])


def failed_tests(stamp: dict | None, dean: dict | None = None) -> list[str]:
    names = list((dean or {}).get("failed_names") or [])
    if not stamp:
        return list(dict.fromkeys(names))
    names += [ln.split(" - ")[0].strip() for ln in stamp.get("contracts_failed_lines") or []]
    names += [ln.strip() for ln in stamp.get("ratchet_failures") or []]
    return list(dict.fromkeys(n for n in names if n))


def stamp_is_fresh(stamp: dict | None, today: dt.date) -> bool:
    return bool(stamp) and str(stamp.get("finished") or "").startswith(today.isoformat())


def stale_mark(stamp: dict) -> str:
    """22.09 (#453): a stale stamp's numbers were printed as `Contracts: 774
    passed`, the same shape as a real night, and the comparison counted a
    'healed' test from them. The mark sits inside the line, before the numbers,
    and breaks the `^Contracts: \\d+` shape parse_report reads the next night."""
    return (f" (СТАРИЙ штамп, не цієї ночі: finished {stamp.get('finished') or '—'}, "
            f"head {str(stamp.get('head') or '—')[:8]})")


def timing_line(started: dt.datetime, finished: dt.datetime) -> str:
    """When the run really happened. 22.09 (#453): the 03:35 task started at
    05:43 in a one-second wake from Modern Standby, froze with the machine and
    resumed at 09:09 -- the report said none of it. No verdict word here."""
    mins = int((finished - started).total_seconds() // 60)
    line = f"Час: старт {started:%H:%M}, кінець {finished:%H:%M} ({mins // 60} год {mins % 60:02d} хв)"
    scheduled = dt.datetime.combine(started.date(), SCHEDULED)
    notes = []
    if started - scheduled > dt.timedelta(hours=1):
        notes.append(f"запуск на {int((started - scheduled).total_seconds() // 60)} хв пізніше "
                     f"{SCHEDULED:%H:%M}")
    if finished - started > dt.timedelta(minutes=LONG_RUN_MIN):
        notes.append(f"довше {LONG_RUN_MIN} хв — машина, найімовірніше, спала посеред прогону")
    return line + ("; " + "; ".join(notes) if notes else "")


def read_power() -> dict | None:
    """{'plugged': bool, 'percent': int} now, or None when there is no battery
    to ask (a desktop) or psutil cannot read it. Never raises: a report line
    must not be the reason a night writes no report."""
    try:
        import psutil

        b = psutil.sensors_battery()
    except Exception:  # noqa: BLE001
        return None
    if b is None or b.power_plugged is None:
        return None
    return {"plugged": bool(b.power_plugged), "percent": int(round(b.percent))}


def power_line(at_start: dict | None, at_end: dict | None) -> str:
    """Mains or battery at the start and at the end of the run (#456). 22.09
    (#453) the cause of a sleeping night was found only in the Windows event
    log: on battery this laptop sleeps after 30 min and wake timers are off.
    The owner's grid is often down at night, so the line says what the machine
    ran on, not what anyone should do. No verdict word here."""
    def one(p: dict | None) -> str:
        if p is None:
            return "невідомо"
        return f"{'мережа' if p['plugged'] else 'батарея'} {p['percent']}%"

    line = f"Живлення: {one(at_start)} → {one(at_end)}"
    if any(p is not None and not p["plugged"] for p in (at_start, at_end)):
        line += " — на батареї машина засинає через 30 хв, таймери пробудження вимкнені (#453)"
    return line


def previous_report(report_dir: Path, today: dt.date) -> Path | None:
    earlier = sorted(p for p in report_dir.glob("????-??-??.md") if p.stem < today.isoformat())
    return earlier[-1] if earlier else None


def parse_report(text: str) -> dict:
    head = re.search(r"^HEAD: (\w+)", text, re.M)
    passed = re.search(r"^Contracts: (\d+) passed", text, re.M)
    failed = re.findall(r"^- ((?:FAILED |ERROR )?\S+::\S+)", text, re.M)
    return {"head": head.group(1) if head else None,
            "passed": int(passed.group(1)) if passed else None,
            "failed": {f.split(" ", 1)[-1] for f in failed}}


def render(*, today: dt.date, head: str, dirty: list[str], stamp: dict | None,
           gate_exit: int | None, wiki_line: str, busy: list[str],
           previous: tuple[str, str] | None, dean: dict | None = None,
           capture: str = "не запускався", started: dt.datetime | None = None,
           finished: dt.datetime | None = None, power: str | None = None,
           journal: str = "не запускався", news: str = "не запускався",
           options: str = "не запускався", analysts: str = "не запускався",
           reddit: str = "не запускався", jobs: str = "не запускався") -> str:
    lines = [f"# Нічна перевірка {today.isoformat()} (скрипт nightly_gate.py)", ""]
    when = [timing_line(started, finished)] if started and finished else []
    when += [power] if power else []
    if busy:
        lines += [f"HEAD: {head}", *when, "Іде важкий прогін, ворота не запускались:"]
        lines += [f"  {b}" for b in busy[:5]]
        lines.append(f"Ціни мертвих імен (#434): {capture}")
        lines.append(f"Журнал уперед (#482): {journal}")
        lines.append(f"Новини (#489): {news}")
        lines.append(f"Опціони (#489б): {options}")
        lines.append(f"Аналітики (#489в): {analysts}")
        lines.append(f"Reddit (#501): {reddit}")
        lines.append(f"Вакансії (#513): {jobs}")
        lines.append("Вердикт: ПРОПУЩЕНО")
        return "\n".join(lines) + "\n"
    if dirty:
        lines.append(f"ДЕРЕВО БРУДНЕ: {len(dirty)} файлів — результат про незакомічений код")
    lines.append(f"HEAD: {head}")
    lines += when
    word, why = verdict(stamp, today, gate_exit, dean)
    fresh = stamp_is_fresh(stamp, today)
    mark = "" if fresh or not stamp else stale_mark(stamp)
    c = (stamp or {}).get("contracts")
    lines.append(f"Contracts{mark}: " + (f"{c['passed']} passed / {c['skipped']} skipped / "
                                         f"{c['failed']} failed / {c['error']} error" if c else "—"))
    if stamp:
        tail = (stamp.get("ratchet_tail") or ["—"])[-1]
        lines.append(f"Храповик{mark}: exit {stamp.get('ratchet_exit')} — «{tail}»")
    lines.append(dean_os_line(dean))
    failed = failed_tests(stamp if fresh else None, dean)
    if not fresh:
        c = None  # an old stamp's count is not tonight's: no count comparison below
    if failed:
        lines.append(f"Впалі ({len(failed)}, до 10):")
        lines += [f"- {n}" for n in failed[:10]]
        if all(KNOWN_FLAKY in n for n in failed):
            lines.append("лише #376")
    lines.append(f"Карта вікі (#373): {wiki_line}")
    lines.append(f"Ціни мертвих імен (#434): {capture}")
    lines.append(f"Журнал уперед (#482): {journal}")
    lines.append(f"Новини (#489): {news}")
    lines.append(f"Опціони (#489б): {options}")
    lines.append(f"Аналітики (#489в): {analysts}")
    lines.append(f"Reddit (#501): {reddit}")
    lines.append(f"Вакансії (#513): {jobs}")
    if previous and stamp and not fresh:
        lines.append(f"Порівняння з {previous[0]}: не порівнювалось — числа воріт зі старого штампа")
    elif previous:
        name, text = previous
        prev = parse_report(text)
        now_names = {n.split(" ", 1)[-1] for n in failed}
        new = sorted(now_names - prev["failed"])
        healed = sorted(prev["failed"] - now_names)
        lines.append(f"Порівняння з {name}: нові червоні {len(new)}, полагодились {len(healed)}"
                     + (f"; нові: {', '.join(new[:3])}" if new else ""))
        if (c and prev["passed"] is not None and prev["head"]
                and head.startswith(prev["head"][:7]) and abs(c["passed"] - prev["passed"]) > 5):
            lines.append(f"кількість тестів змінилась без коміту: {prev['passed']} -> {c['passed']}")
    else:
        lines.append("Порівняння: попереднього звіту немає")
    if why:
        lines.append(f"Причина: {why}")
    lines.append(f"Вердикт: {word}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- run

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=REPORT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    started = dt.datetime.now()
    power_at_start = read_power()
    today = started.date()
    args.dir.mkdir(parents=True, exist_ok=True)
    head = _git("rev-parse", "--short", "HEAD").strip() or "—"
    dirty = [ln for ln in _git("status", "--porcelain", "--", "src", "tests").splitlines() if ln.strip()]
    busy = heavy_processes(os.getpid())
    copies = running_copies(os.getpid())
    if args.dry_run:
        print(f"HEAD {head}, dirty {len(dirty)}, heavy {busy}, other nightly copies {copies}")
        return 0
    if copies:
        # The copy already running writes today's report; a second one would
        # only ask every source twice. Said in a file of its own, never in the
        # report, so the report stays the running copy's.
        (args.dir / f"{today.isoformat()}.second_copy_refused.log").write_text(
            f"{started:%H:%M:%S} refused: nightly_gate.py already running as pid "
            f"{copies}; nothing collected, nothing gated by this copy.\n", encoding="utf-8")
        print(f"another nightly_gate.py is running (pid {copies}); this copy does nothing")
        return 3

    stamp, gate_exit, wiki_line, dean = None, None, "не перевірялась", None
    py = _console_python()
    cap = run_bounded([py, CAPTURE, "--budget", str(CAPTURE_BUDGET)], cwd=ROOT,
                      timeout_s=CAPTURE_LIMIT_S)
    capture = capture_line(cap.stdout, cap.timed_out, cap.returncode)
    (args.dir / f"{today.isoformat()}.capture.log").write_text(
        cap.stdout + "\n--- stderr ---\n" + cap.stderr[-2000:], encoding="utf-8")
    jr = run_bounded([py, JOURNAL, "record"], cwd=ROOT, timeout_s=JOURNAL_LIMIT_S)
    journal = journal_line(jr.stdout, jr.timed_out, jr.returncode)
    (args.dir / f"{today.isoformat()}.journal.log").write_text(
        jr.stdout + "\n--- stderr ---\n" + jr.stderr[-2000:], encoding="utf-8")
    nw = run_bounded([py, NEWS], cwd=ROOT, timeout_s=NEWS_LIMIT_S)
    news = news_line(nw.stdout, nw.timed_out, nw.returncode)
    (args.dir / f"{today.isoformat()}.news.log").write_text(
        nw.stdout[-20000:] + "\n--- stderr ---\n" + nw.stderr[-2000:], encoding="utf-8")
    op = run_bounded([py, OPTIONS], cwd=ROOT, timeout_s=OPTIONS_LIMIT_S)
    options = options_line(op.stdout, op.timed_out, op.returncode)
    (args.dir / f"{today.isoformat()}.options.log").write_text(
        op.stdout[-20000:] + "\n--- stderr ---\n" + op.stderr[-2000:], encoding="utf-8")
    an = run_bounded([py, ANALYSTS], cwd=ROOT, timeout_s=ANALYSTS_LIMIT_S)
    analysts = analysts_line(an.stdout, an.timed_out, an.returncode)
    (args.dir / f"{today.isoformat()}.analysts.log").write_text(
        an.stdout[-20000:] + "\n--- stderr ---\n" + an.stderr[-2000:], encoding="utf-8")
    rd = run_bounded([py, REDDIT], cwd=ROOT, timeout_s=REDDIT_LIMIT_S)
    reddit = reddit_line(rd.stdout, rd.timed_out, rd.returncode)
    (args.dir / f"{today.isoformat()}.reddit.log").write_text(
        rd.stdout[-20000:] + "\n--- stderr ---\n" + rd.stderr[-2000:], encoding="utf-8")
    jb = run_bounded([py, JOBS], cwd=ROOT, timeout_s=JOBS_LIMIT_S)
    jobs = jobs_line(jb.stdout, jb.timed_out, jb.returncode)
    (args.dir / f"{today.isoformat()}.jobs.log").write_text(
        jb.stdout[-20000:] + "\n--- stderr ---\n" + jb.stderr[-2000:], encoding="utf-8")
    if not busy:
        gate = run_bounded([py, "scripts/maintenance/commit_gate.py", "run"], cwd=ROOT,
                           timeout_s=3 * STEP_LIMIT_S)
        (args.dir / f"{today.isoformat()}.log").write_text(
            gate.stdout + "\n--- stderr ---\n" + gate.stderr, encoding="utf-8")
        gate_exit = None if gate.timed_out else gate.returncode
        sp = ROOT / _git("rev-parse", "--git-path", "commit_gate_stamp.json").strip()
        if sp.is_file():
            stamp = json.loads(sp.read_text(encoding="utf-8"))
        wiki = run_bounded([py, WIKI], cwd=ROOT, timeout_s=300)
        out = [ln for ln in wiki.stdout.splitlines() if ln.strip()]
        if wiki.timed_out or wiki.returncode not in (0, 1):
            wiki_line = "НЕ ПЕРЕВІРЕНО: " + (out[-1] if out else "без виводу")
        elif wiki.returncode == 0:
            wiki_line = next((ln for ln in out if ln.startswith("live titles")), "0") + " — чисто"
        else:
            wiki_line = "; ".join(ln for ln in out if ln.startswith("MOVED"))
        if gate_exit not in (None, 2):
            run = run_bounded([py, "-m", "pytest", "tests/dean_os", "-q", "-rfE", "--no-header"],
                              cwd=ROOT, timeout_s=DEAN_OS_LIMIT_S)
            with (args.dir / f"{today.isoformat()}.log").open("a", encoding="utf-8") as log:
                log.write("\n--- tests/dean_os ---\n" + "\n".join(run.stdout.splitlines()[-40:])
                          + "\n--- stderr ---\n" + run.stderr[-2000:])
            dean = dean_os_result(run.stdout, run.timed_out)

    prev = previous_report(args.dir, today)
    text = render(today=today, head=head, dirty=dirty, stamp=stamp, gate_exit=gate_exit,
                  wiki_line=wiki_line, busy=busy, dean=dean, capture=capture,
                  started=started, finished=dt.datetime.now(), journal=journal, news=news, options=options,
                  analysts=analysts, reddit=reddit, jobs=jobs,
                  power=power_line(power_at_start, read_power()),
                  previous=(prev.name, prev.read_text(encoding="utf-8")) if prev else None)
    (args.dir / f"{today.isoformat()}.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
