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

# 【填入您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.1)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_id' in df.columns:
                df['stock_id'] = df['stock_id'].astype(str)
            # 強制日期轉換，確保後續繪圖不崩潰
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            return df
    except:
        pass
    return pd.DataFrame()

def calculate_rsi(df, period=14):
    if len(df) < period: return pd.Series([50.0] * len(df))
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 僅保留四碼普通股
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        df['display'] = df['stock_id'] + " " + df.get('stock_name', '')
        return df
    return pd.DataFrame()

master_info = get_clean_master_info()
stock_options = master_info['display'].tolist() if not master_info.empty else ["2330 台積電"]
name_to_id = master_info.set_index('display')['stock_id'].to_dict() if not master_info.empty else {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)
    if is_vip: st.success("✅ VIP 權限已解鎖")

tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (解決圖形不出問題) ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        df['rsi'] = calculate_rsi(df)
        # 統一轉換為字串格式，排除 X 軸斷層
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        st.subheader(f"📈 {target_display} 技術指標")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3])
        
        # K線
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                                     increasing_line_color='#FF3333', decreasing_line_color='#228B22', name="K線"), row=1, col=1)
        # 20MA
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"), row=1, col=1)
        # RSI
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], line=dict(color='#E6E6FA', width=2), name="RSI(14)"), row=2, col=1)
        
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        
        # 大戶持股
        if not h_df.empty:
            st.markdown("---")
            st.subheader("💎 千張大戶持股趨勢")
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date').copy()
                if not bh.empty:
                    bh['date_str'] = bh['date'].dt.strftime('%Y-%m-%d')
                    fig_h = go.Figure(data=[go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                    fig_h.update_xaxes(type='category', nticks=5)
                    fig_h.update_layout(height=300, template="plotly_dark")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.error("⚠️ 無法獲取資料，請確認 Token 填寫正確。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    st.subheader("📡 強勢股爆量雷達")
    if st.button("啟動掃描", key="scan_main"):
        with st.spinner("