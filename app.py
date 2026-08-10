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

# 💡 最新株価の一括取得関数（10分キャッシュ）
@st.cache_data(ttl=600)
def fetch_latest_prices(symbols):
    price_map = {}
    if not symbols:
        return price_map
    
    yf_symbols = [f"{s}.T" if str(s).isdigit() and len(str(s)) == 4 else str(s) for s in symbols]
    
    try:
        tickers = yf.Tickers(" ".join(yf_symbols))
        for orig_symbol, yf_symbol in zip(symbols, yf_symbols):
            try:
                hist = tickers.tickers[yf_symbol].history(period="1d")
                if not hist.empty:
                    price_map[str(orig_symbol)] = hist["Close"].iloc[-1]
            except Exception:
                pass
    except Exception as e:
        st.warning(f"株価取得時に一部エラーが発生しました: {e}")
        
    return price_map

# 💡 数値クレンジング用の補助関数
def clean_number(val):
    if val is None:
        return 0.0
    s = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

# 💡 システム用シート一覧（PredictionHistoryもここに追加して除外）
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
                # PredictionHistoryなどが混ざっている場合はフィルタリング
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
                            "総資産": f"¥{int(row['総資産']):,}",
                            "総損益": f"¥{pnl:+,.0f}",
                            "利益率": f"{row['利益率']:+.2f}%",
                            "前日比": f"¥{diff:+,.0f} ({diff_rate:+.2f}%)"
                        })
                    
                    st.dataframe(pd.DataFrame(ranking_display), use_container_width=True)
            else:
                st.info("DailyLogにデータがありません。")
        except Exception as e:
            st.error(f"DailyLogの読み込みエラー: {e}")

    # =========================================================================
    # TAB 2: 個人別詳細（買付余力・税引後実現損益・合計総資産 対応版）
    # =========================================================================
    with tab_personal:
        st.header("👤 個人別ポートフォリオ詳細")
        
        selected_member = st.selectbox("メンバーを選択してください", members, key="personal_select")
        
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
                    # ----------------------------------------------------
                    # 🔄 買付余力 ＆ 税引後実現損益 ＆ 保有計算ロジック
                    # ----------------------------------------------------
                    INITIAL_CAPITAL = 1000000 # 初期元本 100万円
                    realized_pnl_pre_tax = 0.0 # 税引前実現損益
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
                                # 売り決済による利益（損失）の加算
                                trade_profit = (price - avg_cost) * shares
                                realized_pnl_pre_tax += trade_profit
                                
                                holdings[code]["shares"] = max(0, holdings[code]["shares"] - shares)
                                holdings[code]["total_cost"] = max(0.0, holdings[code]["total_cost"] - (avg_cost * shares))

                    # 💡 税金の計算 (利益が出ている場合のみ 20.315% を引く)
                    tax = int(realized_pnl_pre_tax * 0.20315) if realized_pnl_pre_tax > 0 else 0
                    realized_pnl_post_tax = realized_pnl_pre_tax - tax
                    
                    # 現在保有中のポジションの取得総額
                    current_stock_cost = sum([data["total_cost"] for data in holdings.values() if data["shares"] > 0])
                    
                    # 💡 買付余力（現金残高）の計算: 元本 + 税引後実現損益 - 現状の株買い付けコスト
                    cash_balance = INITIAL_CAPITAL + realized_pnl_post_tax - current_stock_cost
                    
                    # 現在保有中の銘柄コード
                    active_codes = [code for code, data in holdings.items() if data["shares"] > 0]
                    
                    # 株価の取得と評価額計算
                    price_map = fetch_latest_prices(active_codes) if active_codes else {}
                    
                    total_stock_eval = 0.0
                    total_unrealized_pnl = 0.0
                    portfolio_data = []
                    
                    for code in active_codes:
                        h = holdings[code]
                        shares = h["shares"]
                        avg_price = h["total_cost"] / shares if shares > 0 else 0.0
                        current_price = price_map.get(str(code), avg_price)
                        
                        eval_val = current_price * shares
                        cost_val = h["total_cost"]
                        pnl_val = eval_val - cost_val
                        pnl_rate = (pnl_val / cost_val * 100) if cost_val > 0 else 0.0
                        
                        total_stock_eval += eval_val
                        total_unrealized_pnl += pnl_val
                        
                        portfolio_data.append({
                            "コード": code,
                            "銘柄名": h["name"],
                            "保有株数": f"{shares:,} 株",
                            "取得単価": f"¥{int(avg_price):,}",
                            "現在株価": f"¥{int(current_price):,}",
                            "評価額": f"¥{int(eval_val):,}",
                            "含み損益": f"¥{pnl_val:+,.0f}",
                            "損益率": f"{pnl_rate:+.2f}%"
                        })
                    
                    # 💡 合計総資産 (買付余力 + 株式評価額)
                    total_assets = cash_balance + total_stock_eval
                    total_profit = total_assets - INITIAL_CAPITAL
                    total_profit_rate = (total_profit / INITIAL_CAPITAL) * 100
                    
                    # ----------------------------------------------------
                    # 📊 資産状況サマリー（4列カード表示）
                    # ----------------------------------------------------
                    st.subheader(f"📊 {selected_member} の資産状況サマリー")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("合計総資産", f"¥{int(total_assets):,}", delta=f"{total_profit:+,.0f}円 ({total_profit_rate:+.2f}%)")
                    col2.metric("買付余力 (現金)", f"¥{int(cash_balance):,}")
                    col3.metric("実現損益 (税引後)", f"¥{int(realized_pnl_post_tax):,+}")
                    col4.metric("含み損益 (評価益)", f"¥{int(total_unrealized_pnl):,+}")
                    
                    st.markdown("---")
                    st.subheader(f"📈 現在保有銘柄 一覧")
                    
                    if portfolio_data:
                        st.dataframe(pd.DataFrame(portfolio_data), use_container_width=True)
                    else:
                        st.info("現在保有中の銘柄はありません。")
                    
                    with st.expander("📜 全取引履歴を表示／非表示"):
                        st.dataframe(df_trade.iloc[:, :7], use_container_width=True)
                else:
                    st.info("取引履歴のデータが空です。")
            else:
                st.info("まだ取引履歴がありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
