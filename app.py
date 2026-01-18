import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 初始化鎖定機制
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
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            return df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 獲取全市場清單 ---
@st.cache_data(ttl=86400)
def get_full_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = info_df[info_df['stock_id'].str.match(r'^\d{4,5}$', na=False)].copy()
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_full_market_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄回呼邏輯 (修復核心) ---
def on_stock_change():
    # 這是點擊選單後第一個執行的動作
    st.session_state.active_sid = display_to_id[st.session_state.stock_selector]

# 確保選單初始值與 active_sid 同步
if 'stock_selector' not in st.session_state:
    current_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
    st.session_state.stock_selector = current_name

with st.sidebar:
    st.header("⚡ 策略選單")
    st.selectbox(
        "🔍 選擇全市場個股", 
        options=display_options, 
        key="stock_selector",
        on_change=on_stock_change,
        help="支援搜尋代號或名稱"
    )
    st.divider()
    st.caption(f"當前鎖定標的: {st.session_state.active_sid}")

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
        
        plot_df = df.dropna(subset=['ma5', 'ma20', 'ma60']).tail(180).copy()
        
        if not plot_df.empty:
            dates_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖
            fig.add_trace(go.Candlestick(
                x=dates_str, 
                open=plot_df['open'].tolist(), 
                high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(), 
                close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', 
                decreasing_line_color='#00AA00', 
                name="K線"
            ), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=dates_str, y=plot_df['volume'].tolist(), marker_color='gray', opacity=0.4, name="成交量"), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據長度不足以計算 60MA 指標。")
    else:
        st.error(f"無法取得代號 {sid} 的數據。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃描")
    if st.button("🚀 開始全市場策略掃描"):
        with st.spinner("正在執行大戶籌碼與均線篩選..."):
            test_ids = master_df['stock_id'].tolist()[:80] # 掃描樣本
            results = []
            for tsid in test_ids:
                c_df = safe_fetch("TaiwanStockShareholding", tsid, (datetime.now()-timedelta(days=35)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", tsid, (datetime.now()-timedelta(days=50)).strftime('%Y-%m-%d'))
                if not c_df.empty and len(p_df) >= 20:
                    big_ones = c_df[c_df['stage'].astype(str) == '15'].sort_values('date')
                    if len(big_ones) >= 2:
                        change = big_ones.iloc[-1]['percent'] - big_ones.iloc[-2]['percent']
                        p_df['ma20'] = p_df['close'].rolling(20).mean()
                        last_p = p_df.iloc[-1]
                        if change > 0 and last_p['close'] > last_p['ma20']:
                            results.append({
                                "代號": tsid, 
                                "名稱": master_df[master_df['stock_id']==tsid]['stock_name'].values[0],
                                "大戶增減": f"{change:+.2f}%",
                                "收盤價": last_p['close'],
                                "狀態": "🔥 強勢發動"
                            })
            if results:
                st.table(pd.DataFrame(results))
            else:
                st.info("當前範例範圍內無符合條件標的。")