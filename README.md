# U.S. Adult Income Inequality

Interactive Streamlit application for analyzing the supplied `us_adults_sample_100k-2.xlsx` workbook.

## Run locally

Requires Python 3.10 or newer.

```bash
cd income_inequality_app
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Upload the workbook in the sidebar. CSV uploads are also supported for cloud deployment. For the supplied local layout, the app auto-detects `~/Desktop/Signiture Assignment OSM202/us_adults_sample_100k-2.xlsx`; the deployment copy can use `data/us_adults_sample_100k-2.csv`. The expected raw worksheet is `us_adults_sample_100k` when using Excel; it must contain the exact fields `state_name`, `income`, and `acs_weight`. The original workbook is never changed.

## What the app does

Primary U.S. and state results use `acs_weight`, not ordinary unweighted pandas quantiles. Weighted percentiles implement the inverse weighted empirical CDF: income is sorted ascending, cumulative ACS weight is calculated, and the first income at or above `p × total weight` is returned. The state list is generated from `state_name` in the workbook.

The app reports weighted P10, P20, P40, P60, P80, P90, Gini, Theil T, and P90/P10, plus a U.S. percentile curve, a state-versus-U.S. curve/table, and the locked guesses P20=$10,000, P40=$30,000, P60=$45,000, P80=$70,000.

Gini uses the weighted Lorenz curve and retains negative observed incomes. Theil alone recodes negative income to zero; zero-income observations contribute zero. Missing/non-numeric income and missing, non-finite, or non-positive weights are excluded from weighted calculations and visibly counted. P90/P10 is shown as `Undefined (P10 = 0)` when P10 is zero.

The application validates total weight, the six supplied U.S. percentiles, weighted Gini, Theil T, and the Theil weighted mean against the supplied Excel targets. Any mismatch is visible in the app.

## Files

- `app.py` — Streamlit interface and charts.
- `analysis.py` — reusable loading, weighted statistics, state analysis, and validation functions.
- `requirements.txt` — Python dependencies.
