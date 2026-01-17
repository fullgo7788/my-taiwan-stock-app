import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 核心初始化 ---
st.set_page_config(page_title="AlphaRadar VIP策略終端", layout="wide")

if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            })
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎 ---
@st.cache_data(ttl=86400)
def get_universe():
    info = safe_fetch("TaiwanStockInfo")
    backup = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"}
    ])
    if info.empty or 'stock_id' not in info.columns:
        df = backup
    else:
        info = info[info['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([info, backup]).drop_duplicates('stock_id')
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master = get_universe()
tag_to_id = master.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制 ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    try:
        curr_idx = int(master[master['stock_id'] == st.session_state.current_sid].index[0])
    except:
        curr_idx = 0

    sel_tag = st.selectbox("🔍 全市場個股搜尋", options=master['display'].tolist(), index=curr_idx)
    st.session_state.current_sid = tag_to_id[sel_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 權限已啟動")
    elif pw != "":
        st.session_state.is_vip = False
        st.error("❌ 密鑰錯誤")

# --- 5. 功能分頁 ---
tabs = st.tabs(["📊 技術圖表", "📡 動能掃描", "🐳 籌碼分析"])

# TAB 1: 技術連動 (均線 MA5/20/60)
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
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
        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

# TAB 2: 動能掃描 (含 VIP 專屬策略)
with tabs[1]:
    st.subheader("📡 策略掃描器")
    c1, c2 = st.columns(2)
    with c1: target_pct = st.slider("基本漲幅 (%)", 0.0, 10.0, 2.0)
    with c2: target_vol = st.number_input("最低成交量 (張)", 300, 20000, 1000)
    
    st.divider()
    
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        basic_scan = st.button("🔍 執行基礎漲幅掃描")
    
    with btn_col2:
        # VIP 專屬按鈕
        vip_scan = st.button("💎 [VIP] 5日線上量縮收紅")

    if basic_scan:
        with st.spinner("掃描市場中..."):
            for i in range(7):
                dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_fetch("TaiwanStockPrice", start_date=dt)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= target_pct) & (all_p['volume'] >= target_vol * 1000)].copy()
                    if not res.empty:
                        res = res.merge(master[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"結果日期：{dt}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']], use_container_width=True, hide_index=True)
                        break

    if vip_scan:
        if st.session_state.is_vip:
            with st.spinner("VIP 策略運算中 (需抓取歷史資料)..."):
                # 為了計算 MA5 與 昨日成交量，需要多抓幾天的資料
                for i in range(7):
                    target_dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    start_dt = (datetime.now() - timedelta(days=i+15)).strftime('%Y-%m-%d')
                    
                    # 獲取全市場近日資料
                    df_all = safe_fetch("TaiwanStockPrice", start_date=start_dt)
                    if not df_all.empty:
                        # 篩選出目標日期的數據
                        valid_df = []
                        for sid, group in df_all.groupby('stock_id'):
                            if len(group) < 6: continue
                            group = group.sort_values('date')
                            
                            # 計算 MA5
                            group['ma5'] = group['close'].rolling(5).mean()
                            
                            # 獲取今日(目標日)與昨日數據
                            today = group.iloc[-1]
                            yesterday = group.iloc[-2]
                            
                            # 策略條件：1.收紅 2.量縮 3.收盤在MA5之上 4.基本量過濾
                            cond_red = today['close'] > today['open']
                            cond_vol_down = today['volume'] < yesterday['volume']
                            cond_above_ma5 = today['close'] > today['ma5']
                            cond_min_vol = today['volume'] >= target_vol * 1000
                            
                            if cond_red and cond_vol_down and cond_above_ma5 and cond_min_vol:
                                valid_df.append({
                                    'stock_id': sid,
                                    'close': today['close'],
                                    'vol_today': int(today['volume']/1000),
                                    'vol_yesterday': int(yesterday['volume']/1000),
                                    'ma5': round(today['ma5'], 2)
                                })
                        
                        if valid_df:
                            res_vip = pd.DataFrame(valid_df).merge(master[['stock_id', 'stock_name']], on='stock_id', how='left')
                            st.success(f"💎 VIP 策略掃描完成 (日期: {target_dt})")
                            st.dataframe(res_vip[['stock_id', 'stock_name', 'close', 'vol_today', 'vol_yesterday', 'ma5']], use_container_width=True, hide_index=True)
                            break
        else:
            st.error("🔒 此為 VIP 專屬策略，請輸入授權碼解鎖後再執行。")

# TAB 3: 籌碼分析
with tabs[2]:
    if st.session_state.is_vip:
        # (保持原有的籌碼分析邏輯...)
        chip = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            st.line_chart(chip.iloc[:, -1])
    else:
        st.warning("🔒 籌碼趨勢僅限 VIP。")