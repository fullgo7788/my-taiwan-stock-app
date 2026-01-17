import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 初始化 ---
st.set_page_config(page_title="AlphaRadar 終極穩定版", layout="wide")

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

# --- 2. 核心數據引擎 (強制格式轉化) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3) 
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            # 強制日期格式轉化，這是繪圖成功的關鍵
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
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

# --- 4. 側邊欄控制 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    options_list = master_df['display'].tolist()
    try:
        match_idx = master_df[master_df['stock_id'] == st.session_state.current_sid].index
        curr_idx = int(match_idx[0]) if not match_idx.empty else 0
    except: curr_idx = 0
    
    sel_tag = st.selectbox("🔍 全市場搜尋", options=options_list, index=curr_idx)
    st.session_state.current_sid = tag_to_id[sel_tag]
    
    st.divider()
    if not st.session_state.is_vip:
        pw = st.text_input("💎 授權碼解鎖", type="password")
        if st.button("確認解鎖"):
            if pw == VIP_KEY:
                st.session_state.is_vip = True
                st.rerun()
    else:
        st.success("✅ VIP 已啟動")

# --- 5. 主分頁區 (TAB 1-4) ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略"])

# --- TAB 1: 技術 (採用標準 Plotly 渲染) ---
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", st.session_state.current_sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        
        # 繪圖指令強制重繪
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="MA5", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="MA20", line=dict(color='yellow', width=1.5)), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        
        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True, key=f"tech_chart_{st.session_state.current_sid}")
        
    else:
        st.warning("⚠️ 此標的暫無歷史數據")

# --- TAB 3: 籌碼 (修正圖表) ---
with tabs[2]:
    if st.session_state.is_vip:
        chip = safe_fetch("TaiwanStockShareholding", st.session_state.current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            # 尋找「1000張以上」或「15級」的數據
            match_cols = [c for c in chip.columns if any(k in c for k in ['level', 'class', 'stage'])]
            if match_cols:
                lv_col = match_cols[0]
                big = chip[chip[lv_col].astype(str).str.contains('15|1000以上', na=False)].sort_values('date')
                if not big.empty:
                    c_fig = go.Figure()
                    c_fig.add_trace(go.Scatter(x=big['date'], y=big['percent'], mode='lines+markers', name="千張大戶持有比", line=dict(color='cyan')))
                    c_fig.update_layout(height=450, template="plotly_dark", title=f"{sel_tag} 大戶籌碼趨勢", margin=dict(t=50))
                    st.plotly_chart(c_fig, use_container_width=True, key=f"chip_chart_{st.session_state.current_sid}")
                    
            else:
                st.info("無法獲取分級資料，顯示法人持股比")
                st.line_chart(chip.set_index('date').iloc[:,-1])
    else:
        st.write("### 🐳 籌碼深度分析")
        st.caption("解鎖 VIP 後即可查看大戶持股動向。")

# --- TAB 4: VIP 策略 ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 前一交易日：量縮收紅策略")
        v_lim = st.number_input("最低成交量門檻 (張)", 300, 20000, 1000)
        if st.button("🚀 執行全市場掃描"):
            with st.spinner("掃描中..."):
                df_all = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=20)).strftime('%Y-%m-%d'))
                if not df_all.empty:
                    latest = df_all['date'].max()
                    hits = []
                    for sid, g in df_all.groupby('stock_id'):
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        g['ma5'] = g['close'].rolling(5).mean()
                        t, y = g.iloc[-1], g.iloc[-2]
                        if t['date'] == latest and t['close'] > t['open'] and t['volume'] < y['volume'] and t['close'] > t['ma5'] and t['volume'] >= v_lim*1000:
                            hits.append({'代號': sid, '收盤': t['close'], '量': int(t['volume']/1000), 'MA5': round(t['ma5'],2)})
                    if hits:
                        st.dataframe(pd.DataFrame(hits), use_container_width=True)
                    else: st.warning("今日查無標的")
    else:
        st.write("### 📡 市場篩選端")
        st.caption("VIP 解鎖後開啟。")