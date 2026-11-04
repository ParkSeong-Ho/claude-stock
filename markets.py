"""
markets.py - 시장(미국/국내)별 설정을 한 곳에 모은 파일 (docs/kr-broker-design.md §3, K-D7~K-D11)
------------------------------------------------------------------
초보자용 설명:
- 미국(us)과 국내(kr)는 통화·수수료·세금·장 마감 시각·벤치마크가 다르다.
  이 값들을 코드 여기저기에 흩어 두면 원화와 달러가 섞이기 쉬우니, 시장 하나 = Market 하나로 묶는다.
- 지갑은 시장별로 따로 쓴다(미국 = 달러 지갑, 국내 = 원화 지갑). 환전은 하지 않는다.
- round_to_tick: 주문 가격을 '호가단위'(가격이 움직일 수 있는 최소 칸)에 맞춘다.
- money: 금액을 시장 통화로 표기한다. 미국 "$1,234.56", 국내 "1,234,567원".
- KR_UNIVERSE: 국내 스크리너가 훑는 고정 종목 목록(KOSPI 시가총액 상위 약 30개).
  KRX 전체 목록 조회는 자주 멈춰서 쓰지 않는다(K-D7). 목록은 사람이 가끔 손으로 고친다.

이 파일은 표준 라이브러리만 쓴다(인터넷·pandas 없음) → 어디서든 가볍게 import 가능.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    key: str            # "us" | "kr"
    currency: str       # "USD" | "KRW"
    fee_rate: float     # 매매 수수료율 (살 때·팔 때 각각)
    sell_tax_rate: float  # 매도 거래세 (팔 때만)
    slippage: float     # 체결 미끄러짐 가정
    benchmark: str      # "SPY" | "KS200"  (국내는 2026-11-04 에 "069500" → "KS200", 아래 설명)
    tz: str             # "America/New_York" | "Asia/Seoul"
    close_cutoff: str   # "16:15" | "16:00"  (현지시간, 이 전이면 오늘 봉 버림)
    total_cash: float   # 10_000 | 10_000_000
    # 벤치마크 시세만 따로 쓰는 확정 시각(현지시간). None 이면 close_cutoff 와 같다(미국 SPY = 예전 그대로).
    # 국내 "22:30": KS200 은 장중에 '미완성 오늘 봉'이 올라오므로 밤에야 오늘 봉을 인정한다 (아래 설명, 2026-11-04).
    bench_cutoff: str | None = None


MARKETS = {
    # 미국: v1 그대로 (D8). 수수료 0.1%, 매도세 0, 슬리피지 0.05%, $10,000.
    "us": Market(key="us", currency="USD", fee_rate=0.001, sell_tax_rate=0.0, slippage=0.0005,
                 benchmark="SPY", tz="America/New_York", close_cutoff="16:15", total_cash=10_000),
    # 국내 (K-D8·K-D9·K-D10):
    #   수수료 0.015% = KIS 0.0140527% + 유관기관 0.0036396% 를 반올림
    #   매도세 0.20% (증권거래세+농특세, 2026 기준), 슬리피지 0.05%
    #   장 마감 15:30 + 시간외·데이터 반영 여유 → 16:00 KST 이전의 '오늘 봉'은 버린다
    #   가상자금 ₩10,000,000 (100만원이면 대형주 1주도 못 사는 종목이 많아 전략이 왜곡됨)
    #   벤치마크 = KOSPI 200 '가격지수'(FinanceDataReader 기호 "KS200") — 2026-11-04 변경 (S0-1).
    #     예전 값은 KODEX 200("069500")이었다. 그런데 FinanceDataReader(네이버)가 주는 069500 시세는
    #     '분배금(배당)을 다시 넣은' 값이고, 우리 국내 주식 시세는 배당이 빠진 '가격만'이다.
    #     → 벤치마크만 배당을 받는 셈이라 비교 줄이 벤치마크 쪽으로 연 약 2%p 기울었다.
    #       (2015-01-02 네이버 069500 19,639원 vs 실제 종가 24,725원 /
    #        2015~2026 수익률 네이버 069500 +354.8% vs KS200 +261.8%)
    #     둘 다 '가격만'으로 맞추려고 가격지수 KS200 을 쓴다. 지수라 6자리 종목코드가 아니므로
    #     main.load_benchmark 만 이 기호를 받을 수 있다(main.load_prices 의 allow_index).
    #   KS200 시세의 출처 (2026-11-04 확인): 네이버가 아니다. FinanceDataReader 0.9.110 이상은
    #     GitHub 저장소 FinanceData/fdr_krx_data_cache 의 data/index/year_ks200/<연도>.csv 를 읽는다
    #     (0.9.90~0.9.102 는 data.krx.co.kr 을 직접 부르는데, 지금은 로그인 없이는 거절됨 → requirements.txt 하한 0.9.110).
    #     이 캐시는 거래일 12:00~14:20 KST 쯤 '미완성 오늘 봉'(종가가 장중 값, 거래량 절반쯤)을 올리고,
    #     16:50~21:53 KST 사이에 종가를 고친다(2026-09-10 ~ 11-04 커밋 61개 관찰, 그 뒤 커밋은 거래량만 바뀜).
    #     그래서 벤치마크만 bench_cutoff="22:30" — 한국 시간 22:30 전에는 KS200 의 '오늘 봉'을 버린다.
    #     → team 의 기준 날짜도 22:30 전에는 하루 전 봉. 국내 실행 권장: 22:30 KST 이후 또는 다음날 아침 09:00 전.
    "kr": Market(key="kr", currency="KRW", fee_rate=0.00015, sell_tax_rate=0.0020, slippage=0.0005,
                 benchmark="KS200", tz="Asia/Seoul", close_cutoff="16:00", total_cash=10_000_000,
                 bench_cutoff="22:30"),
}

# 벤치마크를 사람이 읽는 이름 (비교 줄에 찍힘). 국내는 2026-11-04 까지 "KODEX 200" 이었다(위 설명).
BENCH_NAMES = {"us": "SPY", "kr": "KOSPI 200(가격지수)"}


def get_market(key: str) -> Market:
    """'us' / 'kr' → Market. 모르는 값이면 바로 알려 준다(조용히 미국으로 가지 않음)."""
    k = (key or "").strip().lower()
    if k not in MARKETS:
        raise ValueError(f"모르는 시장 '{key}' — 'us' 또는 'kr' 만 됩니다.")
    return MARKETS[k]


# 국내 호가단위표 (2023-01-25 개편, 코스피·코스닥 공통): (이 가격 '미만'이면, 이 단위)
KR_TICKS = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (math.inf, 1_000),
)


def kr_tick(price: float) -> int:
    """국내 주식 가격 price 의 호가단위(원)."""
    for limit, tick in KR_TICKS:
        if price < limit:
            return tick
    return 1_000


def round_to_tick(market_key: str, price: float, side: str) -> float:
    """가격을 호가단위에 맞춘다. side="buy" 는 올림(사려면 조금 더 줘야), "sell" 은 내림.

    us: 0.01달러 단위.  kr: 위 호가단위표.
    예) round_to_tick("kr", 51_234, "buy") → 51_300 / "sell" → 51_200
    국내에서 올림하다가 구간 경계를 넘으면(예: 199,950 → 200,000) 그 값도 새 구간의 칸 위라 그대로 맞다.
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side 는 'buy' 또는 'sell' (받은 값: {side!r})")
    price = float(price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"가격이 이상해요: {price}")
    mk = get_market(market_key)
    if mk.key == "us":
        cents = price * 100
        # 부동소수점 오차(예: 1.1*100=110.00000000000001)로 한 칸 더 올리지 않게 살짝 반올림 후 처리
        cents = round(cents, 6)
        n = math.ceil(cents) if side == "buy" else math.floor(cents)
        return round(n / 100, 2)
    tick = kr_tick(price)
    q = round(price / tick, 9)
    n = math.ceil(q) if side == "buy" else math.floor(q)
    # 구간 경계값(2,000·5,000·20,000 …)은 위·아래 두 단위의 배수라, 경계를 넘나들어도 항상 칸 위다.
    return float(n * tick)


def money(market_key: str, v: float, sign=True) -> str:
    """금액을 시장 통화로 표기. 숫자가 아니면 '계산 불가'.
    us: "+$1,234.56" / "$1,234.56"(sign=False).  kr: "+1,234,567원" / "1,234,567원"(sign=False)."""
    mk = get_market(market_key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "계산 불가"
    if not math.isfinite(f):
        return "계산 불가"
    if mk.key == "us":
        body = f"${abs(f):,.2f}"
    else:
        body = f"{abs(round(f)):,.0f}원"     # 원은 소수점 없이
    if sign:
        return ("+" if f >= 0 else "-") + body
    return ("-" if f < 0 else "") + body


def price_text(market_key: str, px: float) -> str:
    """주가 한 개 표기(부호 없음). us "$123.45", kr "71,300원"."""
    return money(market_key, px, sign=False)


def code_ok(market_key: str, code: str) -> bool:
    """이 종목코드가 이 시장 것인지(통화 섞임 방지). 국내 = 숫자 6자리. 미국 = 그 외 전부."""
    is_kr = isinstance(code, str) and len(code) == 6 and code.isdigit()
    return is_kr if get_market(market_key).key == "kr" else not is_kr


# 국내 스크리너 종목군: KOSPI 시가총액 상위 약 30개 (2026년 하반기 기준, 우선주 제외).
# 순위는 수시로 바뀌니 '대략 상위권 대형주' 목록으로 본다. 바꾸려면 여기만 고치면 된다.
KR_UNIVERSE = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "기아": "000270",
    "셀트리온": "068270",
    "KB금융": "105560",
    "한화에어로스페이스": "012450",
    "HD현대중공업": "329180",
    "NAVER": "035420",
    "신한지주": "055550",
    "삼성물산": "028260",
    "현대모비스": "012330",
    "두산에너빌리티": "034020",
    "POSCO홀딩스": "005490",
    "삼성생명": "032830",
    "하나금융지주": "086790",
    "카카오": "035720",
    "메리츠금융지주": "138040",
    "삼성화재": "000810",
    "HD한국조선해양": "009540",
    "고려아연": "010130",
    "LG화학": "051910",
    "삼성SDI": "006400",
    "SK스퀘어": "402340",
    "삼성중공업": "010140",
    "KT&G": "033780",
    "한국전력": "015760",
    "SK텔레콤": "017670",
    "LG전자": "066570",
    "우리금융지주": "316140",
}


def kr_name(code: str) -> str | None:
    """6자리 코드 → 종목 이름 (목록에 없으면 None)."""
    for name, c in KR_UNIVERSE.items():
        if c == code:
            return name
    return None
