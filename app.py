import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

if 'vip_auth' not in st.session_state:
    st.session_state.vip_auth = False

# 【API 設定】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 (強化版) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for attempt in range(2):
        try:
            time.sleep(0.3)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                df = df.rename(columns={'max': 'high', 'min': 'low', 'trading_volume': 'volume'})
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
    return pd.DataFrame()

# --- 3. 股票清單引擎 (解決 2436 消失與搜尋問題) ---
@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    
    # 強制確保 2436 等熱門股存在
    backup_data = pd.DataFrame([
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "3629", "stock_name": "地心引力"},
        {"stock_id": "2454", "stock_name": "聯發科"},
        {"stock_id": "3035", "stock_name": "智原"}
    ])

    if df.empty:
        df = backup_data
    else:
        # 抓取所有 4 碼數字股票 (解除開頭數字限制)
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([df, backup_data]).drop_duplicates('stock_id')

    if 'stock_name' not in df.columns: 
        df['stock_name'] = df['stock_id']
    
    # 【關鍵：格式化顯示內容】
    # 這樣搜尋時，輸入 "2436" 會中，輸入 "偉詮" 也會中
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()

# --- 4. UI 側邊欄 (搜尋優化) ---
with st.sidebar:
    st.header("⚡ 戰情控制中心")
    
    # 搜尋技巧：selectbox 預設支援文字搜尋
    target_display = st.selectbox(
        "🎯 搜尋個股 (輸入代號或名稱)", 
        options=list(name_to_id.keys()), 
        index=0,
        key="main_selector",
        help="您可以直接輸入 '2436' 或 '偉詮' 來快速找到股票"
    )
    sel_sid = name_to_id[target_display]
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.vip_auth = True
        st.success("VIP 權限已解鎖")

# --- 5. 分頁功能 (Tab 1 強化) ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

with tabs[0]:
    st.subheader(f"🔍 診斷報告：{target_display}")
    start_dt = (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d')
    df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    
    if not df.empty:
        df = df.sort_values('date').reset_index(drop=True)
        # 指標：20MA 與 乖離率
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.05, row_heights=[0.5, 0.2, 0.3],
                           subplot_titles=("K線與均線", "成交量", "20MA 乖離率 (%)"))
        
        # 1. K線
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], name="20MA", line=dict(color='orange')), row=1, col=1)
        
        # 2. 成交量
        fig.add_trace(go.Bar(x=df['date_str'], y=df['volume'], name="量", marker_color='gray'), row=2, col=1)
        
        # 3. 乖離率 (BIAS)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['bias'], name="乖離", fill='tozeroy', line=dict(color='cyan')), row=3, col=1)
        fig.add_hline(y=0, line_color="white", row=3, col=1)

        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("此代號暫無行情數據。")