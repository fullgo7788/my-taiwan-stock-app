import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 初始化 ---
st.set_page_config(page_title="台股量價籌碼系統", layout="wide")

FINMIND_TOKEN = "fullgo" # 請務必填入有效 Token

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全抓取函數 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.2) # 增加延遲避免被封鎖
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            return df
    except Exception as e:
        print(f"Error fetching {dataset}: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_stock_options():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df['display'].tolist(), df.set_index('display')['stock_id'].to_dict()
    return ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
options, name_to_id = get_stock_options()

with st.sidebar:
    st.header("🔍 決策中心")
    selected_stock = st.selectbox("搜尋標的", options, index=0)
    target_sid = name_to_id[selected_stock]
    bias_limit = st.slider("乖離警示門檻 (%)", 5, 15, 10)
    st.info("💡 貼心提醒：全市場掃描建議在 14:30 後執行，資料最為完整。")

tab1, tab2 = st.tabs(["📊 個股深度診斷", "📡 強勢股雷達掃描"])

with tab1:
    # 抓取資料
    start_date = (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_date)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_date)
    
    if not p_df.empty:
        # 計算指標
        df = p_df.rename(columns={'max':'high', 'min':'low', 'trading_volume':'volume'})
        df['ma20'] = df['close'].rolling(20).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        
        # 性格分析 (強化防禦)
        if len(df) >= 20:
            vol = ((df['high'].tail(20) - df['low'].tail(20)) / df['close'].tail(20)).mean() * 100
            strength = (df.tail(20)['close'] > df.tail(20)['ma20']).sum()
            
            if vol > 4.5:
                tag, color, desc = "⚡ 短線爆發型", "orange", "波幅較大，注意追高風險。"
            elif strength >= 15:
                tag, color, desc = "📈 長線趨勢型", "lime", "處於多頭慣性，適合回檔佈局。"
            else:
                tag, color, desc = "🌀 區間震盪型", "cyan", "盤整蓄勢，觀察放量突破。"
        else:
            tag, color, desc = "⏳ 數據積累中", "gray", "資料不足 20 日，難以判定性格。"

        # 頂部看板
        st.markdown(f"<div style='background-color: #1e1e1e; padding: 20px; border-radius: 10px; border-left: 10px solid {color};'><h2 style='margin:0; color: {color};'>{selected_stock} | {tag}</h2><p style='margin:5px 0 0 0; color: #dcdcdc;'>{desc}</p></div>", unsafe_allow_html=True)
        
        # 核心數據
        c1, c2, c3 = st.columns(3)
        curr_price = df['close'].iloc[-1]
        c1.metric("當前股價", f"{curr_price}", f"{round(df['close'].pct_change().iloc[-1]*100, 2)}%")
        c2.metric("20MA 乖離", f"{round(df['bias'].iloc[-1], 2)}%", delta_color="inverse" if df['bias'].iloc[-1] > bias_limit else "normal")
        
        # 大戶資料
        big_h = pd.DataFrame()
        if not h_df.empty:
            col = next((c for c in h_df.columns if 'class' in c), None)
            if col:
                big_h = h_df[h_df[col].astype(str).str.contains('1000以上')].sort_values('date')
        
        if not big_h.empty:
            change = round(big_h['percent'].iloc[-1] - big_h['percent'].iloc[-2], 2)
            c3.metric("千張大戶持股", f"{big_h['percent'].iloc[-1]}%", f"{change}%")
        else:
            c3.metric("大戶持股", "無資料")

        # K線圖
        fig = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線")])
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='cyan', width=2), name="月線"))
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("無法讀取個股資料，請檢查 Token 有效性。")

with tab2:
    st.subheader("🚀 全市場法人強勢雷達")
    st.write("過濾條件：漲幅 > 3% 且 成交張數 > 2,000張")
    
    if st.button("啟動雷達掃描"):
        with st.spinner("掃描全台股資料中..."):
            # 取得最近一個交易日的資料 (考慮周末)
            scan_date = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
            all_data = safe_get_data("TaiwanStockPrice", start_date=scan_date)
            
            if not all_data.empty:
                # 篩選邏輯
                res = all_data[
                    (all_data['close'] > all_data['open'] * 1.03) & 
                    (all_data['trading_volume'] > 2000000)
                ].copy()
                
                if not res.empty:
                    res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
                    res['成交張數'] = (res['trading_volume'] / 1000).astype(int)
                    
                    st.success(f"掃描完畢！共有 {len(res)} 檔標的符合。")
                    st.dataframe(res[['stock_id', 'close', '漲幅%', '成交張數']].sort_values('漲幅%', ascending=False), use_container_width=True)
                else:
                    st.info("今日無符合爆量起漲條件之標的。")
            else:
                st.error("無法獲取市場掃描資料，請稍後再試。")