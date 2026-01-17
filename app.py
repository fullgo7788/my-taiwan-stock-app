import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 終極穩定版", layout="wide")

# 初始化 VIP 狀態，確保切換分頁不掉線
if 'vip_auth' not in st.session_state:
    st.session_state.vip_auth = False

# 【請替換為您的有效 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據抓取引擎 (含自適應欄位修正) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    """
    對 API 回傳進行標準化，防止 KeyError 或資料不全導致的崩潰
    """
    try:
        time.sleep(0.3) # 避免過快請求被封鎖
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            # 統一轉換為小寫，解決 API 欄位大小寫不一問題
            df.columns = [col.lower() for col in df.columns]
            
            # 欄位映射：將各種變體統一為標準名稱
            rename_map = {
                'trading_volume': 'volume',
                'max': 'high',
                'min': 'low',
                'stock_hold_class': 'level',
                'stock_hold_level': 'level',
                'stage': 'level'
            }
            df = df.rename(columns=rename_map)
            if 'stock_id' in df.columns: 
                df['stock_id'] = df['stock_id'].astype(str)
            return df
    except Exception as e:
        print(f"API Error: {e}")
    return pd.DataFrame()

# --- 3. 全市場索引引擎 (確保 2382, 2201 100% 存在) ---
@st.cache_data(ttl=86400)
def get_full_universe():
    """
    抓取全台股索引，若 API 回傳不全則啟用保底機制
    """
    raw_info = safe_fetch("TaiwanStockInfo")
    
    # 核心保底名單：確保 API 抽風時基本功能正常
    backup_list = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "2201", "stock_name": "裕隆"},
        {"stock_id": "2436", "stock_name": "偉詮電"},
        {"stock_id": "3035", "stock_name": "智原"}
    ])
    
    if raw_info.empty or 'stock_id' not in raw_info.columns:
        df = backup_list
    else:
        # 過濾純 4 碼數字 (排除權證、牛熊證等雜訊)
        raw_info = raw_info[raw_info['stock_id'].str.match(r'^\d{4}$')]
        df = pd.concat([raw_info, backup_list]).drop_duplicates('stock_id')
    
    df['display_tag'] = df['stock_id'] + " " + df['stock_name'].fillna("未知")
    return df.sort_values('stock_id').reset_index(drop=True)

# 載入主索引並建立字典
master_df = get_full_universe()
tag_to_id = master_df.set_index('display_tag')['stock_id'].to_dict()

# --- 4. 側邊欄控制與 VIP 驗證 ---
with st.sidebar:
    st.header("⚡ 策略控制中心")
    
    # 自動定位到廣達 (若存在)
    try:
        start_idx = int(master_df[master_df['stock_id'] == "2382"].index[0])
    except:
        start_idx = 0

    selected_display = st.selectbox(
        "🔍 全市場搜尋 (輸入代號/名稱)",
        options=master_df['display_tag'].tolist(),
        index=start_idx
    )
    
    # 強制連動：獲取當前選擇的 ID
    current_sid = tag_to_id[selected_display]
    
    st.divider()
    pw_input = st.text_input("💎 VIP 授權碼", type="password")
    # 即時驗證邏輯
    if pw_input == VIP_KEY:
        st.session_state.vip_auth = True
        st.success("✅ VIP 權限已啟動")
    elif pw_input:
        st.session_state.vip_auth = False
        st.error("❌ 密碼錯誤")

# --- 5. 主戰情室分頁 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 VIP 籌碼"])

# Tab 1: 技術診斷 (標籤與數據強連動)
with tabs[0]:
    st.subheader(f"📈 行情診斷：{selected_display}")
    hist = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    
    if not hist.empty:
        df = hist.sort_values('date')
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        # K線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], 
                                   low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        # 成交量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray'), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("⚠️ 目前查無即時行情數據，請確認 API 額度。")

# Tab 2: 強勢掃描 (修正沒反應問題)
with tabs[1]:
    st.subheader("📡 全市場即時動能雷達")
    c1, c2 = st.columns(2)
    with c1: pct_target = st.slider("漲幅門檻 (%)", 1.0, 10.0, 3.5)
    with c2: vol_target = st.number_input("成交量門檻 (張)", 500, 20000, 2000)
    
    if st.button("🚀 執行全量掃描"):
        with st.spinner("掃描台股 1800+ 標的中..."):
            found_data = False
            for i in range(7): # 自動找最近的交易日
                check_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_prices = safe_fetch("TaiwanStockPrice", start_date=check_date)
                
                if not all_prices.empty and len(all_prices) > 500:
                    all_prices['pct'] = ((all_prices['close'] - all_prices['open']) / all_prices['open'] * 100).round(2)
                    # 篩選邏輯：成交量單位換算為張
                    res = all_prices[
                        (all_prices['pct'] >= pct_target) & 
                        (all_prices['volume'] >= vol_target * 1000) &
                        (all_prices['stock_id'].str.len() == 4)
                    ].copy()
                    
                    if not res.empty:
                        res = res.merge(master_df[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現最新交易日：{check_date}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'pct', 'volume']].sort_values('pct', ascending=False), 
                                     use_container_width=True, hide_index=True)
                        found_data = True
                        break
            if not found_data: st.warning("當前設定查無符合標的。")

# --- Tab 3: VIP 籌碼 (大戶+外資 雙重自動適應版) ---
with tabs[2]:
    if st.session_state.vip_auth:
        st.subheader(f"🐳 {selected_display} 籌碼綜合分析")
        
        # 1. 嘗試抓取「大戶分級」資料
        chip_df = safe_fetch("TaiwanStockShareholding", current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        
        # 2. 判斷資料類型並繪圖
        if not chip_df.empty:
            # 偵測是否存在分級欄位 (level, class)
            level_cols = [c for c in chip_df.columns if any(k in c for k in ['level', 'class', 'stage'])]
            
            if level_cols:
                # --- 模式 A: 顯示大戶分級趨勢 ---
                l_col = level_cols[0]
                big_players = chip_df[chip_df[l_col].astype(str).str.contains('1000以上|15|999,999')].sort_values('date')
                
                if not big_players.empty:
                    st.caption("🔍 數據來源：集保中心千張大戶持股比")
                    fig_big = go.Figure()
                    fig_big.add_trace(go.Scatter(x=big_players['date'], y=big_players['percent'], mode='lines+markers', line=dict(color='#00FFCC', width=3)))
                    fig_big.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="持股比 (%)")
                    st.plotly_chart(fig_big, use_container_width=True)
                    st.metric("千張大戶比例", f"{big_players['percent'].iloc[-1]}%", f"{round(big_players['percent'].iloc[-1] - big_players['percent'].iloc[-2], 2) if len(big_players)>1 else 0}%")
                else:
                    st.info("此標的目前無 1000 張以上之大戶細節數據。")
            
            elif 'foreigninvestmentsharesratio' in chip_df.columns:
                # --- 模式 B: 顯示外資持股趨勢 (自動切換) ---
                st.caption("📡 偵測到外資持股格式 - 自動切換分析模式")
                fig_foreign = go.Figure()
                fig_foreign.add_trace(go.Scatter(
                    x=chip_df['date'], 
                    y=chip_df['foreigninvestmentsharesratio'], 
                    mode='lines', 
                    fill='tozeroy',
                    line=dict(color='#FF3366', width=2),
                    name='外資持股比'
                ))
                fig_foreign.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="外資比 (%)")
                st.plotly_chart(fig_foreign, use_container_width=True)
                
                last_f = chip_df['foreigninvestmentsharesratio'].iloc[-1]
                st.metric("外資持股比例", f"{last_f}%")
            else:
                st.error(f"❌ 無法辨識回傳格式。欄位：{list(chip_df.columns)}")
        else:
            st.info("💡 暫無籌碼變動資料回傳，請確認個股代號是否正確。")
    else:
        st.warning("🔒 VIP 專屬功能：請在左側輸入正確授權碼以解鎖籌碼與外資趨勢。")