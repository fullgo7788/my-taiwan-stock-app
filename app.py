import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請確認您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 (內建重試與延遲) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for attempt in range(2):
        try:
            time.sleep(0.3) # 增加延遲確保穩定
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 強制統一欄位名
                rename_map = {'max': 'high', 'min': 'low', 'trading_volume': 'volume'}
                df = df.rename(columns=rename_map)
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    backup_df = pd.DataFrame({
        'stock_id': ['2330', '2317', '2454', '3629', '2303'],
        'stock_name': ['台積電', '鴻海', '聯發科', '地心引力', '聯電']
    })
    if df.empty:
        df = backup_df
    else:
        # 修復：放寬過濾條件，確保 2436 等非 23 開頭股票也能顯示
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        if 'stock_name' not in df.columns: df['stock_name'] = df['stock_id']
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id')

# --- 3. 處理狀態同步 ---
master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()
id_to_name = master_info.set_index('stock_id')['stock_name'].to_dict()

with st.sidebar:
    st.header("⚡ 系統核心")
    target_display = st.selectbox(
        "🎯 選擇個股", 
        options=list(name_to_id.keys()),
        index=0,
        key="global_selector"
    )
    sel_sid = name_to_id[target_display]
    sel_sname = id_to_name.get(sel_sid, "未知")
    
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)
    if is_vip: st.success("✅ VIP 已解鎖")

# --- 4. 功能分頁 ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (標題與圖表完全連動) ---
with tabs[0]:
    st.subheader(f"🔍 診斷報告：{sel_sid} {sel_sname}")
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        # 技術指標
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(
            x=df['date_str'], open=df['open'], high=df['high'], 
            low=df['low'], close=df['close'], name="K線"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], name="20MA", line=dict(color='gold')), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date_str'], y=df['volume'], name="成交量"), row=2, col=1)
        
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 該個股目前無資料，請檢查 API Token。")

# --- Tab 2: 強勢掃描 (解決 2436 找不到問題) ---
with tabs[1]:
    st.subheader("📡 強勢股爆量雷達")
    min_gain = st.slider("📈 漲幅門檻 (%)", 0.0, 10.0, 3.0)
    if st.button("啟動雷達掃描", key="btn_t2"):
        with st.spinner("正在搜尋最近交易日..."):
            found = False
            for i in range(10):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty and len(all_p) > 200:
                    df_scan = all_p.copy()
                    df_scan['gain'] = ((df_scan['close'] - df_scan['open']) / df_scan['open'] * 100)
                    res = df_scan[(df_scan['gain'] >= min_gain) & (df_scan['volume'] >= 1000000)].copy()
                    if not res.empty:
                        res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'volume']].sort_values('volume', ascending=False))
                        found = True; break
            if not found: st.info("近期盤面無符合條件之標的。")

# --- Tab 3: VIP 鎖碼雷達 (加入延遲防止失效) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請在側邊欄輸入 VIP 授權碼。")
    else:
        st.subheader("🚀 鎖碼雷達 (大戶連增分析)")
        if st.button("執行深度鎖碼分析", key="btn_t3"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            # ... (其餘邏輯比照前次修復版本，加入 time.sleep 防止 API 封鎖)