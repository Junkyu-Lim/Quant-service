# Quant-service

Korean stock market (KOSPI/KOSDAQ) quantitative analysis platform. Collects financial data from KRX and FnGuide, applies multi-strategy screening, and serves results via a Flask web dashboard with AI-powered analysis reports.

KOSPI/KOSDAQ 퀀트 데이터 수집, 스크리닝, 웹 대시보드 자동화 파이프라인.

## 🎯 Features

- **데이터 수집** (`quant_collector_enhanced.py`) — KRX 종목 마스터, 일별 시세, 재무제표(IS/BS/CF), 핵심 지표(FnGuide), 주식수, 주가 히스토리(52주)를 DuckDB에 병렬 수집 (ThreadPoolExecutor, MAX_WORKERS=15)
- **퀀트 스크리닝** (`quant_screener.py` v8) — TTM 재무, CAGR 성장, S-RIM 밸류에이션, Piotroski F-Score, 기술적 지표, 백분위 점수 기반 6가지 전략별 스크리닝:
  - **Quality** (우량주/저평가) — ROE 5%+, PER 1~50, PBR 0.1~10, 매출 연속성장 2년+, F스코어 5+
  - **Momentum** (고성장) — CAGR 15%+, 이익률 개선, 분기 YoY 계절성 통제
  - **GARP** (성장+가치) — Peter Lynch PEG < 1.5, ROE 12%+, 매출 CAGR 10%+
  - **Cashcow** (현금흐름) — Buffett 스타일 ROE 10%+, 영업이익률 10%+, FCF, F스코어 6+
  - **Turnaround** (실적 반등) — 흑자전환 또는 이익률 급개선(+5%p)
  - **Dividend Growth** (배당 성장) — 순이익 연속 성장 2년+, 배당금 연속 증가 1년+, 수익+배당 동반증가
- **웹 대시보드** — Flask 기반, Bootstrap 5.3, 8개 탭 (전체 + 6가지 전략 + Watchlist), 서버사이드 정렬/필터/페이징, 종목 상세 모달, 종목 비교(레이더 차트+재무 추이), 수동 파이프라인 트리거
- **REST API** — JSON 기반 주식 목록, 상세, 비교, 재무 시계열, 시장 요약, 파이프라인 제어/상태, 배치 변동 추적
- **AI 분석 리포트** — Claude API 기반 5대 투자 대가 프레임워크의 정성적 분석 보고서 생성/저장/조회 (선택사항)

## 📋 Project Structure

```
├── run.py                       # CLI 진입점
├── config.py                    # 환경 설정 (DuckDB, 웹, Claude API)
├── pipeline.py                  # 파이프라인 오케스트레이터
├── db.py                        # DuckDB 데이터베이스 헬퍼
│
├── quant_collector_enhanced.py  # 데이터 수집기 (KRX + FnGuide + FinanceDataReader)
├── quant_screener.py            # 스크리닝 엔진 (v8, TTM + CAGR + S-RIM + F-Score + 기술적 지표)
│
├── batch/
│   ├── __init__.py
│   └── scheduler.py             # 배치 스케줄러 유틸리티 (미사용 - 수동 파이프라인 트리거로 변경)
│
├── webapp/
│   ├── app.py                   # Flask REST API + 웹 앱
│   ├── __init__.py
│   ├── templates/
│   │   └── dashboard.html       # 싱글페이지 앱 (SPA)
│   └── static/
│       ├── css/style.css
│       └── js/dashboard.js
│
├── analysis/
│   ├── __init__.py
│   └── claude_analyzer.py       # Claude API 정성적 분석 (5대 투자 대가 프레임워크)
│
├── data/                        # 데이터 저장소 (DuckDB, Excel 출력)
│   ├── quant.duckdb             # DuckDB 데이터베이스
│   └── reports/                 # AI 분석 보고서
│
├── requirements.txt
├── .env.example
└── .python-version
```

## 🚀 Quick Start

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Run Commands

```bash
# 테스트 모드 (3개 종목: 삼성, 카카오, SK하이닉스만 수집)
python run.py pipeline --test

# 전체 파이프라인 (수집 + 스크리닝)
python run.py pipeline

# 수집 건너뛰고 스크리닝만 (기존 DB 데이터 사용)
python run.py pipeline --skip-collect

# 수집만 실행
python run.py collect [--test]

# 스크리닝만 실행 (기존 DB 데이터 필요)
python run.py screen

# 웹 서버 시작 (파이프라인은 UI의 "Run Pipeline" 버튼으로 수동 실행)
python run.py server

# 프로덕션 배포 (gunicorn)
gunicorn -w 4 -b 0.0.0.0:5000 webapp.app:app
```

**대시보드 접속:** http://localhost:5000

## 🏗️ Architecture

### Data Flow

```
KRX/FnGuide/FinanceDataReader sources
        ↓
quant_collector_enhanced.py (ThreadPoolExecutor 병렬 수집, MAX_WORKERS=15)
        ↓
DuckDB (data/quant.duckdb)
        ├── master (종목 정보: 종목코드, 종목명, 시장구분)
        ├── daily (일별 시세: 종가, 시가총액, EPS, BPS, DPS)
        ├── financial_statements (재무제표: IS/BS/CF, 연간+분기)
        ├── indicators (지표: PER, PBR, PSR, PEG, ROE 등)
        ├── shares (주식수: 발행주식수, 자사주, 유통주식수)
        ├── price_history (주가 히스토리: 52주 OHLCV)
        ├── dashboard_result (스크리닝 결과: 6가지 전략별 점수)
        └── analysis_reports (AI 분석 보고서)
        ↓
quant_screener.py (v8 스크리닝 엔진: TTM + CAGR + S-RIM + F-Score + 기술적 지표)
        ↓
Excel 파일 (7개) + dashboard_result 테이블
        ↓
Flask REST API (webapp/app.py)
        ├── 서버사이드 정렬/필터/페이징
        ├── 컬럼 범위 필터 (min_*/max_*)
        ├── 워치리스트 & 종목 비교
        ├── 배치 변동 추적 (편입/제거)
        └── JSON 응답 (numpy 타입 안전 변환)
        ↓
Browser Dashboard (Bootstrap 5.3 SPA, 8개 탭, 종목 비교 모달)
```

### Pipeline Orchestration

- **`pipeline.py`** — 수집 → 스크리닝 → 기술적 지표 계산 → DB 저장 → Excel 출력 (CLI 또는 UI 버튼으로 수동 실행)
- **`run.py`** — CLI 진입점

## 📊 Dividend Growth Strategy

**배당 성장 전략** — 수익과 배당이 동반하여 성장하는 우량 배당주

**조건:**
- 순이익 연속 성장 ≥ 2년
- 배당금(DPS) 연속 증가 ≥ 1년
- DPS CAGR > 0% (배당금 연평균 성장률)
- ROE ≥ 5% (수익성)
- 배당수익률 > 0% (배당 중시 기업)
- 시가총액 ≥ 300억원
- 현재 순이익 > 0 (흑자)
- 수익 + 배당 동반 증가 확인

**점수 계산 (가중치 벡터):**
```
배당성장_점수 = DPS_CAGR×3.0 + 순이익_CAGR×2.5 + 배당_연속증가×2.0
              + 순이익_연속성장×2.0 + ROE×1.5 + 배당수익률×1.5
              + 저부채×1.0 + F스코어×0.5 + 저PER×0.5
```
**점수 정규화:** 모든 지표를 백분위로 변환 후 위의 가중치를 적용하여 종합 점수 산출

**출력:** `quant_dividend_growth.xlsx`

## 📚 Core Modules

### `db.py` — DuckDB Database Helper

DuckDB 데이터베이스 관리. 모든 데이터는 `data/quant.duckdb`에 저장됨.
컬럼형 스토리지로 집계 쿼리 성능이 SQLite 대비 향상됨.

**테이블 (8개):**
- `master` — 종목 정보 (종목코드, 종목명, 시장구분, 종목구분)
- `daily` — 일별 시세 (종가, 시가총액, 상장주식수, EPS, BPS, 주당배당금)
- `financial_statements` — 재무제표 (IS/BS/CF, 연간+분기)
- `indicators` — 핵심 지표 (FnGuide: PER, PBR, ROE 등)
- `shares` — 주식수 (발행주식수, 자사주, 유통주식수)
- `price_history` — 주가 히스토리 (OHLCV, 52주 기술적 지표용)
- `dashboard_result` — 스크리닝 결과 (대시보드 표시)
- `analysis_reports` — AI 분석 보고서 (Claude API 생성)

**주요 함수:**
- `init_db()` — DB 초기화 (테이블 + 인덱스 생성)
- `get_conn()` — DuckDB 연결 컨텍스트 매니저
- `save_df(df, table, collected_date)` — DataFrame을 테이블에 저장
- `load_latest(table)` — 최신 `collected_date` 데이터 로드
- `save_dashboard(df)` — 스크리닝 결과 저장 (이전 결과는 `dashboard_result_prev`로 백업)
- `load_dashboard()` / `load_dashboard_prev()` — 현재/이전 대시보드 데이터 로드
- `save_report()` / `load_report()` / `list_reports()` / `delete_report()` — AI 보고서 CRUD
- `load_stock_financials(code)` — 종목별 연간 재무제표 시계열
- `get_data_status()` — 전체 테이블 상태 조회 (webapp용)
- `table_has_data(table, date)` — 특정 날짜 데이터 존재 여부

**날짜 기반 버전 관리:**
- `collected_date` 컬럼으로 각 스냅샷 추적 (기존 날짜별 CSV 파일명 대체)

### `quant_collector_enhanced.py` — Data Collector

FnGuide, KRX, FinanceDataReader에서 병렬로 재무데이터 수집하여 DuckDB에 저장.

**수집 대상 (6가지):**
- **KRX 마스터**: 전체 상장 종목 정보 (종목코드, 종목명, 시장구분)
- **일별 시세**: 종가, 시가총액, EPS, BPS, DPS
- **FnGuide 재무제표**: 손익계산서(IS), 대차대조표(BS), 현금흐름표(CF) — 연간+분기
- **FnGuide 핵심지표**: PER, PBR, PSR, PEG, ROE, 부채비율, 매출총이익률 등
- **주식수**: 발행주식수, 자사주, 유통주식수
- **주가 히스토리**: FinanceDataReader 기반 52주(260일) OHLCV (기술적 지표 계산용)

**주요 기능:**
- **병렬 처리**: ThreadPoolExecutor (MAX_WORKERS=15) 활용으로 수집 시간 단축
- **HTML 크롤링**: FnGuide 페이지에서 테이블 파싱
- **인코딩 자동 감지**: cp949/euc-kr/utf-8 자동 선택
- **DB 저장**: `db.save_df(df, table, collected_date)` 활용 (날짜 기반 버전 관리)
- **중복 수집 방지**: `table_has_data()` 체크로 동일 날짜 데이터 스킵
- **에러 처리**: 종목별 수집 실패 시에도 계속 진행

### `quant_screener.py` — Screening Engine v8

TTM 재무, CAGR 성장률, S-RIM 밸류에이션, Piotroski F-Score(9항목), 기술적 지표 계산 후 백분위 기반 점수화 (각 전략별 가중치 벡터 적용).

**주요 구성 요소:**
- **TTM (Trailing Twelve Months)** — 최근 12개월 재무 수치 집계
- **CAGR (복리연평균 성장률)** — 매출, 영업이익, 순이익, 영업CF, FCF, DPS 성장률 계산
- **S-RIM (Residual Income Model)** — 기업 내재가치 평가 모델 (Ke=8%)
- **Piotroski F-Score (9항목)** — F1 수익성, F2 영업CF, F3 ROA개선, F4 이익품질, F5 레버리지, F6 유동성, F7 희석없음, F8 매출총이익률, F9 자산회전율
- **기술적 지표** — 52주 최고/최저 대비, MA20/60 이격도, RSI 14일, 거래대금 분석, 변동성(60일 연환산)
- **계절성 통제** — 분기별 YoY(전년동기비) + TTM YoY 지표로 연간 CAGR 보완
- **백분위 점수 (Percentile Scoring)** — 정량화된 지표를 백분위로 변환하여 상대적 순위 지정
- **전략별 가중치 벡터** — 각 전략의 특성에 맞게 지표별 가중치 설정

**6가지 스크리닝 전략:**
- **Quality (우량주/저평가)**: ROE 5%+, PER 1~50, PBR 0.1~10, 매출 연속성장 2년+, 순이익 연속성장 1년+, 시총 500억+, F스코어 5+
- **Momentum (고성장)**: CAGR 15%+, 이익률 개선, ROE 5%+, 시총 500억+, 분기 YoY + RSI + MA + 거래대금 반영
- **GARP (성장+가치)**: Peter Lynch PEG < 1.5, ROE 12%+, 매출 CAGR 10%+, PER 5~30, 시총 500억+
- **Cashcow (현금흐름)**: Buffett 스타일 ROE 10%+, 영업이익률 10%+, 부채비율 100% 미만, 이익품질 양호, F스코어 6+, 시총 500억+
- **Turnaround (실적 반등)**: 흑자전환 또는 이익률 급개선(+5%p), 현재 흑자, 시총 300억+, RSI·52주 최고대비 반영
- **Dividend Growth (배당 성장)**: 순이익 연속 성장 2년+, 배당금 연속 증가 1년+, DPS CAGR > 0, ROE 5%+, 시총 300억+, 수익+배당 동반증가

**출력:**
- 7개 Excel 파일 (`quant_all_stocks.xlsx`, `quant_screened.xlsx`, `quant_momentum.xlsx`, `quant_GARP.xlsx`, `quant_cashcow.xlsx`, `quant_turnaround.xlsx`, `quant_dividend_growth.xlsx`)
- DuckDB `dashboard_result` 테이블 (웹 대시보드용 통합 데이터)

**스크리닝 일관성:**
- 스크리닝 로직이 `quant_screener.py`와 `webapp/app.py`의 `_apply_screen_filter()`에 존재
- 스크리닝 조건 변경 시 **두 곳 모두 업데이트 필요**

### `webapp/app.py` — Flask REST API

DuckDB 기반 REST API + 웹 앱. 메모리 캐싱으로 DB 파일 변경 시 자동 리로드.

**주요 기능:**
- 서버사이드 정렬, 필터링, 페이징
- 컬럼 범위 필터 (`min_PER=10&max_PER=20`)
- 워치리스트 (종목코드 기반 필터링)
- 종목 비교 (최대 8개, 레이더 차트 + 재무 추이)
- 배치 변동 추적 (이전 배치 대비 전략별 종목 편입/제거)
- AI 분석 보고서 생성/조회 (Claude API)
- JSON 응답, numpy 타입 안전 변환

**API 엔드포인트:**

| Method | Path | Description | Parameters |
|---|---|---|---|
| GET | `/` | 대시보드 SPA 페이지 | - |
| GET | `/api/stocks` | 종목 목록 (필터, 정렬, 페이징) | `screen` (all/screened/momentum/garp/cashcow/turnaround/dividend_growth), `market` (KOSPI/KOSDAQ), `q` (검색어), `sort` (컬럼명), `order` (asc/desc), `page` (1~), `size` (기본: 50, 최대: 200), `codes` (워치리스트 종목코드), `min_*`/`max_*` (범위 필터) |
| GET | `/api/stocks/<code>` | 종목 상세정보 | - |
| GET | `/api/stocks/<code>/financials` | 연간 재무제표 시계열 (차트용: 매출/영업이익/순이익) | - |
| GET | `/api/stocks/<code>/report` | AI 분석 보고서 조회 | - |
| POST | `/api/stocks/<code>/report` | AI 분석 보고서 생성 (Claude API) | - |
| GET | `/api/stocks/compare` | 종목 비교 (지표 + 재무 시계열) | `codes` (쉼표 구분, 2~8개) |
| GET | `/api/reports` | 전체 AI 보고서 목록 | - |
| GET | `/api/markets/summary` | 시장별 요약 통계 (KOSPI/KOSDAQ) | - |
| GET | `/api/data/status` | 데이터 상태 (테이블별 건수, DB 파일 크기) | - |
| POST | `/api/batch/trigger` | 파이프라인 수동 실행 | JSON body: `skip_collect`, `test_mode` |
| GET | `/api/batch/status` | 파이프라인 실행 상태 (running, started_at, finished_at, error) | - |
| GET | `/api/batch/changes` | 이전 배치 대비 전략별 종목 변동 (편입/제거) | - |

### `analysis/claude_analyzer.py` — AI Analysis (Optional)

Claude API를 사용해 종목의 정성적 분석 보고서 생성. 5대 투자 대가(Warren Buffett, Aswath Damodaran, Philip Fisher, Pat Dorsey, André Kostolany) 프레임워크 기반.

**주요 기능:**
- 스크리닝 결과 기반 정량 데이터 분석
- 5대 투자 대가 관점의 정성 평가
- 리스크 평가
- 투자 인사이트 생성
- 보고서 DB 저장/조회/삭제

**필요 설정:**
- `ANTHROPIC_API_KEY` 환경변수 설정
- `ANALYSIS_MODEL` (기본: `claude-sonnet-4-5-20250929`)

### `config.py` — Central Configuration

환경변수로 모든 설정 관리.

**데이터:**
- `BASE_DIR` — 프로젝트 루트
- `DATA_DIR` — 데이터 디렉토리 (기본: `data/`)
- `DB_PATH` — DuckDB 경로 (기본: `data/quant.duckdb`)
- `REPORT_DIR` — AI 보고서 저장소 (기본: `data/reports/`)

**웹 서버:**
- `HOST` (기본: `0.0.0.0`)
- `PORT` (기본: `5000`)
- `DEBUG` (기본: `false`)

**Claude API (선택):**
- `ANTHROPIC_API_KEY` — Anthropic API 키 (sk-ant-... 형식)
- `ANALYSIS_MODEL` (기본: `claude-sonnet-4-5-20250929`)

## 📱 Frontend

**`webapp/templates/dashboard.html` + `webapp/static/js/dashboard.js`**

- Bootstrap 5.3 기반 싱글페이지 앱 (SPA)
- 8개 탭 (전체 + 6가지 전략 + Watchlist):
  - **All** — 전체 종목 (종합점수 기준)
  - **Quality** — 우량주/저평가 스크리닝
  - **Momentum** — 고성장 모멘텀
  - **GARP** — 성장+합리적 가격
  - **Cashcow** — 현금흐름 우량
  - **Turnaround** — 실적 반등
  - **Dividend Growth** — 배당 성장
  - **Watchlist** — 사용자 워치리스트
- 시장 요약 카드 (KOSPI/KOSDAQ 종목 수, PER/PBR/ROE 중앙값)
- 정렬 가능한 테이블 (컬럼 클릭)
- 종목 상세 모달 (재무 차트 포함)
- 종목 비교 기능 (레이더 차트 + 카테고리별 지표 + 재무 추이 차트)
- 배치 변동 알림 (전략별 편입/제거 종목 표시)
- 수동 파이프라인 트리거 버튼

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | 웹 서버 바인드 주소 |
| `PORT` | `5000` | 웹 서버 포트 |
| `DEBUG` | `false` | Flask 디버그 모드 |
| `BATCH_HOUR` | `18` | 배치 실행 시간 (KST) |
| `BATCH_MINUTE` | `0` | 배치 실행 분 |
| `ANTHROPIC_API_KEY` | `` | Claude API 키 (AI 분석 보고서용, 선택) |
| `ANALYSIS_MODEL` | `claude-sonnet-4-5-20250929` | Claude 모델 ID |

환경변수 설정 예:
```bash
export DEBUG=true
export ANTHROPIC_API_KEY=sk-ant-...
python run.py server
```

## 🔑 Key Patterns & Important Notes

### DuckDB Storage

- 모든 데이터는 `data/quant.duckdb`에 저장 (컬럼형 스토리지)
- `db.load_latest(table)` — 최신 `collected_date`에 해당하는 데이터 반환
- `db.save_dashboard()` — 스크리닝 결과를 `dashboard_result` 테이블에 저장 (이전 결과는 `dashboard_result_prev`로 자동 백업)
- `db.load_dashboard_prev()` — 이전 배치 결과 로드 (변동 추적용)

### Unit Multiplier Detection

- Samsung (005930)의 매출 기준으로 **단위 배수 자동 감지** (억원, 백만원 등)
- PER, PBR, PEG 등 지표 계산에 필수 (정확도에 영향)

### Stock Codes

- 항상 6자리 0패딩 문자열 (`zfill(6)`)
- 예: `005930` (삼성전자)

### Encoding

- FnGuide HTML 크롤링 시 cp949/euc-kr/utf-8 자동 감지
- 한글 재무데이터 처리에 필수

### Screening Consistency

⚠️ **중요:** 스크리닝 로직이 두 곳에 존재함:
1. `quant_screener.py` — 스크리닝 엔진 (Excel 출력)
2. `webapp/app.py`의 `_apply_screen_filter()` — 웹 API 필터

**스크리닝 조건 변경 시 반드시 두 곳 모두 업데이트할 것!**

### Scoring Weights

- 각 전략마다 다른 가중치 벡터 적용
- `quant_screener.py`에 정의됨
- 백분위 기반 점수 합산

## 📊 Dashboard Columns

대시보드에 표시되는 컬럼 (60+개):

**기본 정보:** 종목코드, 종목명, 시장구분, 종가, 시가총액

**밸류에이션:** PER, PBR, PSR, PEG, 적정주가(S-RIM), 괴리율

**수익성:** ROE(%), EPS, BPS, 영업이익률(%), 이익수익률(%), FCF수익률(%)

**안정성:** 부채비율(%), 부채상환능력, 이익품질, 현금전환율, CAPEX비율, F스코어 (9항목 상세)

**기술:** 52주 최고/최저 대비(%), MA20/60 이격도(%), RSI_14, 거래대금(20일평균/증감%), 변동성(60일)

**성장률 (연간):** 매출/영업이익/순이익/영업CF/FCF CAGR, DPS CAGR

**성장률 (분기 YoY):** Q_매출/영업이익/순이익 YoY(%), 연속YoY성장, TTM YoY(%)

**연속성:** 매출/영업이익/순이익/영업CF 연속성장, 배당 연속증가, 배당 수익동반증가

**턴어라운드:** 흑자전환, 이익률 개선/급개선, 이익률 변동폭, 영업이익률(최근/전년)

**배당:** DPS 최근, DPS CAGR, 배당 연속증가, 배당수익률(%)

**TTM 원본:** TTM 매출/영업이익/순이익/영업CF/CAPEX/FCF, 자본, 부채, 자산총계

**종합 점수:** 종합점수 (백분위 기반 가중 합산)

## 🛠️ Development

### Running Tests

```bash
# 테스트 모드 (3개 종목만 수집)
python run.py pipeline --test
```

### Debugging

```bash
# 디버그 모드로 웹 서버 실행
export DEBUG=true
python run.py server
```

### Database Inspection

```bash
# DuckDB CLI로 데이터베이스 확인
duckdb data/quant.duckdb

# 테이블 목록
SHOW TABLES;

# 특정 테이블 조회
SELECT * FROM dashboard_result LIMIT 10;

# 테이블별 건수 확인
SELECT 'master' as tbl, COUNT(*) FROM master
UNION ALL SELECT 'daily', COUNT(*) FROM daily
UNION ALL SELECT 'dashboard_result', COUNT(*) FROM dashboard_result;
```

## 📝 Log & Output

**로그:**
- 콘솔 출력: `[YYYY-MM-DD HH:MM:SS] [LEVEL] module - message`

**출력 파일:**
- Excel: `data/` 디렉토리
- 분석 보고서: `data/reports/` 디렉토리

## 🔗 API Examples

### Get Stock List (Quality 전략, KOSPI, 페이지 1)

```bash
curl "http://localhost:5000/api/stocks?screen=screened&market=KOSPI&page=1&size=20"
```

### Get Stock List (Dividend Growth 전략)

```bash
curl "http://localhost:5000/api/stocks?screen=dividend_growth&market=KOSPI&page=1&size=20"
```

### Get Stock List with Range Filter

```bash
curl "http://localhost:5000/api/stocks?screen=all&min_PER=5&max_PER=15&min_ROE(%)=10"
```

### Get Stock Details

```bash
curl "http://localhost:5000/api/stocks/005930"
```

### Get Stock Financials (Chart Data)

```bash
curl "http://localhost:5000/api/stocks/005930/financials"
```

### Compare Stocks

```bash
curl "http://localhost:5000/api/stocks/compare?codes=005930,000660,035720"
```

### Get Market Summary

```bash
curl "http://localhost:5000/api/markets/summary"
```

### Trigger Pipeline Manually

```bash
curl -X POST http://localhost:5000/api/batch/trigger
```

### Check Pipeline Status

```bash
curl "http://localhost:5000/api/batch/status"
```

### Get Batch Changes (Strategy-level Diffs)

```bash
curl "http://localhost:5000/api/batch/changes"
```

### Get AI Analysis Report

```bash
curl "http://localhost:5000/api/stocks/005930/report"
```

### Generate AI Analysis Report

```bash
curl -X POST "http://localhost:5000/api/stocks/005930/report"
```

### List All Reports

```bash
curl "http://localhost:5000/api/reports"
```

### Check Data Status

```bash
curl "http://localhost:5000/api/data/status"
```

## 🤝 Contributing

코드 변경 시:
1. `git checkout -b feature/your-feature`
2. 필요시 `db.py`, `quant_screener.py`, `webapp/app.py` 일관성 확인
3. 테스트: `python run.py pipeline --test`
4. 커밋 및 PR

## 📄 License

(프로젝트 라이선스 추가 예정)

## 📧 Support

버그 신고 및 제안: GitHub Issues

---

**마지막 업데이트:** 2026-02-18
