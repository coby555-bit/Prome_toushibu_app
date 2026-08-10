import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
import re
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
                # 直近2日分のデータから現在株価と前日終値を割り出し
                hist = tickers.tickers[yf_symbol].history(period="5d")
                if not hist.empty and len(hist) >= 1:
                    current_price = hist["Close"].iloc[-1]
                    prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else current_price
                    detail_map[str(orig_symbol)] = {
                        "current": current_price,
                        "prev_close": prev_close
                    }
            except Exception:
                pass
    except Exception as e:
        st.warning(f"株価取得時に一部エラーが発生しました: {e}")
        
    return detail_map

# 💡 数値クレンジング用の補助関数
def clean_number(val):
    if val is None:
        return 0.0
    s = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

# 💡 プラス（緑）/ マイナス（赤）装飾用のHTML補助関数
def color_text_html(val, is_currency=True, is_percent=False):
    try:
        f_val = float(val)
        if is_currency:
            text = "¥" + "{:+,.0f}".format(f_val)
        elif is_percent:
            text = "{:+.2f}%".format(f_val)
        else:
            text = "{:+,.0f}".format(f_val)
            
        if f_val > 0:
            return f'<span style="color: #28a745; font-weight: bold;">{text}</span>'
        elif f_val < 0:
            return f'<span style="color: #dc3545; font-weight: bold;">{text}</span>'
        else:
            return f'<span style="color: #6c757d;">{text}</span>'
    except (ValueError, TypeError):
        return str(val)

# システム用シート一覧
SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData', 'PredictionHistory', 'ログ', '設定']

try:
    sh = get_spreadsheet()
    all_worksheets = [ws.title for ws in sh.worksheets()]
    members = [name for name in all_worksheets if name not in SYSTEM_SHEETS and name.strip() != '']
    
    # メインタブの作成
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
                
                st.subheader("📈 全員の資産推移グラフ")
                df_pivot = df_log.pivot(index='日付', columns='メンバー', values='総資産')
                st.line_chart(df_pivot)
                
                st.subheader("🏆 最新資産ランキング")
                dates = sorted(df_log['日付'].unique())
                latest_date = dates[-1] if dates else None
                prev_date = dates[-2] if len(dates) >= 2 else None
                
                if latest_date:
                    st.caption(f"表示基準日: {latest_date}")
                    df_latest = df_log[df_log['日付'] == latest_date].copy()
                    
                    if prev_date:
                        df_prev = df_log[df_log['日付'] == prev_date][['メンバー', '総資産']].rename(columns={'総資産': '前日総資産'})
                        df_latest = pd.merge(df_latest, df_prev, on='メンバー', how='left')
                        df_latest['前日総資産'] = df_latest['前日総資産'].fillna(1000000)
                        df_latest['前日比(円)'] = df_latest['総資産'] - df_latest['前日総資産']
                        df_latest['前日比(%)'] = (df_latest['前日比(円)'] / df_latest['前日総資産']) * 100
                    else:
                        df_latest['前日比(円)'] = 0
                        df_latest['前日比(%)'] = 0.0
                    
                    df_latest = df_latest.sort_values(by='総資産', ascending=False).reset_index(drop=True)
                    df_latest['順位'] = df_latest.index + 1
                    df_latest['総損益'] = df_latest['総資産'] - 1000000
                    
                    ranking_display = []
                    for _, row in df_latest.iterrows():
                        pnl = row['総損益']
                        diff = row['前日比(円)']
                        diff_rate = row['前日比(%)']
                        
                        ranking_display.append({
                            "順位": f"{int(row['順位'])}位",
                            "メンバー": row['メンバー'],
                            "総資産": "¥{:,.0f}".format(row['総資産']),
                            "総損益": color_text_html(pnl),
                            "利益率": color_text_html(row['利益率'], is_currency=False, is_percent=True),
                            "前日比": f"{color_text_html(diff)} ({color_text_html(diff_rate, is_currency=False, is_percent=True)})"
                        })
                    
                    # HTMLタグ（赤字・緑字）を正しく表示するため to_html を利用
                    df_rank_df = pd.DataFrame(ranking_display)
                    st.write(df_rank_df.to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.info("DailyLogにデータがありません。")
        except Exception as e:
            st.error(f"DailyLogの読み込みエラー: {e}")

    # =========================================================================
    # TAB 2: 個人別詳細
    # =========================================================================
    with tab_personal:
        st.header("👤 個人別ポートフォリオ詳細")
        
        # 💡 ドロップダウンから「ラジオボタン」に変更（水平並び）
        selected_member = st.radio("メンバーを選択してください", members, horizontal=True, key="personal_radio")
        
        if selected_member:
            worksheet = sh.worksheet(selected_member)
            all_values = worksheet.get_all_values()
            
            if len(all_values) > 1:
                header = all_values[0]
                rows = all_values[1:]
                df = pd.DataFrame(rows)
                
                columns = [h if h.strip() != "" else f"列_{i+1}" for i, h in enumerate(header)]
                df.columns = columns
                
                df_trade = df[df.iloc[:, 0] != ""].copy()
                
                if not df_trade.empty:
                    INITIAL_CAPITAL = 1000000
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
                    
                    # 💡 株価詳細（前日終値含む）を一括取得
                    detail_map = fetch_stock_details(active_codes) if active_codes else {}
                    
                    total_stock_eval = 0.0
                    total_unrealized_pnl = 0.0
                    portfolio_data = []
                    
                    for code in active_codes:
                        h = holdings[code]
                        shares = h["shares"]
                        avg_price = h["total_cost"] / shares if shares > 0 else 0.0
                        
                        stock_info = detail_map.get(str(code), {"current": avg_price, "prev_close": avg_price})
                        current_price = stock_info["current"]
                        prev_close = stock_info["prev_close"]
                        
                        # 前日比（株単価ベースおよび保有株数ベース）
                        day_diff_price = current_price - prev_close
                        day_diff_rate = (day_diff_price / prev_close * 100) if prev_close > 0 else 0.0
                        day_diff_total = day_diff_price * shares
                        
                        eval_val = current_price * shares
                        cost_val = h["total_cost"]
                        pnl_val = eval_val - cost_val
                        pnl_rate = (pnl_val / cost_val * 100) if cost_val > 0 else 0.0
                        
                        total_stock_eval += eval_val
                        total_unrealized_pnl += pnl_val
                        
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
                    
                    total_assets = cash_balance + total_stock_eval
                    total_profit = total_assets - INITIAL_CAPITAL
                    total_profit_rate = (total_profit / INITIAL_CAPITAL) * 100
                    
                    # ----------------------------------------------------
                    # 📊 資産状況サマリー（4列カード表示）
                    # ----------------------------------------------------
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.subheader(f"📊 {selected_member} の資産状況サマリー")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("合計総資産", "¥{:,.0f}".format(total_assets), delta="{:+,.0f}円 ({:+.2f}%)".format(total_profit, total_profit_rate))
                    col2.metric("買付余力 (現金)", "¥{:,.0f}".format(cash_balance))
                    col3.metric("実現損益 (税引後)", "¥{:,.0f}".format(realized_pnl_post_tax))
                    col4.metric("含み損益 (評価益)", "¥{:,.0f}".format(total_unrealized_pnl))
                    
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
                    st.info("取引履歴のデータが空です。")
            else:
                st.info("まだ取引履歴がありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
