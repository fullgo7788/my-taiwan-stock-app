import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請填入您的 FinMind Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據抓取引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

master_info = get_clean_master_info()
if not master_info.empty:
    stock_options = master_info['display'].tolist()
    name_to_id = master_info.set_index('display')['stock_id'].to_dict()
else:
    stock_options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 鎖碼雷達"] if is_vip else []))

# --- Tab 1: 個股診斷 (修正圖表不顯示問題) ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    
    if not p_df.empty:
        # 資料清洗與排序
        df = p_df.copy()
        df = df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        # 將日期轉為字串格式，避免 Plotly 解析錯誤
        df['date_str'] = df['date'].astype(str)
        
        st.subheader(f"📈 {target_display}")
        
        fig = go.Figure()
        
        # 繪製 K 線
        fig.add_trace(go.Candlestick(
            x=df['date_str'], 
            open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22',
            increasing_fillcolor='#FF3333', decreasing_fillcolor='#228B22', 
            name="K線"
        ))
        
        # 繪製 20MA
        fig.add_trace(go.Scatter(
            x=df['date_str'], y=df['ma20'], 
            line=dict(color='#00CED1', width=1.5), 
            name="20MA"
        ))
        
        # 圖表設定：修正顯示問題
        fig.update_xaxes(
            type='category', 
            nticks=15, 
            tickangle=-45,
            rangeslider_visible=False  # 關閉滑桿增加穩定性
        )
        fig.update_layout(
            height=500, 
            template="plotly_dark", 
            margin=dict(l=10, r=10, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 大戶籌碼圖
        if not h_df.empty:
            bh = h_df[h_df.iloc[:, 2].astype(str).str.contains('1000以上')].sort_values('date')
            bh['date_str'] = bh['date'].astype(str)
            st.write("💎 千張大戶持股比例趨勢 (%)")
            fig_h = go.Figure(data=[go.Scatter(
                x=bh['date_str'], y=bh['percent'], 
                mode='lines+markers', 
                line=dict(color='#FFD700', width=2),
                marker=dict(size=8)
            )])
            fig_h.update_xaxes(type='category', nticks=10, tickangle=-45)
            fig_h.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 無法獲取股價資料，請檢查 API Token 是否填寫正確。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    st.subheader("📡 強勢股掃描 (漲幅>3% 且 2000張以上)")
    if st.button("啟動雷達"):
        with st.spinner("掃描最近交易日中..."):
            found = False
            for i in range(7):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    day_p = all_p[all_p['date'] == d]
                    if not day_p.empty:
                        res = day_p[(day_p['close'] > day_p['open'] * 1.03) & (day_p['trading_volume'] >= 2000000)].copy()
                        if not res.empty:
                            res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
                            res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                            st.success(f"✅ 掃描日期：{d}")
                            st.dataframe(res[['stock_id', 'stock_name', 'close', '漲幅%', 'trading_volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                            found = True
                            break
            if not found:
                st.error("❌ 無法取得資料。")