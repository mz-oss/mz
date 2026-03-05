"""BigQuery 연결 및 데이터 조회 모듈."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account


@st.cache_resource
def get_bq_client() -> bigquery.Client:
    """BigQuery 클라이언트를 생성하고 캐싱합니다.

    인증 우선순위:
    1. Streamlit secrets (toml 파일에 service_account 정보)
    2. GOOGLE_APPLICATION_CREDENTIALS 환경변수
    3. credentials.json 파일 (프로젝트 루트)
    """
    project_id = os.getenv("BQ_PROJECT_ID", "elecle-9be54")

    # 1) Streamlit secrets
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        project_id = project_id or st.secrets["gcp_service_account"].get("project_id", "")
        return bigquery.Client(credentials=creds, project=project_id)

    # 2) 환경변수 또는 로컬 파일
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path:
        local_creds = Path(__file__).resolve().parent.parent / "credentials.json"
        if local_creds.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(local_creds)
            return bigquery.Client(project=project_id or None)

    if creds_path:
        return bigquery.Client(project=project_id or None)

    # 인증 정보가 없는 경우 안내 메시지 표시
    st.error(
        "BigQuery 인증 정보가 설정되지 않았습니다.\n\n"
        "**Streamlit Cloud 사용 시:**\n"
        "1. App settings → Secrets 에 서비스 계정 JSON을 등록하세요.\n"
        "2. 형식:\n"
        "```toml\n"
        "[gcp_service_account]\n"
        'type = "service_account"\n'
        'project_id = "elecle-9be54"\n'
        '# ... credentials.json 의 나머지 필드\n'
        "```\n\n"
        "**로컬 실행 시:** 프로젝트 루트에 `credentials.json`을 배치하세요."
    )
    st.stop()


def _read_query(filename: str) -> str:
    """queries/ 디렉토리에서 SQL 파일을 읽습니다."""
    query_path = Path(__file__).resolve().parent.parent / "queries" / filename
    return query_path.read_text(encoding="utf-8")


@st.cache_data(ttl=3600)
def fetch_district_stats() -> pd.DataFrame:
    """District 단위 최근 14일 공급 통계를 조회합니다."""
    client = get_bq_client()
    sql = _read_query("district_stats.sql")
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=86400)
def fetch_district_polygons() -> pd.DataFrame:
    """District 폴리곤 정보를 조회합니다."""
    client = get_bq_client()
    sql = _read_query("district_polygons.sql")
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def fetch_rebalance_zones() -> pd.DataFrame:
    """Rebalance Zone 정보를 조회합니다."""
    client = get_bq_client()
    sql = _read_query("rebalance_zones.sql")
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def fetch_area_group_list() -> list[str]:
    """운영 중인 Area Group 목록을 조회합니다."""
    client = get_bq_client()
    sql = """
    SELECT DISTINCT `elecle-9be54.udf.get_area_group`(h3_area_name) AS area_group
    FROM `elecle-9be54.management.daily_bike_accessibility_by_district`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
      AND h3_area_name IS NOT NULL
    ORDER BY area_group
    """
    df = client.query(sql).to_dataframe()
    return df["area_group"].dropna().tolist()
