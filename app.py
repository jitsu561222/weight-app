import streamlit as st
import pandas as pd
from datetime import date, datetime
import altair as alt
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="体重・体脂肪・走行距離ログ",
    page_icon="📊",
    layout="centered"
)

st.title("体重")

st.markdown("""
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 1rem;
    max-width: 900px;
}
div[data-testid="stMetric"] {
    background-color: #0f172a;
    padding: 14px 18px;
    border-radius: 14px;
    color: white;
}
div[data-testid="stMetricLabel"] {
    color: #cbd5e1 !important;
}
div[data-testid="stMetricValue"] {
    color: white !important;
}
.small-note {
    color: #64748b;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

# =========================
# Google Sheets 接続設定
# =========================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_NAME = "weight_log"
LOG_WORKSHEET_NAME = "Sheet1"
SETTINGS_WORKSHEET_NAME = "Settings"
DEFAULT_GOAL_WEIGHT = 68.0

EXPECTED_LOG_HEADERS = ["Date", "Weight", "BodyFat", "RunDistance", "Memo", "UpdatedAt"]
EXPECTED_SETTINGS_HEADERS = ["Key", "Value", "UpdatedAt"]


@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    return spreadsheet


def get_or_create_worksheet(spreadsheet, worksheet_name, rows=1000, cols=20):
    try:
        return spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=worksheet_name, rows=rows, cols=cols)


def ensure_log_sheet_headers(ws):
    values = ws.get_all_values()

    if not values:
        ws.append_row(EXPECTED_LOG_HEADERS)
        return

    first_row = values[0]
    normalized = first_row[:len(EXPECTED_LOG_HEADERS)] + [""] * max(0, len(EXPECTED_LOG_HEADERS) - len(first_row))

    needs_fix = False
    for i, expected in enumerate(EXPECTED_LOG_HEADERS):
        cell_val = normalized[i].strip() if normalized[i] else ""
        if cell_val != expected:
            needs_fix = True
            break

    if needs_fix:
        ws.update("A1:F1", [EXPECTED_LOG_HEADERS])


def ensure_settings_sheet_headers(ws):
    values = ws.get_all_values()

    if not values:
        ws.append_row(EXPECTED_SETTINGS_HEADERS)
        return

    first_row = values[0]
    normalized = first_row[:len(EXPECTED_SETTINGS_HEADERS)] + [""] * max(0, len(EXPECTED_SETTINGS_HEADERS) - len(first_row))

    needs_fix = False
    for i, expected in enumerate(EXPECTED_SETTINGS_HEADERS):
        cell_val = normalized[i].strip() if normalized[i] else ""
        if cell_val != expected:
            needs_fix = True
            break

    if needs_fix:
        ws.update("A1:C1", [EXPECTED_SETTINGS_HEADERS])


# =========================
# 設定読み書き
# =========================
def get_setting(ws, key, default_value=None):
    try:
        values = ws.get_all_values()
    except Exception as e:
        st.error(f"Settingsシートの読み込みに失敗しました: {e}")
        return default_value

    if len(values) <= 1:
        return default_value

    for row in values[1:]:
        if len(row) >= 2 and row[0] == key:
            return row[1]

    return default_value


def set_setting(ws, key, value):
    try:
        values = ws.get_all_values()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = [key, str(value), now_str]

        if len(values) <= 1:
            ws.append_row(new_row)
            return

        for i, row in enumerate(values[1:], start=2):
            if len(row) >= 1 and row[0] == key:
                ws.update(f"A{i}:C{i}", [new_row])
                return

        ws.append_row(new_row)
    except Exception as e:
        st.error(f"目標体重の保存に失敗しました: {e}")


def get_goal_weight(settings_ws):
    value = get_setting(settings_ws, "goal_weight", DEFAULT_GOAL_WEIGHT)
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_GOAL_WEIGHT


# =========================
# データ読み込み
# =========================
def load_data(ws):
    try:
        values = ws.get_all_values()
    except Exception as e:
        st.error(f"記録シートの読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=EXPECTED_LOG_HEADERS)

    if not values:
        return pd.DataFrame(columns=EXPECTED_LOG_HEADERS)

    # ヘッダー行を除いたデータ部分だけ読む
    rows = values[1:] if len(values) > 1 else []

    fixed_rows = []
    for row in rows:
        row = row[:len(EXPECTED_LOG_HEADERS)] + [""] * max(0, len(EXPECTED_LOG_HEADERS) - len(row))
        fixed_rows.append(row)

    if not fixed_rows:
        return pd.DataFrame(columns=EXPECTED_LOG_HEADERS)

    df = pd.DataFrame(fixed_rows, columns=EXPECTED_LOG_HEADERS)

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Weight"] = pd.to_numeric(df["Weight"], errors="coerce")
    df["BodyFat"] = pd.to_numeric(df["BodyFat"], errors="coerce")
    df["RunDistance"] = pd.to_numeric(df["RunDistance"], errors="coerce")
    df["UpdatedAt"] = pd.to_datetime(df["UpdatedAt"], errors="coerce")

    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    return df


# =========================
# 1日1件: 同日データは上書き
# =========================
def upsert_data(ws, log_date, weight, bodyfat, run_distance, memo):
    try:
        all_values = ws.get_all_values()
    except Exception as e:
        return False, f"保存前のシート読み込みに失敗しました: {e}"

    date_str = pd.to_datetime(log_date).strftime("%Y-%m-%d")
    new_row = [
        date_str,
        f"{weight:.1f}",
        f"{bodyfat:.1f}",
        f"{run_distance:.1f}",
        memo,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ]

    try:
        if len(all_values) <= 1:
            ws.append_row(new_row)
            return verify_saved_row(ws, date_str)

        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > 0 and row[0] == date_str:
                ws.update(f"A{i}:F{i}", [new_row])
                return verify_saved_row(ws, date_str, updated=True)

        ws.append_row(new_row)
        return verify_saved_row(ws, date_str)

    except Exception as e:
        return False, f"保存処理に失敗しました: {e}"


def verify_saved_row(ws, date_str, updated=False):
    try:
        values = ws.get_all_values()
    except Exception as e:
        return False, f"保存後の確認に失敗しました: {e}"

    for row in values[1:]:
        if len(row) > 0 and row[0] == date_str:
            if updated:
                return True, "updated"
            return True, "added"

    return False, "保存確認ができませんでした。シートに反映されていない可能性があります。"


# =========================
# データ整形
# =========================
def prepare_dataframe(df):
    if df.empty:
        return df.copy()

    temp = df.copy()
    temp = temp.dropna(subset=["Date"])
    temp = temp.sort_values(["Date", "UpdatedAt"])

    temp["DateOnly"] = temp["Date"].dt.date
    temp = temp.groupby("DateOnly", as_index=False).last()
    temp["Date"] = pd.to_datetime(temp["Date"])
    temp = temp.sort_values("Date").reset_index(drop=True)

    temp["RunDistance"] = temp["RunDistance"].fillna(0)
    temp["FatMass"] = temp["Weight"] * (temp["BodyFat"] / 100.0)
    temp["LeanMass"] = temp["Weight"] - temp["FatMass"]
    temp["WeightMA7"] = temp["Weight"].rolling(7).mean()
    temp["BodyFatMA7"] = temp["BodyFat"].rolling(7).mean()
    temp["WeightDiff"] = temp["Weight"].diff()

    return temp


def get_month_data(df, target_month):
    if df.empty:
        return df.copy()

    month_start = pd.Timestamp(target_month.year, target_month.month, 1)
    if target_month.month == 12:
        month_end = pd.Timestamp(target_month.year + 1, 1, 1)
    else:
        month_end = pd.Timestamp(target_month.year, target_month.month + 1, 1)

    return df[(df["Date"] >= month_start) & (df["Date"] < month_end)].copy()


# =========================
# Altair グラフ
# =========================
def build_weight_chart(month_df, goal_weight):
    chart_df = month_df.copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])

    base = alt.Chart(chart_df).encode(
        x=alt.X(
            "Date:T",
            axis=alt.Axis(
                title="",
                format="%m/%d",
                labelAngle=0,
                tickCount="week",
                grid=False
            )
        )
    )

    weight_line = base.mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=3).encode(
        y=alt.Y(
            "Weight:Q",
            title="kg",
            scale=alt.Scale(zero=False)
        ),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("Weight:Q", title="体重", format=".1f")
        ]
    )

    ma_line = base.mark_line(strokeDash=[6, 4], opacity=0.65, strokeWidth=2).encode(
        y=alt.Y("WeightMA7:Q"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("WeightMA7:Q", title="7日移動平均", format=".2f")
        ]
    )

    goal_df = pd.DataFrame({"y": [goal_weight]})
    goal_rule = alt.Chart(goal_df).mark_rule(strokeWidth=2).encode(
        y="y:Q"
    )

    goal_text_df = pd.DataFrame({
        "Date": [chart_df["Date"].max()],
        "y": [goal_weight],
        "label": [f"目標 {goal_weight:.1f}kg"]
    })

    goal_text = alt.Chart(goal_text_df).mark_text(
        align="right",
        dx=-8,
        dy=-8,
        fontSize=12
    ).encode(
        x="Date:T",
        y="y:Q",
        text="label:N"
    )

    chart = (goal_rule + weight_line + ma_line + goal_text).properties(
        height=320
    ).configure_axis(
        grid=True,
        gridOpacity=0.15,
        domain=False,
        tickColor="#cbd5e1",
        labelColor="#334155",
        titleColor="#334155"
    ).configure_view(
        strokeWidth=0
    )

    return chart


def build_run_distance_chart(month_df):
    chart_df = month_df.copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])

    chart = alt.Chart(chart_df).mark_bar(
        cornerRadiusTopLeft=4,
        cornerRadiusTopRight=4
    ).encode(
        x=alt.X(
            "Date:T",
            axis=alt.Axis(
                title="",
                format="%m/%d",
                labelAngle=0,
                tickCount="week",
                grid=False
            )
        ),
        y=alt.Y("RunDistance:Q", title="km"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("RunDistance:Q", title="走行距離", format=".1f")
        ]
    ).properties(
        height=220
    ).configure_axis(
        grid=True,
        gridOpacity=0.15,
        domain=False
    ).configure_view(
        strokeWidth=0
    )

    return chart


def build_bodyfat_chart(month_df):
    chart_df = month_df.copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])

    line1 = alt.Chart(chart_df).mark_line(
        point=alt.OverlayMarkDef(size=50),
        strokeWidth=3
    ).encode(
        x=alt.X(
            "Date:T",
            axis=alt.Axis(title="", format="%m/%d", labelAngle=0, tickCount="week", grid=False)
        ),
        y=alt.Y("BodyFat:Q", title="%"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("BodyFat:Q", title="体脂肪率", format=".1f")
        ]
    )

    line2 = alt.Chart(chart_df).mark_line(
        strokeDash=[6, 4],
        opacity=0.65,
        strokeWidth=2
    ).encode(
        x="Date:T",
        y=alt.Y("BodyFatMA7:Q"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("BodyFatMA7:Q", title="7日移動平均", format=".2f")
        ]
    )

    chart = (line1 + line2).properties(
        height=260
    ).configure_axis(
        grid=True,
        gridOpacity=0.15,
        domain=False
    ).configure_view(
        strokeWidth=0
    )

    return chart


def build_body_composition_chart(month_df):
    chart_df = month_df.copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])

    fat_line = alt.Chart(chart_df).mark_line(
        point=alt.OverlayMarkDef(size=50),
        strokeWidth=3
    ).encode(
        x=alt.X(
            "Date:T",
            axis=alt.Axis(title="", format="%m/%d", labelAngle=0, tickCount="week", grid=False)
        ),
        y=alt.Y("FatMass:Q", title="kg"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("FatMass:Q", title="推定脂肪量", format=".2f")
        ]
    )

    lean_line = alt.Chart(chart_df).mark_line(
        point=alt.OverlayMarkDef(size=50),
        strokeWidth=3,
        opacity=0.75
    ).encode(
        x="Date:T",
        y=alt.Y("LeanMass:Q"),
        tooltip=[
            alt.Tooltip("Date:T", title="日付", format="%Y-%m-%d"),
            alt.Tooltip("LeanMass:Q", title="推定除脂肪量", format=".2f")
        ]
    )

    chart = (fat_line + lean_line).properties(
        height=260
    ).configure_axis(
        grid=True,
        gridOpacity=0.15,
        domain=False
    ).configure_view(
        strokeWidth=0
    )

    return chart


# =========================
# シート初期化
# =========================
spreadsheet = get_spreadsheet()
log_ws = get_or_create_worksheet(spreadsheet, LOG_WORKSHEET_NAME, rows=5000, cols=10)
settings_ws = get_or_create_worksheet(spreadsheet, SETTINGS_WORKSHEET_NAME, rows=100, cols=5)

ensure_log_sheet_headers(log_ws)
ensure_settings_sheet_headers(settings_ws)

saved_goal_weight = get_goal_weight(settings_ws)

# =========================
# 入力フォーム
# =========================
st.subheader("✍️ 今日の記録")

with st.form("log_form"):
    col1, col2 = st.columns(2)

    with col1:
        log_date = st.date_input("日付", value=date.today())
        weight = st.number_input(
            "体重 (kg)",
            min_value=0.0,
            max_value=300.0,
            step=0.1,
            format="%.1f"
        )
        bodyfat = st.number_input(
            "体脂肪率 (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.1f"
        )

    with col2:
        run_distance = st.number_input(
            "走行距離 (km)",
            min_value=0.0,
            max_value=200.0,
            step=0.1,
            format="%.1f"
        )
        goal_weight_input = st.number_input(
            "目標体重 (kg)",
            min_value=30.0,
            max_value=150.0,
            value=float(saved_goal_weight),
            step=0.1,
            format="%.1f"
        )
        memo = st.text_input("メモ", value="")

    submitted = st.form_submit_button("保存する")

    if submitted:
        ok, message = upsert_data(log_ws, log_date, weight, bodyfat, run_distance, memo)

        if ok:
            set_setting(settings_ws, "goal_weight", goal_weight_input)

            if message == "updated":
                st.success("記録を上書きし、目標体重も保存しました。")
            else:
                st.success("記録と目標体重を保存しました。")

            st.rerun()
        else:
            st.error(message)
            st.stop()

# =========================
# データ取得
# =========================
raw_df = load_data(log_ws)
df = prepare_dataframe(raw_df)

if df.empty:
    st.info("まだデータがありません。まずは1件入力してください。")
    st.stop()

# =========================
# 月選択と目標体重変更
# =========================
latest_date = df["Date"].max()
default_month = latest_date.to_pydatetime().date().replace(day=1)

st.subheader("📅 月表示")
col_month, col_goal, col_button = st.columns([2, 1, 1])

with col_month:
    selected_month = st.date_input("表示する月", value=default_month)

with col_goal:
    current_goal_weight = st.number_input(
        "現在の目標体重 (kg)",
        min_value=30.0,
        max_value=150.0,
        value=float(get_goal_weight(settings_ws)),
        step=0.1,
        format="%.1f",
        key="goal_weight_display"
    )

with col_button:
    st.write("")
    st.write("")
    if st.button("目標を保存"):
        set_setting(settings_ws, "goal_weight", current_goal_weight)
        st.success("目標体重を保存しました。")
        st.rerun()

month_df = get_month_data(df, selected_month)

if month_df.empty:
    st.warning("この月のデータはありません。")
    st.stop()

# =========================
# 月次集計
# =========================
month_label = f"{selected_month.year}年{selected_month.month}月"

avg_weight = month_df["Weight"].mean()
avg_bodyfat = month_df["BodyFat"].mean()
sum_run = month_df["RunDistance"].sum()
avg_fat_mass = month_df["FatMass"].mean()

latest_row = month_df.sort_values("Date").iloc[-1]
prev_row = month_df.sort_values("Date").iloc[-2] if len(month_df) >= 2 else None
weight_delta = latest_row["Weight"] - prev_row["Weight"] if prev_row is not None else 0.0
goal_diff = latest_row["Weight"] - current_goal_weight

# =========================
# 大きな月平均表示
# =========================
st.markdown(f"## {month_label}")
st.markdown(
    f"""
    <div style="background:#0f172a;padding:18px 22px;border-radius:16px;margin-bottom:18px;">
        <div style="color:#cbd5e1;font-size:1rem;">{selected_month.month}月1日 - {selected_month.month}月末 の平均体重</div>
        <div style="color:white;font-size:3rem;font-weight:700;line-height:1.1;margin-top:8px;">{avg_weight:.2f} <span style="font-size:1.4rem;">kg</span></div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# サマリー
# =========================
st.subheader("📊 月のまとめ")
c1, c2, c3, c4 = st.columns(4)
c1.metric("月平均体重", f"{avg_weight:.2f} kg")
c2.metric("月平均体脂肪率", f"{avg_bodyfat:.2f} %")
c3.metric("月間走行距離", f"{sum_run:.1f} km")
c4.metric("平均推定脂肪量", f"{avg_fat_mass:.2f} kg")

st.subheader("📌 最新データ")
c5, c6, c7, c8, c9 = st.columns(5)
c5.metric("最新体重", f"{latest_row['Weight']:.1f} kg", f"{weight_delta:+.1f} kg")
c6.metric("最新体脂肪率", f"{latest_row['BodyFat']:.1f} %")
c7.metric("最新走行距離", f"{latest_row['RunDistance']:.1f} km")
c8.metric("推定脂肪量", f"{latest_row['FatMass']:.2f} kg")
c9.metric("目標まで", f"{goal_diff:+.1f} kg")

# =========================
# グラフ
# =========================
st.subheader("📉 体重")
st.altair_chart(
    build_weight_chart(month_df, goal_weight=current_goal_weight),
    use_container_width=True
)

st.subheader("🏃 走行距離")
st.altair_chart(
    build_run_distance_chart(month_df),
    use_container_width=True
)

st.subheader("🔥 体脂肪率")
st.altair_chart(
    build_bodyfat_chart(month_df),
    use_container_width=True
)

st.subheader("🧪 推定体組成")
st.altair_chart(
    build_body_composition_chart(month_df),
    use_container_width=True
)

# =========================
# データ表
# =========================
st.subheader("📋 記録一覧")

display_df = month_df.copy()
display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")

st.dataframe(
    display_df[[
        "Date",
        "Weight",
        "BodyFat",
        "FatMass",
        "LeanMass",
        "RunDistance",
        "WeightDiff",
        "Memo"
    ]].rename(columns={
        "Date": "日付",
        "Weight": "体重(kg)",
        "BodyFat": "体脂肪率(%)",
        "FatMass": "推定脂肪量(kg)",
        "LeanMass": "推定除脂肪量(kg)",
        "RunDistance": "走行距離(km)",
        "WeightDiff": "前日比(kg)",
        "Memo": "メモ"
    }),
    use_container_width=True
)
