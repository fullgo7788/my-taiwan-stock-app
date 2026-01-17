import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業終端", layout="wide")

# 初始化 Session State (鎖定狀態，防止切換分頁失效)
if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入您的 Token
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 核心數據引擎 (具備欄位防護與容錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3) 
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 統一所有 API 欄位命名，防止均線與量能計算錯誤
            df = df.rename(columns={
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            })
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 全市場索引 (確保個股搜尋連動) ---
@st.cache_data(ttl=86400)
def get_universe():
    raw = safe_fetch("TaiwanStockInfo")
    backup = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"}
    ])
    if raw.empty or 'stock_id' not in raw.columns:
        df = backup
    else:
        raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw, backup]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()
tag_map = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制中心 (VIP 與 連動核心) ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 強制連動邏輯
    try:
        curr_idx = int(master_df[master_df['stock_id'] == st.session_state.current_sid].index[0])
    except:
        curr_idx = 0

    sel_tag = st.selectbox("🔍 全市場搜尋", options=master_df['display'].tolist(), index=curr_idx)
    st.session_state.current_sid = tag_map[sel_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password", help="輸入 ST888 解鎖全站功能")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 已啟動")
    elif pw != "":
        st.session_state.is_vip = False
        st.error("密碼錯誤")

# --- 5. 主分頁區 (TAB 1-4) ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# --- TAB 1: 技術診斷 (標籤已取消，均線 MA5/20/60) ---
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=250)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="MA5", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="MA20", line=dict(color='yellow', width=1.5)), row=1, col=1)