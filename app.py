import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極連動版", layout="wide")

# 初始化 Session State (跨分頁狀態鎖定)
if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

# 【核心配置】
FINMIND_TOKEN = "fullgo" # 請填入有效 Token
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
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 欄位名稱自動映射規則 (預防 API 改名)
            rename_map = {
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            }
            df = df.rename(columns=rename_map)
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 全市場索引 (確保個股搜尋不中斷) ---
@st.cache_data(ttl=86400)
def get_stock_universe():
    raw = safe_fetch("TaiwanStockInfo")
    # 核心保底索引
    core = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2454", "stock_name": "聯發科"}
    ])
    if raw.empty or 'stock_id' not in raw.columns:
        df = core
    else:
        # 只取 4 碼個股
        raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw, core]).drop_duplicates('stock_id')
    
    df['display'] = df['stock_id'] + " " + df['stock_name'].fillna("個股")
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_stock_universe()
tag_map = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄控制與全站連動 ---
with st.sidebar:
    st.header("⚡ 終端控制台")
    
    # 全局連動選單
    try:
        default_idx = int(master_df[master_df['stock_id'] == st.session_state.current_sid].index[0])
    except:
        default_idx = 0

    selected_tag = st.selectbox(
        "🔍 搜尋/切換個股 (代號或名稱)",
        options=master_df['display'].tolist(),
        index=default_idx
    )
    
    # 當選單切換，立即更新全局狀態
    st.session_state.current_sid = tag_map[selected_tag]
    current_sid = st.session_state.current_sid
    
    st.divider()
    
    # VIP 授權持久化
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY:
        st.session_state.is_vip = True
        st.success("✅ VIP 權限已鎖定連動")
    elif pw:
        st.session_state.is_vip = False
        st.error("密碼錯誤")

# --- 5. 功能連動區 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼分析"])

# --- TAB 1: 技術連動 ---
with tabs[0]:
    st.subheader(f"📈 行情：{selected_tag}")
    price_hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
    
    if not price_hist.empty:
        df = price_hist.sort_values('date')
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        # K線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        # 成交量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='#444444'), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("🔎 API 資料讀取中或緩存建立中...")

# --- TAB 2: 強勢掃描 (不限當前個股) ---
with tabs[1]:
    st.subheader("📡 全市場即時動能雷達")
    c1, c2 = st.columns(2)
    with c1: pct_val = st.slider("漲幅門檻 (%)", 1.0, 10.0, 3.5)
    with c2: vol_val = st.number_input("最低成交量 (張)", 500, 20000, 2000)
    
    if st.button("🚀 啟動掃描引擎"):
        with st.spinner("掃描台股全市場數據..."):
            found_res = False
            for i in range(7):
                dt = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_fetch("TaiwanStockPrice", start_date=dt)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= pct_val) & (all_p['volume'] >= vol_val * 1000) & (all_p['stock_id'].str.len() == 4)].copy()
                    if not res.empty:
                        res = res.merge(master_df[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{dt}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), 
                                     use_container_width=True, hide_index=True)
                        found_res = True; break
            if not found_res: st.warning("當前設定查無符合條件之強勢股。")

# --- TAB 3: 籌碼連動 (自動適應所有回傳格式) ---
with tabs[2]:
    if st.session_state.is_vip:
        st.subheader(f"🐳 {selected_tag} 籌碼綜合連動")
        chip_raw = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        
        if not chip_raw.empty:
            # 偵測大戶分級欄位 (level) 或 外資持股欄位
            level_tags = [c for c in chip_raw.columns if any(k in c for k in ['level', 'class', 'stage'])]
            foreign_ratio = 'foreigninvestmentsharesratio'
            
            if level_tags:
                # 模式 A: 大戶分級 (15級 = 千張大戶)
                l_col = level_tags[0]
                big = chip_raw[chip_raw[l_col].astype(str).str.contains('1000以上|15|999,999')].sort_values('date')
                if not big.empty:
                    st.caption("集保中心：千張大戶持股比例趨勢")
                    st.line_chart(big.set_index('date')['percent'])
                    st.metric("最新持股比", f"{big['percent'].iloc[-1]}%", f"{round(big['percent'].iloc[-1] - big['percent'].iloc[-2], 2) if len(big)>1 else 0}%")
            elif foreign_ratio in chip_raw.columns:
                # 模式 B: 外資持股 (API 自適應)
                st.caption("📡 偵測到外資格式 - 自動切換分析模式")
                st.line_chart(chip_raw.set_index('date')[foreign_ratio])
                st.metric("外資持股比", f"{chip_raw[foreign_ratio].iloc[-1]}%")
            else:
                st.error(f"❌ 無法辨識回傳欄位: {list(chip_raw.columns)}")
        else:
            st.info(f"💡 {selected_tag} 目前無大戶或外資週變動資料。")
    else:
        st.warning("🔒 VIP 專屬連動功能。請於側邊欄輸入 ST888 解鎖全站籌碼資料。")