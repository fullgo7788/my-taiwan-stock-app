import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 初始化與介面設定 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請務必檢查此處 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 強化版數據抓取引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        # 增加短暫延遲避免被 API 阻擋
        time.sleep(0.05)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except Exception as e:
        st.sidebar.caption(f"⚠️ API 請求異常: {dataset}")
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 排除權證與非股票標的
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
    # Token 狀態偵測燈
    if "你的" in FINMIND_TOKEN:
        st.error("❌ Token 尚未填寫")
    else:
        st.success("✅ Token 已帶入")
        
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 鎖碼雷達"] if is_vip else []))

# --- Tab 1: 個股診斷 ---
with tabs[0]:
    # 診斷需要較長的時間跨度 (150天)
    start_dt = (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        st.subheader(f"📈 {target_display}")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22', name="K線"))
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                st.write("💎 千張大戶持股比例趨勢 (%)")
                fig_h = go.Figure(data=[go.Scatter(x=bh['date'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                fig_h.update_layout(height=250, template="plotly_dark")
                st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 此標的目前無資料，請確認是否為新上櫃公司或代號正確。")

# --- Tab 2: 強勢掃描 (強化自動尋找交易日) ---
with tabs[1]:
    st.subheader("📡 今日爆量強勢股雷達")
    st.write("篩選準則：漲幅 > 3% 且 成交張數 > 2000張")
    
    if st.button("啟動強勢掃描"):
        with st.spinner("雷達搜尋中...正在過濾最近一個交易日數據..."):
            found_data = False
            # 往回尋找最近 7 天，解決連假與週末問題
            for i in range(7):
                scan_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=scan_date)
                
                if not all_p.empty:
                    # 只取當天的數據進行篩選
                    day_data = all_p[all_p['date'] == scan_date]
                    if not day_data.empty:
                        # 2000000 股 = 2000 張
                        res = day_data[(day_data['close'] > day_data['open'] * 1.03) & (day_data['trading_volume'] >= 2000000)].copy()
                        if not res.empty:
                            res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
                            # 併入股票名稱
                            res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                            st.success(f"✅ 掃描完成！顯示日期：{scan_date}")
                            st.dataframe(res[['stock_id', 'stock_name', 'close', '漲幅%', 'trading_volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                            found_data = True
                            break
            
            if not found_data:
                st.error("❌ 掃描失敗：API 未回傳近 7 日資料。請確認 Token 是否有效或今日伺服器是否維護。")