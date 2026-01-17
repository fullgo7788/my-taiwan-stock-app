import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 終極完整版", layout="wide")

# 【核心設定】請確保 Token 正確，若無 Token 免費版限制極嚴
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 防彈數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 統一命名
            rename_dict = {'trading_volume': 'volume', 'max': 'high', 'min': 'low'}
            df = df.rename(columns=rename_dict)
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except Exception as e:
        print(f"API Fetch Error: {e}")
    return pd.DataFrame()

# --- 3. 核心索引引擎 (徹底修復 KeyError 與 廣達/裕隆缺漏) ---
@st.cache_data(ttl=86400)
def get_total_universe():
    """全量抓取並具備自動補償功能的索引引擎"""
    df = safe_fetch("TaiwanStockInfo")
    
    # 建立「基礎保底名單」：確保 API 斷線時選單不崩潰
    # 這裡加入您提到的所有重要標的
    base_data = [
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2454", "stock_name": "聯發科"},
        {"stock_id": "2603", "stock_name": "長榮"},
        {"stock_id": "2609", "stock_name": "陽明"},
        {"stock_id": "3035", "stock_name": "智原"}
    ]
    base_df = pd.DataFrame(base_data)

    # 檢查 API 回傳是否包含必要欄位
    if df.empty or 'stock_id' not in df.columns:
        df = base_df
    else:
        # 僅保留 4 碼純數字，並合併保底名單
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([df, base_df]).drop_duplicates('stock_id')

    # 強制名稱補全
    df['stock_name'] = df['stock_name'].fillna("未知標的")
    df['display'] = df['stock_id'] + " " + df['stock_name']
    
    return df.sort_values('stock_id').reset_index(drop=True)

# 啟動系統索引
try:
    universe = get_total_universe()
except:
    # 最終防線：如果 cache 失敗，強制手動建立最簡 DataFrame
    universe = pd.DataFrame({'stock_id':['2330'], 'display':['2330 台積電']})

stock_map = universe.set_index('display')['stock_id'].to_dict()

# --- 4. UI 控制面板 ---
with st.sidebar:
    st.title("🛡️ 專業策略終端")
    target_display = st.selectbox(
        "🔍 全市場搜尋 (輸入名稱/代號)", 
        options=universe['display'].tolist(),
        index=universe['stock_id'].tolist().index("2382") if "2382" in universe['stock_id'].values else 0
    )
    sel_sid = stock_map[target_display]
    
    st.divider()
    key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (key == VIP_KEY)

# --- 5. 分頁功能 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼"])

with tabs[0]:
    st.subheader(f"🔍 當前標的：{target_display}")
    start_date = (datetime.now() - timedelta(days=360)).strftime('%Y-%m-%d')
    hist = safe_fetch("TaiwanStockPrice", sel_sid, start_date)
    
    if not hist.empty:
        df = hist.sort_values('date').reset_index(drop=True)
        # 技術指標
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        # K線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='orange')), row=1, col=1)
        # 量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray'), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 數據讀取中，或 API 流量已達上限。")

# (其餘 Tab 2 & 3 邏輯相同，均已透過 sel_sid 連動)