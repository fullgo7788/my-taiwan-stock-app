import streamlit as st
import pandas as pd
import requests
import urllib3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 1. 系統環境設定 ---
st.set_page_config(page_title="AlphaRadar", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 2. 官方名單抓取 (欄位自動對位版) ---
@st.cache_data(ttl=86400)
def get_official_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=20, verify=False)
        res.encoding = 'big5'
        
        dfs = pd.read_html(res.text)
        df = dfs[0]
        # 自動識別包含 "代號及名稱" 的第一欄位
        target_col = df.iloc[0].values[0] 
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        def split_id_name(val):
            parts = str(val).split('\u3000') # 處理全形空白
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                return parts[0], parts[1]
            return None, None

        # 使用索引 [0] 確保抓到第一欄，不受空白字元影響
        df[['sid', 'sname']] = df.iloc[:, 0].apply(lambda x: pd.Series(split_id_name(x)))
        clean_df = df.dropna(subset=['sid'])[['sid', 'sname']].copy()
        clean_df['display'] = clean_df['sid'] + " " + clean_df['sname']
        
        return clean_df.sort_values('sid').reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame([{"sid":"2330","sname":"台積電","display":"2330 台積電"}])

# 載入名單
master_df = get_official_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

# --- 3. 狀態與數據管理 ---
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

def sync_selection():
    st.session_state.active_sid = id_map[st.session_state.stock_selector_key]

@st.cache_resource
def get_loader(): return DataLoader()

def fetch_data(sid):
    dl = get_loader()
    start_dt = (datetime.now() - timedelta(days=450)).strftime('%Y-%m-%d')
    try:
        # 價格數據
        price = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, start_date=start_dt)
        if price is None or price.empty: return pd.DataFrame()
        price.columns = [c.lower() for c in price.columns]
        price = price.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
        price['date'] = pd.to_datetime(price['date'])
        
        # 指標計算
        df = price.sort_values('date')
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
        
        # 法人數據 (容錯)
        try:
            inst = dl.get_data(dataset="InstitutionalInvestorsBuySell", data_id=sid, start_date=start_dt)
            if not inst.empty:
                inst = inst.groupby(['date', 'name'])['buy_sell'].sum().unstack().fillna(0)
                inst.index = pd.to_datetime(inst.index)
                df = df.merge(inst, left_on='date', right_index=True, how='left').fillna(0)
                df['total_inst'] = df.get('Foreign_Investor', 0) + df.get('Investment_Trust', 0) + df.get('Dealer', 0)
            else: df['total_inst'] = 0
        except: df['total_inst'] = 0
            
        return df
    except: return pd.DataFrame()

# --- 4. UI 佈局 ---
with st.sidebar:
    st.header("⚡ 策略監控")
    st.selectbox("🔍 搜尋標的", options=display_list, 
                 index=display_list.index(next(s for s in display_list if st.session_state.active_sid in s)), 
                 key="stock_selector_key", on_change=sync_selection)
    st.divider()
    st.caption(f"已同步：{len(display_list)} 檔上市個股")

# --- 5. 繪圖顯示 ---
df = fetch_data(st.session_state.active_sid)

if not df.empty:
    pdf = df.tail(120)
    d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.02, 
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=("K線 / 布林通道", "MACD 指標", "三大法人買賣超", "成交量")
    )

    # 1. K線 + 布林
    fig.add_trace(go.Candlestick(x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'], name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['upper'], line=dict(color='rgba(255,255,255,0.2)', width=1), name="上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['lower'], line=dict(color='rgba(255,255,255,0.2)', width=1), fill='tonexty', name="下軌"), row=1, col=1)

    # 2. MACD
    colors = ['#FF3232' if x > 0 else '#00AA00' for x in pdf['macd_hist']]
    fig.add_trace(go.Bar(x=d_str, y=pdf['macd_hist'], marker_color=colors, name="MACD柱"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dif'], line=dict(color='white', width=1.5), name="DIF"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d_str, y=pdf['dea'], line=dict(color='yellow', width=1.5), name="DEA"), row=2, col=1)

    # 3. 法人
    fig.add_trace(go.Bar(x=d_str, y=pdf['total_inst'], marker_color='#AB63FA', name="法人"), row=3, col=1)

    # 4. 成交量
    vol_colors = ['#FF3232' if pdf['close'].iloc[i] >= pdf['open'].iloc[i] else '#00AA00' for i in range(len(pdf))]
    fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color=vol_colors, name="成交量"), row=4, col=1)

    fig.update_layout(height=900, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)