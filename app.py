import streamlit as st
import pandas as pd
import requests
import urllib3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 系統與 CSS 優化 ---
st.set_page_config(page_title="AlphaRadar | Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.markdown("""
    <style>
    .stApp { background-color: #000000; }
    [data-testid="stSidebar"] { background-color: #111111; }
    .stMetric { background-color: #1A1A1A; padding: 10px; border-radius: 5px; border: 1px solid #333; }
    h1, h2, h3, p, span { color: #E0E0E0 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 官方名單 (上市 + 上櫃) ---
@st.cache_data(ttl=86400)
def get_full_stock_list():
    headers = {'User-Agent': 'Mozilla/5.0'}
    def split_id_name(val):
        parts = str(val).split('\u3000') 
        if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
            return parts[0], parts[1]
        return None, None
    all_dfs = []
    for m in [2, 4]: # 2:上市, 4:上櫃
        try:
            res = requests.get(f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={m}", headers=headers, verify=False)
            res.encoding = 'big5'
            df = pd.read_html(res.text)[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            df[['sid', 'sname']] = df.iloc[:, 0].apply(lambda x: pd.Series(split_id_name(x)))
            all_dfs.append(df.dropna(subset=['sid'])[['sid', 'sname']])
        except: continue
    full = pd.concat(all_dfs).drop_duplicates().sort_values('sid')
    full['display'] = full['sid'] + " " + full['sname']
    return full.reset_index(drop=True)

master_df = get_full_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

if 'active_sid' not in st.session_state: st.session_state.active_sid = "2330"

def sync_selection(): st.session_state.active_sid = id_map[st.session_state.stock_selector_key]

# --- 3. 數據核心 ---
@st.cache_resource
def get_loader(): return DataLoader()

def fetch_data(sid):
    dl = get_loader()
    start_dt = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    try:
        # 價格數據
        price = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, start_date=start_dt)
        if price is None or price.empty: return pd.DataFrame()
        price.columns = [c.lower() for c in price.columns]
        price = price.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
        price['date'] = pd.to_datetime(price['date'])
        df = price.sort_values('date')
        
        # 指標計算 (MA/BBands/MACD)
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['up'] = df['ma20'] + (df['close'].rolling(20).std() * 2)
        df['dn'] = df['ma20'] - (df['close'].rolling(20).std() * 2)
        df['dif'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
        df['dea'] = df['dif'].ewm(span=9).mean()
        df['macd'] = df['dif'] - df['dea']
        
        # 三大法人 (修復邏輯)
        try:
            inst = dl.get_data(dataset="InstitutionalInvestorsBuySell", data_id=sid, start_date=start_dt)
            if not inst.empty:
                inst_sum = inst.groupby('date')['buy_sell'].sum().reset_index()
                inst_sum['date'] = pd.to_datetime(inst_sum['date'])
                df = df.merge(inst_sum, on='date', how='left').fillna(0)
            else: df['buy_sell'] = 0
        except: df['buy_sell'] = 0
        return df
    except: return pd.DataFrame()

# --- 4. 介面佈局 ---
with st.sidebar:
    st.title("阿爾法雷達")
    st.selectbox("🔍 搜尋標的", options=display_list, 
                 index=display_list.index(next(s for s in display_list if st.session_state.active_sid in s)), 
                 key="stock_selector_key", on_change=sync_selection)
    st.info(f"已同步：{len(display_list)} 檔上市櫃個股")

df = fetch_data(st.session_state.active_sid)

if not df.empty:
    last = df.iloc[-1]
    prev = df.iloc[-2]
    diff = last['close'] - prev['close']
    pct = (diff / prev['close']) * 100
    
    # 頂部即時行情看板
    c1, c2, c3, c4 = st.columns(4)
    color = "#FF0000" if diff > 0 else "#00FF00"
    c1.metric("最新價", f"{last['close']:.2f}", f"{diff:+.2f} ({pct:+.2f}%)")
    c2.metric("最高/最低", f"{last['high']:.2f} / {last['low']:.2f}")
    c3.metric("成交量", f"{int(last['volume']):,}")
    c4.metric("20MA (月線)", f"{last['ma20']:.2f}")

    # 圖表繪製
    pdf = df.tail(100)
    d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=("K線 / 均線 / 布林通道", "MACD 趨勢", "三大法人買賣超 (張)", "成交量"))

    # K線與指標
    fig.add_trace(go.Candlestick(x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'], 
                                increasing_line_color='#FF0000', decreasing_line_color='#00FF00', name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma5'], line=dict(color='#FFFFFF', width=1), name="5MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma10'], line=dict(color='#FFFF00', width=1), name="10MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma20'], line=dict(color='#FF00FF', width=1.5), name="20MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['up'], line=dict(color='#00FFFF', width=1, dash='dot'), name="上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dn'], line=dict(color='#00FFFF', width=1, dash='dot'), name="下軌"), row=1, col=1)

    # MACD / 法人 / 成交量
    fig.add_trace(go.Bar(x=d_str, y=pdf['macd'], marker_color=['#FF0000' if x > 0 else '#00FF00' for x in pdf['macd']], name="MACD"), row=2, col=1)
    fig.add_trace(go.Bar(x=d_str, y=pdf['buy_sell'], marker_color=['#FF0000' if x > 0 else '#00FF00' for x in pdf['buy_sell']], name="法人"), row=3, col=1)
    fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color=['#FF0000' if pdf['close'].iloc[i] >= pdf['open'].iloc[i] else '#00FF00' for i in range(len(pdf))], name="量"), row=4, col=1)

    fig.update_layout(height=1000, template="plotly_dark", paper_bgcolor='#000000', plot_bgcolor='#000000', 
                      showlegend=False, xaxis_rangeslider_visible=False, margin=dict(t=50, b=20, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("數據讀取中...")