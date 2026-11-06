"""
h1_mac.py — 맥에서 H1 포워드를 준비할 때 손으로 칠 것을 줄여 주는 도우미 (단계 7 준비, 2026-11-06)

주식 초보용 설명
- 운영 안내서 `docs/h1-forward-run.md` 의 §3.3~§3.4(venv 만들기 → 시험 → 지킴이 → 재현 → 지문 확인)와
  §4(자동 실행 설정 파일 plist 세 개 만들기), §3.7(시작 전 확인)을 명령 하나씩으로 묶었다.
- 이 파일은 **장부·시험 대상 코드(h1.CODE_FILES)가 아니다.** 바꿔도 코드 지문·재현 통과 기록에 영향이 없다.
- 진짜 돈·주문·운영 폴더(`/Users/나/claude-stock`)·운영 장부는 건드리지 않는다. launchd 에 켜는 일(`launchctl load`)도
  하지 않고, 칠 명령만 화면에 보여 준다(사람이 확인하고 친다).
- 표준 라이브러리만 쓴다(venv 를 만들기 전에도 돈다).

사용 (H1 전용 폴더 `/Users/나/claude-stock-h1` 안에서)
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 tools/h1_mac.py setup
      [1/8] 파이썬 3.13.18 확인 → [2/8] venv 만들기(없으면) → [3/8] 라이브러리 설치 → [4/8] pytest → [5/8] R2 자료 받기
      → [6/8] 지킴이 → [7/8] 재현(약 8분) → [8/8] 코드 지문 비교. 하나라도 실패하면 거기서 멈춘다(종료 코드 1).
      --from N 으로 N 번째부터 다시 할 수 있다. --dry-run 은 할 일만 보여 준다.
  ~/.venv-h1/bin/python tools/h1_mac.py plists [--claude /경로/claude] [--icloud-status] [--force]
      ~/Library/LaunchAgents/ 에 com.claude-stock.h1-kr / h1-us / h1-report .plist 를 만든다(plistlib 로 써서 XML 이 깨질 일이
      없다). 이미 있으면 덮지 않는다(--force 로 덮음). 켜는 명령은 화면에 보여 주기만 한다.
  ~/.venv-h1/bin/python tools/h1_mac.py check
      시작 전 확인(안내서 §3.7): 태그·깨끗함·status·KS200 최근 날짜·S&P500 목록 수·launchd 파일이 H1 폴더만 가리키는지.

종료 코드: 0 모두 됨 / 1 어느 단계 실패(화면 글을 Claude Code 에 보여 주기) / 9 인자 오류
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # H1 전용 폴더(이 파일이 있는 저장소)
PY_WANT = (3, 13, 18)
VENV_NAME = ".venv-h1"
TAG = "h1-forward-v1"
R2_BRANCH = "research-r2-2026-11-04"
LABELS = {"kr": "com.claude-stock.h1-kr", "us": "com.claude-stock.h1-us", "report": "com.claude-stock.h1-report"}
WORDS = {"kr": "국내", "us": "미국"}
# 운영 안내서 §4 표와 같은 시각(맥 = 한국 시간). launchd Weekday: 0·7 = 일, 1 = 월 … 6 = 토
SCHEDULE = {
    "kr": [(d, 23, 5) for d in (1, 2, 3, 4, 5)] + [(d, 7, 40) for d in (1, 2, 3, 4, 5, 6)],
    "us": [(d, 7, 10) for d in (2, 3, 4, 5, 6)] + [(d, 8, 40) for d in (1, 2, 3, 4, 5, 6)],
}
REPORT_AT = {"Day": 2, "Hour": 9, "Minute": 30}
BASE_PATH = ("/opt/homebrew/bin", "/usr/bin", "/bin")


class Stop(Exception):
    """이 단계에서 멈춤(사람이 화면을 보고 판단)."""


def say(*a):
    print(*a, flush=True)


def icloud_dir(home: Path) -> Path:
    return home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def venv_python(home: Path) -> Path:
    return home / VENV_NAME / "bin" / "python"


# ============================ setup ============================

def _run(cmd, *, cwd=ROOT, what=""):
    say("    $ " + " ".join(str(c) for c in cmd))
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd))
    except OSError as e:
        raise Stop(f"{what} 실행 못 함({type(e).__name__}: {e})")
    if p.returncode != 0:
        raise Stop(f"{what} 실패(종료 코드 {p.returncode})")


def _out(cmd, *, cwd=ROOT) -> str:
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True)
    if p.returncode != 0:
        raise Stop(f"{' '.join(str(c) for c in cmd)} 실패: {(p.stderr or p.stdout).strip()[-400:]}")
    return p.stdout.strip()


def check_location(root: Path, home: Path):
    """H1 폴더가 iCloud 동기화 폴더(~/Desktop·~/Documents·iCloud Drive) 안이면 멈춤(안내서 §3.3)."""
    r = root.resolve()
    for bad in (home / "Desktop", home / "Documents", icloud_dir(home)):
        try:
            r.relative_to(bad.resolve())
        except ValueError:
            continue
        raise Stop(f"H1 폴더 {r} 가 iCloud 동기화 폴더({bad}) 안에 있어요 → 그 밖(예 {home}/claude-stock-h1)에 다시 만드세요")


def setup_steps(home: Path):
    vpy = venv_python(home)
    return [
        ("파이썬 3.13.18 인지 확인", lambda: _check_python(sys.version_info[:3], sys.executable)),
        (f"H1 전용 venv({home / VENV_NAME}) 만들기(이미 있으면 버전만 확인)", lambda: _make_venv(home)),
        ("라이브러리 설치(requirements-h1.txt, 정확한 버전)",
         lambda: _run([vpy, "-m", "pip", "install", "-r", "requirements-h1.txt"], what="라이브러리 설치")),
        ("시험(pytest, 약 4분 — 전부 통과해야 함)", lambda: _run([vpy, "-m", "pytest", "-q"], what="pytest")),
        (f"재현 기준값 자료 받기(git fetch origin {R2_BRANCH})",
         lambda: _run(["git", "fetch", "origin", R2_BRANCH], what="git fetch")),
        ("지킴이(약 5분 — 마지막에 '모두 통과')",
         lambda: _run([vpy, "tools/h1_test_guard.py", "--quick"], what="지킴이")),
        ("재현(약 8분 — 마지막에 '종료 코드 0 — 통과 + 기록함')", lambda: _run([vpy, "h1_replay.py"], what="재현")),
        ("코드 지문이 재현 통과 기록과 같은지", lambda: _compare_hash(vpy)),
    ]


def _check_python(ver, exe):
    if tuple(ver) != PY_WANT:
        raise Stop(f"이 파이썬은 {'.'.join(map(str, ver))} ({exe}). 3.13.18 이어야 해요 → python.org 의 3.13.18 로 다시 "
                   "(안내서 §3.1). brew 파이썬은 쓰지 않아요")
    say(f"    파이썬 {'.'.join(map(str, ver))} ({exe}) — 맞음")


def _make_venv(home: Path):
    vpy = venv_python(home)
    if not vpy.exists():
        _run([sys.executable, "-m", "venv", home / VENV_NAME], what="venv 만들기")
    got = _out([vpy, "-c", "import platform; print(platform.python_version())"])
    if got != ".".join(map(str, PY_WANT)):
        raise Stop(f"venv 의 파이썬이 {got} 이에요(3.13.18 이어야 함) → {home / VENV_NAME} 를 지우고 다시 setup")
    say(f"    venv 파이썬 {got} — 맞음")


def _compare_hash(vpy: Path):
    now = _out([vpy, "-c", "import h1; print(h1.code_hash()[0])"])
    p = ROOT / "state" / "h1" / "replay_pass.json"
    try:
        last = json.loads(p.read_text(encoding="utf-8"))[-1]["code_hash"]
    except (OSError, ValueError, LookupError, TypeError) as e:
        raise Stop(f"재현 통과 기록 {p} 를 읽지 못함({type(e).__name__}) → 재현부터 다시(--from 7)")
    say(f"    지금 코드 {now}\n    통과 기록 {last}")
    if now != last:
        raise Stop("지문이 달라요 → 멈추고 Claude Code 에 이 화면을 보여 주세요")
    say("    같음")


def cmd_setup(a, home: Path) -> int:
    steps = setup_steps(home)
    try:
        check_location(ROOT, home)
    except Stop as e:
        say(f"[setup] 멈춤: {e}")
        return 1
    start = a.from_step
    if not 1 <= start <= len(steps):
        say(f"[setup] --from 은 1~{len(steps)}")
        return 9
    for i, (what, fn) in enumerate(steps, 1):
        if i < start:
            continue
        say(f"[{i}/{len(steps)}] {what}")
        if a.dry_run:
            continue
        try:
            fn()
        except Stop as e:
            say(f"\n[setup] {i}번째에서 멈춤: {e}\n  이 화면 글을 그대로 Claude Code 에 보여 주세요. 고친 뒤에는 --from {i} 로 이어서.")
            return 1
    if a.dry_run:
        say("[setup] --dry-run: 위 순서로 합니다(아무것도 안 함)")
    else:
        say("[setup] 모두 통과 — 다음: 안내서 §3.5(claude 시험)·§3.6(잠자기) → tools/h1_mac.py plists → check")
    return 0


# ============================ plists ============================

def claude_dir(claude: str | None) -> str:
    path = claude or shutil.which("claude")
    if not path:
        raise Stop("claude 를 찾지 못했어요 → 터미널에서 `which claude` 로 경로를 보고 --claude /그/경로/claude 로 다시")
    p = Path(path)
    if p.name != "claude":
        raise Stop(f"--claude 는 claude 실행 파일 경로여야 해요(받은 값 {path})")
    return str(p.parent)


def launch_path(cdir: str) -> str:
    parts = [cdir] + [x for x in BASE_PATH if x != cdir]
    return ":".join(parts)


def run_command(mk: str, root: Path, home: Path, icloud_status: bool) -> str:
    py = venv_python(home)
    word = WORDS[mk]
    tee = ""
    if icloud_status:
        dest = icloud_dir(home) / f"H1-상태-{mk}.txt"
        tee = f' {py} h1.py status --market {mk} | tee "{dest}" ;'
    return (f"{py} h1.py run --market {mk}; c=$?;{tee} [ $c -eq 0 ] || osascript -e "
            f"\"display notification \\\"H1 {word} 종료 코드 $c (logs/h1-{mk}.log)\\\" with title \\\"claude-stock\\\"\"; exit $c")


def make_plist(kind: str, root: Path, home: Path, path_env: str, icloud_status=False) -> dict:
    logs = root / "logs"
    if kind == "report":
        py = venv_python(home)
        return {
            "Label": LABELS["report"], "WorkingDirectory": str(root),
            "ProgramArguments": ["/bin/sh", "-c",
                                 f"m=$(date -v-1m +%Y-%m); for k in us kr; do {py} h1_report.py --market $k --month $m; done"],
            "StartCalendarInterval": dict(REPORT_AT),
            "StandardOutPath": str(logs / "h1-report.log"), "StandardErrorPath": str(logs / "h1-report.log"),
        }
    return {
        "Label": LABELS[kind], "WorkingDirectory": str(root),
        "EnvironmentVariables": {"PATH": path_env},
        "ProgramArguments": ["/usr/bin/caffeinate", "-i", "/bin/sh", "-c", run_command(kind, root, home, icloud_status)],
        "StartCalendarInterval": [{"Weekday": d, "Hour": h, "Minute": m} for d, h, m in SCHEDULE[kind]],
        "StandardOutPath": str(logs / f"h1-{kind}.log"), "StandardErrorPath": str(logs / f"h1-{kind}.log"),
    }


def cmd_plists(a, home: Path) -> int:
    try:
        cdir = claude_dir(a.claude)
    except Stop as e:
        say(f"[plists] 멈춤: {e}")
        return 1
    out = Path(a.out) if a.out else home / "Library" / "LaunchAgents"
    out.mkdir(parents=True, exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    pathenv = launch_path(cdir)
    targets = {k: out / f"{LABELS[k]}.plist" for k in ("kr", "us", "report")}
    have = [p for p in targets.values() if p.exists()]
    if have and not a.force:
        say("[plists] 이미 있어 덮지 않았어요: " + ", ".join(p.name for p in have) + " (다시 만들려면 --force)")
        return 1
    for k, p in targets.items():
        d = make_plist(k, ROOT, home, pathenv, a.icloud_status)
        blob = plistlib.dumps(d, fmt=plistlib.FMT_XML, sort_keys=False)
        if plistlib.loads(blob) != d:                     # 다시 읽어 같은지(깨진 파일을 남기지 않게)
            say(f"[plists] {p.name} 을 다시 읽었더니 달라요 — 멈춤")
            return 1
        tmp = p.with_suffix(".plist.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, p)
        say(f"[plists] 만듦: {p}")
    say(f"  PATH = {pathenv}  (claude 폴더 {cdir} 가 맨 앞)")
    say("  다음 명령으로 확인하고 켜세요(안내서 §4.2 — start 전에 켜기):")
    say("    plutil -lint " + " ".join(str(p) for p in targets.values()))
    for k in ("kr", "us", "report"):
        say(f"    launchctl load -w {targets[k]}")
    say(f"    launchctl kickstart gui/$(id -u)/{LABELS['kr']}")
    return 0


# ============================ check ============================

def cmd_check(a, home: Path) -> int:
    vpy = venv_python(home)
    problems = []

    def item(title, fn):
        say(f"- {title}")
        try:
            fn()
        except Stop as e:
            problems.append(f"{title}: {e}")
            say(f"    ✗ {e}")

    def tag():
        got = _out(["git", "describe", "--tags", "--exact-match"])
        if got != TAG:
            raise Stop(f"태그가 {got} 예요({TAG} 이어야 함)")
        say(f"    {got} — 맞음")

    def clean():
        got = _out(["git", "status", "--short"])
        if got:
            raise Stop("고친 파일이 있어요:\n" + got)
        say("    깨끗함")

    def status():
        for mk in ("kr", "us"):
            p = subprocess.run([str(vpy), "h1.py", "status", "--market", mk], cwd=str(ROOT), capture_output=True, text=True)
            say("    " + "\n    ".join((p.stdout or p.stderr).strip().splitlines()[:3]))

    def ks200():
        say("    " + _out([vpy, "-c", "import FinanceDataReader as f; print(f.DataReader('KS200').tail(3))"])
            .replace("\n", "\n    "))
        say("    → 맨 아래 날짜가 어제(22:30 뒤면 오늘)여야 해요")

    def sp500():
        n = _out([vpy, "-c", "import screener; print(len(screener.universe(40)))"])
        if n != "40":
            raise Stop(f"S&P500 목록에서 {n} 종목(40 이어야 함)")
        say("    40 — 맞음")

    def agents():
        d = home / "Library" / "LaunchAgents"
        bad = []
        for p in sorted(d.glob("*.plist")) if d.exists() else []:
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if str(ROOT) in txt and not p.name.startswith("com.claude-stock.h1-"):
                bad.append(p.name)
        if bad:
            raise Stop("H1 폴더를 가리키는 다른 작업이 있어요: " + ", ".join(bad))
        mine = [p.name for p in d.glob("com.claude-stock.h1-*.plist")] if d.exists() else []
        say("    H1 작업: " + (", ".join(sorted(mine)) or "아직 없음(§4 전이면 정상)"))

    item(f"태그 {TAG}", tag)
    item("고친 파일 없음", clean)
    item("h1.py status(start 전이면 '장부 없음'이 정상)", status)
    item("KS200 최근 날짜", ks200)
    item("미국 S&P500 목록 받기", sp500)
    item("launchd 파일", agents)
    if problems:
        say("\n[check] 확인할 것 " + str(len(problems)) + "개 — 화면을 Claude Code 에 보여 주세요")
        return 1
    say("\n[check] 모두 맞음 — 다음: 안내서 §4(자동 실행 켜기) → §5(start)")
    return 0


# ============================ main ============================

def main(argv=None, home: Path | None = None) -> int:
    ap = argparse.ArgumentParser(prog="h1_mac.py", description="맥 H1 준비 도우미(setup · plists · check)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="venv → 시험 → 지킴이 → 재현 → 지문(안내서 §3.3·§3.4)")
    s.add_argument("--from", dest="from_step", type=int, default=1)
    s.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("plists", help="launchd 설정 파일 세 개 만들기(안내서 §4·§7)")
    p.add_argument("--claude", default=None, help="claude 실행 파일 경로(없으면 which claude)")
    p.add_argument("--icloud-status", action="store_true", help="실행 뒤 status 글을 iCloud Drive 에 남김(안내서 §6)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--out", default=None, help=argparse.SUPPRESS)       # 시험용
    sub.add_parser("check", help="시작 전 확인(안내서 §3.7)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 9
    home = home or Path.home()
    return {"setup": cmd_setup, "plists": cmd_plists, "check": cmd_check}[a.cmd](a, home)


if __name__ == "__main__":
    sys.exit(main())
