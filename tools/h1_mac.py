"""
h1_mac.py — 맥에서 H1 포워드를 준비할 때 손으로 칠 것을 줄여 주는 도우미 (단계 7 준비, 2026-11-06, 검토 7a 반영)

주식 초보용 설명
- 운영 안내서 `docs/h1-forward-run.md` 의 §3.3~§3.4(venv 만들기 → 시험 → 지킴이 → 재현 → 지문 확인),
  §3.7(시작 전 확인), §4.1·§7(자동 실행 설정 파일 plist 세 개)을 명령 하나씩으로 묶었다.
- 이 파일은 **장부·시험 대상 코드(h1.CODE_FILES)가 아니다.** 바꿔도 코드 지문·재현 통과 기록에 영향이 없다.
- 진짜 돈·주문·운영 폴더(`/Users/나/claude-stock`)·운영 장부는 건드리지 않는다. launchd 에 켜는 일(`launchctl load`)도
  하지 않고, 칠 명령만 화면에 보여 준다(사람이 확인하고 친다).
- 표준 라이브러리만 쓴다(venv 를 만들기 전에도 돈다).

순서 (H1 전용 폴더 `/Users/나/claude-stock-h1` 안에서, 안내서 순서와 같음)
  1) /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 tools/h1_mac.py setup     (안내서 §3.3·§3.4)
       [1/8] 파이썬 확인 → [2/8] venv(+logs 폴더) → [3/8] 라이브러리 → [4/8] R2 자료 받기 → [5/8] pytest(건너뜀도 0 이어야)
       → [6/8] 지킴이 → [7/8] 재현(약 8분) → [8/8] 코드 지문 비교. 실패하면 거기서 멈춘다(--from N 으로 이어서).
  2) 안내서 §3.5(claude 시험)·§3.6(잠자기)은 손으로
  3) ~/.venv-h1/bin/python tools/h1_mac.py check        (안내서 §3.7)
  4) ~/.venv-h1/bin/python tools/h1_mac.py plists [--claude /경로/claude] [--icloud-status] [--force]   (안내서 §4.1·§7)
       ~/Library/LaunchAgents/ 에 com.claude-stock.h1-kr / h1-us / h1-report .plist 를 만든다(plistlib 로 써서 XML 이 깨질
       일이 없다, 경로는 셸 따옴표로 감쌈). 켜는 명령은 화면에 보여 주기만 한다. H1 전용 폴더(이름 claude-stock-h1)에서만.

종료 코드: 0 모두 됨 / 1 어느 단계 실패·확인할 것 있음(화면 글을 Claude Code 에 보여 주기) / 9 인자 오류 / 130 사람이 멈춤
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # H1 전용 폴더(이 파일이 있는 저장소)
H1_DIR_NAME = "claude-stock-h1"                      # 안내서 §3.3 의 폴더 이름(리허설 폴더와 구별, 검토 7a M-3)
PY_WANT = (3, 13, 18)
FRAMEWORK = "/Library/Frameworks/Python.framework/Versions/3.13"
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
KS200_STALE_DAYS = 5                                  # KS200 마지막 날짜가 이보다 오래되면 "확인할 것"(주말·연휴 감안)


class Stop(Exception):
    """이 단계에서 멈춤(사람이 화면을 보고 판단)."""


def say(*a):
    print(*a, flush=True)


def icloud_dir(home: Path) -> Path:
    return home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def venv_python(home: Path) -> Path:
    return home / VENV_NAME / "bin" / "python"


def q(p) -> str:
    """셸 글에 넣을 경로를 따옴표로 감쌈(빈칸·한글이 든 경로, 검토 7a M-2)."""
    return shlex.quote(str(p))


# ============================ 명령 돌리기 ============================

def _run(cmd, *, cwd=None, what=""):
    """화면에 보이며 돌림. 0 이 아니면 Stop. cwd 기본은 부르는 순간의 ROOT(검토 7a M-9)."""
    say("    $ " + " ".join(q(c) for c in cmd))
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd or ROOT))
    except OSError as e:
        raise Stop(f"{what} 실행 못 함({type(e).__name__}: {e})")
    if p.returncode != 0:
        raise Stop(f"{what} 실패(종료 코드 {p.returncode})")


def _out(cmd, *, cwd=None) -> str:
    """조용히 돌려 글을 받음. 0 이 아니거나 실행 못 하면 Stop(검토 7a M-12)."""
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd or ROOT), capture_output=True, text=True)
    except OSError as e:
        raise Stop(f"{' '.join(str(c) for c in cmd)} 실행 못 함({type(e).__name__}: {e})")
    if p.returncode != 0:
        raise Stop(f"{' '.join(str(c) for c in cmd)} 실패: {(p.stderr or p.stdout).strip()[-400:]}")
    return p.stdout.strip()


# ============================ setup ============================

def check_location(root: Path, home: Path):
    """H1 폴더가 iCloud 동기화 폴더(~/Desktop·~/Documents·iCloud Drive) 안이면 멈춤(안내서 §3.3)."""
    r = root.resolve()
    for bad in (home / "Desktop", home / "Documents", icloud_dir(home)):
        try:
            r.relative_to(bad.resolve())
        except ValueError:
            continue
        raise Stop(f"H1 폴더 {r} 가 iCloud 동기화 폴더({bad}) 안에 있어요 → 그 밖(예 {home}/{H1_DIR_NAME})에 다시 만드세요")


def _check_python(ver, exe, *, platform=None, base_prefix=None, cafile=None):
    """3.13.18 인지. 맥이면 python.org 파이썬인지·인증서 단계를 했는지도(검토 7a M-13, 6d D-2)."""
    platform = sys.platform if platform is None else platform
    if tuple(ver) != PY_WANT:
        raise Stop(f"이 파이썬은 {'.'.join(map(str, ver))} ({exe}). 3.13.18 이어야 해요 → python.org 의 3.13.18 로 다시 "
                   "(안내서 §3.1). brew 파이썬은 쓰지 않아요")
    if platform == "darwin":
        bp = sys.base_prefix if base_prefix is None else base_prefix
        if not str(bp).startswith(FRAMEWORK):
            raise Stop(f"이 파이썬({bp})은 python.org 설치본이 아니에요(brew 등) → 안내서 §3.1 의 "
                       f"{FRAMEWORK}/bin/python3.13 로 다시")
        ca = ssl.get_default_verify_paths().cafile if cafile is None else cafile
        if not ca or not os.path.exists(ca):
            raise Stop("인증서 단계가 안 됐어요 → Finder → 응용 프로그램 → Python 3.13 → "
                       "'Install Certificates.command' 를 두 번 눌러 실행한 뒤 다시(안내서 §3.1)")
    say(f"    파이썬 {'.'.join(map(str, ver))} ({exe}) — 맞음")


def _make_venv(home: Path):
    vpy = venv_python(home)
    if not vpy.exists():
        _run([sys.executable, "-m", "venv", home / VENV_NAME], what="venv 만들기")
    got = _out([vpy, "-c", "import platform; print(platform.python_version())"])
    if got != ".".join(map(str, PY_WANT)):
        raise Stop(f"venv 의 파이썬이 {got} 이에요(3.13.18 이어야 함) → {home / VENV_NAME} 를 지우고 다시 setup")
    (ROOT / "logs").mkdir(exist_ok=True)              # launchd 로그 폴더(안내서 §3.3 mkdir -p logs, 검토 7a M-11)
    say(f"    venv 파이썬 {got} — 맞음 · logs/ 폴더 있음")


def _pytest(vpy: Path):
    """pytest 를 돌리고 건너뜀(skipped)도 0 인지 본다(R2 자료가 없으면 20개가 건너뛰어짐, 검토 7a M-10)."""
    with tempfile.TemporaryDirectory(prefix="h1-mac-") as d:
        xml = Path(d) / "junit.xml"
        _run([vpy, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"], what="pytest")
        try:
            root = ET.parse(xml).getroot()
        except (OSError, ET.ParseError) as e:
            raise Stop(f"pytest 결과 파일을 읽지 못함({type(e).__name__})")
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    n = {k: int((suite.get(k) if suite is not None else None) or 0) for k in ("tests", "failures", "errors", "skipped")}
    if n["failures"] or n["errors"] or n["skipped"]:
        raise Stop(f"시험 {n['tests']}개 중 실패 {n['failures']} · 오류 {n['errors']} · 건너뜀 {n['skipped']} "
                   "— 모두 0 이어야 해요(건너뜀이면 4단계 R2 자료 받기를 확인)")
    say(f"    시험 {n['tests']}개 모두 통과(건너뜀 0)")


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


def setup_steps(home: Path):
    vpy = venv_python(home)
    return [
        ("파이썬 3.13.18(python.org)인지 확인", lambda: _check_python(sys.version_info[:3], sys.executable)),
        (f"H1 전용 venv({home / VENV_NAME}) 만들기(이미 있으면 버전만 확인) · logs/ 폴더", lambda: _make_venv(home)),
        ("라이브러리 설치(requirements-h1.txt, 정확한 버전)",
         lambda: _run([vpy, "-m", "pip", "install", "-r", "requirements-h1.txt"], what="라이브러리 설치")),
        (f"재현 기준값 자료 받기(git fetch origin {R2_BRANCH} — 이 폴더의 git 기록만 받음, 운영 파일은 그대로)",
         lambda: _run(["git", "fetch", "origin", R2_BRANCH], what="git fetch")),
        ("시험(pytest, 약 4분 — 실패·건너뜀 모두 0 이어야 함)", lambda: _pytest(vpy)),
        ("지킴이(약 5분 — 마지막에 '모두 통과')",
         lambda: _run([vpy, "tools/h1_test_guard.py", "--quick"], what="지킴이")),
        ("재현(약 8분 — 마지막에 '종료 코드 0 — 통과 + 기록함')", lambda: _run([vpy, "h1_replay.py"], what="재현")),
        ("코드 지문이 재현 통과 기록과 같은지", lambda: _compare_hash(vpy)),
    ]


def cmd_setup(a, home: Path) -> int:
    steps = setup_steps(home)
    if not 1 <= a.from_step <= len(steps):
        say(f"[setup] --from 은 1~{len(steps)}")
        return 9
    try:
        check_location(ROOT, home)
    except Stop as e:
        say(f"[setup] 멈춤: {e}")
        return 1
    for i, (what, fn) in enumerate(steps, 1):
        if i < a.from_step:
            continue
        say(f"[{i}/{len(steps)}] {what}")
        if a.dry_run:
            continue
        try:
            fn()
        except Stop as e:
            say(f"\n[setup] {i}번째에서 멈춤: {e}\n  이 화면 글을 그대로 Claude Code 에 보여 주세요. 고친 뒤에는 --from {i} 로 이어서.")
            return 1
        except KeyboardInterrupt:
            say(f"\n[setup] {i}번째에서 사람이 멈춤 — 이어서 하려면 --from {i}")
            return 130
    if a.dry_run:
        say("[setup] --dry-run: 위 순서로 합니다(아무것도 안 함)")
    else:
        say("[setup] 모두 통과 — 다음: 안내서 §3.5(claude 시험) → §3.6(잠자기) → §3.7(tools/h1_mac.py check)")
    return 0


# ============================ plists ============================

def claude_dir(claude: str | None) -> str:
    """claude 실행 파일이 든 폴더(launchd PATH 맨 앞). 절대 경로·있는 파일·실행 가능해야 함(검토 7a M-5)."""
    path = claude or shutil.which("claude")
    if not path:
        raise Stop("claude 를 찾지 못했어요 → 터미널에서 `which claude` 로 경로를 보고 --claude /그/경로/claude 로 다시")
    p = Path(path).expanduser()
    if not p.is_absolute() or p.name != "claude" or not p.is_file() or not os.access(p, os.X_OK):
        raise Stop(f"--claude 는 실행할 수 있는 claude 파일의 전체 경로여야 해요(받은 값 {path}). "
                   "`which claude` 가 'aliased to …' 를 내면 그 뒤의 경로를 쓰세요")
    return str(p.parent)


def launch_path(cdir: str) -> str:
    parts = [cdir] + [x for x in BASE_PATH if x != cdir]
    return ":".join(parts)


def run_command(mk: str, root: Path, home: Path, icloud_status: bool) -> str:
    py = q(venv_python(home))
    word = WORDS[mk]
    tee = ""
    if icloud_status:
        dest = q(icloud_dir(home) / f"H1-상태-{mk}.txt")
        tee = f" {py} h1.py status --market {mk} | tee {dest} ;"
    return (f"{py} h1.py run --market {mk}; c=$?;{tee} [ $c -eq 0 ] || osascript -e "
            f"\"display notification \\\"H1 {word} 종료 코드 $c (logs/h1-{mk}.log)\\\" with title \\\"claude-stock\\\"\"; exit $c")


def report_command(home: Path) -> str:
    py = q(venv_python(home))
    return f"m=$(date -v-1m +%Y-%m); for k in us kr; do {py} h1_report.py --market $k --month $m; done"


def make_plist(kind: str, root: Path, home: Path, path_env: str, icloud_status=False) -> dict:
    logs = root / "logs"
    if kind == "report":
        return {
            "Label": LABELS["report"], "WorkingDirectory": str(root),
            "ProgramArguments": ["/bin/sh", "-c", report_command(home)],
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


def _read_plist(p: Path):
    try:
        with open(p, "rb") as f:
            return plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException, ET.ParseError) as e:
        raise Stop(f"{p.name} 을 읽지 못함({type(e).__name__}) — 파일이 깨졌을 수 있어요")


def cmd_plists(a, home: Path) -> int:
    if ROOT.name != H1_DIR_NAME:
        say(f"[plists] 멈춤: 여기({ROOT})는 H1 전용 폴더({H1_DIR_NAME})가 아니에요. 리허설 폴더에서는 plists 를 쓰지 마세요 "
            "— 진짜와 같은 이름의 작업이 생겨 진짜 H1 이 안 돌 수 있어요(안내서 §10)")
        return 1
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
    for p in have:
        try:
            wd = _read_plist(p).get("WorkingDirectory")
        except Stop as e:
            wd = f"(읽지 못함: {e})"
        if wd != str(ROOT):
            say(f"[plists] 주의: 이미 있는 {p.name} 은 다른 폴더({wd})를 가리켜요")
    if have and not a.force:
        say("[plists] 이미 있어 덮지 않았어요: " + ", ".join(p.name for p in have) + " (다시 만들려면 --force)")
        return 1
    for k, p in targets.items():
        d = make_plist(k, ROOT, home, pathenv, a.icloud_status)
        blob = plistlib.dumps(d, fmt=plistlib.FMT_XML, sort_keys=False)
        tmp = p.with_suffix(".plist.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, p)
        say(f"[plists] 만듦: {p}")
    say(f"  PATH = {pathenv}  (claude 폴더 {cdir} 가 맨 앞 — §3.5 에서 시험한 PATH 와 같은지 보세요)")
    say("  다음 명령을 한 줄씩 쳐서 확인하고 켜세요(안내서 §4.2 — start 전에 켜기):")
    say("    plutil -lint " + " ".join(q(p) for p in targets.values()))
    if have:
        say("    (이미 켜 둔 작업은 꺼졌다 켜져야 바뀐 내용이 먹어요)")
        for k in ("kr", "us", "report"):
            say(f"    launchctl unload -w {q(targets[k])}")
    for k in ("kr", "us", "report"):
        say(f"    launchctl load -w {q(targets[k])}")
    say("  그다음 안내서 §4.2 의 osascript·kickstart·tail 줄 → §5(start)")
    return 0


# ============================ check ============================

def latest_weekday(now: datetime) -> date:
    """KS200 이 마지막 봉으로 가질 수 있는 가장 최근 평일(22:30 전이면 그 전 평일). 공휴일은 모름."""
    d = now.date() if now.hour * 60 + now.minute >= 22 * 60 + 30 else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def check_agents(home: Path, root: Path) -> list:
    """launchd 파일 확인(검토 7a M-3): H1 작업 파일은 이 폴더를 가리키는지, 다른 작업이 이 폴더를 가리키지 않는지."""
    d = home / "Library" / "LaunchAgents"
    problems, mine = [], []
    for p in sorted(d.glob("*.plist")) if d.exists() else []:
        if p.name in {f"{v}.plist" for v in LABELS.values()}:
            mine.append(p.name)
            try:
                pl = _read_plist(p)
            except Stop as e:
                problems.append(str(e))
                continue
            args = " ".join(str(x) for x in pl.get("ProgramArguments") or [])
            if pl.get("Label") != p.name[:-len(".plist")]:
                problems.append(f"{p.name}: Label 이 파일 이름과 달라요({pl.get('Label')})")
            if pl.get("WorkingDirectory") != str(root):
                problems.append(f"{p.name}: 다른 폴더({pl.get('WorkingDirectory')})를 가리켜요 → 여기서 plists --force")
            if str(venv_python(home)) not in args:
                problems.append(f"{p.name}: H1 venv 파이썬({venv_python(home)})으로 돌지 않아요")
            path0 = ((pl.get("EnvironmentVariables") or {}).get("PATH") or "").split(":")[0]
            if p.name != f"{LABELS['report']}.plist" and not os.access(os.path.join(path0, "claude"), os.X_OK):
                problems.append(f"{p.name}: PATH 맨 앞({path0})에 claude 가 없어요 → plists --claude … --force")
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if str(root) in txt:
            problems.append(f"{p.name}: H1 폴더를 가리키는 다른 작업이에요(운영 작업이면 안 됨)")
    return problems, mine


def cmd_check(a, home: Path) -> int:
    vpy = venv_python(home)
    problems = []
    say("(자동 실행이 도는 중이면 status 가 잠금을 기다려 몇 분 멈춘 듯 보일 수 있어요)")

    def item(title, fn):
        say(f"- {title}")
        try:
            fn()
        except Stop as e:
            problems.append(f"{title}: {e}")
            say(f"    ✗ {e}")

    def timezone():
        off = datetime.now().astimezone().utcoffset()
        if off != timedelta(hours=9):
            raise Stop(f"맥 시간대가 한국(UTC+9)이 아니에요(지금 {off}) → 안내서 §3.2")
        say("    한국 시간 — 맞음")

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
            try:
                p = subprocess.run([str(vpy), "h1.py", "status", "--market", mk], cwd=str(ROOT),
                                   capture_output=True, text=True)
            except OSError as e:
                raise Stop(f"h1.py status 실행 못 함({type(e).__name__})")
            lines = (p.stdout + p.stderr).strip().splitlines()
            if p.returncode not in (0, 8):
                raise Stop(f"{mk} status 종료 코드 {p.returncode}:\n    " + "\n    ".join(lines[-6:]))
            say("    " + "\n    ".join(lines[:3]))

    def ks200():
        start = (date.today() - timedelta(days=30)).isoformat()
        got = _out([vpy, "-c", "import FinanceDataReader as f; d = f.DataReader('KS200', %r); "
                               "print(d.index[-1].date() if len(d) else '')" % start])
        if not got:
            raise Stop("KS200 시세가 비었어요")
        last, want = date.fromisoformat(got[-10:]), latest_weekday(datetime.now())
        say(f"    KS200 마지막 날짜 {last} (가장 최근 평일 {want})")
        if (want - last).days > KS200_STALE_DAYS:
            raise Stop(f"KS200 이 {last} 에 멈춰 있어요(가장 최근 평일 {want}) → start 하지 말고 물어보기")
        if last != want:
            say("    → 그 사이가 휴장일이면 정상이에요. 아니면 start 전에 물어보기")

    def sp500():
        n = _out([vpy, "-c", "import screener; print(len(screener.universe(40)))"])
        if n != "40":
            raise Stop(f"S&P500 목록에서 {n} 종목(40 이어야 함)")
        say("    40 — 맞음")

    def agents():
        probs, mine = check_agents(home, ROOT)
        if probs:
            raise Stop("\n    ".join(probs))
        say("    H1 작업: " + (", ".join(mine) or "아직 없음(§4 전이면 정상)"))
        return mine

    item("맥 시간대", timezone)
    item(f"태그 {TAG}", tag)
    item("고친 파일 없음", clean)
    item("h1.py status(start 전이면 '장부 없음'이 정상)", status)
    item("KS200 최근 날짜", ks200)
    item("미국 S&P500 목록 받기", sp500)
    item("launchd 파일", agents)
    if problems:
        say(f"\n[check] 확인할 것 {len(problems)}개 — 화면을 Claude Code 에 보여 주세요")
        return 1
    d = home / "Library" / "LaunchAgents"
    have = d.exists() and all((d / f"{v}.plist").exists() for v in LABELS.values())
    say("\n[check] 모두 맞음 — 다음: " + ("안내서 §4.2(켜기 확인) → §5(start)" if have else "안내서 §4.1(tools/h1_mac.py plists)"))
    return 0


# ============================ main ============================

def main(argv=None, home: Path | None = None) -> int:
    ap = argparse.ArgumentParser(prog="h1_mac.py", description="맥 H1 준비 도우미(setup → check → plists)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="venv → 시험 → 지킴이 → 재현 → 지문(안내서 §3.3·§3.4)")
    s.add_argument("--from", dest="from_step", type=int, default=1)
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("check", help="시작 전 확인(안내서 §3.7)")
    p = sub.add_parser("plists", help="launchd 설정 파일 세 개 만들기(안내서 §4.1·§7)")
    p.add_argument("--claude", default=None, help="claude 실행 파일 전체 경로(없으면 which claude)")
    p.add_argument("--icloud-status", action="store_true", help="실행 뒤 status 글을 iCloud Drive 에 남김(안내서 §6)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--out", default=None, help=argparse.SUPPRESS)       # 시험용
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 9
    home = home or Path.home()
    try:
        return {"setup": cmd_setup, "plists": cmd_plists, "check": cmd_check}[a.cmd](a, home)
    except KeyboardInterrupt:
        say("\n[h1_mac] 사람이 멈춤")
        return 130
    except OSError as e:
        say(f"\n[h1_mac] 환경 문제({type(e).__name__}: {e}) — 화면을 Claude Code 에 보여 주세요")
        return 1


if __name__ == "__main__":
    sys.exit(main())
