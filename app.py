import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 核心系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業版", layout="wide")

# 【VIP 狀態持久化】
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

# --- 2. 工業級防彈數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    """具備 3 次重試與全欄位自動校正功能"""
    for _ in range(3):
        try:
            time.sleep(0.3)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 強制校準成交量欄位 (Tab 2 沒反應的主因)
                if 'trading_volume' in df.columns:
                    df = df.rename(columns={'trading_volume': 'volume'})
                df = df.rename(columns={'max': 'high', 'min': 'low'})
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                return df
        except:
            time.sleep(0.5)
    return pd.DataFrame()

# --- 3. 全市場清單 (100% 確保廣達、裕隆在內) ---
@st.cache_data(ttl=86400)
def get_full_universe():
    info = safe_fetch("TaiwanStockInfo")
    # 保底名單，防止 API 斷線導致選單空白
    essential = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2603", "stock_name": "長榮"},
        {"stock_id": "3035", "stock_name": "智原"}
    ])
    if info.empty or 'stock_id' not in info.columns:
        df = essential
    else:
        # 只取 4 碼台股，排除權證 (符合證券軟體邏輯)
        info = info[info['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([info, essential]).drop_duplicates('stock_id')
    
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

universe_df = get_full_universe()
stock_map = universe_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制中心 (標籤連動關鍵) ---
with st.sidebar:
    st.header("⚡ 系統控制中心")
    
    # 選單與全局數據連動
    # 若要預設廣達：
    target_idx = universe_df[universe_df['stock_id'] == "2382"].index[0] if "2382" in universe_df['stock_id'].values else 0
    sel_display = st.selectbox("🎯 個股搜尋與診斷", options=universe_df['display'].tolist(), index=int(target_idx))
    sel_id = stock_map[sel_display]
    
    st.divider()
    
    # VIP 密碼驗證 (持久化修正)
    pw_input = st.text_input("💎 VIP 授權碼", type="password")
    if pw_input == VIP_KEY:
        st.session_state.vip_auth = True
        st.success("VIP 權限：已解鎖")
    elif pw_input:
        st.session_state.vip_auth = False
        st.error("密碼錯誤")

# --- 5. 主分頁數據渲染 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼"])

# --- Tab 1: 診斷標籤連動 ---
with tabs[0]:
    st.subheader(f"📈 行情分析：{sel_display}")
    price_df = safe_fetch("TaiwanStockPrice", sel_id, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    if not price_df.empty:
        p_df = price_df.sort_values('date')
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=p_df['date'], open=p_df['open'], high=p_df['high'], low=p_df['low'], close=p_df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Bar(x=p_df['date'], y=p_df['volume'], name="量", marker_color='gray'), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("資料加載中或當前代號無權限...")

# --- Tab 2: 強勢掃描 (反應式修正) ---
with tabs[1]:
    st.subheader("📡 全市場即時動能雷達")
    c1, c2 = st.columns(2)
    with c1: pct_limit = st.slider("最低漲幅 (%)", 1.0, 10.0, 3.0)
    with c2: vol_limit = st.number_input("最低成交量 (張)", 500, 20000, 2000)
    
    if st.button("🚀 啟動掃描引擎"):
        with st.spinner("雷達掃描中...這會遍歷台股所有個股數據"):
            found = False
            # 自動找最近 10 天內有開盤的那天
            for i in range(10):
                scan_dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_data = safe_fetch("TaiwanStockPrice", start_date=scan_dt)
                
                if not all_data.empty and len(all_data) > 500:
                    # 邏輯運算：漲幅與成交量(張)
                    all_data['pct'] = ((all_data['close'] - all_data['open']) / all_data['open'] * 100).round(2)
                    res = all_data[
                        (all_data['pct'] >= pct_limit) & 
                        (all_data['volume'] >= vol_limit * 1000) &
                        (all_data['stock_id'].str.len() == 4)
                    ].copy()
                    
                    if not res.empty:
                        res = res.merge(universe_df[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{scan_dt}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), 
                                     use_container_width=True, hide_index=True)
                        found = True
                        break
            if not found: st.warning("當前設定下查無符合標的。")

# --- Tab 3: VIP 籌碼 ---
with tabs[2]:
    if st.session_state.vip_auth:
        st.subheader(f"🐳 {sel_display} 大戶持股趨勢")
        chip = safe_fetch("TaiwanStockShareholding", sel_id, (datetime.now()-timedelta(days=90)).strftime('%Y-%m-%d'))
        if not chip.empty:
            lv_col = [c for c in chip.columns if 'level' in c or 'class' in c][0]
            big = chip[chip[lv_col].astype(str).str.contains('1000以上')].sort_values('date')
            st.line_chart(big.set_index('date')['percent'])
        else:
            st.info("該標的暫無大戶籌碼數據。")
    else:
        st.warning("🔒 VIP 專屬功能，請於側邊欄輸入正確授權碼解鎖。")