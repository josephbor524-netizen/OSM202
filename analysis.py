"""Reusable weighted income-distribution calculations for the Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"state_name", "income", "acs_weight"}
EXPECTED_VALIDATION = {
    "total_weight": 17_769_934.0,
    "percentiles": {10: 0.0, 20: 10_087.0, 40: 29_133.0, 60: 50_977.0, 80: 86_770.0, 90: 124_731.0},
    "gini": 0.55547,
    "theil": 0.58664857,
    "theil_mean": 58_592.7114,
}


@dataclass
class LoadReport:
    sheet_name: str
    original_rows: int
    usable_rows: int
    excluded_missing_income: int
    excluded_invalid_weight: int
    excluded_non_numeric: int
    warnings: list[str]


def find_default_workbook() -> Path | None:
    """Find the supplied workbook on the author's machine, if present.

    The app still supports upload, so this is only a convenience for local use.
    """
    candidates = [
        Path("us_adults_sample_100k-2.xlsx"),
        Path("us_adults_sample_100k-2.csv"),
        Path(__file__).resolve().parent / "data/us_adults_sample_100k-2.xlsx",
        Path(__file__).resolve().parent / "data/us_adults_sample_100k-2.csv",
        Path.home() / "Desktop/Signiture Assignment OSM202/us_adults_sample_100k-2.xlsx",
        Path.home() / "Desktop/Signature Assignment OSM202/us_adults_sample_100k-2.xlsx",
    ]
    return next((path for path in candidates if path.exists()), None)


def load_dataset(source: str | Path | object, sheet_name: str = "us_adults_sample_100k") -> tuple[pd.DataFrame, LoadReport]:
    """Load the raw worksheet and retain only rows valid for weighted analysis.

    Invalid/missing income and missing, non-finite, or non-positive weights are
    excluded from calculations and counted in the returned report. The source
    workbook itself is never modified.
    """
    source_name = str(getattr(source, "name", source)).lower()
    if source_name.endswith(".csv"):
        frame = pd.read_csv(source)
    elif hasattr(source, "read"):
        frame = pd.read_excel(source, sheet_name=sheet_name)
    else:
        frame = pd.read_excel(Path(source), sheet_name=sheet_name)

    missing_columns = REQUIRED_COLUMNS - set(frame.columns)
    if missing_columns:
        raise ValueError(
            "The selected worksheet is missing required column(s): "
            + ", ".join(sorted(missing_columns))
        )

    original_rows = len(frame)
    income = pd.to_numeric(frame["income"], errors="coerce")
    weights = pd.to_numeric(frame["acs_weight"], errors="coerce")
    missing_income = income.isna()
    invalid_weight = weights.isna() | ~np.isfinite(weights) | (weights <= 0)
    non_numeric = frame["income"].notna() & income.isna()
    usable = ~(missing_income | invalid_weight)
    cleaned = frame.loc[usable].copy()
    cleaned["income"] = income.loc[usable].astype(float)
    cleaned["acs_weight"] = weights.loc[usable].astype(float)

    warnings: list[str] = []
    if missing_income.any():
        warnings.append(f"Excluded {int(missing_income.sum())} row(s) with missing/non-numeric income.")
    if invalid_weight.any():
        warnings.append(f"Excluded {int(invalid_weight.sum())} row(s) with missing, non-finite, or non-positive ACS weights.")
    return cleaned, LoadReport(
        sheet_name=sheet_name,
        original_rows=original_rows,
        usable_rows=len(cleaned),
        excluded_missing_income=int(missing_income.sum()),
        excluded_invalid_weight=int(invalid_weight.sum()),
        excluded_non_numeric=int(non_numeric.sum()),
        warnings=warnings,
    )


def _sorted_arrays(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    if data.empty:
        raise ValueError("No usable observations are available for this analysis.")
    ordered = data[["income", "acs_weight"]].sort_values("income", kind="mergesort")
    return ordered["income"].to_numpy(dtype=float), ordered["acs_weight"].to_numpy(dtype=float)


def weighted_percentile(data: pd.DataFrame, percentile: float) -> float:
    """Inverse weighted empirical CDF: first income with cumulative weight >= target."""
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100")
    incomes, weights = _sorted_arrays(data)
    return _weighted_percentile_from_sorted(incomes, weights, percentile)


def _weighted_percentile_from_sorted(incomes: np.ndarray, weights: np.ndarray, percentile: float) -> float:
    target = (percentile / 100.0) * weights.sum()
    index = int(np.searchsorted(np.cumsum(weights), target, side="left"))
    return float(incomes[min(index, len(incomes) - 1)])


def weighted_percentile_curve(data: pd.DataFrame, percentiles: Iterable[float] | None = None) -> pd.DataFrame:
    """Return a table suitable for charting a weighted percentile curve."""
    ps = list(percentiles if percentiles is not None else range(0, 101))
    incomes, weights = _sorted_arrays(data)
    return pd.DataFrame({"percentile": ps, "income": [_weighted_percentile_from_sorted(incomes, weights, p) for p in ps]})


def weighted_gini(data: pd.DataFrame) -> float:
    """Weighted Lorenz-curve Gini, retaining negative observed incomes."""
    incomes, weights = _sorted_arrays(data)
    total_weight = weights.sum()
    total_income = np.sum(incomes * weights)
    if np.isclose(total_income, 0):
        raise ValueError("Weighted income total is zero; Gini is undefined.")
    population_share = np.concatenate(([0.0], np.cumsum(weights) / total_weight))
    income_share = np.concatenate(([0.0], np.cumsum(incomes * weights) / total_income))
    # np.trapezoid is new in NumPy 2.x; np.trapz keeps the app compatible with
    # the NumPy 1.x versions commonly available in classroom environments.
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    lorenz_area = float(integrate(income_share, population_share))
    return float(1.0 - 2.0 * lorenz_area)


def weighted_theil(data: pd.DataFrame) -> tuple[float, float]:
    """Weighted Theil T; negative income is recoded to zero only here."""
    weights = data["acs_weight"].to_numpy(dtype=float)
    adjusted = np.maximum(data["income"].to_numpy(dtype=float), 0.0)
    mean = float(np.sum(adjusted * weights) / np.sum(weights))
    if np.isclose(mean, 0):
        raise ValueError("Adjusted weighted mean income is zero; Theil is undefined.")
    ratios = adjusted / mean
    contributions = np.zeros_like(ratios)
    positive = ratios > 0
    contributions[positive] = ratios[positive] * np.log(ratios[positive])
    return float(np.sum(weights * contributions) / np.sum(weights)), mean


def p90_p10(data: pd.DataFrame) -> float | None:
    p10 = weighted_percentile(data, 10)
    if np.isclose(p10, 0):
        return None
    return weighted_percentile(data, 90) / p10


def analyze(data: pd.DataFrame) -> dict:
    """Calculate all primary measures for the supplied U.S. or state subset."""
    percentiles = {p: weighted_percentile(data, p) for p in (10, 20, 40, 60, 80, 90)}
    theil, theil_mean = weighted_theil(data)
    return {
        "n": len(data),
        "total_weight": float(data["acs_weight"].sum()),
        "percentiles": percentiles,
        "gini": weighted_gini(data),
        "theil": theil,
        "theil_mean": theil_mean,
        "p90_p10": p90_p10(data),
    }


def validate_us(us_results: dict) -> list[dict]:
    """Return visible validation results instead of silently accepting mismatch."""
    checks = [
        ("Total ACS weight", us_results["total_weight"], EXPECTED_VALIDATION["total_weight"], 0.5),
        *[(f"P{p}", us_results["percentiles"][p], expected, 1.0) for p, expected in EXPECTED_VALIDATION["percentiles"].items()],
        ("Weighted Gini", us_results["gini"], EXPECTED_VALIDATION["gini"], 0.0005),
        ("Weighted Theil T", us_results["theil"], EXPECTED_VALIDATION["theil"], 0.0005),
        ("Theil weighted mean", us_results["theil_mean"], EXPECTED_VALIDATION["theil_mean"], 1.0),
    ]
    return [{"check": name, "actual": actual, "expected": expected, "passed": abs(actual - expected) <= tolerance} for name, actual, expected, tolerance in checks]
