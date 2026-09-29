"""キャンペーン集計アプリのメイン画面。
顧客コード検索、キャンペーン実績の入力フォーム、管理職チェック（承認・破棄）、
過去データの修正・破棄を実装している。
集計（承認済みデータの件数・金額などの集計表示）はまだ仕様検討中のため未実装。"""
import streamlit as st
import pandas as pd
from datetime import date, datetime

from views.common import lookup_customer, post_to_gas, read_csv_cached, BRANCH_CUSTOMER_CSV, CAMPAIGN_SHEET_URL, CAMPAIGN_SHEET_CSV, JST

CATEGORIES = ["きれいBOX", "セリング", "増加・切替", "ケアサービス"]
CARE_TYPES = ["SM", "TMX", "MM", "その他"]

SELLING_ROWS = 5   # セリングの入力行数
INCREASE_ROWS = 5  # 増加・切替＞増加の入力行数

# 💡 登録成功後にキャンペーン実績入力欄をクリアするために消すキー一覧
#    （顧客コード検索欄・検索結果は残す＝同じ顧客に続けて別カテゴリを登録しやすくするため）。
_ENTRY_FORM_KEYS = (
    ["camp_category", "camp_kb_sales", "camp_kb_price"]
    + [f"camp_sl_{field}_{i}" for i in range(SELLING_ROWS) for field in ("code", "sales", "price")]
    + ["camp_ic_sub"]
    + [f"camp_ic_{field}_{i}" for i in range(INCREASE_ROWS) for field in ("code", "cycle", "price", "qty")]
    + [
        "camp_ic_before_code", "camp_ic_before_price", "camp_ic_before_qty",
        "camp_ic_after_code", "camp_ic_after_price", "camp_ic_after_qty",
        "camp_care_type", "camp_care_content", "camp_care_date", "camp_care_amount",
    ]
)

# 💡 保存先シートの列（0始まり）。カテゴリごとに使うフィールドが異なるため、
#    全カテゴリ分の列を持つ1枚のシートに、該当しない列は空欄のまま書き込む
#    （kensakuの各モードと同じ考え方）。セリングと増加・切替＞増加は、それぞれ
#    最大5行（商品5件分）まで入力できるようにしている。
# 0 タイムスタンプ, 1 申請者, 2 拠点, 3 エリア, 4 顧客コード, 5 顧客名, 6 加盟店名, 7 加盟店コード, 8 カテゴリ,
# 9 きれいBOX 販売数, 10 単価,
# 11〜25 セリング 商品①〜⑤（1商品あたり3列＝商品記号/販売数/単価）,
# 26〜45 増加 商品①〜⑤（1商品あたり4列＝商品記号/サイクル/単価/数量）,
# 46 切替 変更前商品, 47 変更前単価, 48 変更前数量, 49 変更後商品, 50 変更後単価, 51 変更後数量,
# 52 ケア種別, 53 サービス内容, 54 実施日, 55 金額,
# 56 ステータス（申請中／承認済み／破棄）, 57 処理者, 58 処理日時, 59 備考・破棄理由
STATUS_COL = 56
APPROVER_COL = 57
APPROVE_TIME_COL = 58
COMMENT_COL = 59

# 💡 管理職チェックタブを表示できる権限（ユーザーマスターF列、kensakuと同じ値を流用）。
#    権限0＝全権限（全拠点の申請を確認可）、権限1＝拠点の管理職（自分の拠点の申請のみ確認可）。
#    それ以外の権限は入力タブのみで、管理職チェックタブ自体が表示されない。
MANAGER_ROLES = {"0", "1"}
ALL_BRANCH_ROLES = {"0"}


def _get_current_role():
    role = str(st.session_state.get("user_role", "")).strip()
    if role.endswith(".0"):
        role = role[:-2]
    return role


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _fmt_amount(v):
    """金額表示用（整数円に丸めてカンマ区切り）。0円は空欄にする（未入力行を目立たせないため）。"""
    if not v:
        return ""
    return f"{round(v):,}"


def _parse_date(s):
    try:
        return datetime.strptime(str(s).strip(), "%Y/%m/%d").date()
    except (TypeError, ValueError):
        return date.today()


def _customer_search_section():
    st.write("**🔍 顧客コード検索**")
    col_input, col_btn = st.columns([4, 1])
    cust_code = col_input.text_input("顧客コード", key="camp_cust_code")
    btn_search = col_btn.button("🔍 検索", use_container_width=True)

    if btn_search:
        if not cust_code.strip():
            st.warning("顧客コードを入力してください。")
        elif str(st.session_state.get("user_branch", "")).strip() not in BRANCH_CUSTOMER_CSV:
            st.error(
                f"⚠️ 拠点「{st.session_state.get('user_branch', '(未設定)')}」に対応する顧客データが"
                "設定されていません。管理者にお問い合わせください。"
            )
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
    sales_count = unit_price = ""
    selling_items = [("", "", "")] * SELLING_ROWS
    increase_items = [("", "", "", "")] * INCREASE_ROWS
    product_before = price_before = qty_before = ""
    product_after = price_after = qty_after = ""
    care_type = care_content = care_date_str = care_amount = ""

    if category == "きれいBOX":
        c1, c2, c3 = st.columns(3)
        sales_count = c1.text_input("販売数", key="camp_kb_sales")
        unit_price = c2.text_input("単価", key="camp_kb_price")
        kb_amount = _to_float(sales_count) * _to_float(unit_price)
        c3.metric("金額", f"{_fmt_amount(kb_amount) or 0} 円")

        st.write(f"**総合計：{_fmt_amount(kb_amount) or 0} 円**")

    elif category == "セリング":
        rows = []
        sl_total = 0.0
        for i in range(SELLING_ROWS):
            st.caption(f"商品 {i + 1}")
            c1, c2, c3, c4 = st.columns(4)
            code = c1.text_input("商品記号", key=f"camp_sl_code_{i}")
            sales = c2.text_input("販売数", key=f"camp_sl_sales_{i}")
            price = c3.text_input("単価", key=f"camp_sl_price_{i}")
            amount = _to_float(sales) * _to_float(price)
            sl_total += amount
            c4.metric("金額", f"{_fmt_amount(amount) or 0} 円")
            rows.append((code, sales, price))
        selling_items = rows

        st.write(f"**総合計：{_fmt_amount(sl_total) or 0} 円**")

    elif category == "増加・切替":
        sub_category = st.radio("増加 / 切替", ["増加", "切替"], horizontal=True, key="camp_ic_sub")
        if sub_category == "増加":
            rows = []
            ic_total = 0.0
            for i in range(INCREASE_ROWS):
                st.caption(f"商品 {i + 1}")
                c1, c2, c3, c4, c5 = st.columns(5)
                code = c1.text_input("商品記号", key=f"camp_ic_code_{i}")
                cycle = c2.text_input("サイクル", key=f"camp_ic_cycle_{i}")
                price = c3.text_input("単価", key=f"camp_ic_price_{i}")
                qty = c4.text_input("数量", key=f"camp_ic_qty_{i}")
                # 💡 増加の金額＝商品単価×(4÷サイクル)×数量（サイクルが未入力・0の場合は計算しない）
                cycle_f = _to_float(cycle)
                amount = _to_float(price) * (4 / cycle_f) * _to_float(qty) if cycle_f else 0.0
                ic_total += amount
                c5.metric("金額", f"{_fmt_amount(amount) or 0} 円")
                rows.append((code, cycle, price, qty))
            increase_items = rows

            st.write(f"**総合計：{_fmt_amount(ic_total) or 0} 円**")
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
        c1, c2, c3, c4 = st.columns(4)
        care_type = c1.selectbox("種別", CARE_TYPES, key="camp_care_type")
        care_content = c2.text_input("サービス内容", key="camp_care_content")
        care_date = c3.date_input("実施日", value=date.today(), key="camp_care_date")
        care_date_str = care_date.strftime("%Y/%m/%d") if care_date else ""
        care_amount = c4.text_input("金額", key="camp_care_amount")

    if st.button("✅ 登録する", type="primary", use_container_width=True):
        if not customer:
            st.error("⚠️ 先に顧客コードを検索してください。")
            return

        selling_flat = [v for item in selling_items for v in item]
        increase_flat = [v for item in increase_items for v in item]

        full_row = [
            datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S"),
            st.session_state.get("user_name", ""),
            st.session_state.get("user_branch", ""),
            st.session_state.get("user_area", ""),
            customer["cust_code"], customer["cust_name"],
            customer["store_name"], customer["store_code"],
            category,
            sales_count, unit_price,
        ] + selling_flat + increase_flat + [
            product_before, price_before, qty_before,
            product_after, price_after, qty_after,
            care_type, care_content, care_date_str, care_amount,
            "申請中", "", "", "",
        ]
        res = post_to_gas({
            "action": "SUBMIT_CAMPAIGN_ENTRY",
            "target_sheet_url": CAMPAIGN_SHEET_URL,
            "full_row": full_row,
        })
        if res.get("status") == "success":
            for k in _ENTRY_FORM_KEYS:
                st.session_state.pop(k, None)
            st.toast("✅ 登録しました。管理職チェック待ちです。", icon="✅")
            st.rerun()
        else:
            st.error(f"登録に失敗しました: {res.get('message')}")


def _val(row, idx):
    return str(row.iloc[idx]) if len(row) > idx and pd.notna(row.iloc[idx]) else ""


def _render_entry_readonly(row, key_prefix):
    """1件分のキャンペーン実績を、カテゴリに応じた項目だけ読み取り専用で表示する。"""
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.text_input("拠点", value=_val(row, 2), disabled=True, key=f"{key_prefix}_branch")
    c2.text_input("エリア", value=_val(row, 3), disabled=True, key=f"{key_prefix}_area")
    c3.text_input("顧客コード", value=_val(row, 4), disabled=True, key=f"{key_prefix}_ccode")
    c4.text_input("顧客名", value=_val(row, 5), disabled=True, key=f"{key_prefix}_cname")
    c5.text_input("加盟店名", value=_val(row, 6), disabled=True, key=f"{key_prefix}_sname")
    c6.text_input("加盟店コード", value=_val(row, 7), disabled=True, key=f"{key_prefix}_scode")

    category = _val(row, 8)
    st.text_input("カテゴリ", value=category, disabled=True, key=f"{key_prefix}_category")

    if category == "きれいBOX":
        c1, c2 = st.columns(2)
        c1.text_input("販売数", value=_val(row, 9), disabled=True, key=f"{key_prefix}_kb_sales")
        c2.text_input("単価", value=_val(row, 10), disabled=True, key=f"{key_prefix}_kb_price")

    elif category == "セリング":
        for i in range(SELLING_ROWS):
            base = 11 + i * 3
            code = _val(row, base)
            if not code.strip():
                continue
            c1, c2, c3 = st.columns(3)
            c1.text_input(f"商品記号 {i+1}", value=code, disabled=True, key=f"{key_prefix}_sl_code_{i}")
            c2.text_input(f"販売数 {i+1}", value=_val(row, base + 1), disabled=True, key=f"{key_prefix}_sl_sales_{i}")
            c3.text_input(f"単価 {i+1}", value=_val(row, base + 2), disabled=True, key=f"{key_prefix}_sl_price_{i}")

    elif category == "増加・切替":
        has_increase = any(_val(row, 26 + i * 4).strip() for i in range(INCREASE_ROWS))
        if has_increase:
            for i in range(INCREASE_ROWS):
                base = 26 + i * 4
                code = _val(row, base)
                if not code.strip():
                    continue
                c1, c2, c3, c4 = st.columns(4)
                c1.text_input(f"商品記号 {i+1}", value=code, disabled=True, key=f"{key_prefix}_ic_code_{i}")
                c2.text_input(f"サイクル {i+1}", value=_val(row, base + 1), disabled=True, key=f"{key_prefix}_ic_cycle_{i}")
                c3.text_input(f"単価 {i+1}", value=_val(row, base + 2), disabled=True, key=f"{key_prefix}_ic_price_{i}")
                c4.text_input(f"数量 {i+1}", value=_val(row, base + 3), disabled=True, key=f"{key_prefix}_ic_qty_{i}")
        else:
            st.caption("変更前")
            b1, b2, b3 = st.columns(3)
            b1.text_input("変更前商品", value=_val(row, 46), disabled=True, key=f"{key_prefix}_before_code")
            b2.text_input("単価", value=_val(row, 47), disabled=True, key=f"{key_prefix}_before_price")
            b3.text_input("数量", value=_val(row, 48), disabled=True, key=f"{key_prefix}_before_qty")
            st.caption("変更後")
            a1, a2, a3 = st.columns(3)
            a1.text_input("変更後商品", value=_val(row, 49), disabled=True, key=f"{key_prefix}_after_code")
            a2.text_input("単価", value=_val(row, 50), disabled=True, key=f"{key_prefix}_after_price")
            a3.text_input("数量", value=_val(row, 51), disabled=True, key=f"{key_prefix}_after_qty")

    elif category == "ケアサービス":
        c1, c2, c3, c4 = st.columns(4)
        c1.text_input("種別", value=_val(row, 52), disabled=True, key=f"{key_prefix}_care_type")
        c2.text_input("サービス内容", value=_val(row, 53), disabled=True, key=f"{key_prefix}_care_content")
        c3.text_input("実施日", value=_val(row, 54), disabled=True, key=f"{key_prefix}_care_date")
        c4.text_input("金額", value=_val(row, 55), disabled=True, key=f"{key_prefix}_care_amount")


def _render_entry_edit_form(row, key_prefix):
    """1件分のキャンペーン実績を、カテゴリに応じた項目だけ編集可能な状態で表示する。
    カテゴリ自体は変更できない（カテゴリを間違えた場合は破棄して入力し直してもらう）。
    戻り値は、行全体のコピーにカテゴリ該当列だけ編集後の値を反映した更新行
    （GASへの上書き保存にそのまま使える）。"""
    category = _val(row, 8)
    st.text_input("カテゴリ（変更不可）", value=category, disabled=True, key=f"{key_prefix}_category")

    updated_row = [
        ("" if pd.isna(row.iloc[i]) else str(row.iloc[i])) if i < len(row) else ""
        for i in range(max(len(row), COMMENT_COL + 1))
    ]

    if category == "きれいBOX":
        c1, c2 = st.columns(2)
        sales = c1.text_input("販売数", value=_val(row, 9), key=f"{key_prefix}_kb_sales")
        price = c2.text_input("単価", value=_val(row, 10), key=f"{key_prefix}_kb_price")
        updated_row[9] = sales
        updated_row[10] = price

    elif category == "セリング":
        for i in range(SELLING_ROWS):
            base = 11 + i * 3
            st.caption(f"商品 {i + 1}")
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("商品記号", value=_val(row, base), key=f"{key_prefix}_sl_code_{i}")
            sales = c2.text_input("販売数", value=_val(row, base + 1), key=f"{key_prefix}_sl_sales_{i}")
            price = c3.text_input("単価", value=_val(row, base + 2), key=f"{key_prefix}_sl_price_{i}")
            updated_row[base] = code
            updated_row[base + 1] = sales
            updated_row[base + 2] = price

    elif category == "増加・切替":
        has_increase = any(_val(row, 26 + i * 4).strip() for i in range(INCREASE_ROWS))
        if has_increase:
            for i in range(INCREASE_ROWS):
                base = 26 + i * 4
                st.caption(f"商品 {i + 1}")
                c1, c2, c3, c4 = st.columns(4)
                code = c1.text_input("商品記号", value=_val(row, base), key=f"{key_prefix}_ic_code_{i}")
                cycle = c2.text_input("サイクル", value=_val(row, base + 1), key=f"{key_prefix}_ic_cycle_{i}")
                price = c3.text_input("単価", value=_val(row, base + 2), key=f"{key_prefix}_ic_price_{i}")
                qty = c4.text_input("数量", value=_val(row, base + 3), key=f"{key_prefix}_ic_qty_{i}")
                updated_row[base] = code
                updated_row[base + 1] = cycle
                updated_row[base + 2] = price
                updated_row[base + 3] = qty
        else:
            st.caption("変更前")
            b1, b2, b3 = st.columns(3)
            bc = b1.text_input("変更前商品", value=_val(row, 46), key=f"{key_prefix}_before_code")
            bp = b2.text_input("単価", value=_val(row, 47), key=f"{key_prefix}_before_price")
            bq = b3.text_input("数量", value=_val(row, 48), key=f"{key_prefix}_before_qty")
            st.caption("変更後")
            a1, a2, a3 = st.columns(3)
            ac = a1.text_input("変更後商品", value=_val(row, 49), key=f"{key_prefix}_after_code")
            ap = a2.text_input("単価", value=_val(row, 50), key=f"{key_prefix}_after_price")
            aq = a3.text_input("数量", value=_val(row, 51), key=f"{key_prefix}_after_qty")
            updated_row[46] = bc
            updated_row[47] = bp
            updated_row[48] = bq
            updated_row[49] = ac
            updated_row[50] = ap
            updated_row[51] = aq

    elif category == "ケアサービス":
        c1, c2, c3, c4 = st.columns(4)
        cur_type = _val(row, 52)
        type_index = CARE_TYPES.index(cur_type) if cur_type in CARE_TYPES else 0
        care_type = c1.selectbox("種別", CARE_TYPES, index=type_index, key=f"{key_prefix}_care_type")
        care_content = c2.text_input("サービス内容", value=_val(row, 53), key=f"{key_prefix}_care_content")
        care_date = c3.date_input("実施日", value=_parse_date(_val(row, 54)), key=f"{key_prefix}_care_date")
        care_amount = c4.text_input("金額", value=_val(row, 55), key=f"{key_prefix}_care_amount")
        updated_row[52] = care_type
        updated_row[53] = care_content
        updated_row[54] = care_date.strftime("%Y/%m/%d") if care_date else ""
        updated_row[55] = care_amount

    return updated_row


def _manager_check_section():
    st.write("**🔍 管理職チェック**")
    st.caption("申請中のキャンペーン実績を確認し、承認または破棄できます。")

    if st.button("🔄 最新の申請を読み込む", key="camp_check_reload"):
        read_csv_cached.clear()

    try:
        # 💡 1行目は見出し行なのでheader=0でスキップする（header=Noneのままだと
        #    見出し行までデータ扱いになり、承認時に書き込む行番号が1つずれてしまう）。
        df = read_csv_cached(CAMPAIGN_SHEET_CSV, header=0)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return

    if df.empty or len(df.columns) <= STATUS_COL:
        st.info("現在、申請データはありません。")
        return

    pending_df = df[df.iloc[:, STATUS_COL].astype(str).str.strip() == "申請中"]

    # 💡 権限0（全権限）以外は、自分の拠点（C列）の申請だけを確認・承認できる。
    if _get_current_role() not in ALL_BRANCH_ROLES:
        my_branch = str(st.session_state.get("user_branch", "")).strip()
        pending_df = pending_df[pending_df.iloc[:, 2].astype(str).str.strip() == my_branch]

    if pending_df.empty:
        st.info("現在、承認待ちの申請はありません。")
        return

    st.warning(f"承認待ち: **{len(pending_df)} 件**")

    for idx, row in pending_df.iloc[::-1].iterrows():
        row_id = idx + 2  # 見出し行(1行目)を含めた実際のシート行番号
        applicant = _val(row, 1)
        cust_name = _val(row, 5)
        category = _val(row, 8)
        timestamp = _val(row, 0)

        with st.expander(f"⏳ 【{category}】{cust_name} | 申請者: {applicant} | {timestamp}"):
            _render_entry_readonly(row, key_prefix=f"chk_{row_id}")

            comment = st.text_input("備考（破棄する場合は任意で理由を記入できます）", key=f"chk_reason_{row_id}")
            col_approve, col_discard = st.columns(2)

            if col_approve.button("✅ 承認", key=f"chk_approve_{row_id}", type="primary", use_container_width=True):
                _update_status(row, row_id, "承認済み", comment)

            if col_discard.button("🗑 破棄", key=f"chk_discard_{row_id}", use_container_width=True):
                _update_status(row, row_id, "破棄", comment)


def _update_status(row, row_id, status, comment):
    updated_row = [
        ("" if pd.isna(row.iloc[i]) else str(row.iloc[i])) if i < len(row) else ""
        for i in range(max(len(row), COMMENT_COL + 1))
    ]
    updated_row[STATUS_COL] = status
    updated_row[APPROVER_COL] = st.session_state.get("user_name", "")
    updated_row[APPROVE_TIME_COL] = datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S")
    updated_row[COMMENT_COL] = comment

    res = post_to_gas({
        "action": "UPDATE_CAMPAIGN_STATUS",
        "target_sheet_url": CAMPAIGN_SHEET_URL,
        "row_index": row_id,
        "updated_row": updated_row,
    })
    if res.get("status") == "success":
        st.toast(f"{status}にしました。", icon="✅")
        read_csv_cached.clear()
        st.rerun()
    else:
        st.error(f"更新に失敗しました: {res.get('message')}")


def _save_entry_edit(row_id, updated_row):
    res = post_to_gas({
        "action": "UPDATE_CAMPAIGN_STATUS",
        "target_sheet_url": CAMPAIGN_SHEET_URL,
        "row_index": row_id,
        "updated_row": updated_row,
    })
    if res.get("status") == "success":
        st.toast("修正を保存しました。", icon="✅")
        read_csv_cached.clear()
        st.rerun()
    else:
        st.error(f"保存に失敗しました: {res.get('message')}")


def _past_data_section():
    st.write("**📋 過去データの修正・破棄**")
    st.caption("承認済み・破棄済みも含めた過去の申請を検索し、内容の修正や破棄ができます（申請中のものは「管理職チェック」タブで対応してください）。")

    if st.button("🔄 最新のデータを読み込む", key="camp_past_reload"):
        read_csv_cached.clear()

    try:
        df = read_csv_cached(CAMPAIGN_SHEET_CSV, header=0)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return

    if df.empty or len(df.columns) <= STATUS_COL:
        st.info("データがありません。")
        return

    past_df = df[df.iloc[:, STATUS_COL].astype(str).str.strip() != "申請中"]

    # 💡 権限0（全権限）以外は、自分の拠点（C列）のデータだけを確認・修正できる。
    if _get_current_role() not in ALL_BRANCH_ROLES:
        my_branch = str(st.session_state.get("user_branch", "")).strip()
        past_df = past_df[past_df.iloc[:, 2].astype(str).str.strip() == my_branch]

    if past_df.empty:
        st.info("該当するデータがありません。")
        return

    search = st.text_input("顧客名・申請者名で絞り込み（任意）", key="camp_past_search")
    if search.strip():
        mask = (
            past_df.iloc[:, 5].astype(str).str.contains(search.strip(), na=False)
            | past_df.iloc[:, 1].astype(str).str.contains(search.strip(), na=False)
        )
        past_df = past_df[mask]

    if past_df.empty:
        st.info("該当するデータが見つかりませんでした。")
        return

    shown_df = past_df.iloc[::-1].head(50)
    st.caption(f"該当件数: {len(past_df)} 件（新しい順に最大50件を表示）")

    for idx, row in shown_df.iterrows():
        row_id = idx + 2  # 見出し行(1行目)を含めた実際のシート行番号
        applicant = _val(row, 1)
        cust_name = _val(row, 5)
        category = _val(row, 8)
        timestamp = _val(row, 0)
        status = _val(row, 56)
        icon = {"承認済み": "✅", "破棄": "🗑"}.get(status, "・")

        with st.expander(f"{icon} 【{status}】【{category}】{cust_name} | 申請者: {applicant} | {timestamp}"):
            edit_key = f"past_editing_{row_id}"

            if st.session_state.get(edit_key):
                updated_row = _render_entry_edit_form(row, key_prefix=f"pastedit_{row_id}")
                col_save, col_cancel = st.columns(2)

                if col_save.button("💾 保存", key=f"past_save_{row_id}", type="primary", use_container_width=True):
                    _save_entry_edit(row_id, updated_row)

                if col_cancel.button("✖️ キャンセル", key=f"past_cancel_{row_id}", use_container_width=True):
                    st.session_state.pop(edit_key, None)
                    st.rerun()

            else:
                _render_entry_readonly(row, key_prefix=f"past_{row_id}")
                st.write(f"**現在のステータス：** {status}　**処理者：** {_val(row, 57)}　**処理日時：** {_val(row, 58)}")
                comment = _val(row, 59)
                if comment.strip():
                    st.caption(f"備考: {comment}")

                col_edit, col_discard = st.columns(2)
                if col_edit.button("✏️ 修正する", key=f"past_edit_{row_id}", use_container_width=True):
                    st.session_state[edit_key] = True
                    st.rerun()

                if col_discard.button("🗑 破棄する", key=f"past_discard_{row_id}", use_container_width=True):
                    _update_status(row, row_id, "破棄", comment)


def campaign_screen():
    # 💡 disabled（読み取り専用）入力欄の文字が薄くて読みにくいのを解消
    #    （kensakuの他画面と同じCSS対策：状態を問わず入力欄の文字色を強制する）
    st.markdown("""
        <style>
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input {
            -webkit-text-fill-color: #31333F !important;
            color: #31333F !important;
            opacity: 1 !important;
        }
        input:disabled, input:read-only, input[aria-disabled="true"],
        textarea:disabled, textarea:read-only, textarea[aria-disabled="true"] {
            -webkit-text-fill-color: #31333F !important;
            color: #31333F !important;
            opacity: 1 !important;
        }
        div[data-testid="stTextInput"], div[data-testid="stTextArea"], div[data-testid="stSelectbox"],
        div[data-testid="stTextInput"] label, div[data-testid="stTextArea"] label, div[data-testid="stSelectbox"] label,
        div[data-testid="stWidgetLabel"], div[data-testid="stWidgetLabel"] p, div[data-testid="stWidgetLabel"] label {
            opacity: 1 !important;
            color: #31333F !important;
            -webkit-text-fill-color: #31333F !important;
        }
        div[data-testid="stSelectbox"] div[aria-disabled="true"],
        div[data-testid="stSelectbox"] div[aria-disabled="true"] * {
            opacity: 1 !important;
            color: #31333F !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("#### 📊 キャンペーン集計")
    st.write("---")

    if _get_current_role() in MANAGER_ROLES:
        tab1, tab2, tab3 = st.tabs(["📝 入力", "🔍 管理職チェック", "📋 過去データ修正"])
        with tab1:
            customer = _customer_search_section()
            _entry_form_section(customer)
        with tab2:
            _manager_check_section()
        with tab3:
            _past_data_section()
    else:
        customer = _customer_search_section()
        _entry_form_section(customer)

    st.write("---")
    st.info("📊 集計（承認済みデータの件数・金額の一覧表示）は仕様検討中です。決まり次第、ここに追加します。")
