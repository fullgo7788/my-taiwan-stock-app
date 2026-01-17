import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 初始化與頁面設定 ---
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

# --- 2. 強化數據引擎 (含重試機制) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for i in range(2): # 失敗重試機制
        try:
            time.sleep(0.2)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(0.5)
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    """獲取全市場清單，若失敗則回傳備援名單"""
    df = safe_get_data("TaiwanStockInfo")
    
    # 備援名單：確保選單不為空
    backup_list = pd.DataFrame({
        'stock_id': ['2330', '2317', '2454', '3629', '2881', '2308', '2382'],
        'stock_name': ['台積電', '鴻海', '聯發科', '地心引力', '富邦金', '台達電', '廣達']
    })
    
    if df.empty:
        df = backup_list
    else:
        # 過濾普通股 (4碼)
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        if 'stock_name' not in df.columns:
            df['stock_name'] = df['stock_id']
            
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df

# --- 3. 載入基礎資料 ---
master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()

# --- 4. UI 側邊欄 (修復選單問題) ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    
    # 使用清單索引確保預設選中 2330
    options = list(name_to_id.keys())
    target_display = st.selectbox("🎯 選擇診斷個股", options, index=0)
    target_sid = name_to_id[target_display]
    
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password", help="輸入 ST888 解鎖")
    is_vip = (user_key == VIP_KEY)
    if is_vip:
        st.success("✅ VIP 權限已開啟")
    elif user_key:
        st.error("❌ 授權碼不正確")

# --- 5. 功能分頁 ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (解決繪圖中斷) ---
with tabs[0]:
    st.subheader(f"🔍 分析標的：{target_display}")
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        # 確保繪圖欄位正確
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        
        # RSI 穩定算法
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # 繪圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], line=dict(color='#00CED1'), name="20MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], line=dict(color='orange'), name="RSI"), row=2, col=1)
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # 大戶籌碼
        if not h_df.empty:
            st.divider()
            st.subheader("💎 千張大戶持股比例")
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date').copy()
                if not bh.empty:
                    bh['date_str'] = bh['date'].dt.strftime('%Y-%m-%d')
                    fig_h = go.Figure(go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', name="大戶%"))
                    fig_h.update_layout(height=300, template="plotly_dark")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 查無此標的近期股價資料。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    if st.button("啟動雷達掃描", key="scan_main"):
        with st.spinner("搜尋全市場爆量長紅個股..."):
            found = False
            for i in range(7):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    res = all_p[(all_p['close'] > all_p['open']*1.04) & (all_p['trading_volume'] > 2000000)].copy()
                    if not res.empty:
                        res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'trading_volume']].sort_values('trading_volume', ascending=False))
                        found = True; break
            if not found: st.info("近期盤面無符合爆量長紅條件之標的。")

# --- Tab 3: VIP 鎖碼雷達 (徹底解決無反應問題) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 本功能僅限 VIP 授權使用。")
    else:
        st.subheader("🚀 鎖碼雷達 (追蹤大戶連續增持個股)")
        if st.button("點擊執行深度鎖碼掃描", key="vip_scan_final"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("正在穿越籌碼層面..."):
                # 獲取今日熱門股
                today_df = pd.DataFrame()
                for i in range(7):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_df = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_df.empty: break
                
                if not today_df.empty:
                    # 過濾出具有流動性的中小型股
                    cands = today_df[
                        (today_df['stock_id'].isin(master_info['stock_id'])) & 
                        (today_df['trading_volume'] >= 1000000) & 
                        (today_df['close'] <= 400)
                    ].sort_values('trading_volume', ascending=False).head(15)
                    
                    final_list = []
                    for idx, row in enumerate(cands.iterrows()):
                        sid = row[1]['stock_id']
                        status_text.text(f"🔍 掃描中: {sid} ({idx+1}/15)")
                        progress_bar.progress((idx + 1) / 15)
                        
                        h_data = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=25)).strftime('%Y-%m-%d'))
                        if not h_data.empty:
                            c_col = next((c for c in h_data.columns if 'class' in c), None)
                            if c_col:
                                bh = h_data[h_data[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2:
                                    diff = bh['percent'].iloc[-1] - bh['percent'].iloc[-2]
                                    if diff > 0:
                                        s_name = master_info[master_info['stock_id'] == sid]['stock_name'].values[0]
                                        final_list.append({
                                            "代號": sid, "名稱": s_name, "收盤": row[1]['close'], 
                                            "大戶增幅": f"{round(diff, 2)}%", "最新持股": f"{bh['percent'].iloc[-1]}%"
                                        })
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    if final_list:
                        st.success("🎯 鎖碼掃描完成！")
                        st.table(pd.DataFrame(final_list).sort_values("大戶增幅", ascending=False))
                    else:
                        st.info("目前熱門股中無大戶明顯增持跡象。")
                else:
                    st.error("無法取得行情快照。")