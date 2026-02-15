# Vercel 배포 가이드

## 개요
이 프로젝트를 Vercel에 배포하는 방법을 단계별로 설명합니다.

## 중요한 제약사항

### 1. 서버리스 환경의 한계
Vercel은 **서버리스 플랫폼**이므로 다음과 같은 제약이 있습니다:

- **배치 작업 불가능**: APScheduler로 정의된 일일 스케줄 작업(매일 18시 데이터 수집)은 Vercel에서 작동하지 않습니다
- **파일 저장소 불가능**: SQLite 데이터베이스(`data/quant.db`)는 Vercel의 ephemeral 파일시스템에서 요청 후 삭제됩니다
- **함수 실행 시간 제한**: 요청당 최대 실행 시간 제한(무료: 10초, Pro: 60초, 스케일: 900초)

### 2. 해결책

#### 옵션 A: 외부 데이터베이스 사용 (권장)
- PostgreSQL, MySQL, MongoDB 등을 사용
- 환경변수 `DATABASE_URL` 설정
- 데이터 지속성 보장

#### 옵션 B: Cron Job 서비스 사용
- 외부 Cron Job 서비스(EasyCron, IFTTT 등)에서 API 호출
- `/api/batch/trigger` 엔드포인트 활용

#### 옵션 C: GitHub Actions 사용
- GitHub 리포지토리에서 스케줄 실행
- 매일 Vercel API로 데이터 동기화

## 배포 단계

### 1단계: Vercel 프로젝트 생성

```bash
# Vercel CLI 설치 (없으면)
npm i -g vercel

# 로그인
vercel login

# 프로젝트 배포
vercel
```

### 2단계: 환경변수 설정

Vercel 대시보드에서 다음 단계를 따르세요:

1. **프로젝트 설정 열기**: https://vercel.com/projects
2. **프로젝트 선택**
3. **Settings 탭** → **Environment Variables**
4. **아래 변수들을 추가**:

| 변수명 | 값 | 설명 |
|--------|-----|------|
| `BATCH_HOUR` | `18` | 일일 배치 실행 시간 (18시 KST) |
| `BATCH_MINUTE` | `0` | 일일 배치 실행 분 |
| `HOST` | `0.0.0.0` | 바인드 호스트 |
| `DEBUG` | `false` | 디버그 모드 비활성화 |

### 3단계: 배포 확인

```bash
# 로컬에서 Vercel 환경 시뮬레이션
vercel env pull .env.local
vercel dev
```

### 4단계: 데이터 동기화 (선택사항)

만약 SQLite에서 외부 DB로 전환하려면:

1. **주요 파일 수정**:
   - `db.py`: SQLite 대신 외부 DB 드라이버 사용
   - `config.py`: `DATABASE_URL` 환경변수 읽기
   - `requirements.txt`: psycopg2, pymysql 등 추가

2. **마이그레이션 스크립트 작성**:
   ```python
   # scripts/migrate_to_external_db.py
   # 기존 SQLite → 외부 DB 데이터 이전
   ```

## 환경변수 의미

### Batch 스케줄 설정
- `BATCH_HOUR`: 일일 데이터 수집/스크리닝 실행 시간
  - 기본값: `18` (18시 KST, 장 마감 후)
  - 범위: 0-23

- `BATCH_MINUTE`: 실행 분
  - 기본값: `0`
  - 범위: 0-59

### 웹 서버 설정
- `HOST`: Flask 앱 바인드 주소
  - 기본값: `0.0.0.0` (모든 인터페이스)
  - Vercel에서는 무시됨 (자동 구성)

- `PORT`: 포트 번호
  - 기본값: `5000`
  - Vercel에서는 무시됨 (자동 할당)

- `DEBUG`: 디버그 모드
  - `true`: 개발 모드 (자동 리로드, 상세 오류)
  - `false`: 프로덕션 모드 (기본값)

## 배포 후 작동 확인

### API 테스트
```bash
# 배포된 URL로 테스트
curl https://your-vercel-domain.vercel.app/api/stocks?page=1

# 마켓 요약 조회
curl https://your-vercel-domain.vercel.app/api/markets/summary

# 데이터 상태 조회
curl https://your-vercel-domain.vercel.app/api/data/status
```

### 대시보드 접속
```
https://your-vercel-domain.vercel.app/
```

## 문제 해결

### 데이터베이스 오류
- **원인**: SQLite 파일을 찾을 수 없음
- **해결**: 외부 데이터베이스로 마이그레이션

### 배치 작업이 실행되지 않음
- **원인**: Vercel은 항상 실행되는 서버를 지원하지 않음
- **해결**: 외부 Cron 또는 GitHub Actions 사용

### 의존성 설치 오류
- **해결**: `vercel build`로 빌드 로그 확인
- `requirements.txt`에서 호환되지 않는 버전 제거

## 추천 사항

1. **프로덕션 데이터베이스**: PostgreSQL (Vercel에서 공식 지원)
2. **스케줄링**: GitHub Actions 또는 외부 Cron 서비스
3. **모니터링**: Vercel Analytics + Sentry 같은 에러 트래킹
4. **캐싱**: Vercel KV (Redis) - 대시보드 캐시용

## 추가 리소스

- [Vercel Flask 배포 문서](https://vercel.com/docs/frameworks/flask)
- [Vercel 환경변수 설정](https://vercel.com/docs/projects/environment-variables)
- [Vercel Functions 실행 시간 제한](https://vercel.com/docs/functions/serverless-functions/runtimes#execution-time-limit)
