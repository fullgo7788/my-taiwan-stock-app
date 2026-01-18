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
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 資料抓取引擎 (增強日期回溯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            numeric_cols = ['close', 'open', 'high', 'low', 'volume']
            for col in df.columns:
                if any(k in col for k in numeric_cols):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                # 關鍵：移除任何含有價格空值的列
                df = df.dropna(subset=['open', 'high', 'low', 'close'])
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 獲取市場清單 ---
@st.cache_data(ttl=86400)
def get_all_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_all_market_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

def on_stock_change():
    st.session_state.active_sid = display_to_id[st.session_state.stock_selector]

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略選單")
    try:
        curr_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(curr_name)
    except:
        curr_idx = 0

    st.selectbox("🔍 全市場標的選擇", options=options, index=curr_idx, key="stock_selector", on_change=on_stock_change)

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

# --- TAB 1: 技術分析 (修復數據不足問題) ---
with tabs[0]:
    current_sid = st.session_state.active_sid
    
    # 核心修復：將回溯天數增加到 400 天，確保有足夠交易日計算 MA60
    back_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, back_date)
    
    if not df_raw.empty:
        df = df_raw.sort_values('date').copy()
        
        # 計算技術指標
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 繪圖範圍：只取最近 180 筆交易資料顯示在圖表上，這能保證 MA 指標已經計算完成
        plot_df = df.tail(180).copy()
        
        if not plot_df.empty:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            
            # K線 (漲紅跌綠)
            fig.add_trace(go.Candlestick(
                x=plot_df['date'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
                increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00'
            ), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
            
            # 成交量
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
            st.error("該標的近期無交易數據，無法繪圖。")
    else:
        st.error(f"API 無法獲取代號 {current_sid} 的資料，請檢查網路或稍後再試。")

# --- TAB 2: 名單比對 ---
with tabs[1]:
    st.subheader("🎯 大戶籌碼與均線發動名單")
    if st.button("🚀 執行策略掃描"):
        with st.spinner("掃描市場中..."):
            hit_list = []
            # 掃描前 100 檔
            for s in master_df['stock_id'].tolist()[:100]:
                c_df = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", s, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
                
                if not c_df.empty and len(p_df) > 20:
                    pct_col = next((c for c in c_df.columns if 'percent' in c or 'ratio' in c), None)
                    lvl_col = next((c for c in c_df.columns if 'level' in c or 'stage' in c), None)
                    
                    if pct_col and lvl_col:
                        big = c_df[c_df[lvl_col].astype(str).str.contains('1000|15')].sort_values('date')
                        if len(big) >= 2:
                            diff = float(big.iloc[-1][pct_col]) - float(big.iloc[-2][pct_col])
                            p_df['ma20'] = p_df['close'].rolling(20).mean()
                            latest = p_df.iloc[-1]
                            if diff > 0 and latest['close'] > latest['ma20']:
                                s_name = master_df[master_df['stock_id']==s]['stock_name'].values[0]
                                hit_list.append({"代號": s, "名稱": s_name, "大戶增減": f"{diff:+.2f}%", "收盤": latest['close']})
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.info("當前樣本中暫無符合標的。")