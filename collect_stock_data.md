# collect_stock_data.py 작업지시서

## 개요

국내 상장 전체 주식(코스피 + 코스닥) 종목의 메타데이터를 수집하여 스타일이 적용된 단일 시트 엑셀 파일(`./output/Stock_YYYYMMDD.xlsx`)로 저장하는 스크립트입니다.

네이버 금융의 시가총액 페이지에서 기본 종목 정보를 수집하고, 추가로 업종 분류(KRX/WICS), 투자 지표(PER/PBR/배당수익률), 컨센서스 정보(투자의견/목표주가), 배당금, 관리종목/투자경고 상태 등을 **다중 소스에서 병렬로** 수집하여 통합합니다.

## 데이터 소스

| 데이터 소스 | URL / API | 수집 내용 |
|---|---|---|
| **네이버 시가총액 페이지** | `https://finance.naver.com/sise/sise_market_sum.naver?sosok={0\|1}&page={n}` | 종목코드, 종목명, 시장, 현재가, 시가총액(억), 외국인비율 |
| **네이버 업종(Upjong) 페이지** | `https://finance.naver.com/sise/sise_group.naver?type=upjong` + 상세 페이지 | KRX 업종 매핑 (종목코드 → 업종명) |
| **네이버 배당 리스트** | `https://finance.naver.com/sise/dividend_list.naver?page={n}` | 종목별 배당금 |
| **네이버 관리/경고 페이지** | `management.naver`, `trading_halt.naver`, `investment_alert.naver` | 관리종목, 거래정지, 투자주의/경고/위험 |
| **KOSPI 200 구성종목** | `https://finance.naver.com/sise/entryJongmok.naver?no=028&page={n}` | KOSPI 200 종목코드 |
| **KOSDAQ 150 구성종목** | WiseFN (`cmp_cd=229200`) | KOSDAQ 150 종목명 (CU_data 변수) |
| **Naver Mobile API** | `https://m.stock.naver.com/api/stock/{code}/integration` | 투자의견, 목표주가, 52주 최고/최저, PER, PBR, 배당수익률 |
| **WiseFN 페이지** | `http://companyinfo.stock.naver.com/v1/company/c1010001.aspx?cmp_cd={code}` | WICS 업종 |

### 크롤링 방식

- **시가총액 페이지**: BeautifulSoup으로 HTML 테이블 파싱 (코스피 30페이지, 코스닥 50페이지)
- **업종 매핑**: 업종 카테고리 목록 → 각 카테고리 상세 페이지에서 종목코드-업종명 매핑 (병렬)
- **배당 리스트**: 페이지네이션 순회하며 종목별 배당금 추출
- **관리/경고**: 5개 URL에서 각각 종목코드 수집
- **개별 종목 상세**: Mobile Integration API + WiseFN 페이지 (병렬, max_workers=20, 429 재시도 3회)

## 수집 항목 (컬럼)

총 **17개 컬럼**으로 구성됩니다:

| # | 컬럼명 | 출처 | 설명 |
|---|---|---|---|
| 1 | 종목코드 | 시가총액 페이지 | 6자리 종목코드 |
| 2 | 종목명 | 시가총액 페이지 | 주식 종목명 |
| 3 | 유형 | 로직 계산 | 코스피200, 코스피, 코스닥150, 코스닥 |
| 4 | KRX업종 | 업종 페이지 | KRX 업종 분류명 |
| 5 | WICS업종 | WiseFN | WICS 산업 분류명 |
| 6 | 현재가 | 시가총액 페이지 | 현재 주가 (정수) |
| 7 | 시가총액(억) | 시가총액 페이지 | 시가총액 (억원 단위 정수) |
| 8 | 외국인비율 | 시가총액 페이지 | 외국인 보유 비율 (소수점) |
| 9 | 투자의견 | Mobile API (`consensusInfo.recommMean`) | 컨센서스 투자의견 (실수) |
| 10 | 목표주가 | Mobile API (`consensusInfo.priceTargetMean`) | 컨센서스 목표주가 (정수) |
| 11 | 52주최고 | Mobile API (`highPriceOf52Weeks`) | 52주 최고가 (정수) |
| 12 | 52주최저 | Mobile API (`lowPriceOf52Weeks`) | 52주 최저가 (정수) |
| 13 | PER | Mobile API (`per`) | 주가수익비율 (실수) |
| 14 | PBR | Mobile API (`pbr`) | 주가순자산비율 (실수) |
| 15 | 배당수익률 | Mobile API (`dividendYieldRatio`) | 배당수익률 (소수점, % → 비율 변환) |
| 16 | 배당금 | 배당 리스트 페이지 | 배당금 (정수) |
| 17 | 관리종목 | 관리/경고 페이지 | 관리종목, 거래정지, 투자주의, 투자경고, 투자위험 (콤마 구분) |

### 유형 분류 로직

- 코스피 시장 + KOSPI 200 구성종목 → `"코스피200"`
- 코스피 시장 + 그 외 → `"코스피"`
- 코스닥 시장 + 종목명이 KOSDAQ 150 목록에 포함 → `"코스닥150"`
- 코스닥 시장 + 그 외 → `"코스닥"`

## 출력 형식

- **파일 형식**: Excel (.xlsx)
- **파일 경로**: `./output/Stock_YYYYMMDD.xlsx`
- **시트명**: `국내주식 종목현황`
- **정렬**: 시가총액 내림차순
- **엑셀 스타일링**:
  - 헤더: Malgun Gothic, 10pt, 볼드, 배경색 `#EDF2F7`, 글자색 `#1E293B`
  - 데이터: Malgun Gothic, 10pt
  - 오토필터: 적용 (`ws.auto_filter.ref = ws.dimensions`)
  - 테두리: 얇은 실선, 색상 `#D3D3D3`
  - 헤더 행 높이 25, 데이터 행 높이 20
  - 열 너비 자동 조정 (한글 가중치 반영, 마진 +3, 최소 12)
- **숫자 포맷**:
  - 현재가, 시가총액, 목표주가, 52주최고/최저, 배당금: `#,##0`
  - 외국인비율, 배당수익률: `0.00%`
  - 투자의견, PER, PBR: `0.00`
  - 종목코드: `@` (텍스트)

## 실행 방법

```bash
python collect_stock_data.py
```

CLI 인자 없이 실행합니다. 별도의 명령줄 옵션은 없습니다.

## CLI 인자

없음. 모든 설정은 스크립트 내부 상수로 고정되어 있습니다.

## 동작 흐름

```
1. 전체 주식 기본 정보 수집 (fetch_all_stocks)
   ├─ 코스피: 시가총액 페이지 1~30 병렬 크롤링 (sosok=0)
   ├─ 코스닥: 시가총액 페이지 1~50 병렬 크롤링 (sosok=1)
   └─ ThreadPoolExecutor, max_workers=15

2. 벌크 데이터셋 수집 (병렬)
   ├─ KOSPI 200 구성종목 코드 (fetch_kospi200_codes, max_workers=5)
   ├─ KOSDAQ 150 구성종목 이름 (fetch_kosdaq150_names, WiseFN CU_data)
   ├─ KRX 업종 매핑 (fetch_krx_sector_map, max_workers=10)
   ├─ 배당 리스트 (fetch_dividend_map, 페이지 순차 순회)
   └─ 관리/경고 상태 (fetch_alert_sets, 5개 URL)

3. 종목별 상세 지표 병렬 수집 (fetch_stock_details_parallel)
   ├─ Mobile API → 투자의견, 목표주가, 52주 가격, PER, PBR, 배당수익률
   ├─ WiseFN → WICS 업종
   ├─ ThreadPoolExecutor, max_workers=20
   └─ 429 응답 시 최대 3회 재시도 (지수 백오프)

4. 데이터 병합 및 후처리
   ├─ 기본 정보 + 상세 지표 merge (종목코드 기준)
   ├─ 유형 분류 (코스피200/코스피/코스닥150/코스닥)
   ├─ KRX 업종, 배당금, 관리종목 상태 매핑
   └─ 17개 컬럼 선택 및 시가총액 내림차순 정렬

5. 엑셀 파일 생성 및 스타일링
   ├─ openpyxl로 셀 스타일 적용 (정렬, 서식, 테두리)
   └─ 열 너비 자동 조정 (한글 가중치 반영)
```

## 의존성

| 패키지 | 용도 |
|---|---|
| `requests` | HTTP 요청 (네이버 금융 페이지, Mobile API, WiseFN) |
| `beautifulsoup4` | HTML 파싱 (시가총액 페이지, 업종, 배당, 관리종목) |
| `pandas` | DataFrame 처리 및 병합 |
| `openpyxl` | 엑셀 파일 생성 및 스타일링 |
| `tqdm` | 진행률 표시 |

## 주의사항

1. **대량 크롤링**: 전체 코스피(30페이지) + 코스닥(50페이지) + 개별 종목 상세를 크롤링하므로 실행에 상당한 시간이 소요됩니다.
2. **429 Rate Limit**: Mobile API의 429 응답에 대해 최대 3회 재시도하며, `2 * (attempt + 1)초` 간격으로 대기합니다. WiseFN도 동일한 재시도 로직을 적용합니다.
3. **글로벌 세션**: `requests.Session()`을 사용하여 커넥션을 재사용합니다.
4. **cp949 인코딩**: 네이버 금융의 구형 페이지(시가총액, 업종, 배당, 관리종목)는 cp949 인코딩을 사용하며, `decode("cp949", errors="ignore")`로 처리합니다.
5. **KOSDAQ 150 매칭**: KOSDAQ 150은 종목코드가 아닌 **종목명** 기준으로 매칭합니다 (WiseFN의 CU_data에서 `STK_NM_KOR` 추출).
6. **출력 경로**: 스크립트 상단의 `OUTPUT_DIR = "./output"` 상수를 통해 관리됩니다.
7. **중복 제거**: 시가총액 페이지 크롤링 결과에서 종목코드 기준 중복을 제거합니다.
8. **출력 디렉터리**: `./output` 디렉터리가 없으면 자동으로 생성합니다.
