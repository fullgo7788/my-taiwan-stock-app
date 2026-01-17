import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# --- 1. 初始化與安全設定 ---
st.set_page_config(page_title="台股量價決策系統", layout="wide")

# 【重要】請在此處輸入你的 FinMind Token
# 你也可以在 Streamlit Secrets 設定中加入，安全性更高
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

# --- 2. 核心運算函數 (含防崩潰邏輯) ---

@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=180):
    """獲取歷史資料，並徹底攔截空資料導致的錯誤"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        
        # 嚴格檢查：必須包含基本欄位才回傳
        required_cols = ['date', 'open', 'high', 'low', 'close', 'Volume']
        if df is not None and not df.empty and all(col in df.columns for col in required_cols):
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def calculate_win_rate(df, days_hold=3):
    """計算量價訊號勝率統計 (安全版)"""
    # 再次確認 DataFrame 內容，防止計算時 KeyError
    if df is None or df.empty or 'Volume' not in df.columns:
        return 0, 0
    
    if len(df) < 20:
        return 0, 0
    
    # 複製資料避免警告
    temp_df = df.copy()
    temp_df['Vol_MA5'] = temp_df['Volume'].rolling(5).mean().shift(1)
    
    # 量價訊號：漲幅 > 3% 且 成交量 > 5日均量 2 倍
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

def fetch_scanner_data(row):
    """平行運算：處理單一股票資訊"""
    try:
        return {
            '代號': row['stock_id'],
            '名稱': row['stock_name'],
            '現價': row['close'],
            '漲幅%': round(row['return_rate'], 2),
            '成交量': int(row['Volume'])
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
        sid = st.text_input("輸入股票代碼", "2330")
        hold_days = st.slider("勝率預估持有天數", 1, 10, 3)
    
    df_stock = get_stock_data(sid)
    
    if not df_stock.empty:
        # 僅在確定有資料時才計算勝率
        win_rate, count = calculate_win_rate(df_stock, days_hold=hold_days)
        
        with col_info:
            st.write(f"### 🔍 {sid} 診斷報告")
            c1, c2 = st.columns(2)
            c1.metric("歷史訊號勝率", f"{win_rate}%")
            c2.metric("半年內訊號次數", f"{count} 次")

        # 繪製 K 線圖
        fig = go.Figure(data=[go.Candlestick(
            x=df_stock.date, open=df_stock.open, high=df_stock.high, 
            low=df_stock.low, close=df_stock.close, name="K線"
        )])
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
            st.success(f"🎯 推薦觀察：該股量價慣性強，歷史勝率達 {win_rate}%")
    else:
        st.warning(f"⚠️ 暫時無法取得 {sid} 資料。請確認代碼或檢查 Token 狀態。")

# --- Tab 2: 全市場掃描 ---
with tab2:
    st.header("今日量價強勢掃描")
    st.write("過濾條件：漲幅 > 3% 且 成交量 > 2000 張")
    
    if st.button("🚀 啟動閃電掃描"):
        with st.spinner("正在進行平行運算處理..."):
            try:
                df_all = dl.taiwan_stock_daily_all()
                if df_all is not None and not df_all.empty:
                    potential = df_all[(df_all['return_rate'] > 3) & (df_all['Volume'] > 2000)].to_dict('records')
                    
                    if potential:
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            results = list(executor.map(fetch_scanner_data, potential))
                        
                        final_df = pd.DataFrame([r for r in results if r is not None])
                        st.dataframe(final_df, use_container_width=True, hide_index=True)
                        st.success(f"掃描完成！共發現 {len(final_df)} 檔潛在標的。")
                    else:
                        st.info("今日市場動能較弱，未偵測到符合條件標的。")
                else:
                    st.error("無法取得市場行情，請稍後再試。")
            except Exception as e:
                st.error(f"掃描發生錯誤: {e}")

st.caption("數據來源：FinMind API | 系統開發者：AI Thought Partner")