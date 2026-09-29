"""キャンペーン集計アプリ共通のヘルパー・定数。
顧客マスターはkensaku（メンテナンス依頼アプリ）と同じスプレッドシートを参照する。"""
import streamlit as st
import pandas as pd
import requests
import json
from datetime import timezone, timedelta, datetime

# 顧客マスター（A=加盟店名, B=顧客コード, C=顧客名, D=(未使用), E=加盟店コード）
# kensaku（views/maint_common.py）のCUSTOMER_MASTER_CSVと同一シート・同一列構成。
CUSTOMER_MASTER_CSV = "https://docs.google.com/spreadsheets/d/1AkMb1J2m3VZAIyMCKmr3T3E8-kJB0BDDdWQJuEn7YGc/gviz/tq?tqx=out:csv&gid=127347205"

# 💡 キャンペーン入力データの保存先。まだ専用のスプレッドシート・GAS Web Appが
#    用意できていないため、いずれも空文字のプレースホルダーにしてある。
#    用意でき次第ここに設定すればそのまま保存できるようになる
#    （kensakuのGAS_URL／TARGET_SHEET_URLと同じ仕組み：doPostに action と
#    target_sheet_url、追加する行データ full_row を渡す）。
GAS_URL = ""
CAMPAIGN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1P_T6ZylVbu9FBK5HureFFMPz4wTujJOfB1FUgI8gaO4/edit?gid=0#gid=0"

JST = timezone(timedelta(hours=+9), 'JST')


def post_to_gas(payload):
    if not GAS_URL:
        return {"status": "error", "message": "保存先が未設定です（GAS_URLが空）。管理者に設定を依頼してください。"}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(GAS_URL, data=json.dumps(payload), headers=headers, timeout=30)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@st.cache_data(ttl=15)
def read_csv_cached(url, **kwargs):
    """Google SheetsのCSVをキャッシュ付きで読み込む共通ヘルパー（15秒キャッシュ）。"""
    return pd.read_csv(url, dtype=str, **kwargs)


def lookup_customer(cust_code):
    """顧客コードから顧客マスターを検索し、顧客名・加盟店名・加盟店コードを返す。
    戻り値: {"store_name":..., "cust_name":..., "store_code":...} / 見つからなければ None"""
    if not cust_code or not str(cust_code).strip():
        return None
    try:
        df_master = read_csv_cached(CUSTOMER_MASTER_CSV, storage_options={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None

    matched = df_master[df_master.iloc[:, 1].astype(str).str.strip() == str(cust_code).strip()]
    if matched.empty:
        return None

    last_row = matched.iloc[-1]
    return {
        "store_name": str(last_row.iloc[0]) if pd.notna(last_row.iloc[0]) else "",
        "cust_name": str(last_row.iloc[2]) if pd.notna(last_row.iloc[2]) else "",
        "store_code": str(last_row.iloc[4]) if pd.notna(last_row.iloc[4]) else "",
    }
