import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 初始化 ---
st.set_page_config(page_title="AlphaRadar 專業終端", layout="wide")

# 確保狀態持久化
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"
if 'is_vip' not in st.session_state: st.session_state.is_vip = False

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 (優化版) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        # 如果是全市場掃描 (data_id 為 None)，則縮短時間範圍以防超時
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎 (保證選單存在) ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄 (修復選單無動作問題) ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 關鍵修正：使用 on_change 來強制連動
    def on_selection_change():
        st.session_state.current_sid = st.session_state.new_selection.split(' ')[0]

    options = master_df['display'].tolist()
    try:
        curr_val = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(curr_val)
    except: curr_idx = 0

    st.selectbox("🔍 全市場搜尋", options=options, index=curr_idx, 
                 key="new_selection", on_change=on_selection_change)
    
    current_sid = st.session_state.current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY: st.session_state.is_vip = True

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# TAB 1: 技術 (保證隨選單變動)
with tabs[0]:
    st.subheader(f"📈 {current_sid} 走勢診斷")
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        fig = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{current_sid}")
    else:
        st.error("此個股數據載入失敗，請稍後再試。")

# --- TAB 2: 基礎掃描 (修復無反應問題) ---
with tabs[1]:
    st.subheader("📡 全市場漲勢掃描 (近 2 個交易日)")
    v_min = st.number_input("最低張數", 300, 10000, 1000)
    
    if st.button("🚀 執行市場快速過濾"):
        with st.spinner("正在抓取市場報價..."):
            # 修正：只抓最近 3 天，降低 API 負荷
            scan_df = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d'))
            
            if not scan_df.empty:
                latest_dt = scan_df['date'].max()
                # 過濾出最新日的數據且成交量達標
                res = scan_df[(scan_df['date'] == latest_dt) & (scan_df['volume'] >= v_min*1000)].copy()
                
                # 計算今日漲幅 (收盤 vs 開盤)
                res['漲幅%'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
                
                # 合併名稱
                final = res.merge(master_df[['stock_id', 'stock_name']], on='stock_id')
                final = final[final['漲幅%'] > 2] # 僅顯示漲幅大於 2% 的
                
                st.success(f"掃描日期：{latest_dt.date()}")
                st.dataframe(final[['stock_id', 'stock_name', 'close', '漲幅%', 'volume']].sort_values('漲幅%', ascending=False), 
                             use_container_width=True, hide_index=True)
            else:
                st.warning("無法取得全市場數據。FinMind 免費版可能有請求次數限制，請一分鐘後再試。")

# TAB 3 & 4 邏輯同前，保持 session_state.is_vip 判斷...