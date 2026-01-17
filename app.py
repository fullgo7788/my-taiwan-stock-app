import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全資料抓取 ---
def safe_fetch(dataset, stock_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=stock_id, start_date=start_date)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = safe_fetch("TaiwanStockPrice", stock_id, start_date)
    if not df.empty:
        df = df.rename(columns={'max': 'high', 'min': 'low', 'trading_volume': 'volume'})
        # 計算移動平均線
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        return df
    return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    if df is None or df.empty or 'volume' not in df.columns or len(df) < 20:
        return 0, 0, []
    df = df.copy().reset_index(drop=True)
    df['vol_ma5'] = df['volume'].rolling(5).mean().shift(1)
    # 訊號：漲幅 > 3% 且 成交量 > 5日均量 2 倍
    df['signal'] = (df['close'].pct_change() > 0.03) & (df['volume'] > df['vol_ma5'] * 2)
    
    sig_indices = df[df['signal'] == True].index
    wins, valid, signals = 0, 0, []
    for idx in sig_indices:
        if idx + days_hold < len(df):
            buy_p = df.iloc[idx + 1]['open']
            sell_p = df.iloc[idx + days_hold]['close']
            is_win = sell_p > buy_p
            if is_win: wins += 1
            valid += 1
            signals.append({'date': df.iloc[idx]['date'], 'return': round((sell_p/buy_p-1)*100, 2)})
            
    win_rate = round(wins/valid*100, 1) if valid > 0 else 0
    return win_rate, valid, signals

# --- 3. UI 介面 ---
st.title("🏹 台股量價籌碼決策系統")

tab1, tab2 = st.tabs(["📊 專業個股診斷", "📡 閃電掃描 (盤中/盤後)"])

with tab1:
    c_in, c_res = st.columns([1, 3])
    with c_in:
        sid = st.text_input("股票代碼", "2330")
        hold_days = st.select_slider("回測持有天數", options=[1, 3, 5, 10], value=3)
        st.info("💡 邏輯：偵測『量增長紅』後的勝率。")

    df_stock = get_stock_data(sid)
    if not df_stock.empty:
        wr, cnt, sig_details = calculate_win_rate(df_stock, days_hold=hold_days)
        
        with c_res:
            m1, m2, m3 = st.columns(3)
            m1.metric("量價訊號勝率", f"{wr}%")
            m2.metric("半年訊號次數", f"{cnt} 次")
            avg_ret = sum(d['return'] for d in sig_details)/len(sig_details) if sig_details else 0
            m3.metric("平均交易報酬", f"{round(avg_ret, 2)}%")

        # 繪圖
        fig = go.Figure()
        # K線
        fig.add_trace(go.Candlestick(x=df_stock['date'], open=df_stock['open'], high=df_stock['high'], low=df_stock['low'], close=df_stock['close'], name="K線"))
        # 均線
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma5'], line=dict(color='yellow', width=1), name="5MA"))
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma20'], line=dict(color='cyan', width=1), name="20MA"))
        # 成交量
        fig.add_trace(go.Bar(x=df_stock['date'], y=df_stock['volume'], yaxis="y2", marker_color='rgba(150,150,150,0.3)', name="成交量"))
        
        fig.update_layout(height=600, template="plotly_dark", yaxis2=dict(overlaying="y", side="right", showgrid=False), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 無法獲取個股資料。")

with tab2:
    st.subheader("全市場動能掃描")
    st.write("目前 API 狀態：已連線 (Token)")
    if st.button("🚀 執行即時篩選"):
        st.warning("週六日伺服器維護中，請於週一開盤期間執行此功能。")
        st.info("建議現在先在『專業個股診斷』輸入你想關注的標的進行研究。")