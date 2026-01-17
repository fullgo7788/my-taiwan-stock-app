import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="台股量價籌碼決策系統", layout="wide")

FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 核心數據安全處理函數 ---

def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.1) 
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if isinstance(df, pd.DataFrame) and not df.empty:
            # 強制將欄位名稱轉為小寫
            df.columns = [col.lower() for col in df.columns]
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_comprehensive_data(stock_id):
    start_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    df_p = safe_get_data("TaiwanStockPrice", stock_id, start_date)
    df_h = safe_get_data("TaiwanStockShareholding", stock_id, start_date)
    df_i = safe_get_data("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date)
    return df_p, df_h, df_i

@st.cache_data(ttl=86400)
def get_stock_options():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df['display'].tolist(), df.set_index('display')['stock_id'].to_dict()
    return ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. UI 佈局 ---

options, name_to_id = get_stock_options()

with st.sidebar:
    st.header("🔍 標的選擇")
    selected_stock = st.selectbox("搜尋代碼或名稱", options, index=0)
    target_sid = name_to_id[selected_stock]
    st.divider()
    bias_limit = st.slider("健康乖離率門檻 (%)", 5, 15, 10)

price_raw, holder_raw, inst_raw = fetch_comprehensive_data(target_sid)

if not price_raw.empty:
    df = price_raw.rename(columns={'max':'high', 'min':'low', 'trading_volume':'volume'})
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
    
    # --- 大戶籌碼核心修正區 ---
    big_holders = pd.DataFrame()
    if not holder_raw.empty:
        # 動態偵測欄位名稱 (有些版本是 hold_class, 有些是 holdclass)
        cols = holder_raw.columns.tolist()
        class_col = next((c for c in cols if 'class' in c), None)
        
        if class_col:
            # 確保內容匹配 (有些資料夾雜空白)
            big_holders = holder_raw[holder_raw[class_col].astype(str).str.contains('1000以上')].copy()
            if not big_holders.empty:
                big_holders = big_holders.sort_values('date')
    
    # --- 性格分析 ---
    vol = ((df['high'].tail(20) - df['low'].tail(20)) / df['close'].tail(20)).mean() * 100
    strength = (df.tail(40)['close'] > df.tail(40)['ma20']).sum() / 40
    tag, tag_color = ("⚡ 短線爆發型", "orange") if vol > 4.5 else (("📈 長線趨勢型", "lime") if strength > 0.8 else ("🌀 區間震盪型", "cyan"))

    # --- 介面呈現 ---
    st.markdown(f"<div style='background-color: #1e1e1e; padding: 20px; border-radius: 10px; border-left: 10px solid {tag_color};'><h2 style='margin:0; color: {tag_color};'>{selected_stock} | {tag}</h2></div>", unsafe_allow_html=True)
    
    st.divider()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("當前股價", f"{df['close'].iloc[-1]}", f"{round(df['close'].pct_change().iloc[-1]*100, 2)}%")
    m2.metric("20MA 乖離率", f"{round(df['bias'].iloc[-1], 2)}%", delta_color="inverse")
    
    if not big_holders.empty:
        change = round(big_holders['percent'].iloc[-1] - big_holders['percent'].iloc[-2], 2)
        m3.metric("千張大戶持股", f"{big_holders['percent'].iloc[-1]}%", f"{change}%")
    else:
        m3.metric("千張大戶持股", "無資料")

    if not inst_raw.empty:
        net_buy = inst_raw.tail(9)['buy'].sum() - inst_raw.tail(9)['sell'].sum()
        m4.metric("法人近三日買超", f"{int(net_buy/1000)}k")
    else:
        m4.metric("法人買超", "無資料")

    # 圖表
    tab_k, tab_h = st.tabs(["📊 技術分析 K 線圖", "💎 大戶籌碼趨勢"])
    with tab_k:
        fig_k = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線")])
        fig_k.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='cyan', width=2), name="月線"))
        fig_k.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_k, use_container_width=True)
    
    with tab_h:
        if not big_holders.empty:
            fig_h = go.Figure(go.Scatter(x=big_holders['date'].tail(12), y=big_holders['percent'].tail(12), mode='lines+markers', line=dict(color='gold', width=3)))
            fig_h.update_layout(height=400, template="plotly_dark", title="大戶持股比例 (近12週)")
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.info("無籌碼週資料")
else:
    st.error("⚠️ 無法取得數據。請確認 Token 或該股是否有今日交易。")