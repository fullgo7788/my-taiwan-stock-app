import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 核心初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【填入您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.1) # 增加穩定性
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_id' in df.columns:
                df['stock_id'] = df['stock_id'].astype(str)
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

def calculate_rsi(df, period=14):
    if len(df) < period: return pd.Series([np.nan] * len(df))
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

# 載入主資料集
master_info = get_clean_master_info()
stock_options = master_info['display'].tolist() if not master_info.empty else ["2330 台積電"]
name_to_id = master_info.set_index('display')['stock_id'].to_dict() if not master_info.empty else {"2330 台積電": "2330"}

# --- 3. UI 側邊欄 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password", help="輸入後請按 Enter")
    is_vip = (user_key == VIP_KEY)
    if is_vip:
        st.success("✅ VIP 權限已開啟")

tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 診斷分析 ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, (datetime.now()-timedelta(days=90)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        df['rsi'] = calculate_rsi(df)
        df['date_str'] = df['date'].astype(str)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                                     increasing_line_color='#FF3333', decreasing_line_color='#228B22', name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], line=dict(color='#E6E6FA', width=2), name="RSI(14)"), row=2, col=1)
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=550, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date').copy()
                if not bh.empty:
                    bh['date_str'] = bh['date'].astype(str)
                    st.markdown("### 💎 千張大戶持股趨勢 (%)")
                    fig_h = go.Figure(data=[go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                    fig_h.update_xaxes(type='category', nticks=5)
                    fig_h.update_layout(height=250, template="plotly_dark")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.error("此標的目前無資料，請確認 Token 或代號。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    st.subheader("📡 強勢股爆量掃描")
    if st.button("啟動強勢雷達", key="scan_btn_tab2"):
        with st.spinner("掃描最近一個交易日..."):
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
                            st.success(f"✅ 掃描基準日：{d}")
                            st.dataframe(res[['stock_id', 'stock_name', 'close', '漲幅%', 'trading_volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                            found = True; break
            if not found: st.error("目前抓不到行情資料，請稍後再試。")

# --- Tab 3: VIP 鎖碼雷達 (修復執行邏輯) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請在側邊欄輸入 VIP 授權碼以解鎖功能。")
    else:
        st.subheader("🚀 資本額鎖碼掃描 (30億內+大戶增持)")
        if st.button("執行 VIP 鎖碼掃描", key="vip_scan_btn"):
            with st.spinner("深度分析全市場小盤股籌碼..."):
                small_caps = master_info[(master_info['capital'] <= 3000000000) & (master_info['capital'] >= 100000000)]
                small_ids = small_caps['stock_id'].tolist()
                
                # 取得最新收盤日股價
                today_p = pd.DataFrame()
                for i in range(5):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_p = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_p.empty: break
                
                if not today_p.empty:
                    # 篩選量大且資本額小的股票
                    cands = today_p[(today_p['stock_id'].isin(small_ids)) & (today_p['trading_volume'] >= 500000)].head(15)
                    final_res = []
                    for _, row in cands.iterrows():
                        sid = row['stock_id']
                        h_check = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=21)).strftime('%Y-%m-%d'))
                        if not h_check.empty:
                            c_col = next((c for c in h_check.columns if 'class' in c), None)
                            if c_col:
                                bh = h_check[h_check[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2 and bh['percent'].iloc[-1] > bh['percent'].iloc[-2]:
                                    s_name = small_caps[small_caps['stock_id'] == sid]['stock_name'].values[0]
                                    final_res.append({
                                        "代號": sid, "名稱": s_name, "收盤": row['close'],
                                        "大戶前次": f"{bh['percent'].iloc[-2]}%", "大戶最新": f"{bh['percent'].iloc[-1]}%",
                                        "增幅": round(bh['percent'].iloc[-1] - bh['percent'].iloc[-2], 2)
                                    })
                    if final_res:
                        st.table(pd.DataFrame(final_res).sort_values("增幅", ascending=False))
                    else:
                        st.info("今日無符合鎖碼條件之標的。")
                else:
                    st.error("暫時抓不到股價資料。")