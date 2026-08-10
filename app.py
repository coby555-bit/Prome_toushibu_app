import streamlit as st
import gspread
import pandas as pd
import yfinance as yf
from google.oauth2.service_account import Credentials

# ページの基本設定
st.set_page_config(page_title="投資部レース", layout="wide")
st.title("📊 投資部 100万円投資レース")

# 💡 Streamlitのキャッシュ機能を使ってGoogle認証を高速化
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

# 💡 最新株価をまとめて取得する関数（10分間キャッシュしてアクセス制限を回避）
@st.cache_data(ttl=600)
def fetch_latest_prices(symbols):
    price_map = {}
    if not symbols:
        return price_map
    
    # 4桁の数字コードに '.T' を付与 (例: '7203' -> '7203.T')
    yf_symbols = [f"{s}.T" if s.isdigit() and len(s) == 4 else s for s in symbols]
    
    try:
        # yfinanceで一括取得
        tickers = yf.Tickers(" ".join(yf_symbols))
        for orig_symbol, yf_symbol in zip(symbols, yf_symbols):
            try:
                # 直近1日のデータを取得して最新終値を採用
                hist = tickers.tickers[yf_symbol].history(period="1d")
                if not hist.empty:
                    price_map[orig_symbol] = hist["Close"].iloc[-1]
            except Exception:
                pass
    except Exception as e:
        st.warning(f"株価取得時に一部エラーが発生しました: {e}")
        
    return price_map

# システム用のシート一覧
SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData']

try:
    sh = get_spreadsheet()
    all_worksheets = [ws.title for ws in sh.worksheets()]
    members = [name for name in all_worksheets if name not in SYSTEM_SHEETS and name.strip() != '']
    
    st.sidebar.header("👤 メンバー選択")
    selected_member = st.sidebar.selectbox("メンバーを選んでください", members)
    
    if selected_member:
        worksheet = sh.worksheet(selected_member)
        all_values = worksheet.get_all_values()
        
        if len(all_values) > 1:
            header = all_values[0]
            rows = all_values[1:]
            df = pd.DataFrame(rows)
            
            # 列名の補正
            columns = []
            for i, h in enumerate(header):
                columns.append(h if h.strip() != "" else f"列_{i+1}")
            df.columns = columns
            
            # 日付（1列目）が入っている有効な取引データを抽出
            df_trade = df[df.iloc[:, 0] != ""].copy()
            
            if not df_trade.empty:
                # ----------------------------------------------------
                # 🔄 保有状況の計算ロジック
                # ----------------------------------------------------
                holdings = {} # {code: {"name": str, "shares": int, "total_cost": float}}
                
                # 取引履歴を上から順にスキャン
                for _, row in df_trade.iterrows():
                    try:
                        trade_type = str(row.iloc[1]).strip() # '買い' or '売り'
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

                # 現在保有中の銘柄（株数が1以上）のみに絞り込み
                active_codes = [code for code, data in holdings.items() if data["shares"] > 0]
                
                # ----------------------------------------------------
                # 📈 最新株価の取得と損益表示
                # ----------------------------------------------------
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
                        current_price = price_map.get(code, avg_price) # 取得失敗時は買付単価を代入
                        
                        eval_val = current_price * shares
                        cost_val = h["total_cost"]
                        pnl_val = eval_val - cost_val
                        pnl_rate = (pnl_val / cost_val * 100) if cost_val > 0 else 0.0
                        
                        total_eval_val += eval_val
                        total_pnl_val += pnl_val
                        
                        # 💡 エラー修正箇所: + を前に、, を後に記述 (例: f"{pnl_val:+,.0f}")
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
                    
                    # サマリー（カード形式）で上部に表示
                    col1, col2 = st.columns(2)
                    col1.metric("株式評価額 合計", f"¥{int(total_eval_val):,}")
                    col2.metric("含み損益 合計", f"¥{int(total_pnl_val):,}", delta=f"{total_pnl_val:+,.0f}円")
                    
                    # 保有銘柄の表を表示
                    st.dataframe(pd.DataFrame(portfolio_data), use_container_width=True)
                else:
                    st.info("現在保有中の銘柄はありません。")
                
                # ----------------------------------------------------
                # 📜 取引履歴一覧（アコーディオンで折りたたみ表示）
                # ----------------------------------------------------
                with st.expander("📜 全取引履歴を表示／非表示"):
                    st.dataframe(df_trade.iloc[:, :7], use_container_width=True)
            else:
                st.info("取引履歴のデータが空です。")
        else:
            st.info("まだ取引履歴がありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
