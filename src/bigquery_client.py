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
    project_id = os.getenv("BQ_PROJECT_ID", "")

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


@st.cache_data(ttl=3600)
def fetch_hex_stats() -> pd.DataFrame:
    """Hex 단위 최근 14일 공급 통계를 조회합니다."""
    client = get_bq_client()
    sql = _read_query("hex_stats.sql")
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=86400)
def fetch_district_polygons() -> pd.DataFrame:
    """District 폴리곤 정보를 조회합니다."""
    client = get_bq_client()
    sql = _read_query("district_polygons.sql")
    return client.query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def fetch_area_list() -> list[str]:
    """운영 중인 Area 목록을 조회합니다."""
    client = get_bq_client()
    sql = """
    SELECT DISTINCT h3_area_name
    FROM `management.daily_bike_accessibility_by_district`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
      AND is_operating = TRUE
      AND h3_area_name IS NOT NULL
    ORDER BY h3_area_name
    """
    df = client.query(sql).to_dataframe()
    return df["h3_area_name"].tolist()
