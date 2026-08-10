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
    # カンマや全角、円マーク等を除去して数値化
    s = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

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
        
        try:
            log_sheet = sh.worksheet('DailyLog')
            log_values = log_sheet.get_all_values()
            
            if len(log_values) > 1:
                df_log = pd.DataFrame(log_values[1:], columns=log_values[0])
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
    # TAB 2: 個人別詳細（強化版保有ロジック）
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
                
                # 1列目（日付）が空でない行のみ抽出
                df_trade = df[df.iloc[:, 0] != ""].copy()
                
                if not df_trade.empty:
                    # ----------------------------------------------------
                    # 🔄 強化版：保有状況の計算ロジック
                    # ----------------------------------------------------
                    holdings = {}
                    
                    for _, row in df_trade.iterrows():
                        trade_type = str(row.iloc[1]).strip() # '買い' or '売り'
                        name = str(row.iloc[2]).strip()
                        # 銘柄コードを厳格に文字列化＆4桁に整頓
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
                                holdings[code]["shares"] = max(0, holdings[code]["shares"] - shares)
                                holdings[code]["total_cost"] = max(0.0, holdings[code]["total_cost"] - (avg_cost * shares))

                    # 1株以上保有している銘柄に絞り込み
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
                            current_price = price_map.get(str(code), avg_price)
                            
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
