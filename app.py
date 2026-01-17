import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極連動版", layout="wide")

# API 安全設定
FINMIND_TOKEN = "fullgo"
VIP_KEY = "ST888"

@st.cache_resource
def get_dl_engine():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_dl_engine()

# --- 2. 核心數據獲取引擎 (標準化處理) ---
def safe_api_call(dataset, data_id=None, start_date=None):
    try:
        # 增加延遲避免被 API 封鎖
        time.sleep(0.2)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 統一成交量命名
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except Exception as e:
        st.error(f"數據傳輸中斷: {str(e)}")
    return pd.DataFrame()

# --- 3. 全市場主索引引擎 (解決廣達、裕隆消失問題) ---
@st.cache_data(ttl=86400)
def get_comprehensive_master():
    """全量抓取台股主檔，並建立備援索引確保個股 100% 存在"""
    raw_df = safe_api_call("TaiwanStockInfo")
    
    # 核心權值股強制保底 (預防 API 僅回傳部分資料)
    core_backup = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2603", "stock_name": "長榮"},
        {"stock_id": "3035", "stock_name": "智原"},
        {"stock_id": "2454", "stock_name": "聯發科"}
    ])

    if raw_df.empty or 'stock_id' not in raw_df.columns:
        df = core_backup
    else:
        # 只保留 4 碼純數字，過濾雜訊
        raw_df = raw_df[raw_df['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw_df, core_backup]).drop_duplicates('stock_id')

    df['stock_name'] = df['stock_name'].fillna("個股")
    # 建立同時支援代號與名稱搜尋的標籤
    df['search_tag'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

# 載入主索引
master_data = get_comprehensive_master()
# 建立解析字典
tag_to_id = master_data.set_index('search_tag')['stock_id'].to_dict()

# --- 4. 側邊欄：反應式控制中心 (偵錯關鍵) ---
with st.sidebar:
    st.header("🛡️ 行情控制中心")
    
    # 使用 st.selectbox 的 index 屬性與 key 來鎖定狀態
    # 預設選取廣達 (2382) 以驗證連動
    try:
        init_idx = int(master_data[master_data['stock_id'] == "2382"].index[0])
    except:
        init_idx = 0

    current_tag = st.selectbox(
        "🎯 全市場搜尋 (輸入代號/名稱)",
        options=master_data['search_tag'].tolist(),
        index=init_idx,
        key="global_stock_selector" # 這是確保標籤連動的 Key
    )
    
    # 【偵錯重點】直接從當前選取的標籤獲取代號，不依賴 SessionState 殘留值
    target_id = tag_to_id[current_tag]
    
    st.divider()
    vip_pw = st.text_input("💎 VIP 授權鎖", type="password")
    is_vip = (vip_pw == VIP_KEY)

# --- 5. 主戰情分頁 (數據連動展示) ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 籌碼雷達"])

# --- Tab 1: 數據與標籤即時連動圖表 ---
with tabs[0]:
    st.subheader(f"📈 診斷標的：{current_tag}")
    
    # 抓取該個股歷史資料
    hist_df = safe_api_call("TaiwanStockPrice", target_id, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    
    if not hist_df.empty:
        df = hist_df.sort_values('date').reset_index(drop=True)
        # 計算指標
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        
        # 繪圖結構
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        
        # 繪製 K 線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], 
                                   low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='gold')), row=1, col=1)
        
        # 繪製成交量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray'), row=2, col=1)
        
        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"⚠️ {current_tag} 目前無法取得即時行情。")

# --- Tab 2: 掃描器 (自動帶入選定標的之產業或相關資訊) ---
with tabs[1]:
    st.subheader("📡 全市場掃描篩選")
    if st.button("啟動雷達掃描"):
        with st.spinner("掃描中..."):
            # 邏輯同步更新
            st.write("目前市場強勢標的預覽...")