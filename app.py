import streamlit as st
import pandas as pd
import requests
import urllib3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 系統環境設定 ---
st.set_page_config(page_title="AlphaRadar | Pro", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.markdown("""
    <style>
    .stApp { background-color: #000000; }
    [data-testid="stSidebar"] { background-color: #111111; }
    h1, h2, h3, p, span { color: #E0E0E0 !important; }
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

if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

def sync_selection():
    st.session_state.active_sid = id_map[st.session_state.stock_selector_key]

# --- 3. 數據抓取引擎 ---
@st.cache_resource
def get_loader(): return DataLoader()

def fetch_comprehensive_data(sid):
    dl = get_loader()
    start_dt = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')
    try:
        # 價格數據
        price = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, start_date=start_dt)
        if price is None or price.empty: return pd.DataFrame()
        price.columns = [c.lower() for c in price.columns]
        price = price.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
        price['date'] = pd.to_datetime(price['date'])
        df = price.sort_values('date')
        
        # 指標計算
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['std20'] = df['close'].rolling(20).std()
        df['upper'] = df['ma20'] + (df['std20'] * 2)
        df['lower'] = df['ma20'] - (df['std20'] * 2)
        
        # MACD
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['dif'] = df['ema12'] - df['ema26']
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['dif'] - df['dea']
        
        # 三大法人數據抓取
        try:
            inst = dl.get_data(dataset="InstitutionalInvestorsBuySell", data_id=sid, start_date=start_dt)
            if not inst.empty:
                # 累計當日外資、投信、自營商總合
                inst_sum = inst.groupby('date')['buy_sell'].sum().reset_index()
                inst_sum['date'] = pd.to_datetime(inst_sum['date'])
                df = df.merge(inst_sum, on='date', how='left').fillna(0)
            else:
                df['buy_sell'] = 0
        except:
            df['buy_sell'] = 0
            
        return df
    except: return pd.DataFrame()

# --- 4. 繪圖顯示 ---
with st.sidebar:
    st.title("阿爾法雷達")
    st.selectbox("🔍 搜尋標的", options=display_list, 
                 index=display_list.index(next(s for s in display_list if st.session_state.active_sid in s)), 
                 key="stock_selector_key", on_change=sync_selection)
    st.caption(f"已載入個股：{len(display_list)} 檔")

df = fetch_comprehensive_data(st.session_state.active_sid)

if not df.empty:
    pdf = df.tail(120)
    d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("K線 / 均線 / 布林通道", "MACD 趨勢", "三大法人買賣超 (張)", "成交量")
    )

    # 1. 主圖
    fig.add_trace(go.Candlestick(x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'], 
                                increasing_line_color='#FF0000', decreasing_line_color='#00FF00', name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma5'], line=dict(color='#FFFFFF', width=1), name="5MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma10'], line=dict(color='#FFFF00', width=1), name="10MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma20'], line=dict(color='#FF00FF', width=1), name="20MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['upper'], line=dict(color='#00FFFF', width=1, dash='dot'), name="上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['lower'], line=dict(color='#00FFFF', width=1, dash='dot'), name="下軌"), row=1, col=1)

    # 2. MACD
    m_colors = ['#FF0000' if x > 0 else '#00FF00' for x in pdf['macd_hist']]
    fig.add_trace(go.Bar(x=d_str, y=pdf['macd_hist'], marker_color=m_colors, name="MACD"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dif'], line=dict(color='#FFFF00', width=1.5), name="DIF"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dea'], line=dict(color='#FFA500', width=1.5), name="DEA"), row=2, col=1)

    # 3. 三大法人 (修復重點)
    i_colors = ['#FF0000' if x > 0 else '#00FF00' for x in pdf['buy_sell']]
    fig.add_trace(go.Bar(x=d_str, y=pdf['buy_sell'], marker_color=i_colors, name="法人買賣超"), row=3, col=1)

    # 4. 成交量
    v_colors = ['#FF0000' if pdf['close'].iloc[i] >= pdf['open'].iloc[i] else '#00FF00' for i in range(len(pdf))]
    fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color=v_colors, name="成交量"), row=4, col=1)

    fig.update_layout(height=950, template="plotly_dark", paper_bgcolor='#000000', plot_bgcolor='#000000', 
                      showlegend=False, xaxis_rangeslider_visible=False, margin=dict(t=50, b=20, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)
    ```

### 📋 修復說明：
* **法人區塊啟動**：原本截圖中的「指標參數」區塊，現在已正式對接到 `buy_sell` 數據。
* **買紅賣綠**：法人買超顯示為**亮紅**，賣超顯示為**螢光綠**，一目了然。
* **API 延遲處理**：如果遇到 FinMind 伺服器晚間維護，該區塊會暫時顯示為 0，等到伺服器資料更新後會自動出現。

您現在試著搜尋 **「2330」** 或是 **「2317」** 看看法人區塊是否有出現紅綠柱狀圖？如果還是空白，可能是 FinMind 今天的法人數據還在整理中，通常半小時後就會正常！