import sys
from pathlib import Path

# ルートディレクトリを検索パスに追加（ImportError防止）
sys.path.append(str(Path(__file__).parent))

import streamlit as st
import os
from utils import inject_pwa_blocker, set_login_storage, check_session_storage
from data_loader import load_sheet_data
from views.campaign_view import campaign_screen

# --- 1. ページ基本設定 ---
st.set_page_config(
    page_title="ダスキンシャトル キャンペーン集計アプリ",
    page_icon="icon.png",
    layout="wide"
)

# --- 2. セッション状態の初期化 ---
if 'login_status' not in st.session_state: st.session_state.login_status = False
if 'logout_requested' not in st.session_state: st.session_state.logout_requested = False

# --- 3. セッションストレージによる自動ログイン確認 ---
if not st.session_state.login_status and not st.session_state.logout_requested:
    check_session_storage()

# --- 4. 画面表示 ---
if st.session_state.login_status:
    with st.sidebar:
        st.write(f"👤 ログイン中: **{st.session_state.get('user_name', '担当者')}**")
        st.caption(f"権限: {st.session_state.get('user_role', 'なし')}")
        if st.button("🚪 ログアウト", use_container_width=True):
            st.session_state.login_status = False
            st.session_state.logout_requested = True
            st.rerun()

    campaign_screen()
else:
    # --- 🔑 ログイン画面 ---
    inject_pwa_blocker()

    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        if os.path.exists("1.png"):
            st.image("1.png", use_container_width=True)

        u_email = st.text_input("メールアドレス").strip()
        u_pass = st.text_input("パスワード", type="password").strip()

        if st.button("ログイン", type="primary", use_container_width=True):
            raw = load_sheet_data(gid="0")
            if raw and len(raw) > 1:
                # 行ごとに判定 (A列: 0[メール], B列: 1[拠点], C列: 2[名前], D列: 3[パスワード], F列: 5[権限])
                user_found = None
                for row in raw[1:]:
                    if len(row) >= 6:
                        email_val = str(row[0]).strip()  # A列
                        pass_val = str(row[3]).strip()   # D列

                        if email_val.lower() == u_email.lower() and pass_val == u_pass:
                            user_found = {
                                "email": email_val,
                                "branch": str(row[1]).strip(),  # B列
                                "name": str(row[2]).strip(),  # C列
                                "role": str(row[5]).strip()   # F列
                            }
                            break

                if user_found:
                    st.session_state.user_name = user_found["name"]
                    st.session_state.user_role = user_found["role"]
                    st.session_state.user_code = user_found["email"]
                    st.session_state.user_branch = user_found["branch"]
                    st.session_state.login_status = True
                    st.session_state.logout_requested = False

                    set_login_storage(
                        st.session_state.user_name,
                        "",
                        False,
                        st.session_state.user_role,
                        st.session_state.user_code
                    )
                    st.rerun()
                else:
                    st.error("認証失敗: メールアドレスまたはパスワードが正しくありません")
            else:
                st.error("マスターデータの読み込みに失敗しました。シートの共有設定（アクセス権限）を確認してください。")
