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

FINMIND_TOKEN = "fullgo" 

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
            
            # 轉換日期
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # 強制轉換數值
            cols = ['open', 'high', 'low', 'close', 'volume']
            for col in cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 排除任何含有空值的行，確保 Plotly 不會噴 ValueError
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            return df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 獲取全市場清單 ---
@st.cache_data(ttl=86400)
def get_full_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        # 備援：如果 API 斷線，至少還有台積電能選
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    
    # 篩選正規股票 (4-5 碼數字)
    df = info_df[info_df['stock_id'].str.match(r'^\d{4,5}$', na=False)].copy()
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_full_market_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：同步邏輯修復 ---
def update_stock():
    # 當選單變動時，直接更新 active_sid
    selected = st.session_state.stock_selector
    st.session_state.active_sid = display_to_id[selected]

with st.sidebar:
    st.header("⚡ 策略選單")
    
    # 根據當前 active_sid 找到應該預設在選單的哪一項
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = display_options.index(current_display)
    except:
        curr_idx = 0

    # 使用 on_change 回呼函數，點擊後立即生效
    st.selectbox(
        "🔍 選擇全市場個股", 
        options=display_options, 
        index=curr_idx,
        key="stock_selector",
        on_change=update_stock
    )

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    # 直接從 session_state 讀取當前鎖定的代號
    current_sid = st.session_state.active_sid
    
    # 抓取 450 天數據
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.copy()
        # 指標計算
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 繪圖前最後一道過濾：確保 MA 資料完整
        plot_df = df.dropna(subset=['ma5', 'ma20', 'ma60']).tail(180).copy()
        
        if len(plot_df) > 10:
            # 將日期轉為字串格式，徹底解決 Plotly ValueError
            dates_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖 (漲紅跌綠)
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
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=dates_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=dates_str, y=plot_df['volume'].tolist(), marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=700, 
                template="plotly_dark", 
                showlegend=False, 
                xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據量不足以計算技術指標（需上市滿 60 日以上）。")
    else:
        st.error(f"無法取得代號 {current_sid} 的數據，請確認 API 狀態或更換代號。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃描")
    if st.button("🚀 開始全市場籌碼掃描"):
        st.info("系統掃描中，請稍候...")