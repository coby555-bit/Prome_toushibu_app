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
        
        # 選択されたメンバーのシートを取得
        worksheet = sh.worksheet(selected_member)
        
        # すべてのセルデータを取得（1行目もただのデータとして扱う）
        all_values = worksheet.get_all_values()
        
        if len(all_values) > 1:
            # 1行目を列名、2行目以降をデータとしてPandasデータフレームに変換
            header = all_values[0]
            rows = all_values[1:]
            
            # 取引データが存在する左側の7列（日付, 種別, 銘柄名, コード, 株数, 単価, 金額）を中心に抽出
            df = pd.DataFrame(rows)
            
            # 空の列名を自動補正（空白列を "Un-named" に変更）
            columns = []
            for i, h in enumerate(header):
                if h.strip() == "":
                    columns.append(f"列_{i+1}")
                else:
                    columns.append(h)
            df.columns = columns
            
            # 取引履歴（日付が存在する行のみ抽出）
            # ※1列目（日付）が空でないデータに絞り込み
            df_trade = df[df.iloc[:, 0] != ""].copy()
            
            # 不要な空白行を除外して左側の主要列を表示
            st.dataframe(df_trade.iloc[:, :7], use_container_width=True)
            
        else:
            st.info("まだ取引履歴がありません。")
