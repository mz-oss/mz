# 모바일 화면 최적화 계획

## 현재 문제점 분석

현재 대시보드는 `layout="wide"` + 다단 컬럼 레이아웃으로 데스크톱에 최적화되어 있어 모바일에서 다음 문제가 발생합니다:

1. **상단 컨트롤 3컬럼** (`st.columns(3)`) - 모드 선택, Area Group, 대수 입력이 좁은 화면에서 찌그러짐
2. **KPI 5컬럼** (`st.columns(5)`) - 메트릭 카드 5개가 한 줄에 배치되어 텍스트가 잘림
3. **DataTable 가로 스크롤** - 8~9개 컬럼의 넓은 테이블이 모바일에서 읽기 어려움
4. **지도 높이 부족** - 기본 pydeck 높이가 모바일 세로 화면에서 너무 작음

## 수정 계획

### 1. 반응형 레이아웃 감지 함수 추가 (`app.py`)

Streamlit에서 화면 크기를 직접 감지할 수 없으므로, **CSS 미디어 쿼리 기반 커스텀 스타일**을 `st.markdown`으로 주입합니다.

```python
# app.py 상단에 모바일 반응형 CSS 추가
st.markdown("""
<style>
/* 모바일 (768px 이하) */
@media (max-width: 768px) {
    /* 컬럼이 세로로 쌓이도록 */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
    }
    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    /* metric 카드 간격 조정 */
    [data-testid="stMetric"] {
        padding: 0.5rem 0;
    }
    /* 라디오 버튼 세로 배치 */
    [data-testid="stRadio"] > div {
        flex-direction: column !important;
    }
}
</style>
""", unsafe_allow_html=True)
```

**효과:**
- 모바일에서 `st.columns(3)`, `st.columns(5)` 내부 요소가 자동으로 세로 스택
- 라디오 버튼이 가로 대신 세로로 나열
- 별도 Python 로직 변경 없이 CSS만으로 반응형 처리

### 2. KPI 메트릭 레이아웃 개선 (`app.py:150-165`)

5컬럼을 **2행으로 분리** (3+2)하여 모바일에서도 잘 보이도록 합니다.

```python
# 기존: col1, col2, col3, col4, col5 = st.columns(5)
# 변경:
row1_col1, row1_col2, row1_col3 = st.columns(3)
row1_col1.metric("평균 공급성공률", ...)
row1_col2.metric("총 배치 기기 수", ...)
row1_col3.metric("분석 지역 수", ...)

row2_col1, row2_col2 = st.columns(2)
row2_col1.metric("목표 미달 지역", ...)
row2_col2.metric("목표 초과 지역", ...)
```

**효과:** 데스크톱에서는 3+2행, 모바일에서는 CSS 미디어 쿼리로 각 메트릭이 1행씩 표시

### 3. DataTable 모바일 친화 개선 (`app.py:100-126, 167-194`)

모바일에서 핵심 컬럼만 보이도록 **컬럼 축소**하고, 전체 데이터는 CSV 다운로드로 제공합니다.

할당 결과 테이블의 `column_order` 파라미터를 활용하여 모바일 핵심 컬럼을 우선 배치:

```python
# 모바일 핵심 컬럼 우선 배치 (District, 할당 대수를 앞으로)
alloc_display_cols = [
    "alloc_priority", "h3_district_name", "allocated",
    "gap_int", "avg_bike_count", "avg_accessibility",
    "area_group", "h3_area_name",
]
```

추가로 테이블 CSS를 통해 모바일에서 글자 크기를 줄입니다:

```css
@media (max-width: 768px) {
    [data-testid="stDataFrame"] {
        font-size: 0.8rem;
    }
}
```

### 4. 지도 높이 조정 (`app.py:143`)

`st.pydeck_chart`에 `height` 파라미터를 추가하여 모바일에서도 충분한 높이를 확보합니다.

```python
# 기존
st.pydeck_chart(deck, use_container_width=True)

# 변경: 높이를 명시적으로 지정
st.pydeck_chart(deck, use_container_width=True, height=500)
```

### 5. 제목/캡션 축약 (`app.py:21-22`)

긴 캡션 텍스트가 모바일에서 여러 줄로 넘치므로, `st.expander`로 감싸 접을 수 있게 합니다.

```python
st.title("수거/배치 대시보드")
with st.expander("계산 방식 안내", expanded=False):
    st.caption("최근 14일 공급 성공률 기반 | 목표 공급성공률 80% | 적정 대수 = 현재 대수 x (목표 성공률 / 현재 성공률)")
```

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `app.py` | 반응형 CSS 주입, KPI 레이아웃 2행 분리, 제목/캡션 축약, 지도 높이 설정, 컬럼 순서 조정 |

## 변경하지 않는 파일

- `src/data_processing.py` - 비즈니스 로직 변경 없음
- `src/map_utils.py` - 지도 생성 로직 변경 없음
- `src/bigquery_client.py` - 데이터 소스 변경 없음
- `.streamlit/config.toml` - 테마 설정 유지
