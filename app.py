dl = DataLoader()
dl.login(token="你的_FINMIND_TOKEN")
import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 初始化設定 ---
st.set_page_config(page_title="台股量價決策 App", layout="wide")
dl = DataLoader()

# --- 核心運算函數 ---
@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    """獲取個股歷史資料"""
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    return dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)

def calculate_win_rate(df, days_hold=3):
    """計算量價訊號勝率"""
    if len(df) < 20: return 0, 0
    # 定義訊號：漲幅 > 3% 且 成交量 > 5日均量 2 倍
    df['Signal'] = (df['close'].pct_change() > 0.03) & \
                   (df['Volume'] > df['Volume'].rolling(5).mean().shift(1) * 2)
    
    sig_indices = df[df['Signal'] == True].index
    if len(sig_indices) == 0: return 0, 0
    
    wins = 0
    valid_signals = 0
    for idx in sig_indices:
        if idx + days_hold < len(df):
            buy_price = df.iloc[idx + 1]['open']
            sell_price = df.iloc[idx + days_hold]['close']
            if sell_price > buy_price: wins += 1
            valid_signals += 1
    return round(wins/valid_signals*100, 1) if valid_signals > 0 else 0, valid_signals

def fetch_scanner_data(row):
    """平行掃描用的單一股票處理"""
    try:
        sid = row['stock_id']
        # 簡單籌碼邏輯 (此處為範例，可擴充 FinMind 籌碼 API)
        return {
            '代號': sid,
            '名稱': row['stock_name'],
            '現價': row['close'],
            '漲幅%': round(row['return_rate'], 2),
            '成交量': row['Volume']
        }
    except:
        return None

# --- UI 介面 ---
st.title("🏹 台股量價籌碼決策系統")

tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 全市場閃電掃描"])

# --- Tab 1: 個股診斷 ---
with tab1:
    # ... (前面的輸入框代碼)
    df = get_stock_data(sid)
    
    if not df.empty:
        # 這裡才執行計算勝率與繪圖
        win_rate, count = calculate_win_rate(df, days_hold=hold_days)
        # ... (繪圖程式碼)
    else:
        st.warning(f"⚠️ 無法取得股票 {sid} 的資料。")
        st.info("💡 可能原因：\n1. 請求過於頻繁 (API Limit)\n2. 股票代碼輸入錯誤\n3. 非交易日或資料尚未更新")
with tab1:
    col_input, col_info = st.columns([1, 2])
    with col_input:
        sid = st.text_input("輸入股票代碼", "2330")
        hold_days = st.slider("持有天數預估", 1, 10, 3)
    
    df = get_stock_data(sid)
    if not df.empty:
        win_rate, count = calculate_win_rate(df, days_hold=hold_days)
        
        with col_info:
            c1, c2 = st.columns(2)
            c1.metric("歷史訊號勝率", f"{win_rate}%")
            c2.metric("半年內訊號次數", f"{count} 次")

        # 繪製圖表
        fig = go.Figure(data=[go.Candlestick(x=df.date, open=df.open, high=df.high, low=df.low, close=df.close, name="K線")])
        fig.add_trace(go.Bar(x=df.date, y=df.Volume, name="成交量", yaxis="y2", marker_color='gray', opacity=0.5))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right"), height=500, template="plotly_dark", margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("找不到該股票資料，請確認代碼。")

# --- Tab 2: 閃電掃描 ---
with tab2:
    st.header("全市場量價過濾器")
    if st.button("🚀 開始閃電掃描 (量價+平行運算)"):
        with st.spinner("正在掃描 1,700 檔標的..."):
            df_all = dl.taiwan_stock_daily_all()
            # 濾網：漲幅>3%, 量>2000張
            potential = df_all[(df_all['return_rate'] > 3) & (df_all['Volume'] > 2000)].to_dict('records')
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(fetch_scanner_data, potential))
            
            final_df = pd.DataFrame([r for r in results if r is not None])
            if not final_df.empty:
                st.write("### 💎 今日量價強勢名單")
                st.dataframe(final_df, use_container_width=True)
                
                # 自動停損停利提示
                st.info("💡 實戰策略：建議以爆量長紅 K 低點作為移動停損點。")
            else:
                st.warning("今日市場動能不足，未偵測到符合條件股票。")