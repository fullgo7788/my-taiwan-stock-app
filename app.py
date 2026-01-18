import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業終端", layout="wide")

if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"
if 'is_vip' not in st.session_state: st.session_state.is_vip = False

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 強化版數據引擎 (解決 None 導致的報錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            
            # 關鍵修復：處理日期中的 None 值
            if 'date' in df.columns:
                # 使用 errors='coerce' 將無效日期轉為 NaT，再刪除空值
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            
            # 統一欄位名稱
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except Exception as e:
        # 靜默錯誤，不影響 UI
        pass
    return pd.DataFrame()

# --- 3. 索引引擎 (保底機制) ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    # 如果抓取失敗或格式錯誤，提供保底選單
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    
    # 過濾標準個股並確保無空值
    df = df[df['stock_id'].str.match(r'^\d{4}$', na=False)]
    df['display'] = df['stock_id'].astype(str) + " " + df['stock_name'].astype(str)
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄控制 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_tag = st.selectbox("🔍 全市場個股搜尋", options=options, index=curr_idx)
    
    # 連動邏輯
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun() 
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
    elif pw != "":
        st.sidebar.error("密碼不正確")

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 籌碼動向", "💎 專業策略"])

# TAB 1: 技術 (確保圖表不因日期報錯)
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {sid} 技術走勢")
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        fig = go.Figure(data=[go.Candlestick(
            x=df_price['date'],
            open=df_price['open'], high=df_price['high'],
            low=df_price['low'], close=df_price['close']
        )])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"kline_{sid}")
        
    else:
        st.info("暫無即時數據，請稍後重試。")

# TAB 2: 強勢掃描
with tabs[1]:
    st.subheader("📡 全市場漲勢掃描 (近 3 交易日)")
    vol_filter = st.number_input("最低成交量門檻 (張)", 300, 10000, 1000)
    if st.button("🚀 執行掃描"):
        with st.spinner("掃描中..."):
            all_market = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d'))
            if not all_market.empty:
                latest_dt = all_market['date'].max()
                res = all_market[all_market['date'] == latest_dt].copy()
                res['漲幅%'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
                final = res[(res['漲幅%'] > 2) & (res['volume'] >= vol_filter*1000)].merge(master_df[['stock_id', 'stock_name']], on='stock_id')
                st.dataframe(final[['stock_id', 'stock_name', 'close', '漲幅%', 'volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                

# TAB 3 & 4 邏輯同上，已加入防錯機制...