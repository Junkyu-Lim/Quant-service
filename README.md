# Quant-service

Korean stock market (KOSPI/KOSDAQ) quantitative analysis platform. Collects financial data from KRX and FnGuide, applies multi-strategy screening, and serves results via a Flask web dashboard with AI-powered analysis reports.

KOSPI/KOSDAQ 퀀트 데이터 수집, 스크리닝, 웹 대시보드 자동화 파이프라인.

## 🎯 Features

- **데이터 수집** (`quant_collector_enhanced.py`) — KRX 종목 마스터, 일별 시세, 재무제표(IS/BS/CF), 핵심 지표(FnGuide), 주식수를 SQLite DB에 병렬 수집 (ThreadPoolExecutor, MAX_WORKERS=15)
- **퀀트 스크리닝** (`quant_screener.py` v6) — TTM 재무, CAGR 성장, S-RIM 밸류에이션, 백분위 점수 기반 5가지 전략별 스크리닝:
  - **Quality** (우량주/저평가) — ROE 12%+, PER 낮음, PBR 낮음, 연속 성장
  - **Momentum** (고성장) — CAGR 15%+, 이익률 개선
  - **GARP** (성장+가치) — Peter Lynch PEG < 1.5, ROE 12%+
  - **Cashcow** (현금흐름) — Buffett 스타일 FCF, 수익률 5%+, 이익 품질
  - **Turnaround** (실적 반등) — 흑자전환, 이익률 급개선
- **배치 자동화** — APScheduler로 매일 장 마감 후 자동 실행 (18:00 KST 기본)
- **웹 대시보드** — Flask 기반, Bootstrap 5.3, 6개 스크리닝 탭, 서버사이드 정렬/필터/페이징, 종목 상세 모달
- **REST API** — JSON 기반 주식 목록, 상세, 시장 요약, 파이프라인 제어
- **AI 분석 리포트** — Claude API 기반 정성적 분석 보고서 생성 (선택사항)

## 📋 Project Structure

```
├── run.py                       # CLI 진입점
├── config.py                    # 환경 설정 (SQLite, 배치, 웹, Claude API)
├── pipeline.py                  # 파이프라인 오케스트레이터
├── db.py                        # SQLite 데이터베이스 헬퍼
│
├── quant_collector_enhanced.py  # 데이터 수집기 (KRX + FnGuide)
├── quant_screener.py            # 스크리닝 엔진 (v6, TTM + CAGR + S-RIM)
│
├── batch/
│   ├── __init__.py
│   └── scheduler.py             # APScheduler 배치 스케줄러 (매일 18:00 KST)
│
├── webapp/
│   ├── app.py                   # Flask REST API + 웹 앱
│   ├── __init__.py
│   ├── templates/
│   │   └── dashboard.html       # 싱글페이지 앱 (SPA)
│   └── static/
│       ├── css/
│       └── js/
│
├── analysis/
│   ├── __init__.py
│   └── claude_analyzer.py       # Claude API 정성적 분석 (선택)
│
├── data/                        # 데이터 저장소 (SQLite DB, Excel 출력)
│   ├── quant.db                 # SQLite 데이터베이스
│   └── reports/                 # AI 분석 보고서
│
└── requirements.txt
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

# 스크리닝만 실행 (기존 CSV/DB 데이터 필요)
python run.py screen

# 웹 서버 + 배치 스케줄러 시작 (18:00 KST 자동 실행)
python run.py server

# 프로덕션 배포 (gunicorn)
gunicorn -w 4 -b 0.0.0.0:5000 webapp.app:app
```

**대시보드 접속:** http://localhost:5000

## 🏗️ Architecture

### Data Flow

```
KRX/FnGuide sources
        ↓
quant_collector_enhanced.py (병렬 수집)
        ↓
SQLite DB (data/quant.db)
        ├── master (종목 정보)
        ├── daily (일별 시세)
        ├── financial_statements (재무제표)
        ├── indicators (지표)
        ├── shares (주식수)
        └── dashboard_result (스크리닝 결과)
        ↓
quant_screener.py (v6 스크리닝 엔진)
        ↓
Excel + dashboard_result 테이블
        ↓
Flask API (webapp/app.py)
        ↓
Browser Dashboard (Bootstrap 5.3 SPA)
```

### Pipeline Orchestration

- **`pipeline.py`** — 수집 → 스크리닝 오케스트레이션
- **`run.py`** — CLI 진입점
- **`batch/scheduler.py`** — APScheduler 매일 자동 실행 (기본 18:00 KST)

## 📚 Core Modules

### `db.py` — SQLite Database Helper

SQLite 데이터베이스 관리. 모든 데이터는 `data/quant.db`에 저장됨.

**테이블:**
- `master` — 종목 정보 (종목코드, 종목명, 시장구분)
- `daily` — 일별 시세
- `financial_statements` — 재무제표 (IS/BS/CF)
- `indicators` — 핵심 지표 (FnGuide)
- `shares` — 주식수
- `dashboard_result` — 스크리닝 결과 (대시보드 표시)

**주요 함수:**
- `init_db()` — DB 초기화
- `save_df(table, df, collected_date)` — 데이터 저장
- `load_latest(table)` — 최신 `collected_date` 데이터 로드
- `save_dashboard(df)` — 스크리닝 결과 저장
- `load_dashboard()` — 대시보드 데이터 로드

**날짜 기반 버전 관리:**
- `collected_date` 컬럼으로 각 스냅샷 추적 (기존 날짜별 CSV 파일명 대체)

### `quant_collector_enhanced.py` — Data Collector

FnGuide, KRX에서 병렬로 재무데이터 수집.

**주요 기능:**
- ThreadPoolExecutor 병렬 처리 (MAX_WORKERS=15)
- FnGuide 크롤링: 재무제표, 지표, 주식수
- SQLite DB via `db.save_df()` 저장
- 한글 인코딩 자동 감지 (cp949/euc-kr/utf-8)

### `quant_screener.py` — Screening Engine v6

TTM 재무, CAGR 성장률, S-RIM 밸류에이션 계산 후 백분위 기반 점수화.

**주요 기능:**
- **TTM (Trailing Twelve Months)** — 최근 12개월 재무 수치
- **CAGR (복리연평균 성장률)** — 매출, 영업이익, 순이익, 영업CF, FCF
- **S-RIM (Residual Income Model)** — 내재가치 평가
- **백분위 점수 (Percentile Scoring)** — 각 전략별 가중치 벡터 적용
- **5가지 전략 필터:**
  - Quality: ROE 12%+, PER 낮음
  - Momentum: CAGR 15%+, 이익률 개선
  - GARP: PEG < 1.5
  - Cashcow: FCF 수익률 5%+
  - Turnaround: 흑자전환, 이익률 급개선

**출력:**
- 6개 Excel 파일 (master + 5개 전략)
- SQLite `dashboard_result` 테이블 (웹 대시보드)

**스크리닝 일관성:**
- 스크리닝 로직이 `quant_screener.py`와 `webapp/app.py`의 `_apply_screen_filter()`에 존재
- 스크리닝 조건 변경 시 **두 곳 모두 업데이트 필요**

### `webapp/app.py` — Flask REST API

SQLite DB 기반 REST API + 웹 앱. 메모리 캐싱으로 DB 파일 변경 시 자동 로드.

**주요 기능:**
- 서버사이드 정렬, 필터링, 페이징
- 대시보드 이미지 자동 로드
- JSON 응답, numpy 타입 안전 변환

**API 엔드포인트:**

| Method | Path | Description | Parameters |
|---|---|---|---|
| GET | `/` | 대시보드 페이지 | - |
| GET | `/api/stocks` | 종목 목록 (필터, 정렬, 페이징) | `screen` (전략), `market`, `q` (검색), `sort`, `order`, `page`, `size` |
| GET | `/api/stocks/<code>` | 종목 상세 | - |
| GET | `/api/markets/summary` | 시장별 요약 통계 | - |
| GET | `/api/data/status` | 데이터 파일 상태 | - |
| POST | `/api/batch/trigger` | 파이프라인 수동 실행 | - |
| GET | `/api/report/<code>` | 종목 AI 분석 보고서 | - |

### `analysis/claude_analyzer.py` — AI Analysis (Optional)

Claude API를 사용해 종목의 정성적 분석 보고서 생성 (선택사항).

**주요 기능:**
- 스크리닝 결과 요약
- 산업 분석
- 리스크 평가
- 투자 인시트 생성

**필요 설정:**
- `ANTHROPIC_API_KEY` 환경변수 설정
- `ANALYSIS_MODEL` (기본: `claude-sonnet-4-5-20250929`)

### `config.py` — Central Configuration

환경변수로 모든 설정 관리.

**데이터:**
- `BASE_DIR` — 프로젝트 루트
- `DATA_DIR` — 데이터 디렉토리 (기본: `data/`)
- `DB_PATH` — SQLite DB 경로 (기본: `data/quant.db`)
- `REPORT_DIR` — AI 보고서 저장소 (기본: `data/reports/`)

**배치 스케줄:**
- `BATCH_HOUR` (기본: `18`) — 배치 실행 시각 (KST)
- `BATCH_MINUTE` (기본: `0`) — 배치 실행 분

**웹 서버:**
- `HOST` (기본: `0.0.0.0`)
- `PORT` (기본: `5000`)
- `DEBUG` (기본: `false`)

**Claude API (선택):**
- `ANTHROPIC_API_KEY` — Anthropic API 키
- `ANALYSIS_MODEL` (기본: `claude-sonnet-4-5-20250929`)

## 📱 Frontend

**`webapp/templates/dashboard.html` + `webapp/static/js/dashboard.js`**

- Bootstrap 5.3 기반 싱글페이지 앱 (SPA)
- 6개 탭 (마스터 + 5가지 전략)
- 시장 요약 카드
- 정렬 가능한 테이블
- 종목 상세 모달
- 수동 파이프라인 트리거 버튼

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `BATCH_HOUR` | `18` | 배치 실행 시각 (KST) |
| `BATCH_MINUTE` | `0` | 배치 실행 분 |
| `HOST` | `0.0.0.0` | 웹 서버 바인드 주소 |
| `PORT` | `5000` | 웹 서버 포트 |
| `DEBUG` | `false` | Flask 디버그 모드 |
| `ANTHROPIC_API_KEY` | `` | Claude API 키 (AI 분석 보고서용, 선택) |
| `ANALYSIS_MODEL` | `claude-sonnet-4-5-20250929` | Claude 모델 ID |

환경변수 설정 예:
```bash
export BATCH_HOUR=19
export DEBUG=true
export ANTHROPIC_API_KEY=sk-ant-...
python run.py server
```

## 🔑 Key Patterns & Important Notes

### SQLite Storage

- 모든 데이터는 `data/quant.db`에 저장
- `db.load_latest(table)` — 최신 `collected_date`에 해당하는 데이터 반환
- `db.save_dashboard()` — 스크리닝 결과를 `dashboard_result` 테이블에 저장 (파이프라인 실행 시마다 덮어씀)

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

대시보드에 표시되는 컬럼 (50+개):

**기본 정보:** 종목코드, 종목명, 시장구분, 종가, 시가총액

**밸류에이션:** PER, PBR, PSR, PEG, 적정주가(S-RIM), 괴리율

**수익성:** ROE(%), EPS, BPS, 영업이익률(%), 이익수익률(%), FCF수익률(%)

**안정성:** 부채비율(%), 부채상환능력, 이익품질, 현금전환율, CAPEX비율, F스코어

**기술:** 52주 최고/최저 대비(%), MA20/60 이격도(%), RSI_14, 거래대금, 변동성

**성장률:** 매출/영업이익/순이익/영업CF/FCF CAGR, 배당 CAGR

**연속성:** 매출/영업이익/순이익/영업CF 연속성장, 배당 연속증가

**분기 지표:** Q_매출/영업이익/순이익 YoY, TTM 기반 YoY

**종합 점수:** 종합점수 (백분위 기반)

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
# SQLite 데이터베이스 확인
sqlite3 data/quant.db

# 테이블 목록
.tables

# 특정 테이블 조회
SELECT * FROM dashboard_result LIMIT 10;
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
curl "http://localhost:5000/api/stocks?screen=Quality&market=KOSPI&page=1&size=20"
```

### Get Stock Details

```bash
curl "http://localhost:5000/api/stocks/005930"
```

### Get Market Summary

```bash
curl "http://localhost:5000/api/markets/summary"
```

### Trigger Pipeline Manually

```bash
curl -X POST http://localhost:5000/api/batch/trigger
```

### Get AI Analysis Report (if available)

```bash
curl "http://localhost:5000/api/report/005930"
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

**마지막 업데이트:** 2026-02-17
