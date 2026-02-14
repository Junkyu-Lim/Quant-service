# Quant-service

KOSPI/KOSDAQ 퀀트 데이터 수집, 스크리닝, 웹 대시보드 자동화 파이프라인.

## Features

- **데이터 수집** (`quant_collector_enhanced.py`) — KRX 종목 마스터, 일별 시세, 재무제표(IS/BS/CF), 핵심 지표(FnGuide), 주식수를 CSV로 수집 (ThreadPoolExecutor 병렬 처리)
- **퀀트 스크리닝** (`quant_screener.py` v6) — 5가지 전략별 스크리닝:
  - Quality (우량주/저평가) — ROE, PER, PBR, 연속 성장
  - Momentum (고성장) — CAGR 15%+, 이익률 개선
  - GARP (성장+가치) — PEG < 1.5, ROE 12%+
  - Cashcow (현금흐름) — FCF 수익률 5%+, 이익 품질
  - Turnaround (실적 반등) — 흑자전환, 이익률 급개선
- **배치 자동화** — APScheduler로 매일 장 마감 후 자동 실행 (18:00 KST 기본)
- **웹 대시보드** — Flask 기반, 6개 스크리닝 탭, 서버사이드 정렬/필터/페이징, 종목 상세 모달
- **REST API** — JSON 기반 주식 목록, 상세, 시장 요약, 파이프라인 제어

## Project Structure

```
├── quant_collector_enhanced.py  # 데이터 수집기 (KRX + FnGuide)
├── quant_screener.py            # 퀀트 스크리너 (v6, 5가지 전략)
├── pipeline.py                  # 파이프라인 오케스트레이터
├── config.py                    # 환경 설정
├── run.py                       # CLI 진입점
├── requirements.txt
├── batch/
│   └── scheduler.py             # APScheduler 배치 스케줄러
├── webapp/
│   ├── app.py                   # Flask 웹 앱 + API
│   ├── templates/dashboard.html
│   └── static/{css,js}/
└── data/                        # CSV/Excel 출력 디렉토리
```

## Quick Start

```bash
pip install -r requirements.txt

# 1. 테스트 모드 (3개 종목만 수집)
python run.py pipeline --test

# 2. 전체 파이프라인 (수집 + 스크리닝)
python run.py pipeline

# 3. 수집 건너뛰고 스크리닝만 (CSV가 이미 있을 때)
python run.py pipeline --skip-collect

# 4. 웹 서버 + 배치 스케줄러 시작
python run.py server
```

Dashboard: `http://localhost:5000`

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BATCH_HOUR` | `18` | 배치 실행 시각 (KST) |
| `BATCH_MINUTE` | `0` | 배치 실행 분 |
| `HOST` | `0.0.0.0` | 웹 서버 바인드 주소 |
| `PORT` | `5000` | 웹 서버 포트 |
| `DEBUG` | `false` | Flask 디버그 모드 |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/stocks` | 종목 목록 (screen, market, q, sort, order, page, size) |
| GET | `/api/stocks/<code>` | 종목 상세 |
| GET | `/api/markets/summary` | 시장별 요약 통계 |
| GET | `/api/data/status` | 데이터 파일 상태 |
| POST | `/api/batch/trigger` | 파이프라인 수동 실행 |
