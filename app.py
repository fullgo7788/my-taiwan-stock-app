import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 1. 初始化與安全設定 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【重要】請在此處輸入你的 FinMind Token
FINMIND_TOKEN = "你的_FINMIND_TOKEN_貼在這裡" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        try:
            loader.login(token=FINMIND_TOKEN)
        except:
            pass
    return loader

dl = init_dl()

# --- 2. 核心運算函數 ---

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        
        required_cols = ['date', 'open', 'high', 'low', 'close', 'Volume']
        if df is not None and not df.empty and all(col in df.columns for col in required_cols):
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    if df is None or df.empty or 'Volume' not in df.columns:
        return 0, 0
    if len(df) < 20:
        return 0, 0
    
    temp_df = df.copy()
    temp_df['Vol_MA5'] = temp_df['Volume'].rolling(5).mean().shift(1)
    temp_df['Signal'] = (temp_df['close'].pct_change() > 0.03) & \
                        (temp_df['Volume'] > temp_df['Vol_MA5'] * 2)
    
    sig_indices = temp_df[temp_df['Signal'] == True].index
    if len(sig_indices) == 0:
        return 0, 0
    
    wins = 0
    valid_signals = 0
    for idx in sig_indices:
        if idx + days_hold < len(temp_df):
            buy_price = temp_df.iloc[idx + 1]['open']
            sell_price = temp_df.iloc[idx + days_hold]['close']
            if sell_price > buy_price:
                wins += 1
            valid_signals += 1
            
    win_rate = round(wins / valid_signals * 100, 1) if valid_signals > 0 else 0
    return win_rate, valid_signals

# --- 3. UI 介面設計 ---

st.title("🏹 台股量價籌碼決策系統")

tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 全市場閃電掃描"])

with tab1:
    col_input, col_info = st.columns([1, 2])
    with col_input:
        sid = st.text_input("輸入股票代碼", "2330")
        hold_days = st.slider("勝率預估持有天數", 1, 10, 3)
    
    df_stock = get_stock_data(sid)
    
    if not df_stock.empty:
        win_rate, count = calculate_win_rate(df_stock, days_hold=hold_days)
        with col_info:
            st.write(f"### 🔍 {sid} 診斷報告")
            c1, c2 = st.columns(2)
            c1.metric("歷史訊號勝率", f"{win_rate}%")
            c2.metric("半年內訊號次數", f"{count} 次")

        fig = go.Figure(data=[go.Candlestick(
            x=df_stock.date, open=df_stock.open, high=df_stock.high, 
            low=df_stock.low, close=df_stock.close, name="K線"
        )])
        fig.add_trace(go.Bar(x=df_stock.date, y=df_stock.Volume, name="成交量", yaxis="y2", marker_color='rgba(150, 150, 150, 0.4)'))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False), height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"⚠️ 暫時無法取得 {sid} 資料。")

with tab2:
    st.header("今日量價強勢掃描")
    st.write("過濾條件：漲幅 > 3% 且 成交量 > 2000 張")
    
    if st.button("🚀 啟動閃電掃描"):
        with st.spinner("正在獲取市場資料..."):
            try:
                # 修正點：使用更穩定的方式抓取全市場即時報價
                # 如果 taiwan_stock_daily_all 報錯，改用 get_data 方式
                today_str = datetime.now().strftime('%Y-%m-%d')
                df_all = dl.get_data(dataset="TaiwanStockPrice", start_date=today_str)
                
                if df_all is None or df_all.empty:
                    # 如果當天還沒開盤，抓取前一交易日
                    yesterday_str = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
                    df_all = dl.get_data(dataset="TaiwanStockPrice", start_date=yesterday_str)

                # 計算漲幅
                df_all['return_rate'] = (df_all['close'] - df_all['open']) / df_all['open'] * 100
                
                # 進行篩選
                final_df = df_all[(df_all['return_rate'] > 3) & (df_all['Volume'] > 2000)].copy()
                
                if not final_df.empty:
                    st.dataframe(final_df[['stock_id', 'close', 'Volume', 'return_rate']], use_container_width=True, hide_index=True)
                    st.success(f"掃描完成！發現 {len(final_df)} 檔符合條件標的。")
                else:
                    st.info("尚未發現符合條件的標的。")
            except Exception as e:
                st.error(f"掃描失敗: {e}")

st.caption("數據來源：FinMind API")