import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 (強化狀態鎖定) ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 初始化 Session State，避免切換時丟失代號
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
        time.sleep(0.5)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            # 統一欄位名稱
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            
            # 轉換日期
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # 強制轉換數值，並排除 0 或 NaN 的無效價格
            cols = ['open', 'high', 'low', 'close', 'volume']
            for col in cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 排除任何含有空值的行
            df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            # 排除停牌數據 (開盤價為 0)
            df = df[df['open'] > 0]
            
            return df.sort_values('date').reset_index(drop=True)
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

# --- 4. 側邊欄 (直接驅動模式) ---
with st.sidebar:
    st.header("⚡ 策略選單")
    
    # 查找當前 SID 在選單中的位置
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_stock = st.selectbox("🔍 選擇個股", options=options, index=curr_idx)
    # 立即更新狀態
    st.session_state.active_sid = display_to_id[selected_stock]

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

with tabs[0]:
    current_sid = st.session_state.active_sid
    # 抓取 450 天數據確保 60MA 季線完整
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty and len(df_raw) > 60:
        df = df_raw.copy()
        # 計算指標
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 【防禦性攔截】確保繪圖區間內絕無空值
        plot_df = df.dropna(subset=['ma60']).tail(180).copy()
        
        if not plot_df.empty:
            # 建立畫布
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            # K線圖 (漲紅跌綠)
            fig.add_trace(go.Candlestick(
                x=plot_df['date'],
                open=plot_df['open'], high=plot_df['high'],
                low=plot_df['low'], close=plot_df['close'],
                increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00',
                name="K線"
            ), row=1, col=1)
            
            # 均線配置
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            # 成交量
            fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4, name="成交量"), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據處理後不足以繪圖 (可能為新上市或長期停牌個股)。")
    else:
        st.error(f"目前代號 {current_sid} 的數據暫時無法使用，請切換其他標的。")

with tabs[1]:
    st.subheader("🎯 大戶發動名單掃描")
    st.write("掃描市場中千張大戶持股增加且股價站上均線之標的...")
    if st.button("🚀 執行全市場分析"):
        st.info("功能分析中...請稍候。")