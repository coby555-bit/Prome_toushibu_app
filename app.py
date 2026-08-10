import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.title("📊 投資部 スプレッドシート連携テスト")

# Secretsから認証情報を読み込む
try:
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    # gspreadでログイン
    gc = gspread.authorize(credentials)
    
    # スプレッドシートを開く（IDを指定）
    SPREADSHEET_ID = '1cDErL19Flvjk1EuES0RggRbzI5_wHK2VGhp7A-FQMtA'
    sh = gc.open_by_key(SPREADSHEET_ID)
    
    # ワークシート一覧を取得して表示
    worksheets = [ws.title for ws in sh.worksheets()]
    st.success("✅ スプレッドシートの連携に成功しました！")
    
    st.write("▼ シート一覧")
    st.write(worksheets)

except Exception as e:
    st.error(f"連携エラーが発生しました: {e}")
