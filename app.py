import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 初始化 Session State (核心：這是確保選單不跑掉的關鍵)
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入 Token

@st.cache_resource
def get_loader():
    try:
        loader = DataLoader()
        if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
        return loader
    except: return None

dl = get_loader()

# --- 2. 數據抓取：嚴格過濾與型別校正 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df.dropna(subset=['date', 'open', 'close']).sort_values('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 獲取全市場清單 (包含個股與 ETF) ---
@st.cache_data(ttl=86400)
def get_full_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if not info_df.empty:
        # 正則表達式：抓取 4-6 碼的代號，排除權證
        df = info_df[info_df['stock_id'].str.match(r'^\d{4,6}$', na=False)].copy()
        df = df[~df['stock_name'].str.contains("購|售|牛|熊", na=False)]
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df.sort_values('stock_id').reset_index(drop=True)
    # 備援名單
    backup = pd.DataFrame([{"stock_id":"2330","stock_name":"台積電"},{"stock_id":"2317","stock_name":"鴻海"}])
    backup['display'] = backup['stock_id'] + " " + backup['stock_name']
    return backup

master_df = get_full_market_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：同步邏輯修復 (核心改動) ---
def update_sid():
    # 當選單觸發時，直接更新 active_sid
    selected_text = st.session_state.stock_selector
    st.session_state.active_sid = display_to_id[selected_text]

# 檢查當前選單顯示文字
try:
    current_display_text = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
except:
    current_display_text = display_options[0]

with st.sidebar:
    st.header("⚡ 策略中心")
    # 使用 key 與 on_change 回呼，這是解決選單無效的最穩定做法
    st.selectbox(
        "🔍 搜尋全台個股/ETF",
        options=display_options,
        index=display_options.index(current_display_text),
        key="stock_selector",
        on_change=update_sid
    )
    st.divider()
    st.info(f"當前鎖定標的: {st.session_state.active_sid}")

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    sid = st.session_state.active_sid
    df_raw = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        plot_df = df.dropna(subset=['ma5']).tail(180)
        
        if not plot_df.empty:
            dates_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖
            fig.add_trace(go.Candlestick(
                x=dates_str, open=plot_df['open'].tolist(), high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(), close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', decreasing_line_color='#00AA00', name="K線"
            ), row=1, col=1)
            
            # 均線配置
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=dates_str, y=plot_df['volume'].tolist(), marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
    else:
        st.error(f"無法取得代號 {sid} 的歷史數據。")

with tabs[1]:
    st.subheader("🎯 策略分析")
    st.button("🚀 執行全市場掃描")