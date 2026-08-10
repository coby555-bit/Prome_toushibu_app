import streamlit as st
import yfinance as yf
import pandas as pd

# ページの基本設定
st.set_page_config(page_title="投資部レース (プロトタイプ)", layout="wide")

# タイトル
st.title("📊 投資部 100万円投資レース (Python版)")

# サイドバーで銘柄コードを入力
st.sidebar.header("設定")
symbol = st.sidebar.text_input("銘柄コード (例: 7203)", value="7203")

# .T (東証) を自動付与
if not symbol.endswith(".T") and symbol.isdigit():
    ticker_symbol = f"{symbol}.T"
else:
    ticker_symbol = symbol

st.subheader(f"📈 {ticker_symbol} の過去1ヶ月の株価推移")

try:
    # yfinanceで株価データを取得
    with st.spinner("株価データを取得中..."):
        ticker_data = yf.Ticker(ticker_symbol)
        df = ticker_data.history(period="1mo")
    
    if not df.empty:
        # 終値の折れ線グラフを表示
        st.line_chart(df["Close"])
        
        # データの表を表示
        st.write("▼ 生データ")
        st.dataframe(df[["Open", "High", "Low", "Close", "Volume"]].tail())
    else:
        st.warning("データが見つかりませんでした。銘柄コードを確認してください。")
except Exception as e:
    st.error(f"エラーが発生しました: {e}")
