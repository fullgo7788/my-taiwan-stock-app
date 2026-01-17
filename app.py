import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與視覺風格 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請在此填入您的 FinMind Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據抓取與指標計算引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.05)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

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
stock_options = master_info['display'].tolist() if not master_info.empty else ["2330 台積電"]
name_to_id = master_info.set_index('display')['stock_id'].to_dict() if not master_info.empty else {"2330 台積電": "2330"}

# --- 3. 側邊欄與分頁 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 診斷分析", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 診斷分析 (K線 + RSI + 籌碼) ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        df['rsi'] = calculate_rsi(df)
        df['date_str'] = df['date'].astype(str) # 連續 K 線關鍵
        
        # 繪圖佈局：K線(70%) + RSI(30%)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.7, 0.3])
        
        # 主圖：K線與20MA
        fig.add_trace(go.Candlestick(
            x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22', name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"), row=1, col=1)
        
        # 副圖：RSI
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], line=dict(color='#E6E6FA', width=2), name="RSI(14)"), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#FF4B4B", row=2, col=1) # 超買區
        fig.add_hline(y=30, line_dash="dash", line_color="#00FF00", row=2, col=1) # 超賣區

        fig.update_xaxes(type='category', nticks=12) # 類別軸排除週末
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
        
        # 底部：大戶趨勢
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), h_df.columns[2])
            bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
            bh['date_str'] = bh['date'].astype(str)
            st.markdown("### 💎 千張大戶持股比例變動")
            fig_h = go.Figure(data=[go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
            fig_h.update_xaxes(type='category', nticks=8)
            fig_h.update_layout(height=250, template="plotly_dark", margin=dict(t=10, b=10))
            st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.error(f"❌ 無法獲取 {target_sid} 的資料。請確認代號正確或 Token 額度充足。")

# --- Tab 2: 強勢掃描 (自動日期尋找) ---
with tabs[1]:
    st.subheader("📡 強勢股爆量雷達")
    if st.button("點擊啟動全市場掃描"):
        with st.spinner("雷達掃描中...自動回溯最近交易日..."):
            found = False
            for i in range(10):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    day_p = all_p[all_p['date'] == d]
                    if not day_p.empty:
                        res = day_p[(day_p['close'] > day_p['open'] * 1.03) & (day_p['trading_volume'] >= 2000000)].copy()
                        if not res.empty:
                            res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
                            res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                            st.success(f"✅ 成功掃描資料日期：{d}")
                            st.dataframe(res[['stock_id', 'stock_name', 'close', '漲幅%', 'trading_volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                            found = True; break
            if not found: st.error("❌ 抓不到資料，可能已達 API 今日上限。")