# CLAUDE.md - 자전거 수거/배치 대시보드

## 프로젝트 개요
현장관리팀이 자전거 수거 지역/대수, 배치 지역/대수를 파악하기 위한 Streamlit 대시보드.
BigQuery 실시간 데이터 기반으로 공급 성공률을 분석하고 적정 배치 대수를 산정한다.

## 기술 스택
- **프레임워크**: Streamlit
- **데이터 소스**: Google BigQuery
- **지도 시각화**: pydeck + H3 (Uber)
- **언어**: Python 3.10+

## 프로젝트 구조
```
mz/
├── app.py                     # Streamlit 메인 앱 (엔트리포인트)
├── requirements.txt           # Python 의존성
├── .gitignore
├── .streamlit/
│   └── config.toml            # Streamlit 테마/서버 설정
├── src/
│   ├── __init__.py
│   ├── bigquery_client.py     # BigQuery 연결, 쿼리 실행, 캐싱
│   ├── data_processing.py     # 적정대수/부족대수/우선순위/할당 계산
│   └── map_utils.py           # pydeck 기반 지도 시각화 (Hex, District)
└── queries/
    ├── district_stats.sql     # District 단위 14일 통계
    ├── hex_stats.sql          # Hex 단위 7일 통계 (기기수: daily_hex_48h, 공급성공률: weekly_bike_accessibility_by_hex)
    └── district_polygons.sql  # District 폴리곤 조회
```

## 핵심 비즈니스 로직
```
적정 대수 = 현재 대수 × (목표 공급성공률 / 현재 공급성공률)
부족 대수 = 적정 대수 - 현재 대수
  양수 → 배치 필요
  음수 → 수거 가능
우선순위 = |부족 대수| 내림차순 (큰 곳이 효율적 수거/배치)
```

## BigQuery 테이블
| 테이블 | 용도 |
|--------|------|
| `management.daily_bike_accessibility_by_district` | District 일별 공급성공률/배치기기수 |
| `management.daily_hex_48h` | Hex 시간대별 기기수 (bike_cnt) — 평균 기기수 산출용 |
| `management.weekly_bike_accessibility_by_hex` | Hex 주별 공급성공률/전환율 |
| `service.geo_district` | District 경계 폴리곤 (GeoJSON) |
| `service.geo_district_h3` | District↔H3 매핑 |
| `management.business_riding` | 라이딩 원시 데이터 (참조용) |

### 주요 컬럼
- `bike_cnt` (daily_hex_48h): 시간대별 기기수 → **일별 평균 → 일간 평균 2단계 집계로 배치 기기 대수 산출**
- `accessibility_ratio`: 공급 성공률
- `total_log_cnt`: 앱 오픈 로그 수 (안드로이드만, ×1.5 보정 필요)

## 개발 환경 설정

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. BigQuery 인증
프로젝트 루트에 `credentials.json` (서비스 계정 키) 배치 후:
```bash
export BQ_PROJECT_ID="your-project-id"
```
또는 `.streamlit/secrets.toml`에 설정:
```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
# ... 나머지 서비스 계정 필드
```

### 3. 실행
```bash
streamlit run app.py
```

## 코드 수정 가이드

### SQL 수정
- `queries/` 디렉토리의 `.sql` 파일 직접 수정
- `bigquery_client.py`의 `_read_query()`가 자동으로 읽어감
- 캐시 TTL: 통계 쿼리 1시간, 폴리곤 24시간

### 새 지표 추가
1. SQL에 컬럼 추가
2. `data_processing.py`의 `calculate_supply_gap()`에서 활용
3. `app.py`의 display_cols에 컬럼 추가

### 지도 스타일 변경
- `map_utils.py`의 `_gap_to_color()` 함수에서 색상 로직 수정
- pydeck 레이어 옵션은 각 `create_*_map()` 함수에서 조정

## 컨벤션
- 한국어 docstring/주석 사용
- BigQuery SQL은 `queries/` 디렉토리에 분리
- Streamlit 캐싱: `@st.cache_data` (데이터), `@st.cache_resource` (클라이언트)
- `credentials.json`은 절대 커밋하지 않음 (.gitignore에 포함)
