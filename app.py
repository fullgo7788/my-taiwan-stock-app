import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業版", layout="wide")

if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 (強化防錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] 
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 索引引擎 (全市場選單) ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = df[df['stock_id'].str.match(r'^\d{4}$', na=False)]
    df['display'] = df['stock_id'].astype(str) + " " + df['stock_name'].astype(str)
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄控制 ---
with st.sidebar:
    st.header("⚡ 系統控制台")
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_tag = st.selectbox("🔍 選擇個股", options=options, index=curr_idx)
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun()

# --- 5. 主分頁區 (僅保留兩項) ---
tabs = st.tabs(["📊 技術診斷", "🐳 籌碼趨勢"])

# --- TAB 1: 技術診斷 (全均線) ---
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {selected_tag} 技術分析")
    
    # 抓取較長數據以計算 MA60
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=260)).strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        df = df_price.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="5MA", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma10'], name="10MA", line=dict(color='yellow', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='magenta', width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="60MA", line=dict(color='cyan', width=1.5)), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# --- TAB 2: 籌碼趨勢 (強化解析邏輯) ---
with tabs[1]:
    sid = st.session_state.current_sid
    st.subheader(f"🐳 {sid} 千張大戶持股趨勢")
    
    chip_df = safe_fetch("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    
    if not chip_df.empty:
        # 動態偵測欄位
        lvl_col = next((c for c in chip_df.columns if any(k in c for k in ['level', 'class', 'stage', '分級'])), None)
        pct_col = next((c for c in chip_df.columns if any(k in c for k in ['percent', 'ratio', '比例'])), None)
        
        if not lvl_col or not pct_col:
            lvl_col = chip_df.columns[-2]
            pct_col = chip_df.columns[-1]

        # 模糊篩選千張大戶等級
        mask = chip_df[lvl_col].astype(str).str.contains('1000|15|大於1000', na=False)
        big = chip_df[mask].sort_values('date')
        
        if not big.empty:
            plot_data = big.set_index('date')[[pct_col]]
            st.line_chart(plot_data)
        else:
            st.info("無法過濾出大戶分級資料，顯示原始數據首 5 筆：")
            st.write(chip_df.head(5))
    else:
        st.info("暫無籌碼數據。")