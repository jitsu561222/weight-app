import streamlit as st
import pandas as pd
from datetime import date
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="体重・体脂肪ログ", page_icon="📊", layout="centered")
st.title("📊 体重・体脂肪ログ")

# -----------------------------
# Google Sheets 接続
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)
gc = gspread.authorize(creds)

SPREADSHEET_ID = st.secrets["spreadsheet"]["id"]
worksheet = gc.open_by_key(SPREADSHEET_ID).worksheet("log")


# -----------------------------
# データ読み込み
# -----------------------------
@st.cache_data(ttl=5)
def load_data():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["date", "weight", "bodyfat"])

    df = pd.DataFrame(records)

    # 型をそろえる
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["bodyfat"] = pd.to_numeric(df["bodyfat"], errors="coerce")

    df = df.dropna(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


df = load_data()

# -----------------------------
# 入力欄
# -----------------------------
st.subheader("今日の記録")

input_date = st.date_input("日付", value=date.today())

col1, col2 = st.columns(2)
with col1:
    weight = st.number_input("体重 (kg)", min_value=0.0, max_value=300.0, step=0.1, format="%.1f")
with col2:
    bodyfat = st.number_input("体脂肪率 (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.1f")

if st.button("保存", type="primary"):
    if weight == 0.0 and bodyfat == 0.0:
        st.warning("体重か体脂肪率を入力してください。")
    else:
        new_row = [input_date.strftime("%Y-%m-%d"), float(weight), float(bodyfat)]
        worksheet.append_row(new_row)
        st.cache_data.clear()
        st.success("保存しました。")
        st.rerun()

# -----------------------------
# 表示期間
# -----------------------------
st.subheader("グラフ")

if df.empty:
    st.info("まだデータがありません。最初の1件を保存してください。")
    st.stop()

period = st.radio("表示期間", ["全期間", "直近30日"], horizontal=True)

df_view = df.copy()
if period == "直近30日":
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=30)
    df_view = df_view[df_view["date"] >= cutoff]

if df_view.empty:
    st.info("この期間のデータがありません。")
    st.stop()

# 7日移動平均
df_view["weight_ma7"] = df_view["weight"].rolling(7, min_periods=1).mean()
df_view["bodyfat_ma7"] = df_view["bodyfat"].rolling(7, min_periods=1).mean()

df_view = df_view.set_index("date")

st.write("### 体重")
st.line_chart(df_view[["weight", "weight_ma7"]])

st.write("### 体脂肪率")
st.line_chart(df_view[["bodyfat", "bodyfat_ma7"]])

# -----------------------------
# 最新値表示
# -----------------------------
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) >= 2 else None

col_a, col_b = st.columns(2)
with col_a:
    if prev is not None and pd.notna(prev["weight"]):
        delta_w = latest["weight"] - prev["weight"]
    else:
        delta_w = None
    st.metric("最新体重", f'{latest["weight"]:.1f} kg' if pd.notna(latest["weight"]) else "-", 
              f"{delta_w:+.1f} kg" if delta_w is not None else None)

with col_b:
    if prev is not None and pd.notna(prev["bodyfat"]):
        delta_bf = latest["bodyfat"] - prev["bodyfat"]
    else:
        delta_bf = None
    st.metric("最新体脂肪率", f'{latest["bodyfat"]:.1f} %' if pd.notna(latest["bodyfat"]) else "-", 
              f"{delta_bf:+.1f} %" if delta_bf is not None else None)

# -----------------------------
# データ表
# -----------------------------
with st.expander("記録一覧を表示"):
    show_df = df.copy()
    show_df["date"] = show_df["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(show_df, use_container_width=True)
