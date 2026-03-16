import streamlit as st
import pandas as pd
from datetime import date
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="体重・体脂肪ログ", page_icon="📊")
st.title("📊 体重・体脂肪ログ")

# --- Google Sheets 接続 ---
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
ws = gc.open_by_key(SPREADSHEET_ID).worksheet("log")

# --- データ取得 ---
rows = ws.get_all_records()
if rows:
    df = pd.DataFrame(rows)
else:
    df = pd.DataFrame(columns=["date", "weight", "bodyfat"])

# --- 入力欄 ---
col1, col2 = st.columns(2)

with col1:
    weight = st.number_input("体重 (kg)", min_value=0.0, step=0.1, format="%.1f")

with col2:
    bodyfat = st.number_input("体脂肪率 (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.1f")

today = date.today().isoformat()
st.caption(f"日付: {today}")

# --- 保存処理 ---
if st.button("保存"):
    if weight == 0.0 and bodyfat == 0.0:
        st.warning("体重か体脂肪率を入力してください。")
    else:
        ws.append_row([today, float(weight), float(bodyfat)])
        st.success("保存しました。")
        st.rerun()

# --- 表示 ---
if not df.empty:
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df.set_index("date")

    st.subheader("体重グラフ")
    st.line_chart(df["weight"])

    st.subheader("体脂肪率グラフ")
    st.line_chart(df["bodyfat"])

    with st.expander("最新データ"):
        st.dataframe(df.tail(20))
else:
    st.info("まだデータがありません。最初の1件を保存してください。")
