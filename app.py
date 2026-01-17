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

# --- Tab 3: VIP 籌碼 (超級偵測與自動校準版) ---
with tabs[2]:
    if st.session_state.vip_auth:
        st.subheader(f"🐳 {selected_display} 大戶籌碼趨勢")
        
        # 抓取籌碼週資料
        chip_data = safe_fetch(
            "TaiwanStockShareholding", 
            current_sid, 
            (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d')
        )
        
        if not chip_data.empty:
            # 【偵錯模式】如果還是抓不到，取消下面這行的註釋可以看到 API 到底回傳了什麼
            # st.write("API 回傳欄位:", list(chip_data.columns))
            
            # 1. 深度掃描所有可能的欄位名稱
            possible_cols = ['level', 'stock_hold_class', 'stage', 'type', 'stock_hold_level']
            l_col = None
            for col in chip_data.columns:
                if any(p in col for p in possible_cols):
                    l_col = col
                    break
            
            if l_col:
                # 2. 定義千張大戶過濾條件 (15 級或包含 1000 以上字樣)
                # 這是台股籌碼最標準的分級制度
                big_players = chip_data[
                    (chip_data[l_col].astype(str) == '15') | 
                    (chip_data[l_col].astype(str).str.contains('1000以上|999,999'))
                ].sort_values('date')
                
                if not big_players.empty:
                    # 3. 繪製專業趨勢圖
                    fig_chip = go.Figure()
                    fig_chip.add_trace(go.Scatter(
                        x=big_players['date'], 
                        y=big_players['percent'], 
                        mode='lines+markers',
                        name='千張大戶持股比',
                        line=dict(color='#00FFCC', width=3),
                        hovertemplate="日期: %{x}<br>持股比: %{y}%"
                    ))
                    fig_chip.update_layout(
                        template="plotly_dark",
                        height=450,
                        margin=dict(l=10, r=10, t=10, b=10),
                        yaxis=dict(title="持股比例 (%)", gridcolor="rgba(255,255,255,0.1)"),
                        xaxis=dict(gridcolor="rgba(255,255,255,0.1)")
                    )
                    st.plotly_chart(fig_chip, use_container_width=True)
                    
                    # 4. 數據看板
                    last_val = big_players['percent'].iloc[-1]
                    prev_val = big_players['percent'].iloc[-2] if len(big_players) > 1 else last_val
                    st.metric("最新千張大戶持股比", f"{last_val}%", f"{round(last_val - prev_val, 2)}% (較上週)")
                else:
                    st.info(f"⚠️ 雖然找到欄位 '{l_col}'，但查無符合 1000 張以上的數據。")
                    # 顯示可用的級別供參考
                    st.write("目前資料分級包含：", chip_data[l_col].unique().tolist())
            else:
                st.error(f"❌ 無法辨識籌碼欄位。當前回傳欄位為: {list(chip_data.columns)}")
        else:
            st.info("💡 此標的近期無籌碼變動資料回傳（通常大型股每週末更新一次）。")
    else:
        st.warning("🔒 此為 VIP 專屬功能，請在左側輸入授權碼解鎖。")