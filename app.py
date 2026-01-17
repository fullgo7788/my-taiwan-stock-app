import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

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

# --- 2. 數據引擎 (內建欄位轉換) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for attempt in range(2):
        try:
            time.sleep(0.3)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 標準化欄位名稱
                df = df.rename(columns={'max': 'high', 'min': 'low', 'trading_volume': 'volume'})
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
    return pd.DataFrame()

# --- 3. 股票清單引擎：徹底解鎖全市場 (上市+上櫃) ---
@st.cache_data(ttl=86400)
def get_total_stock_list():
    # 嘗試抓取完整的股票清單
    all_info = safe_get_data("TaiwanStockInfo")
    
    if all_info.empty:
        # 應急避難名單（僅在 API 完全掛掉時顯示）
        return pd.DataFrame({
            'stock_id': ['2330', '2201', '2436', '2317', '3035'],
            'stock_name': ['台積電', '裕隆', '偉詮電', '鴻海', '智原'],
            'display': ['2330 台積電', '2201 裕隆', '2436 偉詮電', '2317 鴻海', '3035 智原']
        })
    
    # 【核心修復】：確保包含所有上市、上櫃 4 位數股票
    # 1. 過濾 4 碼純數字代號
    all_info = all_info[all_info['stock_id'].str.match(r'^\d{4}$')]
    # 2. 確保名稱存在
    if 'stock_name' not in all_info.columns:
        all_info['stock_name'] = all_info['stock_id']
    else:
        all_info['stock_name'] = all_info['stock_name'].fillna(all_info['stock_id'])
    
    # 3. 建立支援雙向搜尋的格式
    all_info['display'] = all_info['stock_id'] + " " + all_info['stock_name']
    
    # 4. 排序並去除重複
    return all_info.sort_values('stock_id').drop_duplicates('stock_id').reset_index(drop=True)

# 載入全市場清單
master_info = get_total_stock_list()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制 ---
with st.sidebar:
    st.header("⚡ 系統核心控制")
    # 此處支援輸入代號(如 2201)或名稱(如 裕隆)
    target_display = st.selectbox(
        "🎯 搜尋個股 (輸入代號或名稱)", 
        options=list(name_to_id.keys()), 
        index=list(name_to_id.values()).index("2330") if "2330" in name_to_id.values() else 0,
        key="global_selector"
    )
    sel_sid = name_to_id[target_display]
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (pw == VIP_KEY)

# --- 5. 分頁功能 ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 診斷報告 (全自動連動) ---
with tabs[0]:
    st.subheader(f"🔍 診斷標的：{target_display}")
    start_dt = (datetime.now()-timedelta(days=360)).strftime('%Y-%m-%d')
    df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    
    if not df.empty:
        df = df.sort_values('date').reset_index(drop=True)
        # 技術指標計算
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # 繪圖
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3],
                           subplot_titles=("K線與20MA", "成交量", "20MA 乖離率 (%)"))
        
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], 
                                   low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], name="20MA", line=dict(color='orange')), row=1, col=1)
        
        fig.add_trace(go.Bar(x=df['date_str'], y=df['volume'], name="成交量", marker_color='gray'), row=2, col=1)
        
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['bias'], name="乖離", fill='tozeroy', line=dict(color='cyan')), row=3, col=1)
        fig.add_hline(y=0, line_color="white", row=3, col=1)

        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"⚠️ 無法抓取 {sel_sid} 行情數據。請確認 API Token 或該股是否停牌。")

# (其餘 Tab 2 & 3 保持邏輯穩定，同步使用主選單的 sel_sid)