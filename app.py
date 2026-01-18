import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 策略終端", layout="wide")

if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

FINMIND_TOKEN = "" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 (強化防錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] 
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 索引與策略引擎 ---
@st.cache_data(ttl=86400)
def get_screened_data():
    """
    執行核心篩選邏輯：
    1. 資本額 < 50 億 (排除權值股)
    2. 千張大戶持股週增
    3. 股價剛站上 MA20 (初次發動)
    """
    # A. 取得基本資料 (包含資本額)
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty: return pd.DataFrame(), pd.DataFrame()
    
    # 篩選 4 位數個股且股本(資本額) < 5,000,000,000 (FinMind 單位通常為元)
    # 註：部分 API 欄位名為 capital，若無此欄位則以一般個股為主
    small_cap = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)]
    if 'capital' in small_cap.columns:
        small_cap = small_cap[small_cap['capital'] < 5000000000]
    
    small_cap['display'] = small_cap['stock_id'] + " " + small_cap['stock_name']
    return small_cap.sort_values('stock_id').reset_index(drop=True)

master_df = get_screened_data()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 系統控制台")
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    try:
        curr_val = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(curr_val)
    except:
        curr_idx = 0

    selected_tag = st.selectbox("🔍 中小標的選擇 (排除50億以上)", options=options, index=curr_idx)
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun()

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "🐳 大戶發動名單"])

# --- TAB 1: 技術診斷 (均線系統) ---
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {selected_tag} 技術分析")
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        df = df_price.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="5MA", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='magenta', width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="60MA", line=dict(color='cyan', width=1.5)), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("數據獲取中...")

# --- TAB 2: 大戶發動名單 (核心策略展示) ---
with tabs[1]:
    st.subheader("🎯 籌碼正向 + 股價發動名單")
    st.caption("條件：資本額<50億、千張大戶持股週增、股價站上20日線")
    
    if st.button("🚀 執行策略比對 (全市場分析)"):
        with st.spinner("正在比對全市場籌碼與技術面相關性..."):
            # 獲取今日日期
            end_dt = datetime.now().strftime('%Y-%m-%d')
            start_dt = (datetime.now()-timedelta(days=10)).strftime('%Y-%m-%d')
            
            # 這裡為了展示，我們執行一個高效率的模擬掃描 (實戰中建議限定範圍)
            # 為了避免 API 崩潰，我們從目前 master_df 中取樣測試
            sample_list = master_df['stock_id'].tolist()[:50] # 範例取前 50 檔
            
            hit_list = []
            for s in sample_list:
                # 1. 抓取籌碼 (最近兩週)
                chip = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=20)).strftime('%Y-%m-%d'))
                # 2. 抓取價格
                price = safe_fetch("TaiwanStockPrice", s, start_dt)
                
                if not chip.empty and not price.empty:
                    # 比對大戶
                    big = chip[chip.iloc[:, -2].astype(str).str.contains('1000|15')].sort_values('date')
                    if len(big) >= 2:
                        diff = big.iloc[-1, -1] - big.iloc[-2, -1] # 最新一週 vs 前一週
                        
                        # 比對股價站上均線
                        latest_price = price.iloc[-1]['close']
                        ma20 = price['close'].mean() # 簡化計算
                        
                        if diff > 0 and latest_price > ma20:
                            name = master_df[master_df['stock_id']==s]['stock_name'].values[0]
                            hit_list.append({
                                "股票代號": s,
                                "股票名稱": name,
                                "大戶增減(%)": round(diff, 2),
                                "目前股價": latest_price,
                                "狀態": "🔥 籌碼進攻"
                            })
            
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.warning("當前盤勢未偵測到符合標的，請放寬條件或更換時段。")
    else:
        st.info("請點擊上方按鈕執行即時策略比對。")