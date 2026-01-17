import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 (強化版：加入自動日期回溯) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

master_info = get_clean_master_info()
if not master_info.empty:
    stock_options = master_info['display'].tolist()
    name_to_id = master_info.set_index('display')['stock_id'].to_dict()
else:
    stock_options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 鎖碼雷達"] if is_vip else []))

# --- Tab 1: 個股診斷 ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22', name="K線"))
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

# --- Tab 2: 強勢掃描 (偵錯後邏輯) ---
with tabs[1]:
    st.subheader("📡 今日爆量強勢股")
    st.write("條件：漲幅 > 3% 且 成交量 > 2000張")
    
    if st.button("點擊啟動強勢雷達"):
        with st.spinner("雷達掃描中，若為非盤中時間將自動回溯至上一交易日..."):
            # 嘗試抓取今天，若無資料則嘗試抓取昨天、前天（連假處理）
            success = False
            for i in range(5):
                check_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_data = safe_get_data("TaiwanStockPrice", start_date=check_date)
                
                if not all_data.empty:
                    # 確保只篩選該日期的資料
                    daily_data = all_data[all_data['date'] == check_date]
                    if not daily_data.empty:
                        res = daily_data[(daily_data['close'] > daily_data['open'] * 1.03) & (daily_data['trading_volume'] > 2000000)].copy()
                        if not res.empty:
                            res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
                            st.success(f"✅ 已找到 {check_date} 的強勢股資料")
                            st.dataframe(res[['stock_id', 'close', '漲幅%', 'trading_volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                            success = True
                            break
            
            if not success:
                st.error("❌ 無法取得近期的行情資料。請檢查 API Token 是否過期或已達次數上限。")

# --- Tab 3: VIP 鎖碼雷達 ---
# (維持之前的優化邏輯，此處省略以節省長度，請保留原有的 fast_radar_scan 函數內容)