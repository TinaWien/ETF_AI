# collect_etf_history.py 작업지시서

## 개요

국내 상장 ETF의 과거 시세(OHLC) 데이터를 수집하여 **6개의 CSV 파일**(실제가격/수정가격 × 일봉/주봉/월봉)로 저장하는 스크립트입니다.

3단계 폴백(Naver Mobile → KRX(pykrx) → Yahoo Finance)을 통해 데이터 수집 신뢰성을 확보하며, 수집된 가격 데이터는 정제(sanitize) 처리 후 날짜·종목코드 기준 오름차순 정렬하여 저장합니다.

## 데이터 소스

3단계 폴백(fallback) 방식으로 데이터를 수집합니다. 1번 소스 실패 시 2번, 2번 실패 시 3번 순서로 시도합니다.

| 우선순위 | 데이터 소스 | URL / 방식 | 비고 |
|---|---|---|---|
| 1 | **Naver Mobile API** | `https://m.stock.naver.com/front-api/external/chart/domestic/info?symbol={code}&requestType=1&startTime={start}&endTime={end}&timeframe={tf}` | `ast.literal_eval`로 응답 파싱, timeframe 파라미터로 일/주/월 직접 지정 |
| 2 | **KRX (pykrx)** | `stock.get_market_ohlcv_by_date()` | 5년 단위 청크 분할 조회, 주/월봉은 pandas `resample` 사용 |
| 3 | **Yahoo Finance** | `yfinance.Ticker("{code}.KS").history()` | `auto_adjust=False`, 수정가 시 `Adj Close` 비율 적용 |

### ETF 목록 조회

`--code` 미지정 시, 네이버 금융 API(`https://finance.naver.com/api/sise/etfItemList.nhn`)에서 전체 ETF 목록을 가져옵니다.

## 수집 항목 (컬럼)

각 CSV 파일은 **7개 컬럼**으로 구성됩니다:

| # | 컬럼명 | 설명 |
|---|---|---|
| 1 | 날짜 | 거래일 (YYYY-MM-DD 형식) |
| 2 | 종목코드 | 6자리 ETF 종목코드 |
| 3 | 시가 | 시가 (정수) |
| 4 | 고가 | 고가 (정수) |
| 5 | 저가 | 저가 (정수) |
| 6 | 종가 | 종가 (정수) |
| 7 | 출처 | 데이터 소스 (Naver / KRX / Yahoo) |

## 출력 형식

총 **6개의 CSV 파일**이 `./output/` 디렉터리에 생성됩니다:

| 파일명 패턴 | 가격 유형 | 주기 |
|---|---|---|
| `ETF_actual_daily_YYYYMMDD.csv` | 실제가격 | 일봉 |
| `ETF_adjusted_daily_YYYYMMDD.csv` | 수정가격 | 일봉 |
| `ETF_actual_weekly_YYYYMMDD.csv` | 실제가격 | 주봉 |
| `ETF_adjusted_weekly_YYYYMMDD.csv` | 수정가격 | 주봉 |
| `ETF_actual_monthly_YYYYMMDD.csv` | 실제가격 | 월봉 |
| `ETF_adjusted_monthly_YYYYMMDD.csv` | 수정가격 | 월봉 |

- **인코딩**: `utf-8-sig` (BOM 포함 UTF-8, 한글 호환)
- **정렬**: `날짜`, `종목코드` 기준 오름차순
- **날짜 형식**: `YYYY-MM-DD`
- **파일명의 YYYYMMDD**: 스크립트 실행일 기준

## 실행 방법

```bash
# 전체 ETF, 최근 1년간 시세 수집 (기본값)
python collect_etf_history.py

# 특정 종목만 수집
python collect_etf_history.py --code 069500,360750

# 기간 지정
python collect_etf_history.py --start 20230101 --end 20231231

# 특정 종목 + 기간 지정
python collect_etf_history.py --code 069500 --start 20200101 --end 20241231
```

## CLI 인자

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `--code` | str | None (전체 ETF) | 특정 ETF 종목코드 (쉼표 구분 가능, 예: `069500,360750`) |
| `--start` | str | 1년 전 (`YYYYMMDD`) | 시작 날짜 (YYYYMMDD 형식) |
| `--end` | str | 오늘 (`YYYYMMDD`) | 종료 날짜 (YYYYMMDD 형식) |

### 날짜 입력 파싱

- 숫자가 아닌 문자는 모두 제거하여 8자리 숫자만 추출합니다.
- 8자리가 아닌 경우 기본값을 사용합니다.

## 동작 흐름

```
1. CLI 인자 파싱 및 날짜 설정
   ├─ --start / --end 파싱 (기본값: 1년 전 ~ 오늘)
   └─ --code 지정 시 해당 종목만, 미지정 시 네이버 API에서 전체 ETF 목록 조회

2. 시세 데이터 수집 (3개 주기 × 2개 가격유형 = 6회 반복)
   ├─ 주기: day → week → month
   └─ 각 주기마다 actual(실제가격)과 adjusted(수정가격) 2회 수집

3. 개별 종목 시세 수집 (3단계 폴백)
   ├─ 1차: Naver Mobile API 시도
   ├─ 2차: 실패 시 KRX(pykrx) 시도
   │   ├─ 5년 단위 청크 분할 조회
   │   └─ 주/월봉은 resample('W' / 'M')로 집계
   └─ 3차: 실패 시 Yahoo Finance 시도
       └─ 수정가격 시 Adj Close / Close 비율을 OHLC에 적용

4. 데이터 정제 (sanitize_and_fix_prices)
   ├─ 종가 0 또는 NaN인 행 제거
   ├─ 시가/고가/저가가 0이면 종가로 대체
   ├─ 고가 < 저가인 행 보정 (4개 가격의 max/min 재계산)
   └─ 모든 가격 정수 변환

5. 병합 및 저장
   ├─ 병렬 수집 (ThreadPoolExecutor, max_workers=20)
   ├─ 날짜·종목코드 기준 오름차순 정렬
   └─ CSV 저장 (utf-8-sig 인코딩)
```

## 의존성

| 패키지 | 용도 |
|---|---|
| `requests` | HTTP 요청 (Naver Mobile API, ETF 목록 API) |
| `pandas` | DataFrame 처리, resample, CSV 저장 |
| `tqdm` | 진행률 표시 |
| `yfinance` | Yahoo Finance 시세 조회 |
| `pykrx` | KRX 시세 조회 |

## 주의사항

1. **Naver Mobile API 파싱**: 응답이 JSON이 아닌 Python 리터럴 형식이므로 `ast.literal_eval`로 파싱합니다. 응답이 빈 배열(`[[]]`)이거나 "날짜" 컬럼이 없으면 실패로 처리합니다.
2. **KRX 5년 제한**: pykrx는 한 번에 5년 이상의 데이터를 조회하면 오류가 발생할 수 있으므로, 5년(`5 * 365일`) 단위로 청크 분할하여 조회합니다.
3. **KRX resample 주의**: 월봉 리샘플링 시 `'M'` (deprecated) 대신 `'ME'`를 사용합니다.
4. **수정가격 처리**: Yahoo Finance에서만 `Adj Close`를 활용하여 수정가격을 계산합니다. KRX는 `adjusted=True` 플래그로 수정주가를 직접 조회합니다. Naver Mobile API는 actual/adjusted 구분이 없으며 기본 시세를 반환합니다.
5. **HTTP 세션 관리**: `requests.Session()`에 커넥션 풀 30개를 설정하여 대량 병렬 요청 성능을 최적화합니다.
6. **데이터 정제**: `sanitize_and_fix_prices` 함수에서 0원 가격, NaN, 고가 < 저가 등의 비정상 데이터를 자동 보정합니다.
7. **날짜 범위 필터**: 폴백으로 받은 데이터 중 지정된 start~end 범위를 벗어나는 행은 제거합니다.
