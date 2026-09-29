"""キャンペーン集計アプリのメイン画面。
現時点では「顧客コード検索→顧客名/加盟店/加盟店コードの自動表示」までを実装している。
集計そのもの（何を・どう数えるか）はまだ仕様検討中のため、下部はプレースホルダー。"""
import streamlit as st

from views.common import lookup_customer


def campaign_screen():
    st.markdown("#### 📊 キャンペーン集計")
    st.write("---")

    st.write("**🔍 顧客コード検索**")
    col_input, col_btn = st.columns([4, 1])
    cust_code = col_input.text_input("顧客コード", key="camp_cust_code")
    btn_search = col_btn.button("🔍 検索", use_container_width=True)

    if btn_search:
        if not cust_code.strip():
            st.warning("顧客コードを入力してください。")
        else:
            result = lookup_customer(cust_code)
            if result is None:
                st.warning("該当する顧客データが見つかりませんでした。")
                st.session_state.pop("camp_customer", None)
            else:
                st.session_state["camp_customer"] = {"cust_code": cust_code.strip(), **result}
                st.toast("顧客情報を取得しました！", icon="✅")

    customer = st.session_state.get("camp_customer")
    if customer:
        st.write("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.text_input("顧客コード", value=customer["cust_code"], disabled=True, key="camp_v_ccode")
        c2.text_input("顧客名", value=customer["cust_name"], disabled=True, key="camp_v_cname")
        c3.text_input("加盟店名", value=customer["store_name"], disabled=True, key="camp_v_sname")
        c4.text_input("加盟店コード", value=customer["store_code"], disabled=True, key="camp_v_scode")

    st.write("---")
    st.info("📊 集計機能は仕様検討中です。どのデータを何件集計するか決まり次第、ここに追加します。")
