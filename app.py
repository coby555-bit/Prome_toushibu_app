import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="投資部レース", layout="wide")
st.title("📊 投資部 100万円投資レース")

# 💡 Streamlitの強力な機能「キャッシュ」を使って、毎回ログインする時間を省き超高速化します
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

try:
    sh = get_spreadsheet()
    
    # 💡 システム用シートを除外してメンバー一覧を作成
    SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData']
    all_worksheets = [ws.title for ws in sh.worksheets()]
    members = [name for name in all_worksheets if name not in SYSTEM_SHEETS and name.strip() != '']
    
    # サイドバーでメンバーを選択
    st.sidebar.header("👤 メンバー選択")
    selected_member = st.sidebar.selectbox("メンバーを選んでください", members)
    
    if selected_member:
        st.subheader(f"📜 {selected_member} の取引履歴")
        
        # 選択されたメンバーのシートデータを一括取得
        worksheet = sh.worksheet(selected_member)
        # 1行目をヘッダー（列名）としてデータを取得
        data = worksheet.get_all_records()
        
        if data:
            # Pandasのデータフレーム（強力な表データ）に変換して表示
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("まだ取引履歴がありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
