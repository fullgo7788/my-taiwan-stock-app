import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")

# 初始化 Session State
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入免費 Token

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
        time.sleep(0.3) # 頻率控制
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

# --- 3. 獲取全市場個股清單 ---
@st.cache_data(ttl=86400)
def get_full_market_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if not info_df.empty:
        # 抓取 4-6 碼之個股與 ETF，排除權證
        df = info_df[info_df['stock_id'].str.match(r'^\d{4,6}$', na=False)].copy()
        df = df[~df['stock_name'].str.contains("購|售|牛|熊", na=False)]
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df.sort_values('stock_id').reset_index(drop=True)
    # 備援名單 (核心權值)
    backup = pd.DataFrame([{"stock_id":"2330","stock_name":"台積電"},{"stock_id":"2317","stock_name":"鴻海"}])
    backup['display'] = backup['stock_id'] + " " + backup['stock_name']
    return backup

master_df = get_full_market_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：同步機制 ---
def handle_change():
    # 當下拉選單變動，更新背後的 active_sid
    st.session_state.active_sid = display_to_id[st.session_state.stock_selector]

# 初始選單文字同步
if "stock_selector" not in st.session_state:
    try:
        init_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
    except:
        init_name = display_options[0]
    st.session_state.stock_selector = init_name

with st.sidebar:
    st.header("⚡ 策略中心")
    st.selectbox(
        "🔍 搜尋全台個股/ETF",
        options=display_options,
        key="stock_selector",
        on_change=handle_change
    )
    st.divider()
    st.caption(f"當前鎖定標的: {st.session_state.active_sid}")

# --- 5. 主分頁實作 ---
tabs = st.tabs(["📊 技術分析", "🎯 大戶發動名單"])

# TAB 1: 技術分析圖表
with tabs[0]:
    sid = st.session_state.active_sid
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=400)).strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        df = df_price.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 只取最後 180 天繪圖
        plot_df = df.dropna(subset=['ma5']).tail(180)
        
        if not plot_df.empty:
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
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
    else:
        st.error(f"目前代號 {sid} 無交易數據，請更換代號。")

# TAB 2: 大戶策略掃描
with tabs[1]:
    st.subheader("🎯 大戶籌碼 + 均線多頭排列篩選")
    st.markdown("篩選條件：**千張大戶持股增加** 且 **股價站上月線(20MA)**")
    
    if st.button("🚀 執行全市場掃描"):
        with st.spinner("正在分析市場籌碼數據 (請稍候約 15 秒)..."):
            # 選取前 80 檔權值股進行掃描 (避免 API 過載)
            scan_list = master_df['stock_id'].tolist()[:80]
            hits = []
            
            for tsid in scan_list:
                # 抓取大戶比例與價格
                c_data = safe_fetch("TaiwanStockShareholding", tsid, (datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d'))
                p_data = safe_fetch("TaiwanStockPrice", tsid, (datetime.now()-timedelta(days=60)).strftime('%Y-%m-%d'))
                
                if not c_data.empty and len(p_data) >= 20:
                    # 抓取千張大戶 (level 15)
                    big_ones = c_data[c_data['stage'].astype(str) == '15'].sort_values('date')
                    if len(big_ones) >= 2:
                        diff = big_ones.iloc[-1]['percent'] - big_ones.iloc[-2]['percent']
                        p_data['ma20'] = p_data['close'].rolling(20).mean()
                        last_p = p_data.iloc[-1]
                        
                        # 條件判定
                        if diff > 0.1 and last_p['close'] > last_p['ma20']:
                            s_name = master_df[master_df['stock_id']==tsid]['stock_name'].values[0]
                            hits.append({
                                "代號": tsid, "名稱": s_name, 
                                "大戶增減": f"{diff:+.2f}%", 
                                "最新價": last_p['close'], "狀態": "🔥 強勢"
                            })
            
            if hits:
                st.success(f"掃描完成！發現 {len(hits)} 檔潛在標的")
                st.table(pd.DataFrame(hits))
            else:
                st.info("當前範例範圍內未發現符合條件之標的。")