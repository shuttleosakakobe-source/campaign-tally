import json
import streamlit as st
from streamlit_local_storage import LocalStorage

# ブラウザのlocalStorageに、ログイン記憶情報を保存するキー名
_LOGIN_STORAGE_KEY = "campaign_tally_login_info"
# 再ログイン画面でメールアドレスを自動入力するための保存キー（ログアウトしても消さない）
_LOGIN_EMAIL_KEY = "campaign_tally_login_email"


def inject_pwa_blocker():
    """PWAブロック用のJavaScriptスクリプト注入（現状は未使用）"""
    pass


def _get_local_storage():
    """LocalStorageコンポーネントのインスタンスをsession_stateにキャッシュして使い回す
    （毎回new LocalStorage()すると、ブラウザとの同期が走り直してしまうため）。
    （kensaku: utils.py と共通の実装。将来1つの業務アプリに統合する際、
    ログイン記憶の仕組みをそのまま流用できるようにしている。）"""
    if "_local_storage" not in st.session_state:
        st.session_state["_local_storage"] = LocalStorage()
    return st.session_state["_local_storage"]


def set_login_storage(user_name, user_url, needs_alert, user_role, user_code, user_branch="", user_area=""):
    """ログイン情報をセッション状態＋ブラウザのlocalStorageに保存する（ログイン記憶機能）。
    ブラウザを閉じて開き直しても再ログインしなくて済むようにする。
    💡 パスワードは一切保存しない。保存するのはログイン状態を復元するための
    最小限の情報（氏名・権限・メール・拠点・エリア）のみ。"""
    st.session_state["user_name"] = user_name
    st.session_state["user_url"] = user_url
    st.session_state["needs_alert"] = needs_alert
    st.session_state["user_role"] = user_role
    st.session_state["user_code"] = user_code
    st.session_state["user_branch"] = user_branch
    st.session_state["user_area"] = user_area

    try:
        _get_local_storage().setItem(_LOGIN_STORAGE_KEY, json.dumps({
            "user_name": user_name,
            "user_role": user_role,
            "user_code": user_code,
            "user_branch": user_branch,
            "user_area": user_area,
        }))
    except Exception:
        # localStorageへの保存に失敗しても、今回のログイン自体（session_state）は
        # 既に完了しているので、アプリの動作は止めない（次回また手入力ログインになるだけ）。
        pass


def check_session_storage():
    """ブラウザのlocalStorageに記憶されたログイン情報があれば、ログイン画面を
    飛ばして自動的にログイン状態を復元する。パスワードの再検証はしない
    （そもそも保存していないため）。ログアウト時は必ず clear_login_storage() で
    消すこと（消さないとログアウトしてもすぐ自動ログインし直されてしまう）。"""
    try:
        raw = _get_local_storage().getItem(_LOGIN_STORAGE_KEY)
    except Exception:
        return

    if not raw:
        return
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return
    if not isinstance(raw, dict) or not raw.get("user_code"):
        return

    st.session_state["user_name"] = raw.get("user_name", "")
    st.session_state["user_role"] = raw.get("user_role", "")
    st.session_state["user_code"] = raw.get("user_code", "")
    st.session_state["user_branch"] = raw.get("user_branch", "")
    st.session_state["user_area"] = raw.get("user_area", "")
    st.session_state["login_status"] = True


def clear_login_storage():
    """ログアウト時に、記憶していたログイン情報をブラウザのlocalStorageから消す。
    （メールアドレスの記憶＝remember_email は、再ログイン時の入力の手間を省くための
    別機能なので、ここでは消さない。）"""
    try:
        _get_local_storage().deleteItem(_LOGIN_STORAGE_KEY)
    except Exception:
        pass


def remember_email(email):
    """次回ログイン画面を開いたときにメールアドレスを自動入力できるよう、
    ブラウザのlocalStorageに保存する。ログアウトしても消さない
    （ログイン状態の保持＝set_login_storageとは別の、入力の手間を省くための機能）。
    パスワードは保存しない。
    （kensaku: utils.py と共通の実装。）"""
    try:
        _get_local_storage().setItem(_LOGIN_EMAIL_KEY, email)
    except Exception:
        pass


def get_remembered_email():
    """保存されているメールアドレスを取得する（無ければ空文字）。"""
    try:
        raw = _get_local_storage().getItem(_LOGIN_EMAIL_KEY)
    except Exception:
        return ""
    return raw if isinstance(raw, str) else ""
