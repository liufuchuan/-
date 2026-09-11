import streamlit as st
import pandas as pd

# 1. 页面标题
st.set_page_config(page_title="简易数据看板", layout="wide")
st.title("📊 业务核心数据看板")

# 2. 关键指标卡片（并排展示）
col1, col2, col3 = st.columns(3)
col1.metric("今日订单量", "1,250 单", "+12.5%")
col2.metric("在途周转率", "94.2%", "-1.1%")
col3.metric("异常预警数", "3 件", "正常")

st.divider()

# 3. 趋势图表
st.subheader("📈 趋势分析")
chart_data = pd.DataFrame({
    "周一": [120, 210],
    "周二": [150, 230],
    "周三": [180, 220],
    "周四": [220, 280],
    "周五": [260, 310]
}, index=["类目A", "类目B"]).T

st.line_chart(chart_data)

# 4. 详细数据表格
st.subheader("📋 详细数据清单")
st.dataframe(chart_data, use_container_width=True)
