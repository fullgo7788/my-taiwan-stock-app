import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import requests

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar | 全市場版", layout="wide")

if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

FINMIND_TOKEN = "fullgo" # 建議填入以維持穩定抓取

@st.cache_resource
def get_loader():
    try:
        loader = DataLoader()
        if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
        return loader
    except: return None

dl = get_loader()

# --- 2. 數據抓取引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    if dl is None: return pd.DataFrame()
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df.dropna(subset=['date', 'open', 'close']).sort_values('date').reset_index(drop=True)
    except: pass
    return pd.DataFrame()

# --- 3. 抓取證交所與櫃買中心官方名單 (上市+上櫃) ---
@st.cache_data(ttl=86400)
def get_taiwan_stock_universe():
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    all_stocks = []
    
    for url in urls:
        try:
            res = requests.get(url)
            res.encoding = 'big5'
            dfs = pd.read_html(res.text)
            df = dfs[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            def extract_info(x):
                try:
                    # 分割全形空白
                    parts = str(x).split('\u3000')
                    # 篩選個股：代號長度為 4 且為純數字
                    if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                        return parts[0], parts[1]
                except: pass
                return None, None

            df[['sid', 'sname']] = df['有價證券代號及名稱'].apply(lambda x: pd.Series(extract_info(x)))
            valid_df = df.dropna(subset=['sid'])
            all_stocks.append(valid_df[['sid', 'sname']])
        except: continue
        
    if not all_stocks:
        return pd.DataFrame([{"sid": "2330", "sname": "台積電", "display": "2330 台積電"}])
    
    final_df = pd.concat(all_stocks).drop_duplicates('sid')
    final_df['display'] = final_df['sid'] + " " + final_df['sname']
    return final_df.sort_values('sid').reset_index(drop=True)

# 載入名單
master_df = get_taiwan_stock_universe()
display_options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['sid'].to_dict()

# --- 4. 側邊欄同步邏輯 ---
def on_select_change():
    # 強制將新選擇的代號同步到 session_state
    new_label = st.session_state.master_selector
    st.session_state.active_sid = display_to_id[new_label]

# 計算當前預設位置
try:
    curr_label = master_df[master_df['sid'] == st.session_state.active_sid]['display'].values[0]
    curr_idx = display_options.index(curr_label)
except:
    curr_idx = 0

with st.sidebar:
    st.header("📊 全台個股中心")
    st.selectbox(
        "🔍 搜尋上市/上櫃個股",
        options=display_options,
        index=curr_idx,
        key="master_selector",
        on_change=on_select_change
    )
    st.divider()
    st.caption(f"當前鎖定：{st.session_state.active_sid}")
    st.info("資料來源：TWSE/TPEx 官方 ISIN")

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術分析圖", "🎯 大戶籌碼掃描"])

with tabs[0]:
    sid = st.session_state.active_sid
    # 抓取足以計算指標的長度
    df_raw = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=400)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty:
        df = df_raw.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        plot_df = df.dropna(subset=['ma5']).tail(180)
        
        if not plot_df.empty:
            d_str = plot_df['date'].dt.strftime('%Y-%m-%d').tolist()
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            fig.add_trace(go.Candlestick(
                x=d_str, open=plot_df['open'].tolist(), high=plot_df['high'].tolist(),
                low=plot_df['low'].tolist(), close=plot_df['close'].tolist(),
                increasing_line_color='#FF3232', decreasing_line_color='#00AA00', name="K線"
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma5'].tolist(), line=dict(color='white', width=1), name="5MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma20'].tolist(), line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d_str, y=plot_df['ma60'].tolist(), line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
            
            fig.add_trace(go.Bar(x=d_str, y=plot_df['volume'].tolist(), marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=35, b=10, l=10, r=10),
                annotations=[dict(x=0, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=14))]
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"目前代號 {sid} 抓取不到足夠的歷史數據。")

with tabs[1]:
    st.subheader("🎯 策略分析")
    st.button("🚀 開始全市場掃描")