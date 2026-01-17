import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 初始化 ---
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

# --- 2. 強化數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for _ in range(2): # 失敗自動重試一次
        try:
            time.sleep(0.2) # 避開 API 頻率限制 (Rate Limit)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 僅保留 4 碼普通股，排除認購權證、ETF
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        # 確保有名字欄位
        if 'stock_name' not in df.columns:
            df['stock_name'] = df['stock_id']
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict() if not master_info.empty else {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", list(name_to_id.keys()))
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (解決繪圖中斷) ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, (datetime.now()-timedelta(days=100)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        # RSI 穩定計算
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], name="RSI(14)", line=dict(color='orange')), row=2, col=1)
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date').copy()
                if not bh.empty:
                    bh['date_str'] = bh['date'].dt.strftime('%Y-%m-%d')
                    fig_h = go.Figure(go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', name="大戶持股%"))
                    fig_h.update_xaxes(type='category', nticks=5)
                    fig_h.update_layout(height=250, template="plotly_dark", title="💎 千張大戶比例")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.error("此標的暫無股價資料。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    if st.button("啟動強勢股雷達", key="t2_btn"):
        with st.spinner("掃描中..."):
            for i in range(7):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    res = all_p[(all_p['close'] > all_p['open']*1.05) & (all_p['trading_volume'] > 3000000)].copy()
                    if not res.empty:
                        res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'trading_volume']])
                        break

# --- Tab 3: VIP 鎖碼雷達 (修復核心崩潰邏輯) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請輸入 VIP 授權碼。")
    else:
        st.subheader("🚀 鎖碼雷達 (大戶增持追蹤)")
        if st.button("執行深度籌碼掃描", key="t3_btn"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. 抓取今日成交量排行標的
            with st.spinner("正在獲取最新市場快照..."):
                today_df = pd.DataFrame()
                for i in range(7):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_df = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_df.empty: break
            
            if not today_df.empty:
                # 篩選量大且非極高價股
                candidates = today_df[
                    (today_p['stock_id'].isin(master_info['stock_id'])) & 
                    (today_p['trading_volume'] >= 1500000) & 
                    (today_p['close'] <= 400)
                ].sort_values('trading_volume', ascending=False).head(15)
                
                final_results = []
                for idx, row in enumerate(candidates.iterrows()):
                    sid = row[1]['stock_id']
                    status_text.text(f"🔍 正在分析籌碼慣性: {sid} ({idx+1}/15)")
                    progress_bar.progress((idx + 1) / 15)
                    
                    # 抓取大戶資料 (3週前 vs 最新)
                    h_data = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=25)).strftime('%Y-%m-%d'))
                    if not h_data.empty:
                        c_col = next((c for c in h_data.columns if 'class' in c), None)
                        if c_col:
                            bh = h_data[h_data[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                            if len(bh) >= 2:
                                diff = bh['percent'].iloc[-1] - bh['percent'].iloc[-2]
                                if diff > 0:
                                    s_name = master_info[master_info['stock_id'] == sid]['stock_name'].values[0] if sid in master_info['stock_id'].values else "未知"
                                    final_results.append({
                                        "代號": sid, "名稱": s_name, "收盤價": row[1]['close'], 
                                        "大戶變動": f"{round(diff, 2)}%", "最新持股": f"{bh['percent'].iloc[-1]}%"
                                    })
                
                status_text.empty()
                progress_bar.empty()
                
                if final_results:
                    st.success("🎯 鎖碼追蹤完成！大戶增持名單如下：")
                    st.table(pd.DataFrame(final_results).sort_values("大戶變動", ascending=False))
                else:
                    st.info("今日盤面熱門標的中，暫無大戶明顯增持跡象。")
            else:
                st.error("無法取得行情資料，請稍後再試。")