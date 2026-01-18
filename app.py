import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統狀態初始化 ---
st.set_page_config(page_title="AlphaRadar 專業終端", layout="wide")

# 確保所有狀態在 App 啟動時即存在
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"
if 'is_vip' not in st.session_state: st.session_state.is_vip = False

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
        # 增加 sleep 確保不被 API 阻擋
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引與回調函數 ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# 關鍵：處理選單連動
def on_sid_change():
    st.session_state.current_sid = st.session_state.sid_selector.split(' ')[0]

# 關鍵：處理密碼驗證
def verify_vip():
    if st.session_state.pw_input == VIP_KEY:
        st.session_state.is_vip = True
    else:
        st.session_state.is_vip = False

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 選單：使用 key 與 on_change 強制連動
    options = master_df['display'].tolist()
    try:
        curr_val = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(curr_val)
    except: curr_idx = 0

    st.selectbox("🔍 全市場搜尋", options=options, index=curr_idx, 
                 key="sid_selector", on_change=on_sid_change)
    
    st.divider()
    
    # 密碼：使用 key 與 on_change 立刻更新 VIP 狀態
    st.text_input("💎 VIP 授權碼", type="password", key="pw_input", on_change=verify_vip)
    
    if st.session_state.is_vip:
        st.success("✅ VIP 權限已啟動")
        if st.button("登出 VIP"):
            st.session_state.is_vip = False
            st.rerun()

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# --- TAB 1: 技術診斷 ---
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {sid} 技術走勢")
    hist = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        fig = go.Figure(data=[go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"plot_{sid}")


# --- TAB 2: 基礎掃描 ---
with tabs[1]:
    st.subheader("📡 全市場漲勢篩選")
    v_min = st.number_input("最低張數門檻", 300, 10000, 1000, key="t2_v")
    if st.button("🚀 執行全市場掃描", key="t2_btn"):
        with st.spinner("掃描中..."):
            df_scan = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d'))
            if not df_scan.empty:
                dt = df_scan['date'].max()
                res = df_scan[df_scan['date'] == dt].copy()
                res['漲幅%'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
                res = res[(res['漲幅%'] > 2) & (res['volume'] >= v_min*1000)]
                final = res.merge(master_df[['stock_id', 'stock_name']], on='stock_id')
                st.dataframe(final[['stock_id', 'stock_name', 'close', '漲幅%', 'volume']].sort_values('漲幅%', ascending=False), use_container_width=True)

# --- TAB 3: 籌碼連動 ---
with tabs[2]:
    if st.session_state.is_vip:
        sid = st.session_state.current_sid
        st.subheader(f"🐳 {sid} 大戶籌碼趨勢")
        chip = safe_fetch("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            # 簡化繪圖邏輯，直接抓取最後一欄（通常是持股比）
            st.line_chart(chip.set_index('date').iloc[:, -1])
            
    else:
        st.write("### 🐳 籌碼深度分析")
        st.caption("請在側邊欄輸入正確密碼以開啟功能。")

# --- TAB 4: VIP 策略 ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 VIP：前一交易日量縮收紅")
        v_lim = st.number_input("成交量門檻", 300, 20000, 1000, key="t4_v")
        if st.button("🚀 執行策略掃描", key="t4_btn"):
            with st.spinner("計算中..."):
                df_vip = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=15)).strftime('%Y-%m-%d'))
                if not df_vip.empty:
                    latest = df_vip['date'].max()
                    hits = []
                    for s, g in df_vip.groupby('stock_id'):
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        g['ma5'] = g['close'].rolling(5).mean()
                        t, y = g.iloc[-1], g.iloc[-2]
                        if t['date'] == latest and t['close'] > t['open'] and t['volume'] < y['volume'] and t['close'] > t['ma5'] and t['volume'] >= v_lim*1000:
                            hits.append({'代號': s, '收盤': t['close'], '量': int(t['volume']/1000)})
                    if hits:
                        st.success(f"掃描基準日：{latest.date()}")
                        st.dataframe(pd.DataFrame(hits), use_container_width=True)
                    else: st.warning("無符合標的。")
    else:
        st.write("### 📡 市場策略掃描端")
        st.caption("授權成功後將在此開啟。")