import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請確認您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 (內建重試與延遲) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for attempt in range(2):
        try:
            time.sleep(0.3) # 增加延遲確保穩定
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    backup_df = pd.DataFrame({
        'stock_id': ['2330', '2317', '2454', '3629', '2303'],
        'stock_name': ['台積電', '鴻海', '聯發科', '地心引力', '聯電']
    })
    if df.empty:
        df = backup_df
    else:
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        if 'stock_name' not in df.columns: df['stock_name'] = df['stock_id']
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df

# --- 3. 處理狀態同步 ---
master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()
id_to_name = master_info.set_index('stock_id')['stock_name'].to_dict()

with st.sidebar:
    st.header("⚡ 系統核心")
    # 這是全局唯一的個股驅動源
    target_display = st.selectbox(
        "🎯 選擇個股", 
        options=list(name_to_id.keys()),
        index=list(name_to_id.values()).index('2330') if '2330' in name_to_id.values() else 0,
        key="global_selector"
    )
    sel_sid = name_to_id[target_display]
    sel_sname = id_to_name.get(sel_sid, "未知")
    
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)
    if is_vip: st.success("✅ VIP 權限已解鎖")

# --- 4. 功能分頁 ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (標題完全連動) ---
with tabs[0]:
    st.subheader(f"🔍 診斷報告：{sel_sid} {sel_sname}")
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", sel_sid, (datetime.now()-timedelta(days=100)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"))
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if not bh.empty:
                    bh['date_str'] = bh['date'].dt.strftime('%Y-%m-%d')
                    fig_h = go.Figure(go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', name="大戶%"))
                    fig_h.update_layout(height=250, template="plotly_dark", title=f"💎 {sel_sname} 大戶持股比例")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 資料抓取中或該股今日無交易。")

# --- Tab 2: 強勢掃描 (修正日期邏輯與反應) ---
with tabs[1]:
    st.subheader("📡 強勢股爆量雷達")
    if st.button("啟動雷達掃描", key="btn_t2"):
        with st.spinner("正在搜尋最近一個交易日..."):
            found = False
            for i in range(10): # 增加回溯天數以應對週末
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    # 篩選當日數據
                    day_p = all_p[all_p['date'].dt.strftime('%Y-%m-%d') == d]
                    if not day_p.empty:
                        res = day_p[(day_p['close'] > day_p['open']*1.04) & (day_p['trading_volume'] >= 3000000)].copy()
                        if not res.empty:
                            res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                            st.success(f"✅ 發現日期：{d}")
                            st.dataframe(res[['stock_id', 'stock_name', 'close', 'trading_volume']].sort_values('trading_volume', ascending=False))
                            found = True; break
            if not found: st.info("近期盤面無符合「漲幅>4%且成交量>3000張」之個股。")

# --- Tab 3: VIP 鎖碼雷達 (加入進度反饋) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請輸入 VIP 授權碼。")
    else:
        st.subheader("🚀 鎖碼雷達 (追蹤大戶集結個股)")
        if st.button("執行深度鎖碼分析", key="btn_t3"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("分析中..."):
                today_df = pd.DataFrame()
                for i in range(7):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_df = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_df.empty: break
                
                if not today_df.empty:
                    cands = today_df[today_df['stock_id'].isin(master_info['stock_id'])].sort_values('trading_volume', ascending=False).head(12)
                    final = []
                    for idx, row in enumerate(cands.iterrows()):
                        sid = row[1]['stock_id']
                        status_text.text(f"🔍 正在分析: {sid} ({idx+1}/12)")
                        progress_bar.progress((idx+1)/12)
                        
                        h_data = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=25)).strftime('%Y-%m-%d'))
                        if not h_data.empty:
                            c_col = next((c for c in h_data.columns if 'class' in c), None)
                            if c_col:
                                bh = h_data[h_data[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2 and bh['percent'].iloc[-1] > bh['percent'].iloc[-2]:
                                    s_name = id_to_name.get(sid, "未知")
                                    final.append({"代號": sid, "名稱": s_name, "收盤": row[1]['close'], "大戶增幅": f"{round(bh['percent'].iloc[-1]-bh['percent'].iloc[-2],2)}%"})
                    
                    status_text.empty(); progress_bar.empty()
                    if final: