import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 初始化系統狀態 ---
st.set_page_config(page_title="AlphaRadar 終極版", layout="wide")

# 核心：確保 Session State 存在
if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3) 
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎 ---
@st.cache_data(ttl=86400)
def get_universe():
    raw = safe_fetch("TaiwanStockInfo")
    backup = pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電"}])
    if raw.empty or 'stock_id' not in raw.columns:
        df = backup
    else:
        raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw, backup]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()
tag_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制 (修正密碼機制) ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 個股選擇
    options_list = master_df['display'].tolist()
    try:
        match_idx = master_df[master_df['stock_id'] == st.session_state.current_sid].index
        curr_idx = int(match_idx[0]) if not match_idx.empty else 0
    except: curr_idx = 0
    
    sel_tag = st.selectbox("🔍 全市場搜尋", options=options_list, index=curr_idx)
    st.session_state.current_sid = tag_to_id[sel_tag]
    
    st.divider()
    
    # 🔑 修正後的 VIP 驗證區
    st.write("💎 **VIP 權限管理**")
    if not st.session_state.is_vip:
        input_pw = st.text_input("請輸入授權碼", type="password", key="pw_input")
        if st.button("確認解鎖"):
            if input_pw == VIP_KEY:
                st.session_state.is_vip = True
                st.success("解鎖成功！")
                time.sleep(1)
                st.rerun() # 強制刷新頁面，讓 Tab 4 立刻出現
            else:
                st.error("代碼不正確")
    else:
        st.success("✅ VIP 權限已啟動")
        if st.button("登出 VIP"):
            st.session_state.is_vip = False
            st.rerun()

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略選股"])

# TAB 1: 技術 (略過，保持原有繪圖邏輯)
with tabs[0]:
    st.write(f"### {sel_tag} 技術走勢")
    # ... 原有繪圖代碼 ...

# TAB 3: 籌碼
with tabs[2]:
    if st.session_state.is_vip:
        st.write("🐳 正在獲取大戶籌碼數據...")
    else:
        st.info("💡 此功能需在側邊欄解鎖 VIP 權限。")

# --- TAB 4: 日線量縮收紅 (無提示、密碼解鎖後才出現功能) ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 VIP 專屬：量縮收紅選股 (前一交易日)")
        v_lim = st.number_input("張數門檻", 300, 20000, 1000)
        
        if st.button("🚀 啟動掃描"):
            with st.spinner("掃描市場數據中..."):
                df_all = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=20)).strftime('%Y-%m-%d'))
                if not df_all.empty:
                    latest_date = df_all['date'].max()
                    hits = []
                    for sid, g in df_all.groupby('stock_id'):
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        g['ma5'] = g['close'].rolling(5).mean()
                        t, y = g.iloc[-1], g.iloc[-2]
                        # 核心邏輯
                        if t['date'] == latest_date and t['close'] > t['open'] and t['volume'] < y['volume'] and t['close'] > t['ma5'] and t['volume'] >= v_lim*1000:
                            hits.append({'代號': sid, '收盤': t['close'], '量': int(t['volume']/1000), 'MA5': round(t['ma5'],2)})
                    
                    if hits:
                        st.write(f"📅 掃描基準日：{latest_date}")
                        st.dataframe(pd.DataFrame(hits), use_container_width=True)
                    else:
                        st.warning("查無符合標的。")
    else:
        # 勿提示密碼，僅靜默顯示說明
        st.write("### 📡 策略掃描模式")
        st.write("全市場量縮收紅自動化篩選。")