import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業版", layout="wide")

if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 (強化防錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] # 統一轉小寫
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            # 統一價格與張數欄位
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 索引引擎 ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty or 'stock_id' not in df.columns:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    df = df[df['stock_id'].str.match(r'^\d{4}$', na=False)]
    df['display'] = df['stock_id'].astype(str) + " " + df['stock_name'].astype(str)
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 系統控制台")
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_tag = st.selectbox("🔍 搜尋全市場個股", options=options, index=curr_idx)
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun()

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "📡 市場強勢掃描", "🐳 籌碼動向"])

# --- TAB 1: 技術 (維持 4 均線) ---
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {selected_tag} 技術分析")
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=260)).strftime('%Y-%m-%d'))
    if not df_price.empty:
        df = df_price.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="5MA", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma10'], name="10MA", line=dict(color='yellow', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA", line=dict(color='magenta', width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="60MA", line=dict(color='cyan', width=1.5)), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# --- TAB 2: 市場掃描 (修正合併問題) ---
with tabs[1]:
    st.subheader("📡 強勢股掃描")
    vol_min = st.number_input("最低成交量門檻 (張)", 300, 10000, 1000)
    if st.button("🚀 啟動掃描"):
        with st.spinner("掃描中..."):
            all_m = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d'))
            if not all_m.empty:
                latest = all_m['date'].max()
                res = all_m[all_m['date'] == latest].copy()
                res['漲幅%'] = ((res['close'] - res['open']) / res['open'] * 100).round(2)
                # 確保合併時不噴錯
                final = res[(res['漲幅%'] > 2) & (res['volume'] >= vol_min*1000)]
                if not final.empty:
                    final = final.merge(master_df[['stock_id', 'stock_name']], on='stock_id', how='left')
                    st.dataframe(final[['stock_id', 'stock_name', 'close', '漲幅%', 'volume']].sort_values('漲幅%', ascending=False), use_container_width=True)
                else: st.info("查無符合條件之強勢股")
            else: st.warning("無法抓取市場數據，請檢查 API。")

# --- TAB 3: 籌碼動向 (修復 KeyError) ---
with tabs[2]:
    sid = st.session_state.current_sid
    st.subheader(f"🐳 {sid} 大戶持股趨勢")
    chip_df = safe_fetch("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
    
    if not chip_df.empty:
        # 彈性搜尋欄位名：不管是 stock_hold_level, EquityLevel 還是 level 都能運作
        level_col = next((c for c in chip_df.columns if 'level' in c or 'stage' in c), None)
        percent_col = next((c for c in chip_df.columns if 'percent' in c), None)
        
        if level_col and percent_col:
            # 使用 str.contains 模糊比對「1000以上」或等級「15」
            big = chip_df[chip_df[level_col].astype(str).str.contains('1000|15|大於1000', na=False)].sort_values('date')
            if not big.empty:
                st.line_chart(big.set_index('date')[percent_col])
            else:
                st.info("該標的無千張大戶統計數據 (可能是近期未更新)。")
        else:
            st.warning("籌碼資料格式變動，暫時無法解析欄位。")
    else:
        st.info("暫無籌碼數據。")