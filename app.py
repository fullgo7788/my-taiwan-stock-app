import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 初始化與 Token 登入 ---
st.set_page_config(page_title="台股量價決策系統 (Token版)", layout="wide")

# 【請在此處填入你的 Token】
FINMIND_TOKEN = "你的_TOKEN_貼在這裡"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and len(FINMIND_TOKEN) > 10:
        try:
            loader.login(token=FINMIND_TOKEN)
            # 測試登入狀態
            st.toast("✅ FinMind Token 登入成功", icon='🚀')
        except Exception as e:
            st.error(f"Token 登入失敗: {e}")
    else:
        st.warning("⚠️ 目前使用匿名模式，建議填入 Token 以免掃描失敗。")
    return loader

dl = init_dl()

# --- 2. 核心運算函數 ---

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    """獲取個股歷史資料"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        # 使用更穩定的 get_data API
        df = dl.get_data(
            dataset="TaiwanStockPrice",
            data_id=stock_id,
            start_date=start_date
        )
        if df is not None and not df.empty:
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    """計算量價突破後的勝率"""
    if df is None or df.empty or 'Volume' not in df.columns or len(df) < 20:
        return 0, 0
    
    df = df.copy()
    # 計算 5 日均量 (不含當天)
    df['Vol_MA5'] = df['Volume'].rolling(5).mean().shift(1)
    # 訊號：漲幅 > 3% 且 成交量 > 5日均量 2 倍
    df['Signal'] = (df['close'].pct_change() > 0.03) & (df['Volume'] > df['Vol_MA5'] * 2)
    
    sig_indices = df[df['Signal'] == True].index
    if len(sig_indices) == 0: return 0, 0
    
    wins = 0
    valid = 0
    for idx in sig_indices:
        # 確保有足夠的天數計算持有回報
        if idx + days_hold < len(df):
            # 以訊號隔日開盤價買入，第 N 天收盤價賣出
            buy_price = df.iloc[idx + 1]['open']
            sell_price = df.iloc[idx + days_hold]['close']
            if sell_price > buy_price:
                wins += 1
            valid += 1
    
    win_rate = round(wins / valid * 100, 1) if valid > 0 else 0
    return win_rate, valid

# --- 3. UI 介面設計 ---
st.title("🏹 台股量價籌碼決策系統")
st.markdown("---")

tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 全市場閃電掃描"])

# --- Tab 1: 個股診斷 ---
with tab1:
    col_input, col_info = st.columns([1, 2])
    with col_input:
        sid = st.text_input("輸入股票代碼", "2330", help="例如 2330 或 2603")
        hold_days = st.slider("勝率預估持有天數 (買入後持有幾天)", 1, 10, 3)
    
    df_stock = get_stock_data(sid)
    if not df_stock.empty:
        wr, cnt = calculate_win_rate(df_stock, days_hold=hold_days)
        with col_info:
            c1, c2 = st.columns(2)
            c1.metric("量價訊號勝率", f"{wr}%")
            c2.metric("半年內訊號次數", f"{cnt} 次")
            
        # 繪製 Plotly K 線圖
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock.date, open=df_stock.open, high=df_stock.high, 
            low=df_stock.low, close=df_stock.close, name="K線"
        )])
        fig.add_trace(go.Bar(
            x=df_stock.date, y=df_stock.Volume, name="成交量", 
            yaxis="y2", marker_color='rgba(150, 150, 150, 0.5)'
        ))
        fig.update_layout(
            height=500, template="plotly_dark",
            yaxis2=dict(overlaying="y", side="right", showgrid=False),
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=10, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 無法獲取個股資料，請確認代碼是否正確或 Token 額度。")

# --- Tab 2: 全市場掃描 ---
with tab2:
    st.header("今日量價強勢股掃描")
    st.info("條件：今日漲幅 > 3% 且 成交量 > 2000 張 (自動避開休市日回溯)")
    
    if st.button("🚀 執行全市場掃描"):
        with st.spinner("正在搜尋最近交易日數據..."):
            try:
                found_data = False
                # 往前尋找最近 7 天內有資料的交易日 (避開周末與例假日)
                for i in range(0, 7):
                    target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    df_all = dl.get_data(
                        dataset="TaiwanStockPrice", 
                        start_date=target_date, 
                        end_date=target_date
                    )
                    if df_all is not None and not df_all.empty:
                        found_data = True
                        break
                
                if found_data:
                    # 計算漲幅
                    df_all['return_rate'] = round((df_all['close'] - df_all['open']) / df_all['open'] * 100, 2)
                    # 篩選條件
                    final = df_all[(df_all['return_rate'] > 3) & (df_all['Volume'] > 2000)].copy()
                    
                    if not final.empty:
                        st.success(f"✅ 掃描成功！資料日期：{target_date}")
                        # 格式化顯示
                        display_df = final[['stock_id', 'close', 'Volume', 'return_rate']].rename(
                            columns={'stock_id': '代號', 'close': '收盤價', 'Volume': '成交量', 'return_rate': '漲幅%'}
                        )
                        st.dataframe(display_df.sort_values(by='漲幅%', ascending=False), use_container_width=True, hide_index=True)
                    else:
                        st.info(f"日期 {target_date} 尚無符合「量大且大漲」的標的。")
                else:
                    st.error("❌ 無法取得近期交易資料，請確認 Token 是否過期或 FinMind 伺服器狀態。")
            except Exception as e:
                st.error(f"掃描程式發生錯誤: {e}")

st.markdown("---")
st.caption("數據來源：FinMind API | 策略邏輯：量價齊揚突破策略")