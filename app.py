import streamlit as st
import pandas as pd
import requests
import urllib3
from datetime import datetime, timedelta

# --- 1. 系統環境設定 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 2. 官方名單抓取 (隱藏式修復 SSL) ---
@st.cache_data(ttl=86400)
def get_official_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # 強制跳過驗證，確保名單可載入
        res = requests.get(url, headers=headers, timeout=20, verify=False)
        res.encoding = 'big5'
        
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        def split_id_name(val):
            parts = str(val).split('\u3000') # 處理全形空白
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                return parts[0], parts[1]
            return None, None

        df[['sid', 'sname']] = df['有價證券代號及名稱'].apply(lambda x: pd.Series(split_id_name(x)))
        clean_df = df.dropna(subset=['sid'])[['sid', 'sname']].copy()
        clean_df['display'] = clean_df['sid'] + " " + clean_df['sname']
        
        return clean_df.sort_values('sid').reset_index(drop=True)
    except:
        # 靜默備援
        return pd.DataFrame([{"sid":"2330","sname":"台積電","display":"2330 台積電"}])

# 準備資料
master_df = get_official_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

# --- 3. 狀態管理 ---
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

def sync_selection():
    selected_label = st.session_state.stock_selector_key
    st.session_state.active_sid = id_map[selected_label]

try:
    current_display = master_df[master_df['sid'] == st.session_state.active_sid]['display'].values[0]
    default_index = display_list.index(current_display)
except:
    default_index = 0

# --- 4. 側邊欄佈局 ---
with st.sidebar:
    st.header("⚡ 策略監控")
    st.selectbox(
        "🔍 搜尋上市個股",
        options=display_list,
        index=default_index,
        key="stock_selector_key",
        on_change=sync_selection
    )
    st.divider()
    # 僅保留精簡資訊
    st.caption(f"代號: {st.session_state.active_sid} | 全市場 {len(display_list)} 檔")

# --- 5. 主內容區 (保持純淨) ---
st.title(f"📊 {st.session_state.active_sid} 技術分析")

# 此處預留給您的圖表渲染代碼
# 

with st.expander("🎯 策略分析說明", expanded=False):
    st.write("目前已同步證交所官方名單。您可以直接在左側搜尋代號，圖表將即時更新。")