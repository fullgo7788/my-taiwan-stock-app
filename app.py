import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與會話管理 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

if 'vip_auth' not in st.session_state:
    st.session_state.vip_auth = False

# 【請確認您的 Token】
# 建議到 FinMind 官網申請個人 Token 填入
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 (內建重試與匿名容錯) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    for attempt in range(3):
        try:
            time.sleep(0.5) # 保護 API，避免過快被封鎖
            df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [col.lower() for col in df.columns]
                # 統一欄位名稱
                rename_map = {'max': 'high', 'min': 'low', 'trading_volume': 'volume'}
                df = df.rename(columns=rename_map)
                if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
                if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
                return df
        except:
            time.sleep(1.5)
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    # 離線備援名單，防止 API 第一步就掛掉
    backup = pd.DataFrame({
        'stock_id': ['2330', '2317', '2454', '3629', '2303'],
        'stock_name': ['台積電', '鴻海', '聯發科', '地心引力', '聯電']
    })
    if df.empty:
        df = backup
    else:
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        if 'stock_name' not in df.columns: df['stock_name'] = df['stock_id']
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df

# --- 3. 處理狀態同步 ---
master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()
id_to_name = master_info.set_index('stock_id')['stock_name'].to_dict()

with st.sidebar:
    st.header("⚡ 戰情控制中心")
    target_display = st.selectbox("🎯 選擇個股", options=list(name_to_id.keys()), index=0, key="global_selector")
    sel_sid = name_to_id[target_display]
    sel_sname = id_to_name.get(sel_sid, "未知")
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password", help="輸入 ST888 並按下 Enter")
    if pw == VIP_KEY:
        st.session_state.vip_auth = True
        st.success("✅ VIP 已解鎖")
    else:
        st.session_state.vip_auth = False

tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1: 趨勢診斷 (含K線、均線、RSI、乖離率) ---
with tabs[0]:
    st.subheader(f"🔍 診斷報告：{sel_sid} {sel_sname}")
    start_dt = (datetime.now()-timedelta(days=360)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        # 技術指標計算
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['bias'] = ((df['close'] - df['ma20']) / df['ma20']) * 100
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
            row_heights=[0.4, 0.1, 0.25, 0.25],
            subplot_titles=("", "", "RSI (14) 強弱指標", "20MA 乖離率 (%)")
        )
        
        fig.add_trace(go.Candlestick(x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], name="20MA", line=dict(color='#FFD700', width=1.5)), row=1, col=1)
        
        v_colors = ['#FF3333' if c >= o else '#228B22' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['date_str'], y=df['volume'], name="量", marker_color=v_colors), row=2, col=1)
        
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['rsi'], name="RSI", line=dict(color='#E195FF')), row=3, col=1)
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['bias'], name="乖離", line=dict(color='#00FF00'), fill='tozeroy'), row=4, col=1)
        fig.add_hline(y=0, line_color="white", row=4, col=1)

        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=900, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("行情數據讀取失敗。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    st.subheader("📡 全市場強勢爆量雷達")
    if st.button("啟動雷達掃描", key="btn_t2"):
        with st.spinner("正在搜尋最近交易日..."):
            found = False
            for i in range(10):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty and len(all_p) > 100:
                    res = all_p[(all_p['close'] > all_p['open']*1.04) & (all_p['volume'] >= 3000000)].copy()
                    if not res.empty:
                        res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'volume']].sort_values('volume', ascending=False))
                        found = True; break
            if not found: st.info("近期無符合條件標的。")

# --- Tab 3: VIP 鎖碼雷達 (穩定度終極強化) ---
with tabs[2]:
    if not st.session_state.vip_auth:
        st.warning("🔒 請在側邊欄輸入授權碼 ST888 並按下 Enter 解鎖。")
    else:
        st.subheader("🚀 鎖碼雷達 (追蹤千張大戶增持股)")
        if st.button("執行籌碼深度分析", key="btn_t3"):
            p = st.progress(0); s = st.empty()
            with st.spinner("正在執行深度掃描，請給系統約 20 秒時間..."):
                t_df = pd.DataFrame()
                for i in range(10):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    t_df = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not t_df.empty and len(t_df) > 100: 
                        st.info(f"📅 分析基準日：{d}")
                        break
                
                if not t_df.empty:
                    cands = t_df[t_df['stock_id'].str.len() == 4].sort_values('volume', ascending=False).head(12)
                    final_list = []
                    for idx, row in enumerate(cands.iterrows()):
                        sid = row[1]['stock_id']
                        s.text(f"🔍 分析進度: {sid} ({idx+1}/12)")
                        p.progress((idx+1)/12)
                        
                        # 擴大搜尋範圍至 50 天，確保能對比本週與上週的大戶持股
                        h = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=50)).strftime('%Y-%m-%d'))
                        if not h.empty:
                            c_col = next((c for c in h.columns if 'class' in c), None)
                            if c_col:
                                bh = h[h[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2:
                                    diff = bh['percent'].iloc[-1] - bh['percent'].iloc[-2]
                                    if diff > 0:
                                        final_list.append({
                                            "代號": sid, 
                                            "名稱": id_to_name.get(sid, "未知"), 
                                            "最新持股%": f"{bh['percent'].iloc[-1]}%",
                                            "大戶增幅": f"📈 +{round(diff, 2)}%"
                                        })
                        time.sleep(0.6) # 關鍵延遲，防止 API 拒絕請求
                    
                    s.empty(); p.empty()
                    if final_list:
                        st.balloons()
                        st.table(pd.DataFrame(final_list).sort_values("大戶增幅", ascending=False))
                    else:
                        st.info("💡 掃描完成。目前熱門股的大戶持股相較前次報告暫無明顯增加。")
                else:
                    st.error("⚠️ 無法獲取行情，請確認 API Token 額度。")