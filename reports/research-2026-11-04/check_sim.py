"""
sim.py 점검 (인터넷 없이 data/ 만 사용)
1) 속도용 처리(지표 한 번 계산 + 최근 80봉만 넘기기 + 보유 없을 때 판단 캐시)가
   '매 봉마다 그날까지의 데이터로 add_indicators 를 새로 계산해 decide 에 전부 넘기는' 원래 방식과
   같은 판단을 내는지 3개 종목 × 3트레이너, 400봉 구간에서 비교한다.
2) 체결이 다음 날 시가인지, 상한 안 0주면 보류인지 확인한다.
실행: ~/.venv-cs/bin/python reports/research-2026-11-04/check_sim.py
"""
import sim


def slow_actions(df, brain_cls, i0, i1, positions):
    brain = brain_cls()
    out = []
    for i in range(i0, i1 + 1):
        window = brain.add_indicators(df.iloc[: i + 1])
        out.append(brain.decide(window, positions.get(i))[0])
    return out


def main():
    bad = 0
    for code in ["AAPL", "TSLA", "XOM"]:
        df = sim.load(code)
        for name, cls in sim.BRAINS.items():
            prep = sim.Prepared(df, cls)
            i0, i1 = sim.idx_range(prep.dates, "2018-01-01", "2019-08-01")
            r = sim.simulate(prep, cls(), i0, i1, 10_000, params_key="default", keep_log=True)
            # 실제 시뮬레이션에서 각 봉의 보유 상태를 재구성해서 느린 방식과 판단 비교
            positions = {}
            for e, x in r["trades"]:
                end = x if x is not None else i1 + 1
                for i in range(e, end):
                    positions[i] = {"buy_price": float(prep.open[e]), "days_held": i - e, "shares": 1}
            fast = []
            for i in range(i0, i1 + 1):
                w = prep.ind.iloc[max(0, i - sim.WINDOW + 1): i + 1]
                fast.append(cls().decide(w, positions.get(i))[0])
            slow = slow_actions(df, cls, i0, i1, positions)
            diff = sum(a != b for a, b in zip(fast, slow))
            bad += diff
            # 체결일 = 신호 다음 날 시가
            for e, x in r["trades"]:
                assert fast[e - 1 - i0] == "매수", (code, name, "매수 신호 다음날 체결 아님")
                if x is not None:
                    assert fast[x - 1 - i0] == "매도", (code, name, "매도 신호 다음날 체결 아님")
            print(f"{code:5s} {name}: 거래 {len(r['trades'])}회, 판단 불일치 {diff}/{len(fast)}")
    # 상한 안 0주 → 보류
    df = sim.load("COST")
    prep = sim.Prepared(df, sim.PioneerBrain)
    i0, i1 = sim.idx_range(prep.dates, "2023-01-01", "2026-12-31")
    r = sim.simulate(prep, sim.PioneerBrain(), i0, i1, 150, cap=1.0, code="COST", keep_log=True)
    holds = [e for e in r["log"] if e["종류"] == "보류"]
    assert r["buys"] == 0 and r["skips"] > 0 and holds and "1주도 못 삼" in holds[0]["사유"]
    print(f"COST $150 파이오니어: 매수 0, 보류 {r['skips']}회 — 예: {holds[0]['사유']}")
    assert bad == 0, f"판단 불일치 {bad}건"
    print("[PASS] 빠른 방식 = 원래 방식, 다음날 시가 체결, 0주 보류 확인")


if __name__ == "__main__":
    main()
