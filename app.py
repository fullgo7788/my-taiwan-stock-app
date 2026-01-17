import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化與 Token 設定 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【請填入你的 Token】
FINMIND_TOKEN = "你的_TOKEN_貼在這裡"

@st.cache_resource
def init_dl():
    try:
        loader = DataLoader()
        if FINMIND_TOKEN and len(FINMIND_TOKEN) > 10:
            loader.token = FINMIND_TOKEN
        return loader
    except Exception as e:
        st.error(f"初始化失敗: {e}")
        return DataLoader()

dl = init_dl()

# --- 2. 核心運算函數 ---

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    """抓取資料並強制標準化欄位名稱"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = dl.get_data(dataset="TaiwanStockPrice", data_id=stock_id, start_date=start_date)
        
        if df is not None and not df.empty:
            # 強制將所有欄位轉為小寫
            df.columns = [col.lower() for col in df.columns]
            
            # 檢查關鍵欄位是否存在，若不存在則手動映射 (處理不同 API 版本差異)
            mapping = {'max': 'high', 'min': 'low', 'trading_volume': 'volume'}
            df = df.rename(columns=mapping)
            
            # 確保必要欄位都存在，否則回傳空表
            cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if all(c in df.columns for c in cols):
                return df[cols]
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    """計算量價突破後的勝率"""
    if df is None or df.empty or len(df) < 20:
        return 0, 0
    
    df = df.copy().reset_index(drop=True)
    df['vol_ma5'] = df['volume'].rolling(5).mean().shift(1)
    # 訊號：漲幅 > 3% 且 成交量 > 5日均量 2 倍
    df['signal'] = (df['close'].pct_change() > 0.03) & (df['volume'] > df['vol_ma5'] * 2)
    
    sig_indices = df[df['signal'] == True].index
    if len(sig_indices) == 0: return 0, 0
    
    wins, valid = 0, 0
    for idx in sig_indices:
        if idx + days_hold < len(df):
            buy_price = df.iloc[idx + 1]['open'] # 隔日開盤買
            sell_price = df.iloc[idx + days_hold]['close'] # 第N天收盤賣
            if sell_price > buy_price: wins += 1
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
            
        # 使用標準化後的欄位繪圖
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock['date'], open=df_stock['open'], high=df_stock['high'], 
            low=df_stock['low'], close=df_stock['close'], name="K線"
        )])
        fig.add_trace(go.Bar(x=df_stock['date'], y=df_stock['volume'], yaxis="y2", marker_color='rgba(150,150,150,0.5)', name="成交量"))
        fig.update_layout(height=500, template="plotly_dark", yaxis2=dict(overlaying="y", side="right", showgrid=False), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 無法獲取該代碼的完整量價資料，請檢查代碼或稍後再試。")

with tab2:
    st.header("今日量價強勢股掃描")
    if st.button("🚀 執行全市場掃描"):
        with st.spinner("搜尋最近交易日資料中..."):
            try:
                found_data = False
                for i in range(0, 7):
                    target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    df_all = dl.get_data(dataset="TaiwanStockPrice", start_date=target_date, end_date=target_date)
                    if df_all is not None and not df_all.empty:
                        df_all.columns = [col.lower() for col in df_all.columns]
                        found_data = True
                        break
                
                if found_data:
                    df_all['return_rate'] = round((df_all['close'] - df_all['open']) / df_all['open'] * 100, 2)
                    final = df_all[(df_all['return_rate'] > 3) & (df_all['volume'] > 2000)].copy()
                    
                    if not final.empty:
                        st.success(f"✅ 掃描完成！日期：{target_date}")
                        st.dataframe(final[['stock_id', 'close', 'volume', 'return_rate']].sort_values(by='return_rate', ascending=False), use_container_width=True, hide_index=True)
                    else:
                        st.info(f"日期 {target_date} 尚無符合條件標的。")
                else:
                    st.error("❌ 無法取得資料，請檢查 Token 有效性。")
            except Exception as e:
                st.error(f"掃描失敗: {e}")

st.caption("數據來源：FinMind API")