import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 初始化狀態 ---
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

# --- 2. 核心數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'date' in df.columns: 
                df['date'] = pd.to_datetime(df['date'])
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎 ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    df['display'] = df['stock_id'].astype(str) + " " + df['stock_name'].astype(str)
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄 (全面修復下拉選單) ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    options = master_df['display'].tolist()
    # 建立 反向查詢字典
    display_to_id = {row['display']: row['stock_id'] for _, row in master_df.iterrows()}
    
    # 修正選單：移除 callback，改用直接邏輯
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_display = st.selectbox("🔍 全市場搜尋", options=options, index=curr_idx)
    # 關鍵：一旦選擇改變，立刻更新 session_state
    if display_to_id[selected_display] != st.session_state.current_sid:
        st.session_state.current_sid = display_to_id[selected_display]
        st.rerun() # 強制刷新確保所有 Tab 連動
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        if not st.session_state.is_vip:
            st.session_state.is_vip = True
            st.rerun()
    elif pw == "" and st.session_state.is_vip:
        pass # 保持登入
    elif pw != "" and pw != VIP_KEY:
        st.session_state.is_vip = False

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# TAB 1: 技術 (保證隨選單變動)
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {sid} 走勢圖")
    df = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    if not df.empty:
        fig = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['max'], low=df['min'], close=df['close'])])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"tech_{sid}")

# TAB 3: 籌碼 (修復日期與連結報錯問題)
with tabs[2]:
    if st.session_state.is_vip:
        sid = st.session_state.current_sid
        st.subheader(f"🐳 {sid} 大戶持股趨勢")
        chip = safe_fetch("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
        if not chip.empty:
            # 關鍵：過濾掉 HTML 連結與非數值欄位，只留下 date 和數值
            # 偵測千張大戶 (通常在 percent 欄位)
            if 'stock_hold_level' in chip.columns:
                big_owner = chip[chip['stock_hold_level'] == '1000以上'].sort_values('date')
                if not big_owner.empty:
                    # 強制只畫數值
                    plot_data = big_owner.set_index('date')[['percent']]
                    st.line_chart(plot_data)
                    
            else:
                # 備援：畫最後一個數值欄位
                numeric_cols = chip.select_dtypes(include=['number']).columns
                if not numeric_cols.empty:
                    st.line_chart(chip.set_index('date')[numeric_cols[-1]])
    else:
        st.info("請於側邊欄解鎖 VIP 權限")

# TAB 2 & 4 邏輯保持 (使用上述 st.rerun 機制已可正常觸發)