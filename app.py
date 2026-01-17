import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【請確認此處 Token 正確】
FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全資料抓取 (深度防護版) ---

def safe_fetch(dataset, stock_id=None, start_date=None):
    """防止任何 KeyError: 'data' 的發生"""
    try:
        # 使用傳遞參數的方式，確保 start_date 與 end_date 相同 (減少資料量，提高成功率)
        df = dl.get_data(
            dataset=dataset,
            data_id=stock_id,
            start_date=start_date,
            end_date=start_date if dataset == "TaiwanStockPrice" and not stock_id else None
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            return df
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = safe_fetch("TaiwanStockPrice", stock_id, start_date)
    if not df.empty:
        # 欄位校正
        mapping = {'max': 'high', 'min': 'low', 'trading_volume': 'volume'}
        df = df.rename(columns=mapping)
        return df
    return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    if df is None or df.empty or 'volume' not in df.columns or len(df) < 20:
        return 0, 0
    df = df.copy().reset_index(drop=True)
    df['vol_ma5'] = df['volume'].rolling(5).mean().shift(1)
    df['signal'] = (df['close'].pct_change() > 0.03) & (df['volume'] > df['vol_ma5'] * 2)
    sig_indices = df[df['signal'] == True].index
    if len(sig_indices) == 0: return 0, 0
    wins, valid = 0, 0
    for idx in sig_indices:
        if idx + days_hold < len(df):
            if df.iloc[idx + days_hold]['close'] > df.iloc[idx + 1]['open']: wins += 1
            valid += 1
    return round(wins/valid*100, 1) if valid > 0 else 0, valid

# --- 3. UI 介面 ---
st.title("🏹 台股量價籌碼決策系統")
tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 全市場閃電掃描"])

with tab1:
    col_input, col_info = st.columns([1, 2])
    with col_input:
        sid = st.text_input("輸入股票代碼", "2330")
        hold_days = st.slider("預估持有天數", 1, 10, 3)
    
    df_stock = get_stock_data(sid)
    if not df_stock.empty:
        wr, cnt = calculate_win_rate(df_stock, days_hold=hold_days)
        with col_info:
            c1, c2 = st.columns(2)
            c1.metric("量價訊號勝率", f"{wr}%")
            c2.metric("半年內訊號次數", f"{cnt} 次")
        fig = go.Figure(data=[go.Candlestick(x=df_stock['date'], open=df_stock['open'], high=df_stock['high'], low=df_stock['low'], close=df_stock['close'], name="K線")])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 查無此代碼資料，或 API 暫時繁忙。")

with tab2:
    st.header("今日量價強勢股掃描")
    if st.button("🚀 執行全市場掃描"):
        with st.spinner("正在尋找最近交易日..."):
            found_df = pd.DataFrame()
            # 自動回溯最近 7 天
            for i in range(0, 7):
                target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                df_all = safe_fetch("TaiwanStockPrice", start_date=target_date)
                
                if not df_all.empty:
                    df_all['return_rate'] = round((df_all['close'] - df_all['open']) / df_all['open'] * 100, 2)
                    found_df = df_all[(df_all['return_rate'] > 3) & (df_all['volume'] > 2000)].copy()
                    if not found_df.empty:
                        st.success(f"✅ 成功找到資料！日期：{target_date}")
                        break
            
            if not found_df.empty:
                st.dataframe(found_df[['stock_id', 'close', 'volume', 'return_rate']].sort_values(by='return_rate', ascending=False), use_container_width=True, hide_index=True)
            else:
                st.error("❌ 掃描失敗。可能原因：1. Token 權限受限 2. 週末資料庫維護 3. 請求過於頻繁。")
                st.info("💡 建議：手動在「個股診斷」分頁輸入代碼測試 API 是否連通。")

st.caption("數據來源：FinMind API")