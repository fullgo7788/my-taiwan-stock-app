import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化與安全設定 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【請填入你的 Token】
FINMIND_TOKEN =fullgo
@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and len(FINMIND_TOKEN) > 10:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全抓取函式 (徹底解決 KeyError: 'data') ---

def safe_get_data(dataset, data_id=None, start_date=None, end_date=None):
    """封裝 API，防止回傳非 DataFrame 格式導致崩潰"""
    try:
        df = dl.get_data(
            dataset=dataset,
            data_id=data_id,
            start_date=start_date,
            end_date=end_date
        )
        # 關鍵：只有當 df 是 Pandas DataFrame 且不為空時才回傳
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
        return pd.DataFrame()
    except Exception:
        # 攔截所有內部錯誤 (如 KeyError: 'data')
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = safe_get_data(dataset="TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    
    if not df.empty:
        df.columns = [col.lower() for col in df.columns]
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
            buy_price = df.iloc[idx + 1]['open']
            sell_price = df.iloc[idx + days_hold]['close']
            if sell_price > buy_price: wins += 1
            valid += 1
    return round(wins/valid*100, 1) if valid > 0 else 0, valid

# --- 3. UI 介面 ---
st.title("🏹 台股量價籌碼決測系統")
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
        fig.add_trace(go.Bar(x=df_stock['date'], y=df_stock['volume'], yaxis="y2", marker_color='rgba(150,150,150,0.5)', name="成交量"))
        fig.update_layout(height=500, template="plotly_dark", yaxis2=dict(overlaying="y", side="right", showgrid=False), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 無法獲取個股資料。")

with tab2:
    st.header("今日量價強勢股掃描")
    if st.button("🚀 執行全市場掃描"):
        with st.spinner("自動回溯搜尋最近交易日資料..."):
            found_data = False
            for i in range(0, 7):
                target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                df_all = safe_get_data(dataset="TaiwanStockPrice", start_date=target_date, end_date=target_date)
                
                if not df_all.empty:
                    df_all.columns = [col.lower() for col in df_all.columns]
                    found_data = True
                    break
            
            if found_data:
                df_all['return_rate'] = round((df_all['close'] - df_all['open']) / df_all['open'] * 100, 2)
                final = df_all[(df_all['return_rate'] > 3) & (df_all['volume'] > 2000)].copy()
                if not final.empty:
                    st.success(f"✅ 掃描成功！資料日期：{target_date}")
                    st.dataframe(final[['stock_id', 'close', 'volume', 'return_rate']].sort_values(by='return_rate', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info(f"日期 {target_date} 尚無符合標的。")
            else:
                st.error("❌ 無法取得資料。請確認 Token 是否正確填寫並具備權限。")

st.caption("數據來源：FinMind API")