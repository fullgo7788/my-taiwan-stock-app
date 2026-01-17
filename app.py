import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 初始化 Session State (確保密碼狀態被保存)
if 'vip_authenticated' not in st.session_state:
    st.session_state.vip_authenticated = False

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    backup = pd.DataFrame({'stock_id':['2330','3629'], 'stock_name':['台積電','地心引力']})
    if df.empty: df = backup
    else: df = df[df['stock_id'].str.match(r'^\d{4}$')]
    if 'stock_name' not in df.columns: df['stock_name'] = df['stock_id']
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df

master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()

# --- 3. 側邊欄與 VIP 驗證邏輯 ---
with st.sidebar:
    st.header("⚡ 系統控制")
    target_display = st.selectbox("🎯 選擇個股", options=list(name_to_id.keys()), key="stock_sel")
    sel_sid = name_to_id[target_display]
    
    st.divider()
    
    # 密碼輸入框優化
    user_key = st.text_input("💎 VIP 授權碼", type="password", help="輸入完請按 Enter")
    
    # 強制驗證邏輯
    if user_key == VIP_KEY:
        st.session_state.vip_authenticated = True
        st.success("✅ VIP 權限已解鎖")
    elif user_key != "":
        st.session_state.vip_authenticated = False
        st.error("❌ 授權碼錯誤")

# --- 4. 功能分頁 ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

with tabs[0]:
    st.subheader(f"🔍 診斷報告：{target_display}")
    # (此處保留之前的繪圖代碼...)

with tabs[1]:
    st.subheader("📡 強勢股掃描")
    if st.button("啟動雷達", key="t2_btn"):
        # (此處保留之前的掃描代碼...)
        st.write("正在搜尋資料...")

with tabs[2]:
    # 使用 Session State 判斷是否顯示內容
    if st.session_state.vip_authenticated:
        st.subheader("🚀 鎖碼雷達 (大戶增持分析)")
        if st.button("執行深度鎖碼分析", key="t3_btn"):
            with st.spinner("籌碼分析中..."):
                # (此處執行原本的分析邏輯)
                st.info("正在執行 VIP 專屬演算法...")
                # 測試輸出
                st.write(f"正在分析全市場熱門股之大戶動向...")
    else:
        st.warning("🔒 本功能僅限 VIP 授權使用。請在側邊欄輸入正確的授權碼並按下 Enter。")