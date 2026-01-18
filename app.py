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

# --- 2. 數據抓取引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            return df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 獲取全市場清單 (強化版) ---
@st.cache_data(ttl=86400)
def get_full_market_universe():
    # 抓取包含上市與上櫃的所有股票資訊
    info_df = safe_fetch("TaiwanStockInfo")
    
    if info_df.empty:
        # 極端備援名單
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    
    # 篩選正規股票 (排除權證、ETF、受益憑證等，通常代碼為 4 碼數字)
    # 若您需要包含 ETF (如 0050)，可放寬此正則表達式
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$|^\d{5}$', na=False)].copy()
    
    # 建立顯示名稱
    df['display'] = df['stock_id'] + " " + df['stock_name']
    
    # 確保依代號排序
    return df.sort_values('stock_id').reset_index(drop=True)

# 載入名單
master_df = get_full_market_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略選單")
    
    # 預設選中當前 SID
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_stock = st.selectbox(
        "🔍 選擇全市場個股", 
        options=options, 
        index=curr_idx,
        help="輸入代號或名稱可快速搜尋"
    )
    st.session_state.active_sid = display_to_id[selected_stock]

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    current_sid = st.session_state.active_sid
    # 抓取足夠天數計算 60MA
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        plot_df = df.dropna(subset=['ma5', 'ma20', 'ma60']).tail(180).copy()
        
        if len(plot_df) > 5:
            # 數據純淨化處理 (預防 ValueError)
            dates_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖
            fig.add_trace(go.Candlestick(
                x=dates_str, open=plot_df['open'].tolist(), high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(), close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', decreasing_line_color='#00AA00', name="K線"
            ), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
            
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
            st.warning("該個股近期成交數據不足，無法繪製技術指標。")
    else:
        st.error(f"目前無法從伺服器獲取代號 {current_sid} 的數據。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃描")
    if st.button("🚀 開始全市場籌碼掃描"):
        # 掃描邏輯 ... (同前述版本)
        st.info("功能分析中...")