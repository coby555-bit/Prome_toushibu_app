import streamlit as st
import gspread
import pandas as pd
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

# システム用のシート一覧（これらはメンバーとして読み込まない）
SYSTEM_SHEETS = ['ダッシュボード', 'DailyLog', 'Temp', 'AppCache', 'PredictionCache', 'RuleData']

try:
    # スプレッドシートの取得
    sh = get_spreadsheet()
    
    # 全シート名からシステム用シートを除外してメンバーリストを作成
    all_worksheets = [ws.title for ws in sh.worksheets()]
    members = [name for name in all_worksheets if name not in SYSTEM_SHEETS and name.strip() != '']
    
    # サイドバーでメンバーを選択
    st.sidebar.header("👤 メンバー選択")
    selected_member = st.sidebar.selectbox("メンバーを選んでください", members)
    
    if selected_member:
        st.subheader(f"📜 {selected_member} の取引履歴")
        
        # 選択されたメンバーのシートを取得
        worksheet = sh.worksheet(selected_member)
        
        # 全セルデータを文字列の二次元配列として安全に一括取得
        all_values = worksheet.get_all_values()
        
        if len(all_values) > 1:
            header = all_values[0]
            rows = all_values[1:]
            
            # データフレームの作成
            df = pd.DataFrame(rows)
            
            # 空欄ヘッダーによるエラーを防ぐため、自動的に列名を補正
            columns = []
            for i, h in enumerate(header):
                if h.strip() == "":
                    columns.append(f"列_{i+1}")
                else:
                    columns.append(h)
            df.columns = columns
            
            # 1列目（日付）が空でない取引データ行のみを抽出
            df_trade = df[df.iloc[:, 0] != ""].copy()
            
            if not df_trade.empty:
                # 取引データが存在する左側の主要7列（日付, 種別, 銘柄名, コード, 株数, 単価, 金額）を表示
                st.dataframe(df_trade.iloc[:, :7], use_container_width=True)
            else:
                st.info("取引履歴のデータが空です。")
        else:
            st.info("まだ取引履歴がありません。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
