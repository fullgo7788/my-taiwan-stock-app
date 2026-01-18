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
    .stMetric { background-color: #1A1A1A; padding: 10px; border-radius: 5px; border: 1px solid #333; }
    h1, h2, h3, p, span { color: #E0E0E0 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 官方名單掛載 ---
@st.cache_data(ttl=86400)
def get_full_stock_list():
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_dfs = []
    for m in [2, 4]:
        try:
            res = requests.get(f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={m}", headers=headers, verify=False)
            res.encoding = 'big5'
            df = pd.read_html(res.text)[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:].copy()
            df['sid'] = df.iloc[:, 0].str.split('\u3000').str[0]
            df['sname'] = df.iloc[:, 0].str.split('\u3000').str[1]
            df = df[df['sid'].str.len() == 4]
            all_dfs.append(df[['sid', 'sname']])
        except: continue
    full = pd.concat(all_dfs).drop_duplicates().sort_values('sid')
    full['display'] = full['sid'] + " " + full['sname']
    return full.reset_index(drop=True)

master_df = get_full_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

if 'active_sid' not in st.session_state: st.session_state.active_sid = "2330"
def sync_selection(): st.session_state.active_sid = id_map[st.session_state.stock_selector_key]

# --- 3. 數據與指標引擎 ---
@st.cache_resource
def get_loader(): return DataLoader()

def fetch_data(sid):
    dl = get_loader()
    start_dt = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')
    try:
        # A. 價格數據
        price = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, start_date=start_dt)
        if price is None or price.empty: return pd.DataFrame()
        price.columns = [c.lower() for c in price.columns]
        price = price.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
        price['date'] = pd.to_datetime(price['date'])
        df = price.sort_values('date')
        
        # B. 技術指標
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['up'] = df['ma20'] + (df['close'].rolling(20).std() * 2)
        df['dn'] = df['ma20'] - (df['close'].rolling(20).std() * 2)
        df['dif'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd'] = df['dif'] - df['dea']
        
        # C. 三大法人關鍵修復 (自動對齊日期)
        try:
            inst = dl.get_data(dataset="InstitutionalInvestorsBuySell", data_id=sid, start_date=start_dt)
            if not inst.empty:
                # 確保 buy_sell 欄位存在並加總
                inst_grouped = inst.groupby('date')['buy_sell'].sum().reset_index()
                inst_grouped['date'] = pd.to_datetime(inst_grouped['date'])
                df = df.merge(inst_grouped, on='date', how='left')
                df['buy_sell'] = df['buy_sell'].fillna(0)
            else: df['buy_sell'] = 0
        except: df['buy_sell'] = 0
        return df
    except: return pd.DataFrame()

# --- 4. 側邊欄與介面 ---
with st.sidebar:
    st.title("⚡ 策略監控")
    st.selectbox("🔍 搜尋標的", options=display_list, 
                 index=display_list.index(next(s for s in display_list if st.session_state.active_sid in s)), 
                 key="stock_selector_key", on_change=sync_selection)
    st.divider()
    st.success(f"已同步：{len(display_list)} 檔上市櫃個股")

df = fetch_data(st.session_state.active_sid)

if not df.empty:
    pdf = df.tail(120)
    d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=("K線 / 均線 / 布林通道", "MACD 趨勢指標", "三大法人合計買賣超 (張)", "成交量"))

    # 1. 主圖層
    fig.add_trace(go.Candlestick(x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'], 
                                increasing_line_color='#FF0000', decreasing_line_color='#00FF00', name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma5'], line=dict(color='#FFFFFF', width=1), name="5MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma10'], line=dict(color='#FFFF00', width=1), name="10MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['ma20'], line=dict(color='#FF00FF', width=1.5), name="20MA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['up'], line=dict(color='#00FFFF', width=1, dash='dot'), name="上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dn'], line=dict(color='#00FFFF', width=1, dash='dot'), name="下軌"), row=1, col=1)

    # 2. MACD
    fig.add_trace(go.Bar(x=d_str, y=pdf['macd'], marker_color=['#FF0000' if x > 0 else '#00FF00' for x in pdf['macd']], name="MACD"), row=2, col=1)

    # 3. 三大法人 (修復後：現在應出現紅綠柱狀)
    fig.add_trace(go.Bar(x=d_str, y=pdf['buy_sell'], marker_color=['#FF0000' if x > 0 else '#00FF00' for x in pdf['buy_sell']], name="法人買賣超"), row=3, col=1)

    # 4. 成交量
    v_colors = ['#FF0000' if pdf['close'].iloc[i] >= pdf['open'].iloc[i] else '#00FF00' for i in range(len(pdf))]
    fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color=v_colors, name="成交量"), row=4, col=1)

    fig.update_layout(height=1000, template="plotly_dark", paper_bgcolor='#000000', plot_bgcolor='#000000', 
                      showlegend=False, xaxis_rangeslider_visible=False, margin=dict(t=50, b=20, l=10, r=10),
                      xaxis4=dict(type='category'))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("數據載入中或該個股今日停牌...")