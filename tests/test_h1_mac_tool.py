"""tools/h1_mac.py (맥 준비 도우미) 시험 — 인터넷·진짜 claude·launchctl 를 쓰지 않는다. plist 는 가짜 집 폴더에 쓴다.
검토 7a(docs/h1-review-7a.md) M-2·M-3·M-4·M-5·M-9·M-10·M-12·M-13 을 지킨다."""

import json
import os
import plistlib
import re
import subprocess
import sys
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import h1_mac as M  # noqa: E402


@pytest.fixture(autouse=True)
def h1root(tmp_path, monkeypatch):
    """도우미가 쓰는 H1 폴더(logs/ 를 만듦)를 임시 폴더로 — 저장소를 건드리지 않게."""
    r = tmp_path / "claude-stock-h1"
    r.mkdir()
    monkeypatch.setattr(M, "ROOT", r)
    return r


def _fake_claude(tmp_path):
    d = tmp_path / "bin with space"
    d.mkdir(parents=True, exist_ok=True)
    c = d / "claude"
    c.write_text("#!/bin/sh\nexit 97\n")
    c.chmod(0o755)
    return c


def _doc_plists():
    """운영 안내서의 손으로 쓴 plist 상자(xml) 세 개 → {Label: dict}."""
    text = (ROOT / "docs" / "h1-forward-run.md").read_text(encoding="utf-8")
    out = {}
    for block in re.findall(r"```xml\n(.*?)```", text, flags=re.S):
        d = plistlib.loads(textwrap.dedent(block).encode("utf-8"))
        out[d["Label"]] = d
    return out


def test_도우미_plist_세_개는_안내서의_손_plist_와_칸까지_같다():
    """검토 7a M-9(5): 문서와 코드가 따로 놀지 않게, 안내서 상자를 읽어 통째로 비교."""
    doc = _doc_plists()
    home, root = Path("/Users/나"), Path("/Users/나/claude-stock-h1")
    pathenv = "/Users/나/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
    assert M.launch_path("/Users/나/.local/bin") == pathenv
    for kind, label in M.LABELS.items():
        assert M.make_plist(kind, root, home, pathenv) == doc[label], kind


def test_plists_세_개를_만들고_다시_읽으면_시각과_명령이_맞다(tmp_path, h1root, capsys):
    home = tmp_path / "home"
    out = tmp_path / "agents"
    c = _fake_claude(tmp_path)
    assert M.main(["plists", "--claude", str(c), "--out", str(out)], home=home) == 0
    pl = {k: plistlib.loads((out / f"{v}.plist").read_bytes()) for k, v in M.LABELS.items()}
    for k in ("kr", "us"):
        assert pl[k]["Label"] == M.LABELS[k] and pl[k]["WorkingDirectory"] == str(h1root)
        assert pl[k]["EnvironmentVariables"]["PATH"] == f"{c.parent}:/opt/homebrew/bin:/usr/bin:/bin"
        assert pl[k]["ProgramArguments"][:4] == ["/usr/bin/caffeinate", "-i", "/bin/sh", "-c"]
        assert pl[k]["StandardOutPath"] == pl[k]["StandardErrorPath"] == str(h1root / "logs" / f"h1-{k}.log")
        assert "&" not in pl[k]["ProgramArguments"][4]
    when = {(d["Weekday"], d["Hour"], d["Minute"]) for d in pl["kr"]["StartCalendarInterval"]}
    assert when == {(d, 23, 5) for d in range(1, 6)} | {(d, 7, 40) for d in range(1, 7)}
    when = {(d["Weekday"], d["Hour"], d["Minute"]) for d in pl["us"]["StartCalendarInterval"]}
    assert when == {(d, 7, 10) for d in range(2, 7)} | {(d, 8, 40) for d in range(1, 7)}
    assert pl["report"]["Label"] == M.LABELS["report"] and pl["report"]["StartCalendarInterval"] == {"Day": 2, "Hour": 9, "Minute": 30}
    assert pl["report"]["StandardOutPath"] == str(h1root / "logs" / "h1-report.log")
    assert (h1root / "logs").is_dir()
    text = capsys.readouterr().out
    assert text.count("launchctl load -w") == 3 and "unload" not in text
    # 이미 있으면 덮지 않음(종료 1), --force 면 덮고 unload 를 먼저 보여 줌(검토 7a M-8)
    assert M.main(["plists", "--claude", str(c), "--out", str(out)], home=home) == 1
    assert M.main(["plists", "--claude", str(c), "--out", str(out), "--force"], home=home) == 0
    text = capsys.readouterr().out
    assert text.count("launchctl unload -w") == 3 and text.index("launchctl unload -w") < text.index("launchctl load -w")


@pytest.mark.parametrize("code", [0, 4])
def test_빈칸_한글_집에서도_sh_글이_돌고_종료_코드와_알림이_맞다(tmp_path, h1root, code):
    """검토 7a M-2: '/Users/김 철수' 같은 집이면 따옴표 없는 경로가 127 로 매번 실패했다."""
    home = tmp_path / "김 철수"
    py = M.venv_python(home)
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\necho \"$@\" >> '{tmp_path}/py.log'\nexit {code}\n")
    py.chmod(0o755)
    fakebin = tmp_path / "fb"
    fakebin.mkdir()
    (fakebin / "osascript").write_text(f"#!/bin/sh\necho \"$@\" >> '{tmp_path}/osa.log'\n")
    (fakebin / "osascript").chmod(0o755)
    (fakebin / "tee").write_text("#!/bin/sh\ncat > /dev/null\n")       # iCloud 폴더가 없어도 됨
    (fakebin / "tee").chmod(0o755)
    for ic in (False, True):
        cmd = M.run_command("kr", h1root, home, ic)
        p = subprocess.run(["/bin/sh", "-c", cmd], cwd=str(h1root), env={"PATH": f"{fakebin}:/usr/bin:/bin"})
        assert p.returncode == code
    runs = (tmp_path / "py.log").read_text().splitlines()
    assert runs[0] == "h1.py run --market kr" and "h1.py status --market kr" in runs
    osa = (tmp_path / "osa.log").read_text() if (tmp_path / "osa.log").exists() else ""
    assert ("H1 국내 종료 코드 4 (logs/h1-kr.log)" in osa) == (code == 4)
    rc = subprocess.run(["/bin/sh", "-n", "-c", M.report_command(home)])
    assert rc.returncode == 0 and M.q(py) in M.report_command(home)


def test_plists_는_H1_폴더에서만_claude_경로를_엄격히_본다(tmp_path, monkeypatch):
    home = tmp_path / "home"
    c = _fake_claude(tmp_path)
    out = tmp_path / "a"
    other = tmp_path / "h1-rehearsal"
    other.mkdir()
    monkeypatch.setattr(M, "ROOT", other)                           # 검토 7a M-3: 리허설 폴더에서는 거절
    assert M.main(["plists", "--claude", str(c), "--out", str(out)], home=home) == 1 and not out.exists()
    monkeypatch.setattr(M, "ROOT", tmp_path / "claude-stock-h1")
    monkeypatch.setattr(M.shutil, "which", lambda name: None)
    assert M.main(["plists", "--out", str(out)], home=home) == 1     # claude 없음
    notexec = tmp_path / "x" / "claude"
    notexec.parent.mkdir()
    notexec.write_text("")
    for bad in ("claude", "./claude", str(tmp_path / "nope" / "claude"), str(notexec), str(c.parent)):
        assert M.main(["plists", "--claude", bad, "--out", str(out)], home=home) == 1, bad   # 검토 7a M-5
    assert not (out / "com.claude-stock.h1-kr.plist").exists()
    assert M.main(["plists", "--claude", str(c), "--out", str(out), "--icloud-status"], home=home) == 0
    cmd = plistlib.loads((out / "com.claude-stock.h1-kr.plist").read_bytes())["ProgramArguments"][4]
    assert "h1.py status --market kr | tee" in cmd and "H1-상태-kr.txt" in cmd and cmd.index("| tee") < cmd.index("exit $c")


def test_setup_명령_순서_R2_받기가_pytest_앞(tmp_path, monkeypatch):
    """검토 7a M-9(2)·M-10: 실제 단계 목록의 명령과 순서."""
    ran = []
    monkeypatch.setattr(M, "_run", lambda cmd, **k: ran.append([str(c) for c in cmd]))
    monkeypatch.setattr(M, "_out", lambda cmd, **k: "3.13.18")
    monkeypatch.setattr(M, "_pytest", lambda vpy: ran.append(["pytest"]))
    monkeypatch.setattr(M, "_compare_hash", lambda vpy: ran.append(["hash"]))
    monkeypatch.setattr(M, "_check_python", lambda *a, **k: ran.append(["python"]))
    monkeypatch.setattr(M, "check_location", lambda root, home: None)
    home = tmp_path / "home"
    M.venv_python(home).parent.mkdir(parents=True)
    M.venv_python(home).write_text("")
    assert M.main(["setup"], home=home) == 0
    vpy = str(M.venv_python(home))
    assert ran == [["python"], [vpy, "-m", "pip", "install", "-r", "requirements-h1.txt"],
                   ["git", "fetch", "origin", "research-r2-2026-11-04"], ["pytest"],
                   [vpy, "tools/h1_test_guard.py", "--quick"], [vpy, "h1_replay.py"], ["hash"]]
    assert (M.ROOT / "logs").is_dir()                                # 검토 7a M-11


def test_setup_은_실패한_단계에서_멈추고_다음_단계를_안_한다(tmp_path, capsys, monkeypatch):
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd)
        raise M.Stop("일부러(종료 코드 1)")
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""))
    monkeypatch.setattr(M, "_check_python", lambda *a, **k: None)
    monkeypatch.setattr(M, "_make_venv", lambda home: None)
    monkeypatch.setattr(M, "check_location", lambda root, home: None)
    assert M.main(["setup"], home=tmp_path) == 1
    out = capsys.readouterr().out
    assert "3번째에서 멈춤: 라이브러리 설치 실패(종료 코드 1)" in out and "--from 3" in out and "[4/8]" not in out
    assert M.main(["setup", "--dry-run", "--from", "9"], home=tmp_path) == 9
    assert M.main(["setup", "--from", "x"], home=tmp_path) == 9
    monkeypatch.setattr(M, "_run", lambda cmd, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert M.main(["setup", "--from", "3"], home=tmp_path) == 130      # 검토 7a M-12


def test_run_의_작업_폴더는_부르는_순간의_ROOT(tmp_path, monkeypatch, h1root):
    seen = {}
    monkeypatch.setattr(M.subprocess, "run", lambda cmd, cwd=None, **k: seen.setdefault("cwd", cwd) and SimpleNamespace(returncode=0))
    M._run(["true"], what="x")
    assert seen["cwd"] == str(h1root)                                # 검토 7a M-9(8)
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("없음")))
    with pytest.raises(M.Stop, match="실행 못 함"):
        M._out(["없는명령"])


def test_파이썬_버전_python_org_인증서를_본다(tmp_path):
    with pytest.raises(M.Stop, match="3.13.18 이어야"):
        M._check_python((3, 13, 19), "/usr/local/bin/python3", platform="linux")
    M._check_python((3, 13, 18), "/x", platform="linux")
    with pytest.raises(M.Stop, match="python.org 설치본이 아니"):           # 검토 7a M-13
        M._check_python((3, 13, 18), "/x", platform="darwin", base_prefix="/opt/homebrew/Cellar/python@3.13/3.13.18",
                        cafile=__file__)
    with pytest.raises(M.Stop, match="Install Certificates"):
        M._check_python((3, 13, 18), "/x", platform="darwin", base_prefix=M.FRAMEWORK, cafile=str(tmp_path / "없음.pem"))
    M._check_python((3, 13, 18), "/x", platform="darwin", base_prefix=M.FRAMEWORK, cafile=__file__)
    home = tmp_path / "home"
    (home / "Documents" / "h1").mkdir(parents=True)
    with pytest.raises(M.Stop, match="iCloud"):
        M.check_location(home / "Documents" / "h1", home)
    (home / "claude-stock-h1").mkdir()
    M.check_location(home / "claude-stock-h1", home)


def test_pytest_건너뜀이_있으면_멈춤(tmp_path, monkeypatch):
    def fake_run(cmd, **k):
        xml = [c for c in cmd if str(c).startswith("--junitxml=")][0].split("=", 1)[1]
        Path(xml).write_text(f'<testsuites><testsuite tests="949" failures="0" errors="0" skipped="{fake_run.skip}"/></testsuites>')
    monkeypatch.setattr(M, "_run", fake_run)
    fake_run.skip = 20
    with pytest.raises(M.Stop, match="건너뜀 20"):
        M._pytest(Path("/x/python"))
    fake_run.skip = 0
    M._pytest(Path("/x/python"))


def test_지문_비교(tmp_path, h1root, monkeypatch):
    monkeypatch.setattr(M, "_out", lambda cmd, **k: "abc")
    with pytest.raises(M.Stop, match="읽지 못함"):
        M._compare_hash(Path("/x"))
    p = h1root / "state" / "h1" / "replay_pass.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps([{"code_hash": "old"}, {"code_hash": "def"}]))
    with pytest.raises(M.Stop, match="지문이 달라요"):
        M._compare_hash(Path("/x"))
    p.write_text(json.dumps([{"code_hash": "abc"}]))
    M._compare_hash(Path("/x"))


# ---------------------------- check ----------------------------

@pytest.fixture(autouse=True)
def _restore_tz():
    yield
    import time
    time.tzset()                                     # monkeypatch 가 TZ 를 되돌린 뒤 다시 읽기


def _check_env(tmp_path, monkeypatch, h1root, *, tag="h1-forward-v1", dirty="", ks="", n="40", status_rc=8, agents=None,
               tz="Asia/Seoul"):
    home = tmp_path / "home"
    ks = ks or M.latest_weekday(datetime.now()).isoformat()
    import time
    monkeypatch.setenv("TZ", tz)
    time.tzset()

    def out(cmd, **k):
        s = " ".join(str(c) for c in cmd)
        if "describe" in s:
            return tag
        if "status --short" in s:
            return dirty
        if "KS200" in s:
            return ks
        if "screener" in s:
            return n
        raise AssertionError(s)
    monkeypatch.setattr(M, "_out", out)
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=status_rc, stdout="[H1 kr 상태] 장부 없음\n", stderr=""))
    monkeypatch.setattr(M, "datetime", type("D", (datetime,), {"now": classmethod(lambda cls, tz=None: datetime(2026, 11, 10, 20, 0).astimezone(
        __import__("zoneinfo").ZoneInfo("Asia/Seoul")))}))
    for name, wd in (agents or {}).items():
        d = home / "Library" / "LaunchAgents"
        d.mkdir(parents=True, exist_ok=True)
        c = _fake_claude(tmp_path)
        pl = M.make_plist(name, Path(wd), home, M.launch_path(str(c.parent))) if name in M.LABELS else \
            {"Label": name, "WorkingDirectory": str(wd), "ProgramArguments": ["/bin/sh", "-c", f"cd {wd} && order_runner"]}
        fname = M.LABELS.get(name, name)
        (d / f"{fname}.plist").write_bytes(plistlib.dumps(pl))
    return home


def test_check_모두_맞음(tmp_path, monkeypatch, h1root, capsys):
    home = _check_env(tmp_path, monkeypatch, h1root, ks="2026-11-10")
    assert M.main(["check"], home=home) == 0
    assert "§4.1" in capsys.readouterr().out                         # plist 가 아직 없으면 다음은 plists(검토 7a M-7)
    home = _check_env(tmp_path, monkeypatch, h1root, ks="2026-11-10", agents={k: h1root for k in M.LABELS})
    assert M.main(["check"], home=home) == 0
    assert "§4.2" in capsys.readouterr().out


@pytest.mark.parametrize("kw, word", [
    ({"tag": "h1-forward-v0"}, "태그"), ({"dirty": " M h1.py"}, "고친 파일"), ({"n": "39"}, "39"),
    ({"status_rc": 2}, "종료 코드 2"), ({"ks": "2026-10-30"}, "멈춰 있어요"), ({"tz": "UTC"}, "시간대"),
])
def test_check_확인할_것(tmp_path, monkeypatch, h1root, capsys, kw, word):
    """검토 7a M-4·M-9(7): 하나라도 이상하면 종료 1."""
    kw.setdefault("ks", "2026-11-10")
    home = _check_env(tmp_path, monkeypatch, h1root, **kw)
    assert M.main(["check"], home=home) == 1
    assert word in capsys.readouterr().out


def test_check_는_다른_폴더를_가리키는_H1_작업과_H1_폴더를_가리키는_다른_작업을_잡는다(tmp_path, monkeypatch, h1root, capsys):
    """검토 7a M-3: 리허설 폴더에서 만든 같은 이름의 작업을 진짜 폴더의 check 가 알아봐야 한다."""
    home = _check_env(tmp_path, monkeypatch, h1root, ks="2026-11-10", agents={"kr": tmp_path / "h1-rehearsal"})
    assert M.main(["check"], home=home) == 1
    assert "다른 폴더" in capsys.readouterr().out
    home = _check_env(tmp_path / "b", monkeypatch, h1root, ks="2026-11-10", agents={"com.claude-stock.kr-place": h1root})
    assert M.main(["check"], home=home) == 1
    assert "다른 작업" in capsys.readouterr().out


def test_가장_최근_평일():
    assert M.latest_weekday(datetime(2026, 11, 10, 23, 0)) == date(2026, 11, 10)     # 화 22:30 뒤
    assert M.latest_weekday(datetime(2026, 11, 10, 20, 0)) == date(2026, 11, 9)      # 화 22:30 전 → 월
    assert M.latest_weekday(datetime(2026, 11, 9, 8, 0)) == date(2026, 11, 6)        # 월 아침 → 금
    assert M.latest_weekday(datetime(2026, 11, 8, 23, 0)) == date(2026, 11, 6)       # 일 → 금
