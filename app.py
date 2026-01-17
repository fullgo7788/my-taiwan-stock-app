import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 1. 初始化設定與資料載入器 ---
st.set_page_config(page_title="台股量價決策 App", layout="wide")

# 初始化 DataLoader 並加入基本的防錯
@st.cache_resource
def init_dataloader():
    return DataLoader()

dl = init_dataloader()

# --- 2. 核心運算函數 ---

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    """獲取個股歷史資料，並加入例外處理防止 KeyError"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        # FinMind API 調用
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        
        if df is None or len(df) == 0:
            return pd.DataFrame()
        return df
    except Exception as e:
        # 發生 API 限制或錯誤時回傳空表，不崩潰
        return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    """計算量價訊號勝率統計"""
    if len(df) < 20:
        return 0, 0
    
    # 定義量價訊號邏輯：漲幅 > 3% 且 成交量 > 5日均量 2 倍
    df['Vol_MA5'] = df['Volume'].rolling(5).mean().shift(1)
    df['Signal'] = (df['close'].pct_change() > 0.03) & (df['Volume'] > df['Vol_MA5'] * 2)
    
    sig_indices = df[df['Signal'] == True].index
    if len(sig_indices) == 0:
        return 0, 0
    
    wins = 0
    valid_signals = 0
    for idx in sig_indices:
        if idx + days_hold < len(df):
            buy_price = df.iloc[idx + 1]['open'] # 隔日開盤買進
            sell_price = df.iloc[idx + days_hold]['close'] # 第 N 天收盤賣出
            if sell_price > buy_price:
                wins += 1
            valid_signals += 1
            
    win_rate = round(wins / valid_signals * 100, 1) if valid_signals > 0 else 0
    return win_rate, valid_signals

def fetch_scanner_data(row):
    """平行掃描用的單一股票處理函數"""
    try:
        return {
            '代號': row['stock_id'],
            '名稱': row['stock_name'],
            '現價': row['close'],
            '漲幅%': round(row['return_rate'], 2),
            '成交量': row['Volume']
        }
    except:
        return None

# --- 3. UI 介面設計 ---

st.title("🏹 台股量價籌碼決策系統")

tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 全市場閃電掃描"])

# --- Tab 1: 個股診斷 ---
with tab1:
    col_input, col_info = st.columns([1, 2])
    with col_input:
        sid = st.text_input("輸入股票代碼", "2330", help="例如: 2330, 2603")
        hold_days = st.slider("勝率預估持有天數", 1, 10, 3)
    
    df_stock = get_stock_data(sid)
    
    if not df_stock.empty:
        win_rate, count = calculate_win_rate(df_stock, days_hold=hold_days)
        
        with col_info:
            st.write(f"### 🔍 {sid} 診斷報告")
            c1, c2 = st.columns(2)
            c1.metric("歷史訊號勝率", f"{win_rate}%")
            c2.metric("半年內訊號次數", f"{count} 次")

        # 繪製互動式 K 線圖
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock.date, open=df_stock.open, high=df_stock.high, 
            low=df_stock.low, close=df_stock.close, name="K線"
        )])
        # 加入成交量柱狀圖
        fig.add_trace(go.Bar(
            x=df_stock.date, y=df_stock.Volume, name="成交量", 
            yaxis="y2", marker_color='rgba(150, 150, 150, 0.4)'
        ))
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", showgrid=False),
            height=500, template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig, use_container_width=True)
        
        if win_rate >= 60:
            st.success(f"🎯 該股量價慣性強，歷史勝率達 {win_rate}%，具備參考價值。")
    else:
        st.warning("⚠️ 暫時無法取得資料。請檢查代碼或稍後再試（可能達到 API 流量限制）。")

# --- Tab 2: 全市場掃描 ---
with tab2:
    st.header("今日量價強勢掃描")
    st.write("過濾條件：漲幅 > 3% 且 成交量 > 2000 張")
    
    if st.button("🚀 啟動閃電掃描"):
        with st.spinner("正在進行平行運算處理..."):
            try:
                # 抓取全市場行情
                df_all = dl.taiwan_stock_daily_all()
                
                # 初步過濾
                potential = df_all[(df_all['return_rate'] > 3) & (df_all['Volume'] > 2000)].to_dict('records')
                
                if potential:
                    # 使用執行緒池加速處理
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        results = list(executor.map(fetch_scanner_data, potential))
                    
                    final_df = pd.DataFrame([r for r in results if r is not None])
                    st.write("### 💎 強勢股掃描結果")
                    st.dataframe(final_df, use_container_width=True, hide_index=True)
                    st.info("💡 建議操作：配合個股診斷頁面確認歷史勝率，並避開高檔爆量長上影線標的。")
                else:
                    st.info("今日市場動能較弱，未偵測到符合條件的標的。")
            except Exception as e:
                st.error(f"掃描失敗，請檢查網路連線或 API 狀態。錯誤訊息: {e}")

# 頁尾提示
st.caption("數據來源：FinMind API | 本 App 僅供量價研究參考，不構成投資建議。")