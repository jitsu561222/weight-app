import streamlit as st
import pandas as pd
import gspread
import altair as alt
from datetime import date
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="体重・体脂肪ログ", page_icon="📊", layout="centered")
st.title("📊 体重・体脂肪ログ")

# -----------------------------
# 設定
# -----------------------------
DEFAULT_HEIGHT_CM = 170.0
DEFAULT_TARGET_WEIGHT = 65.0

# -----------------------------
# Google Sheets 接続
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)
gc = gspread.authorize(creds)

SPREADSHEET_ID = st.secrets["spreadsheet"]["id"]
ws = gc.open_by_key(SPREADSHEET_ID).worksheet("log")

# -----------------------------
# データ読み込み
# -----------------------------
@st.cache_data(ttl=5)
def load_data():
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=["date", "weight", "bodyfat"])

    df = pd.DataFrame(records)

    for col in ["date", "weight", "bodyfat"]:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["bodyfat"] = pd.to_numeric(df["bodyfat"], errors="coerce")

    df = df.dropna(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df

df = load_data()

# -----------------------------
# サイド設定
# -----------------------------
with st.sidebar:
    st.header("設定")
    height_cm = st.number_input(
        "身長 (cm)",
        min_value=50.0,
        max_value=250.0,
        value=DEFAULT_HEIGHT_CM,
        step=0.1,
        format="%.1f"
    )
    target_weight = st.number_input(
        "目標体重 (kg)",
        min_value=0.0,
        max_value=300.0,
        value=DEFAULT_TARGET_WEIGHT,
        step=0.1,
        format="%.1f"
    )
    display_days = st.selectbox(
        "表示期間",
        ["全期間", "直近30日", "直近90日"],
        index=1
    )

# -----------------------------
# 入力欄
# -----------------------------
st.subheader("今日の記録")

input_date = st.date_input("日付", value=date.today())

col1, col2 = st.columns(2)
with col1:
    weight = st.number_input(
        "体重 (kg)",
        min_value=0.0,
        max_value=300.0,
        step=0.1,
        format="%.1f"
    )

with col2:
    bodyfat = st.number_input(
        "体脂肪率 (%)",
        min_value=0.0,
        max_value=100.0,
        step=0.1,
        format="%.1f"
    )

if st.button("保存", type="primary"):
    if weight == 0.0 and bodyfat == 0.0:
        st.warning("体重か体脂肪率を入力してください。")
    else:
        new_date = input_date.strftime("%Y-%m-%d")

        # 同じ日付がすでにある場合は上書き
        if not df.empty and (df["date"].dt.strftime("%Y-%m-%d") == new_date).any():
            row_index = df.index[df["date"].dt.strftime("%Y-%m-%d") == new_date][0]
            sheet_row = row_index + 2  # ヘッダー行があるため +2
            ws.update(f"A{sheet_row}:C{sheet_row}", [[new_date, float(weight), float(bodyfat)]])
            st.success(f"{new_date} の記録を更新しました。")
        else:
            ws.append_row([new_date, float(weight), float(bodyfat)])
            st.success("保存しました。")

        st.cache_data.clear()
        st.rerun()

# -----------------------------
# データが無い場合
# -----------------------------
if df.empty:
    st.info("まだデータがありません。最初の1件を保存してください。")
    st.stop()

# -----------------------------
# 表示用データ作成
# -----------------------------
df_view = df.copy()

if display_days == "直近30日":
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=30)
    df_view = df_view[df_view["date"] >= cutoff]
elif display_days == "直近90日":
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=90)
    df_view = df_view[df_view["date"] >= cutoff]

if df_view.empty:
    st.info("この期間のデータがありません。")
    st.stop()

height_m = height_cm / 100

df_view["bmi"] = df_view["weight"] / (height_m ** 2)
df_view["weight_ma7"] = df_view["weight"].rolling(7, min_periods=1).mean()
df_view["bodyfat_ma7"] = df_view["bodyfat"].rolling(7, min_periods=1).mean()
df_view["bmi_ma7"] = df_view["bmi"].rolling(7, min_periods=1).mean()
df_view["target_weight"] = target_weight
df_view["date_str"] = df_view["date"].dt.strftime("%Y-%m-%d")

# -----------------------------
# 最新サマリー
# -----------------------------
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) >= 2 else None

latest_weight = latest["weight"] if pd.notna(latest["weight"]) else None
latest_bodyfat = latest["bodyfat"] if pd.notna(latest["bodyfat"]) else None
latest_bmi = (latest_weight / (height_m ** 2)) if latest_weight is not None else None

delta_weight = None
delta_bodyfat = None
if prev is not None:
    if pd.notna(prev["weight"]) and latest_weight is not None:
        delta_weight = latest_weight - prev["weight"]
    if pd.notna(prev["bodyfat"]) and latest_bodyfat is not None:
        delta_bodyfat = latest_bodyfat - prev["bodyfat"]

st.subheader("最新サマリー")
c1, c2, c3 = st.columns(3)

with c1:
    st.metric(
        "最新体重",
        f"{latest_weight:.1f} kg" if latest_weight is not None else "-",
        f"{delta_weight:+.1f} kg" if delta_weight is not None else None
    )

with c2:
    st.metric(
        "最新体脂肪率",
        f"{latest_bodyfat:.1f} %" if latest_bodyfat is not None else "-",
        f"{delta_bodyfat:+.1f} %" if delta_bodyfat is not None else None
    )

with c3:
    st.metric(
        "BMI",
        f"{latest_bmi:.1f}" if latest_bmi is not None else "-"
    )

# -----------------------------
# グラフ作成用関数
# -----------------------------
def make_date_line_chart(dataframe, columns, y_title):
    chart_data = dataframe[["date", "date_str"] + columns].copy()
    chart_data = chart_data.melt(
        id_vars=["date", "date_str"],
        value_vars=columns,
        var_name="項目",
        value_name="値"
    )

    label_map = {
        "weight": "体重",
        "weight_ma7": "体重(7日平均)",
        "target_weight": "目標体重",
        "bodyfat": "体脂肪率",
        "bodyfat_ma7": "体脂肪率(7日平均)",
        "bmi": "BMI",
        "bmi_ma7": "BMI(7日平均)",
    }
    chart_data["項目"] = chart_data["項目"].map(label_map).fillna(chart_data["項目"])

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "yearmonthdate(date):T",
                title="日付",
                axis=alt.Axis(format="%m/%d", labelAngle=0)
            ),
            y=alt.Y("値:Q", title=y_title),
            color=alt.Color("項目:N", title="表示"),
            tooltip=[
                alt.Tooltip("date_str:N", title="日付"),
                alt.Tooltip("項目:N", title="項目"),
                alt.Tooltip("値:Q", title=y_title, format=".1f"),
            ],
        )
        .properties(height=320)
        .interactive()
    )
    return chart

# -----------------------------
# グラフ
# -----------------------------
st.subheader("グラフ")

st.write("### 体重")
weight_chart = make_date_line_chart(
    df_view,
    ["weight", "weight_ma7", "target_weight"],
    "体重 (kg)"
)
st.altair_chart(weight_chart, use_container_width=True)

st.write("### 体脂肪率")
bodyfat_chart = make_date_line_chart(
    df_view,
    ["bodyfat", "bodyfat_ma7"],
    "体脂肪率 (%)"
)
st.altair_chart(bodyfat_chart, use_container_width=True)

st.write("### BMI")
bmi_chart = make_date_line_chart(
    df_view,
    ["bmi", "bmi_ma7"],
    "BMI"
)
st.altair_chart(bmi_chart, use_container_width=True)

# -----------------------------
# 月平均
# -----------------------------
st.subheader("月平均")
monthly = df.copy()
monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
monthly_avg = monthly.groupby("month", as_index=False)[["weight", "bodyfat"]].mean()

st.write("### 月平均 体重")
monthly_weight_chart = (
    alt.Chart(monthly_avg)
    .mark_line(point=True)
    .encode(
        x=alt.X("month:N", title="月"),
        y=alt.Y("weight:Q", title="体重 (kg)"),
        tooltip=[
            alt.Tooltip("month:N", title="月"),
            alt.Tooltip("weight:Q", title="体重", format=".1f")
        ],
    )
    .properties(height=280)
)
st.altair_chart(monthly_weight_chart, use_container_width=True)

st.write("### 月平均 体脂肪率")
monthly_bodyfat_chart = (
    alt.Chart(monthly_avg)
    .mark_line(point=True)
    .encode(
        x=alt.X("month:N", title="月"),
        y=alt.Y("bodyfat:Q", title="体脂肪率 (%)"),
        tooltip=[
            alt.Tooltip("month:N", title="月"),
            alt.Tooltip("bodyfat:Q", title="体脂肪率", format=".1f")
        ],
    )
    .properties(height=280)
)
st.altair_chart(monthly_bodyfat_chart, use_container_width=True)

# -----------------------------
# 記録一覧
# -----------------------------
with st.expander("記録一覧を表示"):
    show_df = df.copy()
    show_df["BMI"] = show_df["weight"] / (height_m ** 2)
    show_df["date"] = show_df["date"].dt.strftime("%Y-%m-%d")
    show_df = show_df.rename(
        columns={
            "date": "日付",
            "weight": "体重(kg)",
            "bodyfat": "体脂肪率(%)"
        }
    )
    st.dataframe(show_df, use_container_width=True)
