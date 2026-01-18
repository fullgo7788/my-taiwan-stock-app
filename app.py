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

# --- 2. 數據抓取：嚴格清洗與排序 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.5)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            
            # 強制日期與數值轉換
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 刪除任何無效資料，並確保依日期排序
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            df = df[df['open'] > 0] 
            return df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
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

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略選單")
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except: curr_idx = 0

    selected_stock = st.selectbox("🔍 選擇個股", options=options, index=curr_idx)
    st.session_state.active_sid = display_to_id[selected_stock]

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    current_sid = st.session_state.active_sid
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 繪圖前最後清洗：只取最後 200 筆 MA 完整的資料
        plot_df = df.dropna(subset=['ma60']).tail(200).copy()
        
        # 核心檢查：確保長度大於 0 且序列一致
        if not plot_df.empty and len(plot_df) > 5:
            # 建立畫布
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # 使用 numpy 數組傳遞，這能避開多數 Pandas 索引導致的 Plotly 錯誤
            dates = plot_df['date'].values
            opens = plot_df['open'].values
            highs = plot_df['high'].values
            lows = plot_df['low'].values
            closes = plot_df['close'].values
            
            # 確保所有數組長度絕對對齊
            if len(dates) == len(opens) == len(closes):
                fig.add_trace(go.Candlestick(
                    x=dates, open=opens, high=highs, low=lows, close=closes,
                    increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                    decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00',
                    name="K線"
                ), row=1, col=1)
                
                # 均線
                fig.add_trace(go.Scatter(x=dates, y=plot_df['ma5'].values, line=dict(color='white', width=1)), row=1, col=1)
                fig.add_trace(go.Scatter(x=dates, y=plot_df['ma20'].values, line=dict(color='#FFD700', width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=dates, y=plot_df['ma60'].values, line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
                
                # 成交量
                fig.add_trace(go.Bar(x=dates, y=plot_df['volume'].values, marker_color='gray', opacity=0.4), row=2, col=1)
                
                fig.update_layout(
                    height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                    margin=dict(t=35, b=10, l=10, r=10),
                    annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                     text="● 5MA(白) ● 20MA(黃) ● 60MA(青)", 
                                     showarrow=False, font=dict(color="white", size=14))]
                )
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.error("數據序列不對齊，請重新整理頁面。")
        else:
            st.warning("數據量不足，無法繪製均線指標。")
    else:
        st.error(f"目前代號 {current_sid} 的數據抓取異常。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃描")
    st.button("🚀 點擊執行全市場籌碼掃描")