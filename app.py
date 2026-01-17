import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化設定 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【請務必填入你的 Token】
FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 獲取股票清單 (下拉選單用) ---
@st.cache_data(ttl=86400)
def get_stock_options():
    try:
        df_list = dl.get_data(dataset="TaiwanStockInfo")
        if not df_list.empty:
            # 建立格式如 "2330 台積電" 的選單文字
            df_list['display_name'] = df_list['stock_id'] + " " + df_list['stock_name']
            return df_list['display_name'].tolist(), df_list.set_index('display_name')['stock_id'].to_dict()
    except:
        pass
    return ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. 資料抓取邏輯 ---
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
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        return df
    return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    if df is None or df.empty or 'volume' not in df.columns or len(df) < 20:
        return 0, 0, []
    df = df.copy().reset_index(drop=True)
    df['vol_ma5'] = df['volume'].rolling(5).mean().shift(1)
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
    return (round(wins/valid*100, 1) if valid > 0 else 0), valid, signals

# --- 4. 介面呈現 ---
st.title("🏹 台股量價籌碼決策系統")

options, name_to_id = get_stock_options()

tab1, tab2 = st.tabs(["📊 專業個股診斷", "📡 全市場動能掃描"])

with tab1:
    c_in, c_res = st.columns([1, 3])
    with c_in:
        # 智慧搜尋下拉選單
        selected_stock = st.selectbox("搜尋代碼或名稱", options, index=options.index("2330 台積電") if "2330 台積電" in options else 0)
        target_sid = name_to_id[selected_stock]
        
        hold_days = st.select_slider("回測持有天數", options=[1, 3, 5, 10], value=3)
        st.write(f"🔍 **當前選定：{selected_stock}**")

    df_stock = get_stock_data(target_sid)
    if not df_stock.empty:
        wr, cnt, sig_details = calculate_win_rate(df_stock, days_hold=hold_days)
        with c_res:
            m1, m2, m3 = st.columns(3)
            m1.metric("量價訊號勝率", f"{wr}%")
            m2.metric("半年訊號次數", f"{cnt} 次")
            avg_ret = sum(d['return'] for d in sig_details)/len(sig_details) if sig_details else 0
            m3.metric("平均交易報酬", f"{round(avg_ret, 2)}%")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_stock['date'], open=df_stock['open'], high=df_stock['high'], low=df_stock['low'], close=df_stock['close'], name="K線"))
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma5'], line=dict(color='yellow', width=1.5), name="5MA"))
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma20'], line=dict(color='cyan', width=1.5), name="20MA"))
        fig.add_trace(go.Bar(x=df_stock['date'], y=df_stock['volume'], yaxis="y2", marker_color='rgba(150,150,150,0.3)', name="成交量"))
        fig.update_layout(height=600, template="plotly_dark", yaxis2=dict(overlaying="y", side="right", showgrid=False), xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 暫時無法獲取該股資料，請稍後再試。")

with tab2:
    st.subheader("全市場掃描說明")
    st.info("💡 週末期間伺服器限制較多。正常執行時間：週一至週五 15:00 後。")
    if st.button("🚀 測試掃描介面"):
        st.write("連線測試中... 請於盤後正式執行。")

st.markdown("---")
st.caption("數據來源：FinMind API | 智慧查詢：Enabled")