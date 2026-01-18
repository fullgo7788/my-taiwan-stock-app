import streamlit as st
import pandas as pd
import requests
import urllib3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 系統環境與全黑底 CSS 設定 ---
st.set_page_config(page_title="AlphaRadar | Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 強制注入 CSS 讓全網頁黑底並優化側邊欄文字
st.markdown("""
    <style>
    .stApp { background-color: #000000; }
    header[data-testid="stHeader"] { background: rgba(0,0,0,0); }
    [data-testid="stSidebar"] { background-color: #111111; }
    .stSelectbox label { color: white !important; }
    h1, h2, h3, p { color: #E0E0E0 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 官方名單抓取 ---
@st.cache_data(ttl=86400)
def get_official_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=20, verify=False)
        res.encoding = 'big5'
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        def split_id_name(val):
            parts = str(val).split('\u3000') 
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                return parts[0], parts[1]
            return None, None
        df[['sid', 'sname']] = df.iloc[:, 0].apply(lambda x: pd.Series(split_id_name(x)))
        clean_df = df.dropna(subset=['sid'])[['sid', 'sname']].copy()
        clean_df['display'] = clean_df['sid'] + " " + clean_df['sname']
        return clean_df.sort_values('sid').reset_index(drop=True)
    except:
        return pd.DataFrame([{"sid":"2330","sname":"台積電","display":"2330 台積電"}])

master_df = get_official_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

# --- 3. 狀態管理 ---
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

def sync_selection():
    st.session_state.active_sid = id_map[st.session_state.stock_selector_key]

# --- 4. 數據抓取與指標計算 ---
@st.cache_resource
def get_loader(): return DataLoader()

def fetch_data(sid):
    dl = get_loader()
    start_dt = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')
    try:
        price = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, start_date=start_dt)
        if price is None or price.empty: return pd.DataFrame()
        price.columns = [c.lower() for c in price.columns]
        price = price.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
        price['date'] = pd.to_datetime(price['date'])
        df = price.sort_values('date')
        
        # 指標計算
        df['ma20'] = df['close'].rolling(20).mean()
        df['std20'] = df['close'].rolling(20).std()
        df['upper'] = df['ma20'] + (df['std20'] * 2)
        df['lower'] = df['ma20'] - (df['std20'] * 2)
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['dif'] = df['ema12'] - df['ema26']
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['dif'] - df['dea']
        return df
    except: return pd.DataFrame()

# --- 5. 側邊欄 ---
with st.sidebar:
    st.title("阿爾法雷達")
    st.selectbox("🔍 搜尋標的", options=display_list, 
                 index=display_list.index(next(s for s in display_list if st.session_state.active_sid in s)), 
                 key="stock_selector_key", on_change=sync_selection)
    st.divider()
    st.caption(f"已載入官方個股：{len(display_list)} 檔")

# --- 6. 繪圖顯示 ---
df = fetch_data(st.session_state.active_sid)

if not df.empty:
    pdf = df.tail(120)
    d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("K線 / 布林通道", "MACD 趨勢指標", "指標參數", "成交量")
    )

    # 1. K線圖 (亮紅漲、螢光綠跌)
    fig.add_trace(go.Candlestick(
        x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'], 
        increasing_line_color='#FF0000', increasing_fillcolor='#FF0000',
        decreasing_line_color='#00FF00', decreasing_fillcolor='#00FF00',
        name="K線"
    ), row=1, col=1)
    
    # 亮化布林通道 (亮青色)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['upper'], line=dict(color='#00FFFF', width=1.5, dash='dot'), name="上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['lower'], line=dict(color='#00FFFF', width=1.5, dash='dot'), name="下軌"), row=1, col=1)

    # 2. MACD (紅漲亮綠跌)
    m_colors = ['#FF0000' if x > 0 else '#00FF00' for x in pdf['macd_hist']]
    fig.add_trace(go.Bar(x=d_str, y=pdf['macd_hist'], marker_color=m_colors, name="MACD柱"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dif'], line=dict(color='#FFFF00', width=1.5), name="DIF"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dea'], line=dict(color='#FFA500', width=1.5), name="DEA"), row=2, col=1)

    # 3. 成交量 (與 K 棒顏色連動)
    v_colors = ['#FF0000' if pdf['close'].iloc[i] >= pdf['open'].iloc[i] else '#00FF00' for i in range(len(pdf))]
    fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color=v_colors, name="成交量"), row=4, col=1)

    fig.update_layout(
        height=900, 
        template="plotly_dark",
        paper_bgcolor='#000000', 
        plot_bgcolor='#000000',
        showlegend=False, 
        xaxis_rangeslider_visible=False,
        margin=dict(t=50, b=20, l=10, r=10),
        xaxis=dict(gridcolor='#222222'),
        yaxis=dict(gridcolor='#222222')
    )
    st.plotly_chart(fig, use_container_width=True)
    
else:
    st.info("正在抓取數據，請稍候...")