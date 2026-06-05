# collect_etf_data.py 작업지시서

## 개요

국내 상장된 전체 ETF 종목의 메타데이터를 수집하여 디자인 스타일이 적용된 단일 시트 엑셀 파일(`./output/ETF_YYYYMMDD.xlsx`)로 저장하는 스크립트입니다.

네이버 금융 API로 전체 ETF 목록을 가져온 후, 개별 종목의 상세 정보를 **WiseFN(companyinfo.stock.naver.com)** 페이지에서 자바스크립트 JSON 변수를 파싱하여 수집합니다. 배당금 정보는 **Yahoo Finance(yfinance)**를 통해 보완합니다.

## 데이터 소스

| 데이터 소스 | URL / API | 수집 내용 |
|---|---|---|
| **네이버 금융 ETF 목록 API** | `https://finance.naver.com/api/sise/etfItemList.nhn` | 전체 ETF 목록 (종목코드, 종목명, 시가총액, 거래량, etfTabCode) |
| **WiseFN 상세 페이지** | `http://companyinfo.stock.naver.com/v1/company/c1010001.aspx?cmp_cd={code}` | 기초지수명, ETF 유형, 상장일, 총보수, 자산운용사, 52주 최고/최저, 수익률(3/6/12개월), 지급기준일 |
| **Yahoo Finance (yfinance)** | `yfinance.Ticker("{code}.KS").dividends` | 최근 분배금 |

### WiseFN 페이지 파싱 방식

HTML 본문에 선언된 자바스크립트 JSON 객체 변수를 정규식으로 추출합니다:

- `var status_data = {...};` → 52주 최고/최저(`YR_HIGH`, `YR_LOW`), 수익률(`ERN3`, `ERN6`, `ERN12`)
- `var product_summary_data = {...};` → 기초지수명(`BASE_IDX_NM_KOR`), 상장일(`LIST_DT`), 총보수(`TOT_PAY`), 자산운용사(`ISSUE_NM_KOR`), 지급기준일(`DIV_BASE_DT`)
- `var summary_data = {...};` → ETF 유형명(`ETF_TYP_SVC_NM`)

## 수집 항목 (컬럼)

총 **18개 컬럼**으로 구성됩니다:

| # | 컬럼명 | 출처 | 설명 |
|---|---|---|---|
| 1 | 종목코드 | 네이버 API | 6자리 종목코드 |
| 2 | 종목명 | 네이버 API | ETF 종목명 |
| 3 | 자산운용사 | WiseFN (`ISSUE_NM_KOR`) | 자산운용사명 |
| 4 | 대분류유형 | 로직 계산 | 국내 / 해외 / 기타 (etfTabCode 기반) |
| 5 | 중분류유형 | 로직 계산 | 시장지수 / 업종/테마 / 파생 / 원자재 / 채권 / 기타 |
| 6 | 소분류유형 | 로직 계산 | 종목명 키워드 매칭 (TR, 액티브, 합성, (H), 인버스, 레버리지) |
| 7 | 기초지수명 | WiseFN (`BASE_IDX_NM_KOR`) | 추적 기초지수 이름 |
| 8 | 상장일 | WiseFN (`LIST_DT`) | ETF 상장일 |
| 9 | 시가총액(억원) | 네이버 API (`marketSum`) | 시가총액 (억원 단위) |
| 10 | 거래량 | 네이버 API (`quant`) | 거래량 |
| 11 | 수수료 | WiseFN (`TOT_PAY`) | 총 보수율 (소수점, 예: 0.00150) |
| 12 | 지급기준일 | WiseFN (`DIV_BASE_DT`) | 분배금 지급 기준일 (없으면 "없음") |
| 13 | 최근분배금(원) | Yahoo Finance | 최근 분배금 (원 단위 정수) |
| 14 | 수익률(3개월) | WiseFN (`ERN3`) | 3개월 수익률 (소수점) |
| 15 | 수익률(6개월) | WiseFN (`ERN6`) | 6개월 수익률 (소수점) |
| 16 | 수익률(12개월) | WiseFN (`ERN12`) | 12개월 수익률 (소수점) |
| 17 | 52주최고 | WiseFN (`YR_HIGH`) | 52주 최고가 (정수) |
| 18 | 52주최저 | WiseFN (`YR_LOW`) | 52주 최저가 (정수) |

### 유형 분류 로직 (`parse_categories`)

- **대분류**: `etfTabCode` 1~3 → 국내, 4 → 해외, 그 외 → ETF 유형 텍스트에서 "국내"/"해외" 키워드 판별
- **중분류**: `etfTabCode` 1 → 시장지수, 2 → 업종/테마, 3 → 파생, 4 → 해외(시장대표/업종), 5 → 원자재, 6 → 채권, 7 → 기타
- **소분류**: 종목명에서 `TR`, `액티브`, `합성`, `(H)`, `인버스`, `레버리지` 키워드 매칭 후 콤마 구분 결합

## 출력 형식

- **파일 형식**: Excel (.xlsx)
- **파일 경로**: `./output/ETF_YYYYMMDD.xlsx`
- **시트 구성**: 단일 시트 (`Sheet1`)
- **엑셀 스타일링**:
  - 헤더: Malgun Gothic, 10pt, 볼드, 배경색 `#EDF2F7`, 텍스트 `#1E293B`
  - 데이터: Malgun Gothic, 10pt, 검정색
  - 테두리: 얇은 실선, 색상 `#CBD5E1`
  - 헤더 행 높이 25, 데이터 기본 행 높이 20
  - 오토필터 적용
  - 열 너비 자동 조정 (한글 가중치 2, 영문 가중치 1, 마진 +4, 최소 12)
- **숫자 포맷**:
  - 시가총액, 거래량, 최근분배금, 52주최고/최저: `#,##0` (천 단위 콤마 정수)
  - 수수료: `0.000%` (소수점 3자리 백분율)
  - 수익률(3/6/12개월): `0.00%` (소수점 2자리 백분율)
  - 종목코드: `@` (텍스트)

## 실행 방법

```bash
python collect_etf_data.py
```

CLI 인자 없이 실행합니다. 별도의 명령줄 옵션은 없습니다.

## CLI 인자

없음. 모든 설정은 스크립트 내부 상수로 고정되어 있습니다.

## 동작 흐름

```
1. 네이버 금융 ETF 목록 API 호출
   └─ 전체 ETF 종목 리스트 수신 (종목코드, 종목명, 시가총액, 거래량, etfTabCode)

2. 개별 ETF 상세 정보 병렬 수집 (ThreadPoolExecutor, max_workers=15)
   ├─ WiseFN 페이지에서 JavaScript JSON 변수 3개 파싱
   │   ├─ status_data → 52주 최고/최저, 수익률(3/6/12개월)
   │   ├─ product_summary_data → 기초지수, 상장일, 총보수, 운용사, 지급기준일
   │   └─ summary_data → ETF 유형명
   └─ yfinance로 최근 분배금 조회 (지급기준일이 유효한 종목만)

3. 데이터 병합 및 분류 매핑
   ├─ parse_categories()로 대/중/소 분류 결정
   └─ 18개 컬럼의 딕셔너리 리스트 생성 → DataFrame 변환

4. 엑셀 파일 생성 및 스타일링
   ├─ openpyxl로 헤더/데이터 셀 스타일 적용
   ├─ 열별 정렬 방식 지정 (좌/중앙/우)
   ├─ 숫자 포맷 지정 (#,##0, 0.000%, 0.00%)
   └─ 열 너비 자동 조정 (한글 가중치 반영)
```

## 의존성

| 패키지 | 용도 |
|---|---|
| `requests` | HTTP 요청 (네이버 API, WiseFN 페이지) |
| `pandas` | DataFrame 생성 및 데이터 처리 |
| `openpyxl` | 엑셀 파일 생성 및 스타일링 |
| `tqdm` | 진행률 표시 |
| `yfinance` | Yahoo Finance 배당금 데이터 조회 |

## 주의사항

1. **WiseFN 페이지 의존**: 상세 정보는 WiseFN(companyinfo.stock.naver.com)에서 자바스크립트 변수를 파싱하여 추출하므로, 해당 페이지 구조가 변경되면 파싱이 실패할 수 있습니다.
2. **yfinance 호출 제한**: Yahoo Finance의 과도한 차단을 방지하기 위해 `max_workers`를 15로 제한합니다. 지급기준일이 "지급하지", "없음", "미지급"을 포함하는 종목은 yfinance 호출을 스킵합니다.
3. **수수료 파싱**: WiseFN의 `TOT_PAY` 값은 퍼센트 단위(예: "0.150")로 제공되며, 100으로 나누어 소수점 비율로 변환합니다.
4. **수익률 파싱**: `ERN3`, `ERN6`, `ERN12` 값도 퍼센트 단위이며, 천 단위 쉼표가 포함될 수 있어 제거 후 100으로 나눕니다.
5. **네트워크 오류 처리**: 개별 종목의 상세 정보 수집 실패 시 해당 종목은 기본값(빈 문자열, None, 0)으로 채워집니다.
6. **출력 디렉터리**: `./output` 디렉터리가 없으면 자동으로 생성합니다.
