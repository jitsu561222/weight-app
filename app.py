import streamlit as st
import pandas as pd
from datetime import date
import os

st.title("📊 体重・体脂肪ログ")

file = "data.csv"

if os.path.exists(file):
    df = pd.read_csv(file)
else:
    df = pd.DataFrame(columns=["date", "weight", "bodyfat"])

col1, col2 = st.columns(2)

with col1:
    weight = st.number_input("体重 (kg)", step=0.1)

with col2:
    bodyfat = st.number_input("体脂肪率 (%)", step=0.1)

today = date.today()

if st.button("保存"):
    new_data = pd.DataFrame([[today, weight, bodyfat]],
                            columns=["date", "weight", "bodyfat"])
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(file, index=False)
    st.success("保存しました！")

if not df.empty:
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df.set_index("date")

    st.subheader("体重グラフ")
    st.line_chart(df["weight"])

    st.subheader("体脂肪率グラフ")
    st.line_chart(df["bodyfat"])
