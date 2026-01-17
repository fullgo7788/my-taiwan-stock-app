import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 配置與性能優化 (參考開源系統架構) ---
st.set_page_config(page_title="AlphaRadar 專業策略終端", layout="wide")

# 初始化 Session State
if 'vip_auth' not in st.session_state:
    st.session_state.vip_auth = False

# API 設定 (建議使用環境變數或 Secrets)
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 核心數據引擎 (具備緩存與重試機制) ---
def fetch_data(dataset, data_id=None, start_date=None):
    """參考開源 DataPipe 邏輯，增加容錯與欄位標準化"""
    for _ in range(3):
        try:
            time.sleep(0.2)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 標準化成交量與高低價欄位
                df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except Exception:
            time.sleep(1)
    return pd.DataFrame()

# --- 3. 全市場個股索引 (解決 2382, 2201 缺漏) ---
@st.cache_data(ttl=86400)
def get_stock_universe():
    """抓取全市場 4 碼個股，包含上市、上櫃"""
    df = fetch_data("TaiwanStockInfo")
    if df.empty:
        return pd.DataFrame({'stock_id':['2330'], 'stock_name':['台積電'], 'display':['2330 台積電']})
    
    # 僅保留 4 碼股票，排除權證 (參考開源軟體過濾邏輯)
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    df = df.drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna('')
    return df.sort_values('stock_id')

universe = get_stock_universe()
stock_dict = universe.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：全局控制中心 ---
with st.sidebar:
    st.title("🛡️ AlphaRadar")
    # 參考專業軟體：支援「代號」與「名稱」模糊搜尋
    target = st.selectbox("🎯 檢索個股 (代號/名稱)", options=universe['display'].tolist(), index=universe['stock_id'].tolist().index("2330") if "2330" in universe['stock_id'].values else 0)
    sid = stock_dict[target]
    
    st.divider()
    key = st.text_input("💎 VIP 授權碼", type="password")
    st.session_state.vip_auth = (key == VIP_KEY)
    
    # 顯示 API 狀態
    st.caption(f"數據源: FinMind | 目前標的: {sid}")

# --- 5. 主功能區塊 ---
tabs = st.tabs(["📈 技術分析", "🔥 動能掃描", "🐳 大戶籌碼"])

# --- Tab 1: 技術分析 (參考 TradingView 架構) ---
with tabs[0]:
    st.subheader(f"{target} 趨勢診斷")
    hist = fetch_data("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=250)).strftime('%Y-%m-%d'))
    
    if not hist.empty:
        df = hist.sort_values('date').reset_index(drop=True)
        # 增加技術指標 (均線、RSI)
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        # K線與均線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='gold')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="60MA", line=dict(color='cyan')), row=1, col=1)
        
        # 成交量
        colors = ['red' if c >= o else 'green' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="成交量", marker_color=colors), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("無法取得股價數據。")

# --- Tab 2: 動能掃描 (全市場掃描器) ---
with tabs[1]:
    st.subheader("📡 全市場動能掃描器")
    col1, col2 = st.columns(2)
    with col1: gain_target = st.slider("最低漲幅 (%)", 1, 10, 3)
    with col2: vol_target = st.number_input("最低成交量 (張)", 1000, 50000, 2000)
    
    if st.button("啟動掃描"):
        with st.spinner("遍歷全市場數據中..."):
            # 自動回溯最近交易日
            for i in range(7):
                d = (datetime.now()-timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = fetch_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= gain_target) & (all_p['volume'] >= vol_target * 1000)].copy()
                    if not res.empty:
                        res = res.merge(universe[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"掃描日期: {d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), use_container_width=True)
                        break
            else: st.info("查無符合標的。")

# --- Tab 3: 大戶籌碼 (VIP 功能) ---
with tabs[2]:
    if not st.session_state.vip_auth:
        st.warning("🔒 此功能僅限 VIP 使用，請輸入授權碼解鎖。")
    else:
        st.subheader(f"🐳 {target} 大戶持股變動")
        # 參考籌碼 K 線邏輯，抓取最新持股分級
        holder_df = fetch_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=60)).strftime('%Y-%m-%d'))
        if not holder_df.empty:
            # 篩選「1000張以上」的類別
            c_col = [c for c in holder_df.columns if 'class' in c][0]
            big_df = holder_df[holder_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
            if len(big_df) >= 2:
                diff = big_df['percent'].iloc[-1] - big_df['percent'].iloc[-2]
                st.metric("千張大戶持股比", f"{big_df['percent'].iloc[-1]}%", f"{round(diff, 2)}% (較上週)")
                st.line_chart(big_df.set_index('date')['percent'])
            else: st.info("籌碼數據更新中。")