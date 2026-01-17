import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化 ---
st.set_page_config(page_title="台股量價籌碼決策系統", layout="wide")

FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 核心數據抓取 (加入欄位防錯) ---

@st.cache_data(ttl=3600)
def fetch_data(stock_id):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
    
    # 抓取股價
    df_p = dl.get_data(dataset="TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    # 抓取大戶持股
    df_h = dl.get_data(dataset="TaiwanStockShareholding", data_id=stock_id, start_date=start_date)
    
    # 強制欄位轉小寫防止 KeyError
    if isinstance(df_p, pd.DataFrame) and not df_p.empty:
        df_p.columns = [col.lower() for col in df_p.columns]
    if isinstance(df_h, pd.DataFrame) and not df_h.empty:
        df_h.columns = [col.lower() for col in df_h.columns]
        
    return df_p, df_h

# --- 3. UI 與邏輯處理 ---
# (中間的性格判定與清單代碼保持不變，直接看處理 big_holders 的地方)

# ... (省略部分重複代碼)

price_raw, holder_raw = fetch_data(target_sid)

if not price_raw.empty:
    df = price_raw.rename(columns={'max':'high','min':'low','trading_volume':'volume'})
    # ... (均線計算與性格判定)

    # --- 修正後的籌碼處理區 ---
    big_holders = pd.DataFrame()
    if not holder_raw.empty:
        # 確保 hold_class 欄位存在 (有時可能是 holdclass 或 HoldClass)
        target_col = 'hold_class' if 'hold_class' in holder_raw.columns else None
        if target_col:
            big_holders = holder_raw[holder_raw[target_col] == '1000以上'].copy()
            # 確保有資料才顯示
            if not big_holders.empty:
                big_holders = big_holders.sort_values('date').tail(12)

    # --- 顯示介面 ---
    # (指標顯示區 m1, m2, m3...)
    if not big_holders.empty:
        change = round(big_holders['percent'].iloc[-1] - big_holders['percent'].iloc[-2], 2)
        st.metric("千張大戶持股", f"{big_holders['percent'].iloc[-1]}%", f"{change}%")
    else:
        st.metric("千張大戶持股", "暫無週資料")

    # --- 圖表分頁 ---
    tab_k, tab_hold = st.tabs(["📊 技術分析 K 線", "💎 千張大戶籌碼"])
    
    with tab_k:
        # ... (K線繪圖)
        st.plotly_chart(fig_k, use_container_width=True)
        
    with tab_hold:
        if not big_holders.empty:
            fig_h = go.Figure()
            fig_h.add_trace(go.Scatter(
                x=big_holders['date'], 
                y=big_holders['percent'], 
                mode='lines+markers', 
                line=dict(color='gold', width=3),
                name="千張大戶"
            ))
            fig_h.update_layout(height=400, template="plotly_dark", title=f"{target_sid} 近 12 週大戶持股比例")
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.info("💡 該個股暫無大戶持股數據 (部分權證或新上櫃股可能無資料)。")