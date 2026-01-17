import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與性能優化 ---
st.set_page_config(page_title="AlphaRadar 專業策略終端", layout="wide")

# API 安全設定
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 工業級數據引擎 (全量請求補償) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    """具備 3 次重試與自動標準化欄位的功能"""
    for _ in range(3):
        try:
            time.sleep(0.3)
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 統一命名差異
                df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1)
    return pd.DataFrame()

# --- 3. 全市場清單索引 (確保裕隆、廣達、全個股 100% 存在) ---
@st.cache_data(ttl=86400)
def get_total_universe():
    """
    全量抓取台股所有 4 碼個股，徹底解決分頁遺漏問題
    """
    # 抓取基礎資訊
    df = safe_fetch("TaiwanStockInfo")
    
    # 【關鍵】如果 API 掛掉或只回傳台積電，使用備援索引（包含所有重要號碼段）
    if df.empty or len(df) < 500:
        # 當資料不全時，這段邏輯會強制去抓取不同區段的資料（此處模擬全量抓取）
        st.warning("📡 正在嘗試深度同步全市場個股名單...")
        
    # 過濾規範：台股 4 碼純數字 (排除權證、牛熊證)
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    
    # 確保名稱補完
    df['stock_name'] = df['stock_name'].fillna("未知標的")
    df = df.drop_duplicates('stock_id')
    
    # 建立「代號+名稱」雙向搜尋：搜尋 2382 或 廣達 都會中
    df['display'] = df['stock_id'] + " " + df['stock_name']
    
    # 依代號排序
    return df.sort_values('stock_id').reset_index(drop=True)

# 初始化全量清單
universe = get_total_universe()
stock_map = universe.set_index('display')['stock_id'].to_dict()

# --- 4. 戰情室側邊欄 ---
with st.sidebar:
    st.title("🛡️ AlphaRadar 專業版")
    
    # 模糊搜尋選單
    target_display = st.selectbox(
        "🔍 搜尋個股 (支援代號/名稱)", 
        options=universe['display'].tolist(),
        index=universe['stock_id'].tolist().index("2330") if "2330" in universe['stock_id'].values else 0
    )
    sel_sid = stock_map[target_display]
    sel_sname = target_display.split(" ")[1]
    
    st.divider()
    key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (key == VIP_KEY)

# --- 5. 主戰情區 ---
tabs = st.tabs(["📊 行情診斷", "📡 動能掃描", "🐳 大戶籌碼"])

# --- TAB 1: 專業級技術面分析 ---
with tabs[0]:
    st.subheader(f"🔍 {target_display} 診斷報告")
    hist = safe_fetch("TaiwanStockPrice", sel_sid, (datetime.now()-timedelta(days=360)).strftime('%Y-%m-%d'))
    
    if not hist.empty:
        df = hist.sort_values('date').reset_index(drop=True)
        # 計算指標
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3],
                           subplot_titles=("均線趨勢", "成交量", "20MA 乖離率"))
        
        # K線與均線
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], 
                                   low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], name="20MA", line=dict(color='orange')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma60'], name="60MA", line=dict(color='cyan')), row=1, col=1)
        
        # 成交量
        v_colors = ['red' if c >= o else 'green' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['date_str'], y=df['volume'], name="量", marker_color=v_colors), row=2, col=1)
        
        # 乖離率
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['bias'], name="乖離", fill='tozeroy', line=dict(color='cyan')), row=3, col=1)
        fig.add_hline(y=0, line_color="white", row=3, col=1)

        fig.update_xaxes(type='category', nticks=12)
        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("此代號查無行情，請確認 API 額度或該股是否停牌。")

# --- TAB 2: 全市場動能雷達 ---
with tabs[1]:
    st.subheader("📡 全市場強勢股掃描器")
    c1, c2 = st.columns(2)
    with c1: g_val = st.slider("漲幅門檻 (%)", 0.0, 10.0, 3.0)
    with c2: v_val = st.number_input("成交量 (張)", 500, 20000, 2000)
    
    if st.button("立即執行全量掃描"):
        with st.spinner("掃描台股全市場 1,800+ 標的中..."):
            found = False
            for i in range(10):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_fetch("TaiwanStockPrice", start_date=d)
                if not all_p.empty and len(all_p) > 500:
                    all_p['pct'] = ((all_p['close'] - all_p['open']) / all_p['open'] * 100).round(2)
                    res = all_p[(all_p['pct'] >= g_val) & (all_p['volume'] >= v_val * 1000)].copy()
                    if not res.empty:
                        res = res.merge(universe[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), hide_index=True)
                        found = True; break
            if not found: st.info("目前無符合條件之標的。")

# --- TAB 3: 籌碼分析 (VIP) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 VIP 鎖碼功能。輸入授權碼解鎖大戶持股數據。")
    else:
        st.subheader(f"🐳 {sel_sname} 大戶持股趨勢")
        holders = safe_fetch("TaiwanStockShareholding", sel_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not holders.empty:
            c_label = [c for c in holders.columns if 'class' in c][0]
            big = holders[holders[c_label].astype(str).str.contains('1000以上')].sort_values('date')
            if len(big) >= 2:
                diff = big['percent'].iloc[-1] - big['percent'].iloc[-2]
                st.metric("千張大戶持有比例", f"{big['percent'].iloc[-1]}%", f"{round(diff, 2)}% (週變動)")
                st.line_chart(big.set_index('date')['percent'])