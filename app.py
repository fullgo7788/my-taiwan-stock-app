import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極策略終端", layout="wide")

if 'vip_auth' not in st.session_state:
    st.session_state.vip_auth = False

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 防彈數據引擎 (強化修正版) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 標準化欄位：解決 Tab 2 與 Tab 3 沒反應的問題
            rename_map = {
                'trading_volume': 'volume',
                'max': 'high',
                'min': 'low',
                'stock_hold_class': 'level', # 統一籌碼分級欄位
                'stock_hold_level': 'level'
            }
            df = df.rename(columns=rename_map)
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 全市場索引引擎 (確保 100% 覆蓋) ---
@st.cache_data(ttl=86400)
def get_full_universe():
    info = safe_fetch("TaiwanStockInfo")
    # 強力保底：確保即便 API 失敗，這些股票也絕對在選單內
    essential = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "3035", "stock_name": "智原"},
        {"stock_id": "2317", "stock_name": "鴻海"}
    ])
    if info.empty or 'stock_id' not in info.columns:
        df = essential
    else:
        info = info[info['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([info, essential]).drop_duplicates('stock_id')
    
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

universe_df = get_full_universe()
stock_map = universe_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制與 VIP 驗證 ---
with st.sidebar:
    st.title("🛡️ 證券策略系統")
    
    # 自動定位廣達
    try:
        q_idx = int(universe_df[universe_df['stock_id'] == "2382"].index[0])
    except:
        q_idx = 0

    sel_display = st.selectbox("🎯 全市場個股搜尋", options=universe_df['display'].tolist(), index=q_idx)
    sel_id = stock_map[sel_display]
    
    st.divider()
    pw_input = st.text_input("💎 VIP 授權碼", type="password")
    if pw_input == VIP_KEY:
        st.session_state.vip_auth = True
        st.success("✅ VIP 已解鎖")
    elif pw_input:
        st.error("❌ 密碼錯誤")

# --- 5. 主功能區 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼"])

# Tab 1: 技術連動
with tabs[0]:
    st.subheader(f"📈 行情分析：{sel_display}")
    p_df = safe_fetch("TaiwanStockPrice", sel_id, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    if not p_df.empty:
        p_df = p_df.sort_values('date')
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=p_df['date'], open=p_df['open'], high=p_df['high'], low=p_df['low'], close=p_df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Bar(x=p_df['date'], y=p_df['volume'], name="量", marker_color='gray'), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("API 載入中，請確保 Token 有效...")

# Tab 2: 強勢掃描
with tabs[1]:
    st.subheader("📡 全市場即時動能雷達")
    col1, col2 = st.columns(2)
    with col1: p_limit = st.slider("漲幅 (%)", 1.0, 10.0, 3.0)
    with col2: v_limit = st.number_input("成交量 (張)", 500, 20000, 2000)
    
    if st.button("🚀 啟動全市場掃描"):
        with st.spinner("遍歷資料中..."):
            found = False
            for i in range(7):
                dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_fetch("TaiwanStockPrice", start_date=dt)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= p_limit) & (all_p['volume'] >= v_limit * 1000)].copy()
                    if not res.empty:
                        res = res.merge(universe_df[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"發現交易日：{dt}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), use_container_width=True, hide_index=True)
                        found = True; break
            if not found: st.warning("當前條件查無結果。")

# Tab 3: 籌碼連動 (修復 IndexError)
with tabs[2]:
    if st.session_state.vip_auth:
        st.subheader(f"🐳 {sel_display} 大戶籌碼趨勢")
        chip = safe_fetch("TaiwanStockShareholding", sel_id, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        
        # 【偵錯修正重點】
        if not chip.empty:
            # 使用更安全的欄位搜尋，防止 IndexError
            target_cols = [c for c in chip.columns if 'level' in c or 'class' in c]
            if target_cols:
                lv_col = target_cols[0]
                # 篩選千張大戶
                big_data = chip[chip[lv_col].astype(str).str.contains('1000以上|15')].sort_values('date')
                if not big_data.empty:
                    st.line_chart(big_data.set_index('date')['percent'])
                else:
                    st.info("查無此標的之千張大戶細節數據。")
            else:
                st.error("API 回傳格式變更，無法解析籌碼欄位。")
        else:
            st.info("該標的暫無大戶籌碼資料回傳。")
    else:
        st.warning("🔒 請於側邊欄輸入 VIP 授權碼以解鎖此分頁。")