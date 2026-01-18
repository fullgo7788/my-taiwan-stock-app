import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

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

# --- 2. 數據抓取：嚴格過濾 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.5)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            
            # 強制轉換日期與數值
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 刪除任何含有 NaN 的無效列
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
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

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略選單")
    try:
        curr_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(curr_name)
    except: curr_idx = 0

    # 選單不設回呼，直接用 selectbox 的值
    selected_display = st.selectbox("🔍 選擇個股", options=options, index=curr_idx)
    st.session_state.active_sid = display_to_id[selected_display]

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    # 這裡顯示「技術分析」分頁，且上方不留個股標題
    current_sid = st.session_state.active_sid
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.sort_values('date').copy()
        # 計算 MA
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 【極限過濾】確保繪圖資料完全對齊且不含 NaN
        plot_df = df.dropna(subset=['ma5', 'ma20', 'ma60']).tail(180)
        
        # 額外檢查：如果 plot_df 為空，跳過繪圖以免報錯
        if not plot_df.empty and len(plot_df) > 0:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # 使用 list 轉換確保 Plotly 讀取純粹的數值序列
            fig.add_trace(go.Candlestick(
                x=plot_df['date'].tolist(),
                open=plot_df['open'].tolist(),
                high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(),
                close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00',
                name="K線"
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("資料不足，無法繪製均線（新上市個股或近期停牌）。")
    else:
        st.error(f"目前無法取得 {current_sid} 的數據。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃