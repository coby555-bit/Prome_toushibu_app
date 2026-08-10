import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
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
    
    yf_symbols = [f"{s}.T" if s.isdigit() and len(s) == 4 else s for s in symbols]
    
    try:
        tickers = yf.Tickers(" ".join(yf_symbols))
        for orig_symbol, yf_symbol in zip(symbols, yf_symbols):
            try:
                hist = tickers.tickers[yf_symbol].history(period="1d")
                if not hist.empty:
                    price_map[orig_symbol] = hist["Close"].iloc[-1]
            except Exception:
                pass
    except Exception as e:
        st.warning(f"株価取得時に一部エラーが発生しました: {e}")
        
    return price_map

# システム用シート一覧
SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData']

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
        
        # DailyLogシートの取得
        try:
            log_sheet = sh.worksheet('DailyLog')
            log_values = log_sheet.get_all_values()
            
            if len(log_values) > 1:
                df_log = pd.DataFrame(log_values[1:], columns=log_values[0])
                # 数値型の変換とデータのクレンジング
                df_log['総資産'] = pd.to_numeric(df_log['総資産'], errors='coerce')
                df_log['利益率'] = pd.to_numeric(df_log['利益率'], errors='coerce')
                df_log = df_log.dropna(subset=['日付', 'メンバー', '総資産'])
                
                # --- 1. 資産推移チャート ---
                st.subheader("📈 全員の資産推移グラフ")
                # ピボットテーブルを作成（行: 日付, 列: メンバー, 値: 総資産）
                df_pivot = df_log.pivot(index='日付', columns='メンバー', values='総資産')
                st.line_chart(df_pivot)
                
                # --- 2. 最新ランキング表 ---
                st.subheader("🏆 最新資産ランキング")
                
                # 最新日付と1日前の日付を取得
                dates = sorted(df_log['日付'].unique())
                latest_date = dates[-1] if dates else None
                prev_date = dates[-2] if len(dates) >= 2 else None
                
                if latest_date:
                    st.caption(f"表示基準日: {latest_date}")
                    
                    # 最新日のデータ
                    df_latest = df_log[df_log['日付'] == latest_date].copy()
                    
                    # 前日比の計算
                    if prev_date:
                        df_prev = df_log[df_log['日付'] == prev_date][['メンバー', '総資産']].rename(columns={'総資産': '前日総資産'})
                        df_latest = pd.merge(df_latest, df_prev, on='メンバー', how='left')
                        df_latest['前日総資産'] = df_latest['前日総資産'].fillna(1000000)
                        df_latest['前日比(円)'] = df_latest['総資産'] - df_latest['前日総資産']
                        df_latest['前日比(%)'] = (df_latest['前日比(円)'] / df_latest['前日総資産']) * 100
                    else:
                        df_latest['前日比(円)'] = 0
                        df_latest['前日比(%)'] = 0.0
                    
                    # 資産順にソートして順位を付与
                    df_latest = df_latest.sort_values(by='総資産', ascending=False).reset_index(drop=True)
                    df_latest['順位'] = df_latest.index + 1
                    df_latest['総損益'] = df_latest['総資産'] - 1000000
                    
                    # 💡 表示用にフォーマット (修正箇所: + を前に記述)
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
    # TAB 2: 個人別詳細
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
                    # 保有計算
                    holdings = {}
                    for _, row in df_trade.iterrows():
                        try:
                            trade_type = str(row.iloc[1]).strip()
                            name = str(row.iloc[2]).strip()
                            code = str(row.iloc[3]).strip()
                            shares = int(float(row.iloc[4])) if row.iloc[4] else 0
                            price = float(row.iloc[5]) if row.iloc[5] else 0.0
                            
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
                                    holdings[code]["shares"] = max(0, holdings[code]["shares"] - shares)
                                    holdings[code]["total_cost"] = max(0.0, holdings[code]["total_cost"] - (avg_cost * shares))
                        except Exception:
                            continue

                    active_codes = [code for code, data in holdings.items() if data["shares"] > 0]
                    
                    st.subheader(f"📈 {selected_member} の現在保有銘柄")
                    
                    if active_codes:
                        with st.spinner("最新株価を取得中..."):
                            price_map = fetch_latest_prices(active_codes)
                        
                        portfolio_data = []
                        total_eval_val = 0.0
                        total_pnl_val = 0.0
                        
                        for code in active_codes:
                            h = holdings[code]
                            shares = h["shares"]
                            avg_price = h["total_cost"] / shares if shares > 0 else 0.0
                            current_price = price_map.get(code, avg_price)
                            
                            eval_val = current_price * shares
                            cost_val = h["total_cost"]
                            pnl_val = eval_val - cost_val
                            pnl_rate = (pnl_val / cost_val * 100) if cost_val > 0 else 0.0
                            
                            total_eval_val += eval_val
                            total_pnl_val += pnl_val
                            
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
                        
                        col1, col2 = st.columns(2)
                        col1.metric("株式評価額 合計", f"¥{int(total_eval_val):,}")
                        col2.metric("含み損益 合計", f"¥{int(total_pnl_val):,}", delta=f"{total_pnl_val:+,.0f}円")
                        
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
