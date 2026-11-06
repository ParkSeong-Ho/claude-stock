"""tools/h1_mac.py (맥 준비 도우미) 시험 — 인터넷·진짜 claude·launchctl 를 쓰지 않는다. plist 는 가짜 집 폴더에 쓴다."""

import plistlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import h1_mac as M  # noqa: E402


@pytest.fixture(autouse=True)
def _h1_root(tmp_path, monkeypatch):
    """도우미가 쓰는 H1 폴더(logs/ 를 만듦)를 임시 폴더로 — 저장소를 건드리지 않게."""
    r = tmp_path / "claude-stock-h1"
    r.mkdir()
    monkeypatch.setattr(M, "ROOT", r)
    return r


def _fake_claude(tmp_path):
    d = tmp_path / "bin with space"
    d.mkdir()
    c = d / "claude"
    c.write_text("#!/bin/sh\nexit 97\n")
    c.chmod(0o755)
    return c


def test_plists_세_개를_만들고_다시_읽으면_안내서_시각과_같다(tmp_path, capsys):
    home = tmp_path / "home"
    out = tmp_path / "agents"
    c = _fake_claude(tmp_path)
    assert M.main(["plists", "--claude", str(c), "--out", str(out)], home=home) == 0
    kr = plistlib.loads((out / "com.claude-stock.h1-kr.plist").read_bytes())
    us = plistlib.loads((out / "com.claude-stock.h1-us.plist").read_bytes())
    rp = plistlib.loads((out / "com.claude-stock.h1-report.plist").read_bytes())
    assert kr["Label"] == "com.claude-stock.h1-kr" and kr["WorkingDirectory"] == str(M.ROOT)
    assert kr["EnvironmentVariables"]["PATH"].split(":")[0] == str(c.parent)
    assert kr["ProgramArguments"][:4] == ["/usr/bin/caffeinate", "-i", "/bin/sh", "-c"]
    cmd = kr["ProgramArguments"][4]
    assert f"{home}/.venv-h1/bin/python h1.py run --market kr; c=$?;" in cmd and cmd.endswith("exit $c")
    assert "H1 국내 종료 코드 $c" in cmd and "&" not in cmd
    when = {(d["Weekday"], d["Hour"], d["Minute"]) for d in kr["StartCalendarInterval"]}
    assert when == {(d, 23, 5) for d in range(1, 6)} | {(d, 7, 40) for d in range(1, 7)}
    when = {(d["Weekday"], d["Hour"], d["Minute"]) for d in us["StartCalendarInterval"]}
    assert when == {(d, 7, 10) for d in range(2, 7)} | {(d, 8, 40) for d in range(1, 7)}
    assert "--market us" in us["ProgramArguments"][4] and "H1 미국" in us["ProgramArguments"][4]
    assert rp["StartCalendarInterval"] == {"Day": 2, "Hour": 9, "Minute": 30}
    assert "date -v-1m +%Y-%m" in rp["ProgramArguments"][2] and "h1_report.py --market $k --month $m" in rp["ProgramArguments"][2]
    assert kr["StandardOutPath"] == str(M.ROOT / "logs" / "h1-kr.log")
    # 이미 있으면 덮지 않음(종료 1), --force 면 덮음
    assert M.main(["plists", "--claude", str(c), "--out", str(out)], home=home) == 1
    assert M.main(["plists", "--claude", str(c), "--out", str(out), "--force"], home=home) == 0
    assert "launchctl load -w" in capsys.readouterr().out


def test_plists_icloud_상태_줄과_claude_없으면_멈춤(tmp_path, monkeypatch):
    home = tmp_path / "home"
    c = _fake_claude(tmp_path)
    assert M.main(["plists", "--claude", str(c), "--out", str(tmp_path / "a"), "--icloud-status"], home=home) == 0
    cmd = plistlib.loads((tmp_path / "a" / "com.claude-stock.h1-kr.plist").read_bytes())["ProgramArguments"][4]
    assert "h1.py status --market kr | tee" in cmd and "com~apple~CloudDocs/H1-상태-kr.txt" in cmd
    assert cmd.index("| tee") < cmd.index("exit $c")
    monkeypatch.setattr(M.shutil, "which", lambda name: None)
    assert M.main(["plists", "--out", str(tmp_path / "b")], home=home) == 1
    assert M.main(["plists", "--claude", str(tmp_path), "--out", str(tmp_path / "b")], home=home) == 1
    assert not (tmp_path / "b" / "com.claude-stock.h1-kr.plist").exists()


def test_setup_dry_run_은_8단계를_보여만_주고_from_범위를_본다(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: pytest.fail("dry-run 이 명령을 실행함"))
    assert M.main(["setup", "--dry-run"], home=tmp_path) == 0
    out = capsys.readouterr().out
    assert "[1/8]" in out and "[8/8]" in out and "재현" in out
    assert M.main(["setup", "--dry-run", "--from", "9"], home=tmp_path) == 9
    assert M.main(["setup", "--from", "x"], home=tmp_path) == 9


def test_setup_파이썬_버전과_iCloud_위치를_막는다(tmp_path):
    with pytest.raises(M.Stop, match="3.13.18 이어야"):
        M._check_python((3, 13, 19), "/usr/local/bin/python3")
    M._check_python((3, 13, 18), "/x")
    home = tmp_path / "home"
    (home / "Documents" / "h1").mkdir(parents=True)
    with pytest.raises(M.Stop, match="iCloud"):
        M.check_location(home / "Documents" / "h1", home)
    (home / "claude-stock-h1").mkdir()
    M.check_location(home / "claude-stock-h1", home)


def test_setup_은_실패한_단계에서_멈추고_이어갈_번호를_알려_준다(tmp_path, capsys, monkeypatch):
    calls = []

    def steps(home):
        return [("하나", lambda: calls.append(1)), ("둘", lambda: (_ for _ in ()).throw(M.Stop("일부러"))),
                ("셋", lambda: calls.append(3))]
    monkeypatch.setattr(M, "setup_steps", steps)
    monkeypatch.setattr(M, "check_location", lambda root, home: None)
    assert M.main(["setup"], home=tmp_path) == 1
    out = capsys.readouterr().out
    assert calls == [1] and "2번째에서 멈춤: 일부러" in out and "--from 2" in out
    assert M.main(["setup", "--from", "3"], home=tmp_path) == 0 and calls == [1, 3]
