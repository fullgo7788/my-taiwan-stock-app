import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 系統初始化 ---
st.set_page_config(page_title="台股量價籌碼決策系統", layout="wide")

# 【請填入你的 FinMind Token】
FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 核心數據處理函數 ---

@st.cache_data(ttl=86400)
def get_stock_options():
    try:
        df = dl.get_data(dataset="TaiwanStockInfo")
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df['display'].tolist(), df.set_index('display')['stock_id'].to_dict()
    except:
        return ["2330 台積電"], {"2330 台積電": "2330"}

@st.cache_data(ttl=3600)
def fetch_comprehensive_data(stock_id):
    start_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    
    df_p = dl.get_data(dataset="TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    df_h = dl.get_data(dataset="TaiwanStockShareholding", data_id=stock_id, start_date=start_date)
    df_i = dl.get_data(dataset="TaiwanStockInstitutionalInvestorsBuySell", data_id=stock_id, start_date=start_date)
    
    for df in [df_p, df_h, df_i]:
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            
    return df_p, df_h, df_i

def get_personality(df):
    if len(df) < 40: return "數據不足", "gray", ""
    vol = ((df['high'].tail(20) - df['low'].tail(20)) / df['close'].tail(20)).mean() * 100
    strength = (df.tail(40)['close'] > df.tail(40)['close'].rolling(20).mean()).sum() / 40
    
    if vol > 4.5: return "⚡ 短線爆發型", "orange", "波幅劇烈，適合極短線價差。"
    elif strength > 0.8: return "📈 長線趨勢型", "lime", "趨勢穩健，建議沿月線布局。"
    else: return "🌀 區間震盪型", "cyan", "盤整蓄勢中，建議高拋低吸。"

# --- 3. UI 佈局 ---

options, name_to_id = get_stock_options()

with st.sidebar:
    st.header("🔍 標的選擇")
    selected_stock = st.selectbox("搜尋代碼或名稱", options, index=0)
    target_sid = name_to_id[selected_stock]
    
    st.divider()
    bias_limit = st.slider("健康乖離率門檻 (%)", 5, 15, 10)
    hold_days = st.select_slider("回測持有天數", options=[1, 3, 5, 10], value=3)

price_raw, holder_raw, inst_raw = fetch_comprehensive_data(target_sid)

if not price_raw.empty:
    df = price_raw.rename(columns={'max':'high', 'min':'low', 'trading_volume':'volume'})
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
    
    tag, tag_color, desc = get_personality(df)
    
    st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 20px; border-radius: 10px; border-left: 10px solid {tag_color};">
            <h2 style="margin:0; color: {tag_color};">{selected_stock} | {tag}</h2>
            <p style="margin:5px 0 0 0; color: #dcdcdc; font-size: 16px;">{desc}</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()

    m1, m2, m3, m4 = st.columns(4)
    curr_price = df['close'].iloc[-1]
    m1.metric("當前股價", f"{curr_price}", f"{round(df['close'].pct_change().iloc[-1]*100, 2)}%")
    
    curr_bias = round(df['bias'].iloc[-1], 2)
    m2.metric("20MA 乖離率", f"{curr_bias}%", delta=f"{curr_bias}%", delta_color="inverse" if curr_bias > bias_limit else "normal")
    
    big_holders = pd.DataFrame()
    if not holder_raw.empty:
        target_col = 'hold_class' if 'hold_class' in holder_raw.columns else None
        if target_col:
            big_holders = holder_raw[holder_raw[target_col] == '1000以上'].sort_values('date')
            if not big_holders.empty:
                change = round(big_holders['percent'].iloc[-1] - big_holders['percent'].iloc[-2], 2)
                m3.metric("千張大戶持股", f"{big_holders['percent'].iloc[-1]}%", f"{change}%")
    
    # 修正錯別字：將 "吳週資料" 改為 "無週資料"
    if big_holders.empty: m3.metric("千張大戶持股", "無週資料")

    if not inst_raw.empty:
        inst_sum = inst_raw.tail(9)
        net_buy = inst_sum['buy'].sum() - inst_sum['sell'].sum()
        m4.metric("法人近三日買超", f"{int(net_buy/1000)}k")
    else: m4.metric("法人買超", "無資料")

    st.subheader("🛡️ 智慧操盤建議")
    tp_rate = 0.07 if "短線" in tag else 0.15
    sl_rate = 0.04 if "短線" in tag else 0.07
    
    c_tp, c_sl, c_rr = st.columns(3)
    c_tp.info(f"建議分批停利位：**{round(curr_price*(1+tp_rate), 2)}** (+{int(tp_rate*100)}%)")
    c_sl.warning(f"硬性保護停損位：**{round(curr_price*(1-sl_rate), 2)}** (-{int(sl_rate*100)}%)")
    c_rr.write(f"當前盈虧比：**{round(tp_rate/sl_rate, 2)}**")

    tab_k, tab_holder = st.tabs(["📊 技術分析 K 線圖", "💎 大戶籌碼趨勢圖"])
    
    with tab_k:
        fig_k = go.Figure()
        fig_k.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"))
        fig_k.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='cyan', width=2), name="月線 (20MA)"))
        fig_k.add_hline(y=curr_price*(1+tp_rate), line_dash="dot", line_color="green", opacity=0.5)
        fig_k.add_hline(y=curr_price*(1-sl_rate), line_dash="dot", line_color="red", opacity=0.5)
        fig_k.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10))
        st.plotly_chart(fig_k, use_container_width=True)

    with tab_holder:
        if not big_holders.empty:
            fig_h = go.Figure()
            fig_h.add_trace(go.Scatter(x=big_holders['date'].tail(12), y=big_holders['percent'].tail(12), mode='lines+markers', line=dict(color='gold', width=3)))
            fig_h