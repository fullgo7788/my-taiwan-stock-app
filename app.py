import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 初始化設定 ---
st.set_page_config(page_title="台股量價籌碼決策系統", layout="wide")

# 【請確認 Token】
FINMIND_TOKEN = "fullgo"

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "你的" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 核心運算邏輯 ---

def get_personality(df):
    if len(df) < 40: return "數據不足", "gray", ""
    vol = ((df['high'].tail(20) - df['low'].tail(20)) / df['close'].tail(20)).mean() * 100
    strength = (df.tail(40)['close'] > df.tail(40)['close'].rolling(20).mean()).sum() / 40
    if vol > 4.5: return "⚡ 短線爆發型", "orange", "波幅劇烈"
    elif strength > 0.8: return "📈 長線趨勢型", "lime", "趨勢穩健"
    else: return "🌀 區間震盪型", "cyan", "盤整蓄勢"

@st.cache_data(ttl=3600)
def fetch_data(stock_id):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
    df_p = dl.get_data(dataset="TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    df_h = dl.get_data(dataset="TaiwanStockShareholding", data_id=stock_id, start_date=start_date)
    return df_p, df_h

# --- 3. UI 介面 ---
st.title("🏹 台股量價籌碼決策系統 (專業風控版)")

@st.cache_data(ttl=86400)
def get_options():
    df = dl.get_data(dataset="TaiwanStockInfo")
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df['display'].tolist(), df.set_index('display')['stock_id'].to_dict()

options, name_to_id = get_options()
selected_stock = st.selectbox("搜尋代碼或名稱", options, index=0)
target_sid = name_to_id[selected_stock]

price_raw, holder_raw = fetch_data(target_sid)

if not price_raw.empty:
    price_raw.columns = [col.lower() for col in price_raw.columns]
    df = price_raw.rename(columns={'max':'high','min':'low','trading_volume':'volume'})
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
    
    tag, color, desc = get_personality(df)
    curr_price = df['close'].iloc[-1]
    
    # --- A. 個股性格與風控面板 ---
    st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; border-left: 10px solid {color}; margin-bottom: 20px;">
            <h2 style="margin:0; color: {color};">{tag} ({selected_stock})</h2>
            <p style="margin:5px 0 0 0; color: #dcdcdc;">診斷結果：{desc}</p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    
    # 根據性格動態計算停損停利 (短線嚴格，長線寬鬆)
    if "短線" in tag:
        tp_rate, sl_rate = 0.07, 0.04  # 7% 停利, 4% 停損
    elif "長線" in tag:
        tp_rate, sl_rate = 0.15, 0.07  # 15% 停利, 7% 停損
    else:
        tp_rate, sl_rate = 0.10, 0.05
    
    with c1:
        st.subheader("🎯 停利建議 (Take Profit)")
        st.write(f"第一目標位：**{round(curr_price*(1+tp_rate*0.6), 2)}** (+{(tp_rate*0.6)*100:.0f}%)")
        st.write(f"最終目標位：**{round(curr_price*(1+tp_rate), 2)}** (+{tp_rate*100:.0f}%)")
        
    with c2:
        st.subheader("🛡️ 停損控管 (Stop Loss)")
        st.markdown(f"<h3 style='color: #ff4b4b;'>{round(curr_price*(1-sl_rate), 2)}</h3>", unsafe_allow_html=True)
        st.write(f"最大容忍回撤：-{sl_rate*100:.0f}%")
        
    with c3:
        st.subheader("📊 風險報酬比 (R/R Ratio)")
        rr_ratio = round((tp_rate / sl_rate), 2)
        st.write(f"當前比率：**{rr_ratio}**")
        if rr_ratio >= 1.5: st.success("✅ 具備盈虧比優勢")
        else: st.warning("⚠️ 盈虧比不佳，慎防追高")

    st.divider()

    # --- B. 技術與籌碼圖表 ---
    tab_k, tab_hold = st.tabs(["📊 技術分析 K 線", "💎 千張大戶籌碼"])
    
    with tab_k:
        fig_k = go.Figure()
        fig_k.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"))
        # 加上停損停利輔助線
        fig_k.add_hline(y=curr_price*(1-sl_rate), line_dash="dot", line_color="red", annotation_text="建議停損區")
        fig_k.add_hline(y=curr_price*(1+tp_rate), line_dash="dot", line_color="green", annotation_text="建議停利區")
        fig_k.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_k, use_container_width=True)
        
    with tab_hold:
        big_holders = holder_raw[holder_raw['hold_class'] == '1000以上'].tail(12)
        if not big_holders.empty:
            fig_h = go.Figure()
            fig_h.add_trace(go.Scatter(x=big_holders['date'], y=big_holders['percent'], mode='lines+markers', line=dict(color='gold', width=3)))
            fig_h.update_layout(height=400, template="plotly_dark", title="千張大戶持股比例趨勢 (%)")
            st.plotly_chart(fig_h, use_container_width=True)
        else: st.info("暫無大戶持股數據")
else:
    st.error("查無資料")