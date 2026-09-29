"""キャンペーン集計アプリのメイン画面。
顧客コード検索と、キャンペーン実績の入力フォームを実装している。
集計（入力されたデータの件数・金額などの集計表示）はまだ仕様検討中のため未実装。"""
import streamlit as st
from datetime import date, datetime

from views.common import lookup_customer, post_to_gas, CAMPAIGN_SHEET_URL, JST

CATEGORIES = ["きれいBOX", "セリング", "増加・切替", "ケアサービス"]
CARE_TYPES = ["SM", "TMX", "MM", "その他"]

SELLING_ROWS = 5   # セリングの入力行数
INCREASE_ROWS = 5  # 増加・切替＞増加の入力行数

# 💡 保存先シートの列（0始まり）。カテゴリごとに使うフィールドが異なるため、
#    全カテゴリ分の列を持つ1枚のシートに、該当しない列は空欄のまま書き込む
#    （kensakuの各モードと同じ考え方）。セリングと増加・切替＞増加は、それぞれ
#    最大5行（商品5件分）まで入力できるようにしている。
# 0 タイムスタンプ, 1 申請者, 2 顧客コード, 3 顧客名, 4 加盟店名, 5 加盟店コード, 6 カテゴリ,
# 7 きれいBOX 販売数, 8 単価, 9 個数,
# 10〜29 セリング 商品①〜⑤（1商品あたり4列＝商品記号/販売数/単価/個数）,
# 30〜49 増加 商品①〜⑤（1商品あたり4列＝商品記号/サイクル/単価/数量）,
# 50 切替 変更前商品, 51 変更前単価, 52 変更前数量, 53 変更後商品, 54 変更後単価, 55 変更後数量,
# 56 ケア種別, 57 実施日, 58 金額


def _customer_search_section():
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
    return customer


def _entry_form_section(customer):
    st.write("---")
    st.write("**📝 キャンペーン実績入力**")

    category = st.radio("カテゴリ", CATEGORIES, horizontal=True, key="camp_category")

    # カテゴリ切り替えに応じて空の値を持たせておく（未入力分は空欄のまま送信する）
    sales_count = unit_price = count = ""
    selling_items = [("", "", "", "")] * SELLING_ROWS
    increase_items = [("", "", "", "")] * INCREASE_ROWS
    product_before = price_before = qty_before = ""
    product_after = price_after = qty_after = ""
    care_type = care_date_str = care_amount = ""

    if category == "きれいBOX":
        c1, c2, c3 = st.columns(3)
        sales_count = c1.text_input("販売数", key="camp_kb_sales")
        unit_price = c2.text_input("単価", key="camp_kb_price")
        count = c3.text_input("個数", key="camp_kb_count")

    elif category == "セリング":
        rows = []
        for i in range(SELLING_ROWS):
            st.caption(f"商品 {i + 1}")
            c1, c2, c3, c4 = st.columns(4)
            code = c1.text_input("商品記号", key=f"camp_sl_code_{i}")
            sales = c2.text_input("販売数", key=f"camp_sl_sales_{i}")
            price = c3.text_input("単価", key=f"camp_sl_price_{i}")
            cnt = c4.text_input("個数", key=f"camp_sl_count_{i}")
            rows.append((code, sales, price, cnt))
        selling_items = rows

    elif category == "増加・切替":
        sub_category = st.radio("増加 / 切替", ["増加", "切替"], horizontal=True, key="camp_ic_sub")
        if sub_category == "増加":
            rows = []
            for i in range(INCREASE_ROWS):
                st.caption(f"商品 {i + 1}")
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("商品記号", key=f"camp_ic_code_{i}")
                cycle = c2.text_input("サイクル", key=f"camp_ic_cycle_{i}")
                price = c3.text_input("単価", key=f"camp_ic_price_{i}")
                qty = c4.text_input("数量", key=f"camp_ic_qty_{i}")
                rows.append((code, cycle, price, qty))
            increase_items = rows
        else:
            st.caption("変更前")
            b1, b2, b3 = st.columns(3)
            product_before = b1.text_input("変更前商品", key="camp_ic_before_code")
            price_before = b2.text_input("単価", key="camp_ic_before_price")
            qty_before = b3.text_input("数量", key="camp_ic_before_qty")
            st.caption("変更後")
            a1, a2, a3 = st.columns(3)
            product_after = a1.text_input("変更後商品", key="camp_ic_after_code")
            price_after = a2.text_input("単価", key="camp_ic_after_price")
            qty_after = a3.text_input("数量", key="camp_ic_after_qty")

    elif category == "ケアサービス":
        c1, c2, c3 = st.columns(3)
        care_type = c1.selectbox("種別", CARE_TYPES, key="camp_care_type")
        care_date = c2.date_input("実施日", value=date.today(), key="camp_care_date")
        care_date_str = care_date.strftime("%Y/%m/%d") if care_date else ""
        care_amount = c3.text_input("金額", key="camp_care_amount")

    if st.button("✅ 登録する", type="primary", use_container_width=True):
        if not customer:
            st.error("⚠️ 先に顧客コードを検索してください。")
            return

        selling_flat = [v for item in selling_items for v in item]
        increase_flat = [v for item in increase_items for v in item]

        full_row = [
            datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S"),
            st.session_state.get("user_name", ""),
            customer["cust_code"], customer["cust_name"],
            customer["store_name"], customer["store_code"],
            category,
            sales_count, unit_price, count,
        ] + selling_flat + increase_flat + [
            product_before, price_before, qty_before,
            product_after, price_after, qty_after,
            care_type, care_date_str, care_amount,
        ]
        res = post_to_gas({
            "action": "SUBMIT_CAMPAIGN_ENTRY",
            "target_sheet_url": CAMPAIGN_SHEET_URL,
            "full_row": full_row,
        })
        if res.get("status") == "success":
            st.success("✅ 登録しました。")
        else:
            st.error(f"登録に失敗しました: {res.get('message')}")


def campaign_screen():
    st.markdown("#### 📊 キャンペーン集計")
    st.write("---")

    customer = _customer_search_section()
    _entry_form_section(customer)

    st.write("---")
    st.info("📊 集計（件数・金額の一覧表示）は仕様検討中です。入力されたデータをどう集計・表示するか決まり次第、ここに追加します。")
