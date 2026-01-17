import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import re

# --- 1. 系統初始化 ---
st.set_page_config(page_title="台股 AI 高速決策系統", layout="wide")

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

# --- 2. 高速數據處理函數 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        # 移除不必要的 sleep，改用高效抓取
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 修正 3629 名稱
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_stock_info():
    """加速關鍵：一次性過濾掉權證與非股票標的"""
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 修正 3629
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        
        # 排除權證邏輯：僅保留代號長度 <= 5 且純數字的標的 (權證通常 6 碼且含英文)
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        
        # 排除 ETF (通常 00 開頭) 的話可以視需求調整，目前保留普通股
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

# 初始化緩存資料
stock_info_full = get_clean_stock_info()
if not stock_info_full.empty:
    options = stock_info_full['display'].tolist()
    name_to_id = stock_info_full.set_index('display')['stock_id'].to_dict()
else:
    options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. VIP 高速掃描邏輯 ---
def scan_accumulation_logic(info_df):
    # 預過濾資本額
    small_caps = info_df[(info_df['capital'] <= 3000000000) & (info_df['capital'] >= 100000000)]
    small_ids = small_caps['stock_id'].tolist()

    # 取得最新報價
    today = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
    all_p = safe_get_data("TaiwanStockPrice", start_date=today)
    if all_p.empty: return pd.DataFrame()
    
    # 提速關鍵：先濾股價橫盤，再濾成交量，最後才查籌碼
    all_p['chg'] = ((all_p['close'] / all_p['open']) - 1) * 100
    candidates = all_p[
        (all_p['stock_id'].isin(small_ids)) & 
        (all_p['chg'] >= -1.5) & (all_p['chg'] <= 2.5) &
        (all_p['trading_volume'] > 500000) # 成交量 > 500 張
    ].sort_values('trading_volume', ascending=False).head(20) # 只深度查前 20 名
    
    potential_list = []
    h_start = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
    
    for i, (idx, row) in enumerate(candidates.iterrows()):
        sid = row['stock_id']
        h_df = safe_get_data("TaiwanStockShareholding", sid, h_start)
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                big_h = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if len(big_h) >= 2 and big_h['percent'].iloc[-1] > big_h['percent'].iloc[-2]:
                    s_name = small_caps[small_caps['stock_id'] == sid]['stock_name'].values[0]
                    potential_list.append({
                        "代號": sid, "名稱": s_name, "收盤": row['close'], 
                        "漲幅%": round(row['chg'], 2), 
                        "大戶趨勢": f"{big_h['percent'].iloc[-2]}% ➔ {big_h['percent'].iloc[-1]}%", 
                        "增持%": round(big_h['percent'].iloc[-1] - big_h['percent'].iloc[-2], 2)
                    })
    return pd.DataFrame(potential_list)

# --- 4. UI 介面 ---
with st.sidebar:
    st.title("🎯 高速籌碼雷達")
    # 下拉選單現在已排除權證，搜尋會變超快
    selected_stock = st.selectbox("標的診斷", options)
    target_sid = name_to_id[selected_stock]
    st.divider()
    license_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (license_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 中小鎖碼股"] if is_vip else []))

# --- Tab 1: 個股診斷 ---
with tabs[0]:
    # 診斷頁也優化：只抓必要日期範圍
    start_dt = (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low', 'trading_volume':'volume'})
        df['ma20'] = df['close'].rolling(20).mean()
        
        st.subheader(f"📈 {selected_stock}")
        fig_k = go.Figure()
        fig_k.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22',
            increasing_fillcolor='#FF3333', decreasing_fillcolor='#228B22', name="K線"
        ))
        fig_k.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        fig_k.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_k, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                big_h_all = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                st.write("💎 千張大戶持股比趨勢")
                fig_h = go.Figure(data=[go.Scatter(x=big_h_all['date'], y=big_h_all['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                fig_h.update_layout(height=250, template="plotly_dark")
                st.plotly_chart(fig_h, use_container_width=True)

# --- Tab 2 & 3 保持邏輯但加速 ---
if is_vip:
    with tabs[2]:
        st.subheader("💎 VIP 中小鎖碼股 (高速過濾版)")
        if st.button("啟動 VIP 深度雷達"):
            with st.spinner("正在快速比對籌碼..."):
                res = scan_accumulation_logic(stock_info_full)
                if not res.empty:
                    st.table(res.sort_values("增持%", ascending=False))
                else:
                    st.info("目前無符合條件之標的。")