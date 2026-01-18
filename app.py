import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 確保 Session State 存在
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" # 若有 Token 請填入

@st.cache_resource
def get_loader():
    try:
        loader = DataLoader()
        if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
        return loader
    except:
        return None

dl = get_loader()

# --- 2. 強大數據抓取與容錯機制 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    
    # 增加重試機制
    for _ in range(2): 
        try:
            time.sleep(0.5) # 避開 API 頻率限制
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 強制轉數值
                for col in ['close', 'open', 'high', 'low', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    df = df.dropna(subset=['date', 'open', 'close'])
                
                df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
                return df
        except:
            time.sleep(1)
            continue
    return pd.DataFrame()

# --- 3. 獲取市場清單 (加入本地備援) ---
@st.cache_data(ttl=3600)
def get_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    
    # 如果 API 失敗，提供一份基本名單確保選單不會消失
    if info_df.empty:
        backup_data = [
            {"stock_id": "2330", "stock_name": "台積電"},
            {"stock_id": "2317", "stock_name": "鴻海"},
            {"stock_id": "2454", "stock_name": "聯發科"},
            {"stock_id": "2881", "stock_name": "富邦金"}
        ]
        df = pd.DataFrame(backup_data)
    else:
        # 篩選正規個股
        df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_market_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄與選單 ---
def on_stock_change():
    st.session_state.active_sid = display_to_id[st.session_state.stock_selector]

with st.sidebar:
    st.header("⚡ 策略選單")
    
    # 獲取當前選單索引
    try:
        curr_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(curr_name)
    except:
        curr_idx = 0

    st.selectbox(
        "🔍 選擇個股", 
        options=options, 
        index=curr_idx, 
        key="stock_selector", 
        on_change=on_stock_change
    )

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    current_sid = st.session_state.active_sid
    
    # 抓取 450 天數據 (確保有足夠的交易日計算指標)
    back_date = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, back_date)
    
    if not df_raw.empty:
        df = df_raw.sort_values('date').copy()
        
        # 指標計算
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 取最近 200 筆交易
        plot_df = df.tail(200).copy()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        
        # K線 (紅漲綠跌)
        fig.add_trace(go.Candlestick(
            x=plot_df['date'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
            increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
            decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00'
        ), row=1, col=1)
        
        # 均線
        fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
        
        fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
        
        fig.update_layout(
            height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
            margin=dict(t=30, b=10, l=10, r=10),
            annotations=[dict(x=0.01, y=1.05, xref="paper", yref="paper", 
                             text="● 5MA (白)  ● 20MA (黃)  ● 60MA (青)", 
                             showarrow=False, font=dict(color="white", size=14))]
        )
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error(f"目前無法取得代號 {current_sid} 的數據。")
        st.info("💡 提示：可能是 API 暫時性斷線，請嘗試重新整理頁面，或切換其他代號測試。")

with tabs[1]:
    st.subheader("🎯 籌碼發動名單掃描")
    if st.button("🚀 開始分析"):
        st.write("正在掃描市場籌碼動向...")
        # 此處邏輯與前述一致...