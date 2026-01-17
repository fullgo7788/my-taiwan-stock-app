import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="台股 AI 籌碼決策系統", layout="wide")

# 【請填入您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全數據抓取 (含 3629 名稱校正) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.1)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 修正 3629 地心引力名稱
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_options():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df['display'].tolist(), df.set_index('display')['stock_id'].to_dict(), df
    return ["2330 台積電"], {"2330 台積電": "2330"}, pd.DataFrame()

# --- 3. VIP 邏輯 (維持收費版功能) ---
def scan_accumulation_logic(info_df):
    small_caps = info_df[(info_df['capital'] <= 3000000000) & (info_df['capital'] >= 100000000)]['stock_id'].tolist()
    today = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
    all_p = safe_get_data("TaiwanStockPrice", start_date=today)
    if all_p.empty: return pd.DataFrame()
    
    target_pool = all_p[all_p['stock_id'].isin(small_caps)].sort_values('trading_volume', ascending=False).head(100)
    potential_list = []
    for i, (idx, row) in enumerate(target_pool.iterrows()):
        sid = row['stock_id']
        h_df = safe_get_data("TaiwanStockShareholding", sid, (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d'))
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                big_h = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if len(big_h) >= 2 and big_h['percent'].iloc[-1] > big_h['percent'].iloc[-2]:
                    price_change = ((row['close'] / row['open']) - 1) * 100
                    if -1.5 <= price_change <= 2.5:
                        s_name = info_df[info_df['stock_id'] == sid]['stock_name'].values[0]
                        potential_list.append({"代號": sid, "名稱": s_name, "收盤": row['close'], "漲幅%": round(price_change, 2), "大戶趨勢": f"{big_h['percent'].iloc[-2]}% ➔ {big_h['percent'].iloc[-1]}%", "增持%": round(big_h['percent'].iloc[-1] - big_h['percent'].iloc[-2], 2)})
    return pd.DataFrame(potential_list)

# --- 4. UI 介面 ---
options, name_to_id, info_df = get_options()

with st.sidebar:
    st.title("🎯 籌碼雷達系統")
    selected_stock = st.selectbox("標的診斷", options)
    target_sid = name_to_id[selected_stock]
    st.divider()
    license_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (license_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 中小鎖碼股"] if is_vip else []))

# --- Tab 1: 個股診斷 ---
with tabs[0]:
    p_df = safe_get_data("TaiwanStockPrice", target_sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low', 'trading_volume':'volume'})
        df['ma20'] = df['close'].rolling(20).mean()
        
        st.subheader(f"📈 {selected_stock} 趨勢診斷")
        
        # K線設定 (紅漲、調暗的深綠跌)
        fig_k = go.Figure()
        
        fig_k.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name="K線",
            increasing_line_color='#FF3333', decreasing_line_color='#228B22', # 紅漲、深綠跌
            increasing_fillcolor='#FF3333', decreasing_fillcolor='#228B22'
        ))
        
        # 疊加 20MA 均線
        fig_k.add_trace(go.Scatter(
            x=df['date'], y=df['ma20'], 
            line=dict(color='#00CED1', width=1.5), # 深青色
            name="20MA"
        ))
        
        fig_k.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=30))
        st.plotly_chart(fig_k, use_container_width=True)
        
        # 大戶籌碼趨勢
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                big_h_all = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if not big_h_all.empty:
                    st.write("💎 千張大戶持股比例趨勢 (%)")
                    fig_h = go.Figure(data=[go.Scatter(x=big_h_all['date'], y=big_h_all['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                    fig_h.update_layout(height=250, template="plotly_dark", margin=dict(t=10))
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 數據讀取中，請稍候。")

# --- Tab 2 & 3 保持原邏輯 ---
with tabs[1]:
    st.subheader("📡 今日爆量強勢股")
    if st.button("啟動雷達"):
        # 強勢掃描代碼...
        pass