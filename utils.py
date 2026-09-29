import streamlit as st

def inject_pwa_blocker():
    """PWAブロック用のJavaScriptスクリプト注入（現状は未使用）"""
    pass

def set_login_storage(user_name, user_url, needs_alert, user_role, user_code):
    """ログイン情報をセッション状態に保存"""
    st.session_state["user_name"] = user_name
    st.session_state["user_url"] = user_url
    st.session_state["needs_alert"] = needs_alert
    st.session_state["user_role"] = user_role
    st.session_state["user_code"] = user_code

def check_session_storage():
    """自動ログインチェック関数（現状は未使用）"""
    pass
