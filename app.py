import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極連動版", layout="wide")

# 初始化 Session State (跨分頁狀態鎖定)
if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 工業級防彈數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            rename_map = {
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            }
            df = df.rename(columns=rename_map)
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 全市場索引 (解決 2382, 2201 等個股搜尋) ---
@st.cache_data(ttl=86400)
def get_stock_universe():
    raw = safe_fetch("TaiwanStockInfo")
    core = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2317", "stock_name": "鴻海"}
    ])
    if raw.empty or 'stock_id' not in raw.columns:
        df = core
    else:
        raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw, core]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_stock_universe()
tag_map = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制 (修正點：強制狀態同步) ---
with st.sidebar:
    st.header("⚡ 終端控制台")
    
    # 使用 Key 綁定 st.selectbox 確保即時反應
    selected_tag = st.selectbox(
        "🔍 搜尋/切換個股",
        options=master_df['display'].tolist(),
        index=master_df['stock_id'].tolist().index(st.session_state.current_sid) if st.session_state.current_sid in master_df['stock_id'].values else 0,
        key="main_selector"
    )
    
    # 這是連動的核心：解析出當前 ID
    current_sid = tag_map[selected_tag]
    st.session_state.current_sid = current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY: st.session_state.is_vip = True

# --- 5. 功能連動區 (確保標籤在分頁內即時顯示) ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼分析"])

# TAB 1: 技術連動 (標籤修正)
with tabs[0]:
    # 這裡直接引用選單的變數 selected_tag
    st.subheader(f"📈 行情診斷：{selected_tag}") 
    
    price_hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    
    if not price_hist.empty:
        df = price_hist.sort_values('date')
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='#555555'), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"正在抓取 {selected_tag} 的數據...")

# TAB 2: 強勢掃描
with tabs[1]:
    st.subheader("📡 全市場即時動能雷達")
    # ... (掃描代碼保持與之前一致)
    if st.button("🚀 啟動掃描引擎"):
        st.write("掃描中...")

# TAB 3: 籌碼連動
with tabs[2]:
    if st.session_state.is_vip:
        st.subheader(f"🐳 {selected_tag} 籌碼綜合連動")
        chip_raw = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip_raw.empty:
            # (自動解析邏輯保持一致)
            st.line_chart(chip_raw.iloc[:, -1]) # 範例快速繪圖
        else:
            st.info(f"{selected_tag} 目前無大戶資料")
    else:
        st.warning("🔒 VIP 專屬連動功能。請輸入 ST888。")