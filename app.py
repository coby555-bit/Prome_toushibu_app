import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import altair as alt
import re
from datetime import datetime
from google.oauth2.service_account import Credentials

# ページの基本設定
st.set_page_config(page_title="投資部 100万円投資レース", layout="wide")
st.title("📊 投資部 100万円投資レース")

# 💡 Google認証のキャッシュ処理
@st.cache_resource
def get_spreadsheet():
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(credentials)
    SPREADSHEET_ID = '1cDErL19Flvjk1EuES0RggRbzI5_wHK2VGhp7A-FQMtA'
    return gc.open_by_key(SPREADSHEET_ID)

# 💡 最新株価 ＆ 前日終値の一括取得関数（10分キャッシュ）
@st.cache_data(ttl=600)
def fetch_stock_details(symbols):
    detail_map = {}
    if not symbols:
        return detail_map
    
    yf_symbols = [f"{s}.T" if str(s).isdigit() and len(str(s)) == 4 else str(s) for s in symbols]
    
    try:
        tickers = yf.Tickers(" ".join(yf_symbols))
        for orig_symbol, yf_symbol in zip(symbols, yf_symbols):
            try:
                hist = tickers.tickers[yf_symbol].history(period="5d")
                if not hist.empty and len(hist) >= 1:
                    current_price = hist["Close"].iloc[-1]
                    prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else current_price
                    detail_map[str(orig_symbol)] = {
                        "current": float(current_price),
                        "prev_close": float(prev_close)
                    }
            except Exception:
                pass
    except Exception as e:
        st.warning(f"株価取得時に一部エラーが発生しました: {e}")
        
    return detail_map

# 💡 銘柄コードから会社名を自動取得する関数
@st.cache_data(ttl=3600)
def fetch_company_name(code):
    clean_code = re.sub(r'[^\d]', '', str(code))
    if len(clean_code) == 4:
        try:
            ticker = yf.Ticker(f"{clean_code}.T")
            info = ticker.info
            name = info.get('longName') or info.get('shortName') or info.get('displayTitle')
            if name:
                # 日本語の社名が英語で返ってきた場合などの簡易クレンジング
                return name.replace('Corporation', '').replace('Co., Ltd.', '').strip()
        except Exception:
            pass
    return ""

# 💡 数値クレンジング用の補助関数
def clean_number(val):
    if val is None:
        return 0.0
    s = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

# 💡 プラス（緑）/ マイナス（赤）/ ±0（灰色）の装飾用HTML関数
def color_text_html(val, is_currency=True, is_percent=False):
    try:
        f_val = float(val)
        if is_currency:
            text = "¥" + "{:+,.0f}".format(f_val)
        elif is_percent:
            text = "{:+.2f}%".format(f_val)
        else:
            text = "{:+,.0f}".format(f_val)
            
        if abs(f_val) < 0.0001:
            if is_currency: text = "¥0"
            elif is_percent: text = "0.00%"
            return f'<span style="color: #6c757d; font-weight: bold;">{text}</span>'
        elif f_val > 0:
            return f'<span style="color: #28a745; font-weight: bold;">{text}</span>'
        else:
            return f'<span style="color: #dc3545; font-weight: bold;">{text}</span>'
    except (ValueError, TypeError):
        return str(val)

# 💡 メンバー個人のリアルタイム計算を行う関数
def calculate_member_state(sh, member_name):
    INITIAL_CAPITAL = 1000000
    try:
        worksheet = sh.worksheet(member_name)
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return None
            
        header = all_values[0]
        rows = all_values[1:]
        df = pd.DataFrame(rows)
        columns = [h if h.strip() != "" else f"列_{i+1}" for i, h in enumerate(header)]
        df.columns = columns
        
        df_trade = df[df.iloc[:, 0] != ""].copy()
        if df_trade.empty:
            return None

        realized_pnl_pre_tax = 0.0
        holdings = {}
        
        for _, row in df_trade.iterrows():
            trade_type = str(row.iloc[1]).strip()
            name = str(row.iloc[2]).strip()
            raw_code = str(row.iloc[3]).strip().replace('.0', '')
            code = re.sub(r'^\d{4}$', lambda m: m.group(0), raw_code)
            
            shares = int(clean_number(row.iloc[4]))
            price = clean_number(row.iloc[5])
            
            if not code or shares <= 0 or price <= 0:
                continue
                
            if code not in holdings:
                holdings[code] = {"name": name, "shares": 0, "total_cost": 0.0}
                
            if trade_type == "買い":
                holdings[code]["shares"] += shares
                holdings[code]["total_cost"] += shares * price
                holdings[code]["name"] = name
            elif trade_type == "売り":
                if holdings[code]["shares"] > 0:
                    avg_cost = holdings[code]["total_cost"] / holdings[code]["shares"]
                    trade_profit = (price - avg_cost) * shares
                    realized_pnl_pre_tax += trade_profit
                    
                    holdings[code]["shares"] = max(0, holdings[code]["shares"] - shares)
                    holdings[code]["total_cost"] = max(0.0, holdings[code]["total_cost"] - (avg_cost * shares))

        tax = int(realized_pnl_pre_tax * 0.20315) if realized_pnl_pre_tax > 0 else 0
        realized_pnl_post_tax = realized_pnl_pre_tax - tax
        
        current_stock_cost = sum([data["total_cost"] for data in holdings.values() if data["shares"] > 0])
        cash_balance = INITIAL_CAPITAL + realized_pnl_post_tax - current_stock_cost
        
        active_codes = [code for code, data in holdings.items() if data["shares"] > 0]
        
        return {
            "df_trade": df_trade,
            "holdings": holdings,
            "active_codes": active_codes,
            "cash_balance": cash_balance,
            "realized_pnl_post_tax": realized_pnl_post_tax,
            "current_stock_cost": current_stock_cost
        }
    except Exception:
        return None

# 💡 ルール更新用モーダルダイアログ
@st.dialog("✏️ 投資部ルールの更新")
def open_rule_edit_dialog(sh, current_text):
    with st.form("rule_edit_form_dialog"):
        new_rule_text = st.text_area("新しいルール本文 (改行で箇条書きになります)", value=current_text, height=180)
        rule_note = st.text_input("更新メモ", value="ルール更新")
        submit_rule = st.form_submit_button("保存する", type="primary")
        
        if submit_rule:
            if new_rule_text.strip():
                now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
                rule_sheet = sh.worksheet('RuleData')
                rule_sheet.append_row([now_str, new_rule_text, rule_note])
                st.success("ルールを更新しました！")
                st.rerun()
            else:
                st.error("ルール本文を入力してください。")

# 💡 取引入力用モーダルダイアログ (会社名自動取得機能付き)
@st.dialog("📝 取引の新規入力")
def open_trade_input_dialog(sh, default_member, members):
    input_member = st.selectbox("メンバー", members, index=members.index(default_member) if default_member in members else 0)
    input_type = st.selectbox("売買種別", ["買い", "売り"])
    
    input_code = st.text_input("銘柄コード (4桁)", placeholder="例: 7203", key="dlg_code")
    
    # 自動社名取得
    auto_name = ""
    clean_code = re.sub(r'[^\d]', '', str(input_code))
    if len(clean_code) == 4:
        fetched = fetch_company_name(clean_code)
        if fetched:
            auto_name = fetched
            st.caption(f"💡 自動検出された社名: **{fetched}**")
            
    input_name = st.text_input("銘柄名 / 会社名", value=auto_name, placeholder="例: トヨタ自動車", key="dlg_name")
    input_shares = st.number_input("株数", min_value=1, value=100, step=100)
    input_price = st.number_input("取引単価 (円)", min_value=1.0, value=1000.0, step=10.0)
    input_date = st.date_input("取引日付", datetime.now())
    
    if st.button("🚀 取引を登録する", type="primary"):
        if not clean_code or len(clean_code) < 4:
            st.error("正しい4桁の銘柄コードを入力してください。")
        elif not input_name.strip():
            st.error("銘柄名を入力してください。")
        else:
            try:
                target_sheet = sh.worksheet(input_member)
                formatted_date = input_date.strftime("%Y/%m/%d")
                total_amount = input_shares * input_price
                
                row_data = [
                    formatted_date,
                    input_type,
                    input_name.strip(),
                    clean_code,
                    input_shares,
                    input_price,
                    total_amount
                ]
                target_sheet.append_row(row_data)
                st.success(f"✅ {input_member} に {input_name} ({input_type}) を追加しました！")
                st.rerun()
            except Exception as e:
                st.error(f"登録エラー: {e}")

# システム用シート一覧
SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData', 'PredictionHistory', 'ログ', '設定']

try:
    sh = get_spreadsheet()
    all_worksheets = [ws.title for ws in sh.worksheets()]
    members = [name for name in all_worksheets if name not in SYSTEM_SHEETS and name.strip() != '']

    # =========================================================================
    # 投資部ルール ＆ 更新履歴セクション
    # =========================================================================
    with st.expander("📋 投資部ルール ＆ 更新履歴を表示", expanded=False):
        try:
            try:
                rule_sheet = sh.worksheet('RuleData')
            except Exception:
                rule_sheet = sh.add_worksheet(title='RuleData', rows=100, cols=3)
                rule_sheet.append_row(['日時', '本文', '更新メモ'])
                rule_sheet.append_row([
                    '2026/06/01 00:00',
                    '利益の割合でご馳走の支払い率を決める\nお店は一位の人が決め、一万円以上のコースとする\n配当金と優待は入れない\n国内個別株のみ',
                    '初期ルール制定'
                ])

            rule_values = rule_sheet.get_all_values()
            
            if len(rule_values) > 1:
                raw_rule_rows = [r[:3] + [''] * (3 - len(r[:3])) for r in rule_values[1:]]
                df_rules = pd.DataFrame(raw_rule_rows, columns=['日時', '本文', '更新メモ'])
                df_rules = df_rules[df_rules['日時'] != ''].copy()
                
                if not df_rules.empty:
                    latest_rule = df_rules.iloc[-1]
                    
                    col_r1, col_r2 = st.columns([3, 1])
                    with col_r1:
                        st.subheader("📜 最新の投資部ルール")
                        st.caption(f"最終更新: {latest_rule['日時']}")
                        
                        # 💡 ルール本文を箇条書きに変換して表示
                        lines = [line.strip() for line in latest_rule['本文'].split('\n') if line.strip()]
                        bullet_list = "\n".join([f"* {line}" for line in lines])
                        st.markdown(bullet_list)
                        
                    with col_r2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("✏️ ルールを更新する", type="secondary"):
                            open_rule_edit_dialog(sh, latest_rule['本文'])
                            
                    st.markdown("---")
                    st.write("📜 **過去のルール更新日時一覧**")
                    # 💡 日時のみの一覧を表示
                    df_history_dates = df_rules[['日時']].iloc[::-1].reset_index(drop=True)
                    st.dataframe(df_history_dates, use_container_width=True)
                else:
                    st.info("RuleDataに有効なルール履歴がありません。")
            else:
                st.info("RuleDataにデータがありません。")
        except Exception as e:
            st.error(f"ルールデータ読み込みエラー: {e}")

    # =========================================================================
    # メインタブの作成
    # =========================================================================
    tab_race, tab_personal = st.tabs(["🏆 実績 ＆ 全体ランキング", "👤 個人別詳細"])

    # =========================================================================
    # TAB 1: 実績 ＆ 全体ランキング
    # =========================================================================
    with tab_race:
        st.header("📉 資産推移 ＆ 全体ランキング")
        
        try:
            log_sheet = sh.worksheet('DailyLog')
            log_values = log_sheet.get_all_values()
            
            if len(log_values) > 1:
                df_log = pd.DataFrame(log_values[1:], columns=log_values[0])
                df_log = df_log[~df_log['メンバー'].isin(SYSTEM_SHEETS)]
                df_log['総資産'] = pd.to_numeric(df_log['総資産'], errors='coerce')
                df_log['利益率'] = pd.to_numeric(df_log['利益率'], errors='coerce')
                df_log = df_log.dropna(subset=['日付', 'メンバー', '総資産'])
                
                # --- 1. 資産推移チャート ---
                st.subheader("📈 全員の資産推移グラフ")
                
                df_log['総資産(フォーマット)'] = df_log['総資産'].apply(lambda x: f"¥{int(x):,}")
                df_pivot_log = df_log.pivot(index='日付', columns='メンバー', values='総資産(フォーマット)').reset_index()
                
                chart_base = alt.Chart(df_log).encode(
                    x=alt.X('日付:N', title='日付'),
                    y=alt.Y('総資産:Q', title='総資産 (円)', scale=alt.Scale(zero=False)),
                    color=alt.Color('メンバー:N', title='メンバー')
                )
                
                lines = chart_base.mark_line(strokeWidth=3)
                nearest = alt.selection_point(nearest=True, on='pointerover', fields=['日付'], empty=False)
                tooltip_cols = [alt.Tooltip('日付:N')] + [alt.Tooltip(f'{m}:N', title=m) for m in members if m in df_pivot_log.columns]
                
                selectors = alt.Chart(df_pivot_log).mark_rect().encode(
                    x='日付:N',
                    opacity=alt.value(0),
                    tooltip=tooltip_cols
                ).add_params(nearest)
                
                points = chart_base.mark_point(size=50).encode(
                    opacity=alt.condition(nearest, alt.value(1), alt.value(0))
                )
                
                rules = alt.Chart(df_pivot_log).mark_rule(color='gray', strokeDash=[2, 2]).encode(
                    x='日付:N'
                ).transform_filter(nearest)
                
                final_chart = alt.layer(lines, selectors, points, rules).properties(height=400).interactive()
                st.altair_chart(final_chart, use_container_width=True)
                
                # --- 2. 最新資産ランキング ---
                st.subheader("🏆 最新資産ランキング")
                
                all_member_states = {}
                all_active_codes = set()
                
                for m in members:
                    state = calculate_member_state(sh, m)
                    if state:
                        all_member_states[m] = state
                        all_active_codes.update(state["active_codes"])
                        
                price_details = fetch_stock_details(list(all_active_codes)) if all_active_codes else {}
                
                ranking_data = []
                for m, state in all_member_states.items():
                    total_stock_eval = 0.0
                    total_unrealized_pnl = 0.0
                    
                    for code in state["active_codes"]:
                        h = state["holdings"][code]
                        shares = h["shares"]
                        avg_price = h["total_cost"] / shares if shares > 0 else 0.0
                        info = price_details.get(str(code), {"current": avg_price, "prev_close": avg_price})
                        
                        eval_val = info["current"] * shares
                        pnl_val = eval_val - h["total_cost"]
                        
                        total_stock_eval += eval_val
                        total_unrealized_pnl += pnl_val
                        
                    total_assets = state["cash_balance"] + total_stock_eval
                    total_profit = total_assets - 1000000
                    total_profit_rate = (total_profit / 1000000) * 100
                    
                    ranking_data.append({
                        "メンバー": m,
                        "総資産数値": total_assets,
                        "総資産": "¥{:,.0f}".format(total_assets),
                        "実現損益": color_text_html(state["realized_pnl_post_tax"]),
                        "含み損益": color_text_html(total_unrealized_pnl),
                        "総損益": color_text_html(total_profit),
                        "利益率": color_text_html(total_profit_rate, is_currency=False, is_percent=True),
                        "買付余力": "¥{:,.0f}".format(state["cash_balance"])
                    })
                
                if ranking_data:
                    df_rank = pd.DataFrame(ranking_data)
                    df_rank = df_rank.sort_values(by="総資産数値", ascending=False).reset_index(drop=True)
                    
                    medal_icons = ["🥇 1位", "🥈 2位", "🥉 3位"]
                    df_rank["順位"] = [medal_icons[i] if i < 3 else f"{i+1}位" for i in range(len(df_rank))]
                    
                    display_cols = ["順位", "メンバー", "総資産", "実現損益", "含み損益", "総損益", "利益率", "買付余力"]
                    df_rank_display = df_rank[display_cols]
                    
                    st.write(df_rank_display.to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.info("DailyLogにデータがありません。")
        except Exception as e:
            st.error(f"ランキング計算エラー: {e}")

    # =========================================================================
    # TAB 2: 個人別詳細
    # =========================================================================
    with tab_personal:
        st.header("👤 個人別ポートフォリオ詳細")
        
        col_mem_select, col_btn_add = st.columns([4, 1])
        
        with col_mem_select:
            selected_member = st.radio("メンバーを選択してください", members, horizontal=True, key="personal_radio")
            
        with col_btn_add:
            st.markdown("<br>", unsafe_allow_html=True)
            # 💡 個人別タブ内に「＋ 取引を入力する」ボタンを配置
            if st.button("➕ 取引を入力する", type="primary"):
                open_trade_input_dialog(sh, selected_member, members)
        
        if selected_member:
            state = calculate_member_state(sh, selected_member)
            
            if state:
                df_trade = state["df_trade"]
                holdings = state["holdings"]
                active_codes = state["active_codes"]
                cash_balance = state["cash_balance"]
                realized_pnl_post_tax = state["realized_pnl_post_tax"]
                
                detail_map = fetch_stock_details(active_codes) if active_codes else {}
                
                total_stock_eval = 0.0
                total_unrealized_pnl = 0.0
                total_day_diff = 0.0
                
                portfolio_data = []
                
                for code in active_codes:
                    h = holdings[code]
                    shares = h["shares"]
                    avg_price = h["total_cost"] / shares if shares > 0 else 0.0
                    
                    stock_info = detail_map.get(str(code), {"current": avg_price, "prev_close": avg_price})
                    current_price = stock_info["current"]
                    prev_close = stock_info["prev_close"]
                    
                    day_diff_price = current_price - prev_close
                    day_diff_rate = (day_diff_price / prev_close * 100) if prev_close > 0 else 0.0
                    day_diff_total = day_diff_price * shares
                    
                    eval_val = current_price * shares
                    cost_val = h["total_cost"]
                    pnl_val = eval_val - cost_val
                    pnl_rate = (pnl_val / cost_val * 100) if cost_val > 0 else 0.0
                    
                    total_stock_eval += eval_val
                    total_unrealized_pnl += pnl_val
                    total_day_diff += day_diff_total
                    
                    portfolio_data.append({
                        "コード": code,
                        "銘柄名": h["name"],
                        "保有株数": "{:,} 株".format(shares),
                        "取得単価": "¥{:,.0f}".format(avg_price),
                        "現在株価": "¥{:,.0f}".format(current_price),
                        "前日比": f"{color_text_html(day_diff_total)} ({color_text_html(day_diff_rate, is_currency=False, is_percent=True)})",
                        "評価額": "¥{:,.0f}".format(eval_val),
                        "含み損益": color_text_html(pnl_val),
                        "損益率": color_text_html(pnl_rate, is_currency=False, is_percent=True)
                    })
                
                INITIAL_CAPITAL = 1000000
                total_assets = cash_balance + total_stock_eval
                total_profit = total_assets - INITIAL_CAPITAL
                total_profit_rate = (total_profit / INITIAL_CAPITAL) * 100
                
                # 📊 資産状況サマリー
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader(f"📊 {selected_member} の資産状況サマリー")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("合計総資産", "¥{:,.0f}".format(total_assets), delta="{:+,.0f}円 ({:+.2f}%)".format(total_profit, total_profit_rate))
                col2.metric("買付余力 (現金)", "¥{:,.0f}".format(cash_balance))
                col3.metric("実現損益 (税引後)", "¥{:,.0f}".format(realized_pnl_post_tax))
                col4.metric("含み損益 (評価益)", "¥{:,.0f}".format(total_unrealized_pnl))
                col5.metric("前日比 (合計)", "¥{:,.0f}".format(total_day_diff), delta="{:+,.0f}円".format(total_day_diff))
                
                st.markdown("---")
                st.subheader("📈 現在保有銘柄 一覧")
                
                if portfolio_data:
                    df_port = pd.DataFrame(portfolio_data)
                    st.write(df_port.to_html(escape=False, index=False), unsafe_allow_html=True)
                else:
                    st.info("現在保有中の銘柄はありません。")
                
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("📜 全取引履歴を表示／非表示"):
                    st.dataframe(df_trade.iloc[:, :7], use_container_width=True)
            else:
                st.info("取引データが見つからないか、形式が正しくありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
