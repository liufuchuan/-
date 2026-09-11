# -*- coding: utf-8 -*-
"""
快驴生鲜《预采量订货明细》交互式看板
====================================
功能：
  1. 独立筛选：加工中心名称 / 供应商 / 三级类目 / 四级类目 / 日期 / 原材料SKU / 效期标准
  2. 表格字段自由勾选：勾选哪些字段就展示哪些字段
  3. 曲线图：Top N 原材料SKU 的销量/预测/备货指标对比（多日期数据时自动切换为按日期聚合的趋势线）
  4. 圆形饼图：三级类目、四级类目占比

运行方式：
  pip install pandas streamlit plotly -i https://pypi.tuna.tsinghua.edu.cn/simple
  streamlit run 预采量订货明细看板.py
"""
import io
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ================= 配置 =================
# 云端部署：把数据文件和代码放在同一目录（建议命名 data.csv）
# 本地运行：也可以直接改用绝对路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_CANDIDATES = ["data.csv", "预采量订货明细.csv", "预采量订货明细_2026-09-09 (1).csv"]
PAGE_TITLE = "快驴生鲜 · 预采量订货明细看板"

# 七个独立筛选字段
FILTER_COLS = ["加工中心名称", "上次下单供应商", "三级类目", "四级类目", "查询日期", "原材料SKU", "效期标准"]
FILTER_LABELS = {
    "加工中心名称": "加工中心名称", "上次下单供应商": "供应商", "三级类目": "三级类目",
    "四级类目": "四级类目", "查询日期": "日期", "原材料SKU": "原材料SKU", "效期标准": "效期标准",
}
# 表格默认勾选展示的字段
DEFAULT_SHOW_COLS = [
    "查询日期", "加工中心名称", "原材料SKU", "原材料名称", "品属性", "原材料单位",
    "三级类目", "四级类目", "上次下单供应商", "效期标准",
    "当日销量（09-09）", "预测销量", "目标备货量", "预采建议量",
]

st.set_page_config(page_title=PAGE_TITLE, page_icon="🥬", layout="wide")


# ================= 数据加载 =================
@st.cache_data(show_spinner="加载数据中...")
def load_data(uploaded_file=None):
    if uploaded_file is not None:
        content = uploaded_file.getvalue()
        for enc in ("utf-8-sig", "gbk"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=enc, thousands=",", dtype=str)
                break
            except UnicodeDecodeError:
                continue
    else:
        csv_path = None
        for name in CSV_CANDIDATES:
            candidate = os.path.join(SCRIPT_DIR, name)
            if os.path.exists(candidate):
                csv_path = candidate
                break
        if csv_path is None:
            return pd.DataFrame()
        for enc in ("utf-8-sig", "gbk"):
            try:
                df = pd.read_csv(csv_path, encoding=enc, thousands=",", dtype=str)
                break
            except UnicodeDecodeError:
                continue
    df.columns = [c.strip() for c in df.columns]
    # 数值列清理（去除千分位、百分号）
    for col in df.columns:
        if col in FILTER_COLS or col == "原材料名称":
            continue
        cleaned = df[col].astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
        num = pd.to_numeric(cleaned, errors="coerce")
        if num.notna().mean() > 0.9:
            df[col] = num * (0.01 if df[col].astype(str).str.contains("%").any() else 1)
    return df


def fmt_num(v):
    if pd.isna(v):
        return ""
    return f"{v:,.2f}" if isinstance(v, float) and v % 1 else f"{int(v):,}"


# ================= 侧边栏：独立筛选 =================
st.sidebar.header("🔎 数据筛选")
df_raw = load_data()

with st.sidebar:
    upload = st.file_uploader("上传新的订货明细 CSV（不传则读取代码内路径）", type=["csv"])
if upload is not None:
    df_raw = load_data(upload)
if df_raw.empty:
    st.warning("⚠️ 未找到数据文件：请把数据 CSV 命名为 data.csv 与本代码放在同一目录并重新部署，或在左侧直接上传 CSV 文件")
    st.stop()
filters = {}

for col in FILTER_COLS:
    label = FILTER_LABELS[col]
    options = sorted(df_raw[col].dropna().astype(str).unique().tolist())
    with st.sidebar.expander(f"⬇ {label}", expanded=(col in ("加工中心名称", "三级类目"))):
        select_all = st.checkbox("全选", value=True, key=f"all_{col}")
        if select_all:
            chosen = options
        else:
            search = st.text_input(f"搜索{label}", key=f"search_{col}")
            show_opts = [o for o in options if search in o] if search else options
            chosen = st.multiselect(f"{label}（可多选）", show_opts,
                                    default=show_opts if col == "查询日期" else [],
                                    key=f"ms_{col}", label_visibility="collapsed")
    filters[col] = chosen

# 应用筛选
df = df_raw.copy()
for col, chosen in filters.items():
    if chosen:
        df = df[df[col].astype(str).isin(chosen)]

# ================= 侧边栏：图表设置 =================
st.sidebar.header("📈 图表设置")
metric_options = [c for c in df.columns if df[c].dtype != object]
default_metric = "预采建议量" if "预采建议量" in metric_options else metric_options[0]
pie_metric = st.sidebar.selectbox("饼图统计指标", metric_options, index=metric_options.index(default_metric))
top_n = st.sidebar.slider("曲线图 Top N SKU", 5, 50, 10)

# ================= 页面标题与指标卡 =================
st.title(f"🥬 {PAGE_TITLE}")
st.caption(f"数据范围：{len(df_raw):,} 行 → 筛选后：{len(df):,} 行")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
sum_col = pie_metric if pie_metric in df.columns else None
kpi1.metric("筛选后 SKU 数", f"{df['原材料SKU'].nunique():,}")
kpi2.metric("涉及供应商", f"{df['上次下单供应商'].nunique():,}")
kpi3.metric("涉及加工中心", f"{df['加工中心名称'].nunique():,}")
kpi4.metric(f"{pie_metric} 合计", fmt_num(df[sum_col].sum()) if sum_col else "-")

# ================= 表格：勾选字段呈现 =================
st.header("📋 订货明细表")
st.caption("在下方下拉框中勾选想要呈现的字段，勾选哪些就展示哪些")
all_cols = list(df_raw.columns)
show_cols = st.multiselect("勾选要呈现的字段", all_cols, default=[c for c in DEFAULT_SHOW_COLS if c in all_cols])
if show_cols:
    sort_col = st.selectbox("排序字段", ["（不排序）"] + show_cols)
    show_df = df[show_cols].copy()
    if sort_col != "（不排序）" and show_df[sort_col].dtype != object:
        show_df = show_df.sort_values(sort_col, ascending=False)
    st.dataframe(show_df, use_container_width=True, height=480, hide_index=True)
    csv_bytes = show_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ 导出当前筛选结果 CSV", csv_bytes, "筛选结果.csv", "text/csv")
else:
    st.warning("请至少勾选一个字段")

# ================= 曲线图 =================
st.header("📈 曲线图")
date_count = df["查询日期"].nunique()
if date_count > 1:
    st.caption(f"数据包含 {date_count} 个日期，曲线按日期聚合展示「{pie_metric}」合计走势")
    trend = df.groupby("查询日期")[pie_metric].sum().reset_index().sort_values("查询日期")
    fig = px.line(trend, x="查询日期", y=pie_metric, markers=True)
    fig.update_layout(height=420, xaxis_title="日期", yaxis_title=pie_metric)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("当前数据为单日，曲线图对比各 SKU 的销量/预测/备货核心指标")
    line_metrics = [c for c in ["当日销量（09-09）", "昨日销量（09-08）", "近3日日均销", "近7日日均销", "预测销量", "目标备货量", "预采建议量"] if c in df.columns]
    rank_col = "预采建议量" if "预采建议量" in df.columns else (line_metrics[0] if line_metrics else None)
    if rank_col and line_metrics:
        top = df.groupby(["原材料SKU", "原材料名称"])[rank_col].sum().nlargest(top_n).reset_index()
        top_skus = top["原材料SKU"].tolist()
        tdf = df[df["原材料SKU"].astype(str).isin(top_skus)]
        melted = tdf.groupby("原材料SKU")[line_metrics].sum()
        melted = melted.loc[melted.sum(axis=1).sort_values(ascending=False).index]
        fig = go.Figure()
        for m in line_metrics:
            fig.add_trace(go.Scatter(x=melted.index.astype(str), y=melted[m], mode="lines+markers", name=m))
        fig.update_layout(height=480, xaxis_title="原材料SKU", yaxis_title="数量",
                          legend_title="指标", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("查看 Top N SKU 名称对照"):
            st.dataframe(top.rename(columns={rank_col: f"{rank_col}（排序依据）"}), use_container_width=True, hide_index=True)
    else:
        st.info("未找到可绘制的数值列")

# ================= 饼图 =================
st.header("🥧 类目占比饼图")
c1, c2 = st.columns(2)
for col, title, container in [("三级类目", "三级类目占比", c1), ("四级类目", "四级类目占比", c2)]:
    pie_df = df.groupby(col)[pie_metric].sum().reset_index()
    pie_df = pie_df[pie_df[pie_metric] > 0].sort_values(pie_metric, ascending=False)
    if pie_df.empty:
        container.info(f"「{title}」无数据")
        continue
    fig = px.pie(pie_df, names=col, values=pie_metric, hole=0.45, title=title)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=460, legend_font_size=11)
    container.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("数据来源：快驴预采量订货明细 · 看板由 Streamlit + Plotly 构建")
