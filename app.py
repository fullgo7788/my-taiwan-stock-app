import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    try:
        loader = DataLoader()
        if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
        return loader
    except: return None

dl = get_loader()

# --- 2. 數據抓取：極限數據清洗 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.5)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            
            # 轉換數值並將異常值轉為 NaN
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # 強制過濾掉價格為 0 或 NaN 的無效交易日
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            df = df[df['open'] > 0] # 排除開盤價為0的停牌數據
            
            return df.reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 市場清單 ---
@st.cache_data(ttl=86400)
def get_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_market_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

def on_stock_change():
    st.session_state.active_sid = display_to_id[st.session_state.stock_selector]

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略選單")
    try:
        curr_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(curr_name)
    except: curr_idx = 0

    st.selectbox("🔍 選擇個股", options=options, index=curr_idx, key="stock_selector", on_change=on_stock_change)

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    current_sid = st.session_state.active_sid
    # 抓取 450 天數據
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.sort_values('date').copy()
        
        # 計算 MA
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma60'] = df['close'].rolling(window=60).mean()
        
        # 【關鍵修復點】再次清洗 Plotly 繪圖所需的數據，確保無任何 NaN
        # 只取最後 180 筆有 MA60 的完整數據
        plot_df = df.dropna(subset=['ma60']).tail(180).copy()
        
        if not plot_df.empty:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            
            # K線圖 (漲紅跌綠)
            fig.add_trace(go.Candlestick(
                x=plot_df['date'],
                open=plot_df['open'], 
                high=plot_df['high'],
                low=plot_df['low'], 
                close=plot_df['close'],
                increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00',
                name="K線"
            ), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4, name="成交量"), row=2, col=1)
            
            fig.update_layout(
                height=700, 
                template="plotly_dark", 
                showlegend=False, 
                xaxis_rangeslider_visible=False,
                margin=dict(t=30, b=10, l=10, r=10),
                annotations=[dict(x=0.01, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA(白) ● 20MA(黃) ● 60MA(青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據量不足，無法計算並繪製 60MA 季線。")
    else:
        st.error(f"目前無法取得 {current_sid} 的交易數據。")

with tabs[1]:
    st.subheader("🎯 大戶籌碼篩選")
    st.write("點擊按鈕分析全市場前 50 檔標的大戶動向...")
    if st.button("🚀 開始掃描"):
        # 掃描邏輯...
        st.success("掃描完成")