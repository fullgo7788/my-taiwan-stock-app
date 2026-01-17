import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 初始化 ---
st.set_page_config(page_title="AlphaRadar 終極版", layout="wide")

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

# --- 2. 核心數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.5) # 提高延遲以避免 API 拒絕請求
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            })
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except Exception as e:
        print(f"Error fetching {dataset}: {e}")
    return pd.DataFrame()

# --- 3. 索引引擎 ---
@st.cache_data(ttl=86400)
def get_universe():
    raw = safe_fetch("TaiwanStockInfo")
    backup = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"}, {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"}, {"stock_id": "2436", "stock_name": "偉詮電"}
    ])
    if raw.empty or 'stock_id' not in raw.columns:
        df = backup
    else:
        raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw, backup]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()
tag_map = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    try:
        curr_idx = int(master_df[master_df['stock_id'] == st.session_state.current_sid].index[0])
    except:
        curr_idx = 0

    sel_tag = st.selectbox("🔍 全市場搜尋", options=master_df['display'].tolist(), index=curr_idx)
    st.session_state.current_sid = tag_map[sel_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 已啟動")

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略選股"])

# --- TAB 1: 技術 (保證繪圖) ---
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=250)).strftime('%Y-%m-%d'))
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
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: 基礎掃描 ---
with tabs[1]:
    v_min = st.number_input("最低成交量 (張)", 300, 20000, 1000, key="v2")
    if st.button("🚀 執行漲勢掃描", key="btn2"):
        all_p = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d'))
        if not all_p.empty:
            dt = all_p['date'].max()
            res = all_p[(all_p['date'] == dt) & (all_p['volume'] >= v_min*1000)].copy()
            res['pct'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
            res = res[res['pct'] > 2].merge(master_df[['stock_id', 'stock_name']], on='stock_id', how='left')
            st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), use_container_width=True, hide_index=True)

# --- TAB 3: 籌碼連動 (暴力修復版) ---
with tabs[2]:
    if st.session_state.is_vip:
        chip = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            match_cols = [c for c in chip.columns if any(k in c for k in ['level', 'class', 'stage'])]
            if match_cols:
                lv_col = match_cols[0]
                big = chip[chip[lv_col].astype(str).str.contains('15|1000以上', na=False)].sort_values('date')
                if not big.empty:
                    c_fig = go.Figure()
                    c_fig.add_trace(go.Scatter(x=big['date'], y=big['percent'], mode='lines+markers', name="大戶%"))
                    c_fig.update_layout(height=400, template="plotly_dark", title=f"{current_sid} 大戶持有比趨勢")
                    st.plotly_chart(c_fig, use_container_width=True)
                else:
                    st.warning("⚠️ 查無千張大戶分級細項數據。")
            else:
                st.info("💡 改顯示外資持股比模式")
                st.line_chart(chip.set_index('date')['foreigninvestmentsharesratio'])
        else:
            st.info("💡 此標的近期無數據。")
    else:
        st.warning("🔒 VIP 專屬 (ST888)")

# --- TAB 4: VIP 選股 (強化日期判定) ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 VIP 專屬：5日線上量縮收紅")
        v_limit_4 = st.number_input("最低成交量門檻 (張)", 300, 20000, 1000, key="v4")
        if st.button("🚀 啟動全市場掃描", key="btn4"):
            with st.spinner("正在運算 1,800 檔個股，請稍候..."):
                df_v = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=20)).strftime('%Y-%m-%d'))
                if not df_v.empty:
                    latest = df_v['date'].max()
                    hits = []
                    # 優化遍歷效率
                    for sid, g in df_v.groupby('stock_id'):
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        g['ma5'] = g['close'].rolling(5).mean()
                        t, y = g.iloc[-1], g.iloc[-2]
                        if t['date'] == latest and t['close'] > t['ma5'] and t['volume'] < y['volume'] and t['close'] > t['open'] and t['volume'] >= v_limit_4*1000:
                            hits.append({'stock_id': sid, '收盤': t['close'], '今日量': int(t['volume']/1000), '昨日量': int(y['volume']/1000)})
                    if hits:
                        res_v = pd.DataFrame(hits).merge(master_df[['stock_id', 'stock_name']], on='stock_id')
                        st.success(f"掃描日：{latest}")
                        st.dataframe(res_v, use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"基準日 {latest} 查無符合標的。")
    else:
        st.error("🔒 VIP 專屬分頁")