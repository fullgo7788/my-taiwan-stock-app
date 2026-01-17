import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極終端", layout="wide")

# 初始化 Session State (核心：鎖定 VIP 權限與當前個股)
if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入以避免限制
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 防彈數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3) # 避免 API 頻繁請求被鎖
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

# --- 3. 全市場個股索引 ---
@st.cache_data(ttl=86400)
def get_universe():
    info = safe_fetch("TaiwanStockInfo")
    # 強力保底，確保即便 API 斷線也能搜尋核心標的
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
tag_map = master.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制與 VIP 鎖定 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    # 強連動選單：使用 index 維護狀態
    try:
        current_idx = int(master[master['stock_id'] == st.session_state.current_sid].index[0])
    except:
        current_idx = 0

    sel_tag = st.selectbox("🔍 搜尋個股 (代號/名稱)", options=master['display'].tolist(), index=current_idx)
    st.session_state.current_sid = tag_map[sel_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 已解鎖")
    elif pw != "":
        st.session_state.is_vip = False
        st.error("密碼錯誤")

# --- 5. TAB 1-4 核心功能區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# --- TAB 1: 技術 (均線系統) ---
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
        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)


# --- TAB 2: 基礎掃描 ---
with tabs[1]:
    v_min = st.number_input("最低成交量 (張)", 300, 20000, 1000)
    if st.button("🚀 執行強勢掃描"):
        with st.spinner("遍歷市場中..."):
            all_p = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d'))
            if not all_p.empty:
                dt = all_p['date'].max()
                res = all_p[(all_p['date'] == dt) & (all_p['volume'] >= v_min*1000)].copy()
                res['pct'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
                res = res[res['pct'] > 2].merge(master[['stock_id', 'stock_name']], on='stock_id', how='left')
                st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), use_container_width=True, hide_index=True)

# --- TAB 3: 籌碼連動 ---
with tabs[2]:
    if st.session_state.is_vip:
        chip = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            lv_col = [c for c in chip.columns if any(k in c for k in ['level', 'class', 'stage'])][0]
            big = chip[chip[lv_col].astype(str).str.contains('15|1000以上')].sort_values('date')
            if not big.empty:
                st.line_chart(big.set_index('date')['percent'])
                st.metric("千張大戶持有比", f"{big['percent'].iloc[-1]}%")
    else: st.warning("🔒 籌碼功能僅供 VIP (密碼: ST888)")

# --- TAB 4: VIP 策略 (5日線上量縮收紅) ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 5日線上量縮收紅掃描")
        v_limit = st.number_input("過濾成交量 (張)", 300, 20000, 1000, key="v4")
        if st.button("🚀 啟動 VIP 大數據選股"):
            with st.spinner("分析 1,800 檔個股均線與量能中..."):
                scan_df = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=15)).strftime('%Y-%m-%d'))
                if not scan_df.empty:
                    hits = []
                    for sid, g in scan_df.groupby('stock_id'):
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        g['ma5'] = g['close'].rolling(5).mean()
                        t, y = g.iloc[-1], g.iloc[-2]
                        if t['close'] > t['ma5'] and t['volume'] < y['volume'] and t['close'] > t['open'] and t['volume'] >= v_limit*1000:
                            hits.append({'stock_id': sid, '收盤': t['close'], '今日量': int(t['volume']/1000), '昨日量': int(y['volume']/1000), 'MA5': round(t['ma5'], 2)})
                    if hits:
                        st.dataframe(pd.DataFrame(hits).merge(master[['stock_id', 'stock_name']], on='stock_id'), use_container_width=True, hide_index=True)
                    else: st.warning("今日無符合標的。")
    else: st.error("🔒 VIP 專屬策略分頁。")