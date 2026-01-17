import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar VIP穩定版", layout="wide")

# 初始化 Session State (跨分頁狀態鎖定)
if 'is_vip' not in st.session_state: 
    st.session_state.is_vip = False
if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

# --- 2. 數據抓取引擎 ---
FINMIND_TOKEN = "fullgo" # 若無 Token 則留空
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            })
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 股票索引系統 ---
@st.cache_data(ttl=86400)
def get_universe():
    info = safe_fetch("TaiwanStockInfo")
    # 核心保底標的 (廣達、裕隆、偉詮電)
    backup = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"}
    ])
    if info.empty or 'stock_id' not in info.columns:
        df = backup
    else:
        info = info[info['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([info, backup]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master = get_universe()
tag_to_id = master.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制與 VIP 驗證修復 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 100% 反應式選單
    try:
        curr_idx = int(master[master['stock_id'] == st.session_state.current_sid].index[0])
    except:
        curr_idx = 0

    sel_tag = st.selectbox("🔍 全市場個股搜尋", options=master['display'].tolist(), index=curr_idx)
    st.session_state.current_sid = tag_to_id[sel_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    
    # 【修復重點：VIP 鎖定邏輯】
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 權限已啟動")
    elif pw != "":
        st.session_state.is_vip = False
        st.error("❌ 密鑰錯誤")
    
    if st.session_state.is_vip:
        st.info("當前身份：VIP 專業版")

# --- 5. 主功能分頁 ---
tabs = st.tabs(["📊 技術分析", "📡 動能掃描", "🐳 籌碼分析"])

# TAB 1: 技術連動 (標籤已取消)
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="MA5", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="MA20", line=dict(color='yellow', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="MA60", line=dict(color='magenta', width=2)), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        
        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, hovermode='x unified', margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("⏳ 正在讀取數據，請確保網路連線...")

# TAB 2: 動能掃描
with tabs[1]:
    c1, c2 = st.columns(2)
    with c1: target_pct = st.slider("漲幅 (%)", 1.0, 10.0, 3.5)
    with c2: target_vol = st.number_input("成交量 (張)", 500, 20000, 2000)
    
    if st.button("🚀 啟動掃描"):
        with st.spinner("遍歷全市場個股中..."):
            for i in range(7):
                dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_fetch("TaiwanStockPrice", start_date=dt)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= target_pct) & (all_p['volume'] >= target_vol * 1000)].copy()
                    if not res.empty:
                        res = res.merge(master[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), use_container_width=True, hide_index=True)
                        break

# TAB 3: 籌碼連動 (VIP 邏輯加強)
with tabs[2]:
    if st.session_state.is_vip:
        chip = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            lv_cols = [c for c in chip.columns if any(k in c for k in ['level', 'class', 'stage'])]
            if lv_cols:
                l_col = lv_cols[0]
                big = chip[chip[l_col].astype(str).str.contains('1000以上|15|999,999')].sort_values('date')
                if not big.empty:
                    st.line_chart(big.set_index('date')['percent'])
                    st.metric("千張大戶持有比", f"{big['percent'].iloc[-1]}%")
            elif 'foreigninvestmentsharesratio' in chip.columns:
                st.info("📡 切換：外資持股分析")
                st.line_chart(chip.set_index('date')['foreigninvestmentsharesratio'])
        else:
            st.info("此標的目前無籌碼週報。")
    else:
        # VIP 未解鎖的顯示
        st.warning("🔒 籌碼功能僅供 VIP。請於側邊欄輸入 ST888。")