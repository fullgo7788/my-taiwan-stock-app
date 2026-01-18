import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 初始化 Session State，確保 active_sid 永遠存在
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入 Token 以提高穩定性

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
            return df.dropna(subset=['date', 'open', 'close']).sort_values('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 獲取全台個股清單 (排除 ETF) ---
@st.cache_data(ttl=86400)
def get_stock_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    
    # 如果 API 有回傳
    if not info_df.empty:
        # 正則表達式：^\\d{4}$ 代表精準匹配「4位數字」，這會自動過濾掉 ETF (5-6位)
        df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
        
        # 排除權證與特殊股
        df = df[~df['stock_name'].str.contains("購|售|牛|熊", na=False)]
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df.sort_values('stock_id').reset_index(drop=True)
    
    # API 失敗時的強化備援名單 (確保選單有內容)
    backup_data = [
        {"stock_id": "2330", "stock_name": "台積電"}, {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2454", "stock_name": "聯發科"}, {"stock_id": "2303", "stock_name": "聯電"},
        {"stock_id": "2603", "stock_name": "長榮"}, {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2881", "stock_name": "富邦金"}, {"stock_id": "2882", "stock_name": "國泰金"}
    ]
    df_backup = pd.DataFrame(backup_data)
    df_backup['display'] = df_backup['stock_id'] + " " + df_backup['stock_name']
    return df_backup

# 執行載入
master_df = get_stock_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：同步邏輯 (徹底修復點) ---
def on_select_change():
    # 當下拉選單變動，立刻將選中的 ID 寫入 session_state
    selected_text = st.session_state.stock_selector_key
    st.session_state.active_sid = display_to_id[selected_text]

# 找出當前 active_sid 在清單中的位置
try:
    current_label = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
    curr_idx = display_options.index(current_label)
except:
    curr_idx = 0

with st.sidebar:
    st.header("⚡ 策略中心")
    # 核心修復：結合 key, index 與 on_change
    st.selectbox(
        "🔍 搜尋全台個股",
        options=display_options,
        index=curr_idx,
        key="stock_selector_key",
        on_change=on_select_change
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
        # 指標計算
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        plot_df = df.dropna(subset=['ma5']).tail(180).copy()
        
        if not plot_df.empty:
            # 數據純淨化：日期轉字串，數值轉 list
            d_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖
            fig.add_trace(go.Candlestick(
                x=d_str, open=plot_df['open'].tolist(), high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(), close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', decreasing_line_color='#00AA00', name="K線"
            ), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=d_str, y=plot_df['volume'].tolist(), marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據長度不足以繪製指標。")
    else:
        st.error(f"無法取得代號 {sid} 的歷史數據。")

with tabs[1]:
    st.subheader("🎯 大戶策略分析")
    st.button("🚀 執行全市場掃描")