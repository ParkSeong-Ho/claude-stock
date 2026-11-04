"""run2 진단: team.py에선 후보 0개라 analyst가 불리지 않았다. NaN 봉 제외 시 나왔을 파이오니어 후보로
analyst.analyze를 직접 1회 호출해 claude -p 실응답/폴백 여부를 확인한다(저장소 코드 무수정)."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import analyst
c = [{"code": "TT", "price": 413.33, "rsi": 31.0, "reason": "많이 빠졌다가(RSI 31) 반등이 시작됐어요"},
     {"code": "BA", "price": 175.4, "rsi": 32.0, "reason": "많이 빠졌다가(RSI 32) 반등이 시작됐어요"}]
t = time.time(); a = analyst.analyze("파이오니어", c); dt = time.time() - t
print(f"analyze 소요 {dt:.1f}s, 결과 = {'None(폴백)' if a is None else json.dumps(a, ensure_ascii=False)}")
print("apply 후:", [(x['code'], x.get('verdict'), x.get('conviction')) for x in analyst.apply(c, a)])
