from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis import analyze, find_default_workbook, load_dataset, validate_us, weighted_percentile_curve

st.set_page_config(page_title="U.S. Adult Income Inequality", page_icon="📊", layout="wide")


def money(value: float | None) -> str:
    return "Undefined (P10 = 0)" if value is None else f"${value:,.0f}"


def ratio(value: float | None) -> str:
    return "Undefined (P10 = 0)" if value is None else f"{value:,.2f}"


def percentile_explanation(percentile: int, value: float, population: str = "U.S.") -> str:
    return (
        f"**P{percentile} = {money(value)}**\n\n"
        f"This is the income at or below which approximately {percentile}% of adults in the weighted {population} sample fall. "
        "The app sorts `income` from lowest to highest, carries each row's `acs_weight`, and returns the income of the first row whose cumulative ACS weight reaches the percentile target. "
        "It is therefore a weighted result, not an ordinary unweighted pandas quantile."
    )


def measure_explanation(measure: str, results: dict, population: str = "the U.S.") -> str:
    if measure.startswith("P") and measure[1:].isdigit():
        percentile = int(measure[1:])
        return percentile_explanation(percentile, results["percentiles"][percentile], population)
    if measure == "Gini":
        return (
            f"**Weighted Gini = {results['gini']:.5f}**\n\n"
            "This summarizes inequality using the weighted Lorenz curve. The calculation sorts `income`, retains negative observed incomes, "
            "uses `acs_weight` to build cumulative population and income shares, integrates the curve, and computes `1 - 2 × Lorenz area`. "
            "Higher values indicate more unequal income shares in this sample."
        )
    if measure == "Theil T":
        return (
            f"**Weighted Theil T = {results['theil']:.5f}**\n\n"
            f"This index compares each adjusted income with the weighted mean income of {money(results['theil_mean'])}. "
            "For Theil only, negative `income` values are recoded to zero; zero-income observations contribute zero. `acs_weight` determines each row's contribution."
        )
    return (
        f"**P90/P10 = {ratio(results['p90_p10'])}**\n\n"
        "This is the weighted P90 income divided by the weighted P10 income. It compares the upper-end cutoff with the lower-end cutoff. "
        "It is shown as `Undefined (P10 = 0)` instead of dividing by zero when the lower cutoff is zero."
    )


@st.cache_data(show_spinner="Reading the Excel workbook…")
def cached_load(path: str, modified: float):
    return load_dataset(path)


@st.cache_data
def cached_analysis(data: pd.DataFrame):
    return analyze(data)


st.title("U.S. Adult Income Inequality")
st.caption("Weighted income-distribution analysis using the supplied sample and ACS weights")

default = find_default_workbook()
uploaded = st.sidebar.file_uploader("Upload the Excel workbook or CSV", type=["xlsx", "xls", "csv"])
if uploaded is not None:
    try:
        data, report = load_dataset(uploaded)
    except Exception as exc:
        st.error(f"Could not load workbook: {exc}")
        st.stop()
elif default is not None:
    try:
        data, report = cached_load(str(default), default.stat().st_mtime)
    except Exception as exc:
        st.error(f"Could not load the default workbook: {exc}")
        st.stop()
else:
    st.info("Upload the supplied Excel workbook to begin.")
    st.stop()

if report.warnings:
    with st.sidebar.expander("Data-quality exclusions", expanded=False):
        for warning in report.warnings:
            st.warning(warning)
        st.write(f"Usable rows: {report.usable_rows:,} of {report.original_rows:,}")

us = cached_analysis(data)
states = sorted(data["state_name"].dropna().astype(str).unique())
if not states:
    st.error("The workbook has no usable values in state_name, so state analysis cannot be displayed.")
    st.stop()
selected_state = st.sidebar.selectbox("Select a state", states)
state_data = data[data["state_name"].astype(str).eq(selected_state)]
if state_data.empty:
    st.error("The selected state has no usable observations.")
    st.stop()
state_results = cached_analysis(state_data)

st.subheader("Weighted U.S. distribution")
us_cols = st.columns(6)
for col, p in zip(us_cols, (10, 20, 40, 60, 80, 90)):
    with col.popover(f"P{p}: {money(us['percentiles'][p])}", use_container_width=True):
        st.markdown(percentile_explanation(p, us["percentiles"][p]))

left, right = st.columns(2)
with left:
    with st.popover(f"Weighted Gini: {us['gini']:.5f}", use_container_width=True):
        st.markdown(measure_explanation("Gini", us))
with right:
    with st.popover(f"P90/P10: {ratio(us['p90_p10'])}", use_container_width=True):
        st.markdown(measure_explanation("P90/P10", us))

curve = weighted_percentile_curve(data)
fig = px.line(curve, x="percentile", y="income", markers=False, title="U.S. weighted income by percentile")
fig.update_layout(xaxis_title="Percentile of U.S. adults", yaxis_title="Income ($)", hovermode="x unified")
fig.update_traces(hovertemplate="Percentile %{x}: $%{y:,.0f}<extra></extra>")
st.plotly_chart(fig, use_container_width=True)

st.subheader(f"{selected_state} compared with the U.S.")
state_curve = weighted_percentile_curve(state_data)
comparison_curve = pd.concat([
    curve.assign(series="United States"),
    state_curve.assign(series=selected_state),
], ignore_index=True)
fig2 = px.line(comparison_curve, x="percentile", y="income", color="series", title=f"Weighted income distribution: {selected_state} vs. U.S.")
fig2.update_layout(xaxis_title="Percentile", yaxis_title="Income ($)", hovermode="x unified")
fig2.update_traces(hovertemplate="%{fullData.name}<br>Percentile %{x}: $%{y:,.0f}<extra></extra>")
st.plotly_chart(fig2, use_container_width=True)

rows = []
for label, key in [("P10", 10), ("P20", 20), ("P40", 40), ("P60", 60), ("P80", 80), ("P90", 90)]:
    rows.append({"Measure": label, "United States": money(us["percentiles"][key]), selected_state: money(state_results["percentiles"][key])})
rows.extend([
    {"Measure": "Gini", "United States": f"{us['gini']:.5f}", selected_state: f"{state_results['gini']:.5f}"},
    {"Measure": "Theil T", "United States": f"{us['theil']:.5f}", selected_state: f"{state_results['theil']:.5f}"},
    {"Measure": "P90/P10", "United States": ratio(us["p90_p10"]), selected_state: ratio(state_results["p90_p10"])},
])
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

measure = st.selectbox(
    "Choose a comparison number to explain",
    ["P10", "P20", "P40", "P60", "P80", "P90", "Gini", "Theil T", "P90/P10"],
)
st.info(measure_explanation(measure, state_results, selected_state))

st.subheader("My guess vs. actual weighted U.S. percentile")
guesses = {20: 10_000, 40: 30_000, 60: 45_000, 80: 70_000}
guess_table = pd.DataFrame([
    {"Percentile": f"P{p}", "My guess": money(guess), "Actual weighted U.S.": money(us["percentiles"][p]), "Difference (actual - guess)": money(us["percentiles"][p] - guess)}
    for p, guess in guesses.items()
])
st.dataframe(guess_table, hide_index=True, use_container_width=True)

st.subheader("Validation against the supplied Excel benchmarks")
validation = pd.DataFrame(validate_us(us))
validation["actual"] = validation["actual"].map(lambda x: f"{x:,.5f}" if isinstance(x, float) and abs(x) < 10 else f"{x:,.2f}")
validation["expected"] = validation["expected"].map(lambda x: f"{x:,.5f}" if isinstance(x, float) and abs(x) < 10 else f"{x:,.2f}")
st.dataframe(validation, hide_index=True, use_container_width=True)
if validation["passed"].all():
    st.success("All U.S. benchmark checks passed within the configured tolerances.")
else:
    st.error("One or more U.S. benchmark checks failed. Investigate the workbook, sheet, fields, and weighting implementation.")

with st.expander("Methodology and interpretation"):
    st.markdown("""
    **ACS weights.** `acs_weight` gives each sampled adult their representation in the sample's weighted population. Primary results sort income while carrying its weight, then use the first observation whose cumulative weight reaches the percentile target. Treating every row equally would instead describe the unweighted sample.

    **Percentiles and P90/P10.** A percentile is the income at or below which the specified share of weighted observations falls. P90/P10 compares the 90th-percentile income with the 10th-percentile income. It is displayed as **Undefined (P10 = 0)** when the denominator is zero.

    **Gini and Theil.** Gini summarizes inequality using the area under the weighted Lorenz curve; higher values indicate more unequal observed income shares. Theil T is another inequality index based on income relative to the weighted mean. For Theil only, negative incomes are recoded to zero and zero-income contributions are zero. Negative observed incomes are retained for Gini.

    These are results from the supplied dataset/sample and this methodology, not unsupported claims about causation or official Census estimates.
    """)
    st.write(f"Worksheet: `{report.sheet_name}` · Rows used: {report.usable_rows:,} · Selected state rows: {len(state_data):,}")
