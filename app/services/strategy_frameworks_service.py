"""
Deterministic strategy-framework metrics (Buffett-style DCF, Magic Formula, GARP, factors).

Uses Yahoo Finance via an existing yfinance Ticker. Outputs are for research assistance only.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Any, Final

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

EQUITY_RISK_PREMIUM: Final[float] = 0.05
MARGIN_OF_SAFETY: Final[float] = 0.30
DCF_STAGE_YEARS: Final[int] = 5
DCF_STAGE_GROWTH: Final[float] = 0.025
DCF_TERMINAL_GROWTH: Final[float] = 0.02
MOAT_MIN_MARGIN: Final[float] = 0.40
MOAT_MAX_STDDEV: Final[float] = 0.02  # percentage points of gross margin (0–1 scale)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _pct_from_decimal(x: float | None) -> float | None:
    if x is None:
        return None
    return round(x * 100.0, 4)


def _series_for_columns(frame: pd.DataFrame | None, row_name: str) -> pd.Series | None:
    if frame is None or frame.empty or row_name not in frame.index:
        return None
    return frame.loc[row_name]


def _fetch_risk_free_rate() -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d", interval="1d")
        if hist is None or hist.empty or "Close" not in hist.columns:
            warnings.append("Could not load 10-Year Treasury yield (^TNX).")
            return None, warnings
        close = hist["Close"].dropna()
        if close.empty:
            warnings.append("10-Year Treasury history was empty.")
            return None, warnings
        # Yahoo quotes ^TNX close in yield percent points (e.g. 4.36 => 4.36%).
        rf_pct_points = float(close.iloc[-1])
        rf = rf_pct_points / 100.0
        return rf, warnings
    except Exception:
        logger.exception("Failed to fetch ^TNX")
        warnings.append("Unexpected error while fetching 10-Year Treasury yield.")
        return None, warnings


def _gross_margin_years(financials: pd.DataFrame | None) -> tuple[list[float], list[str]]:
    warnings: list[str] = []
    gp = _series_for_columns(financials, "Gross Profit")
    rev = _series_for_columns(financials, "Total Revenue")
    if gp is None or rev is None:
        warnings.append("Gross Profit or Total Revenue unavailable for moat calculation.")
        return [], warnings
    margins: list[float] = []
    cols = list(gp.index)
    for c in cols[:5]:
        gpv = _num(gp.get(c))
        rv = _num(rev.get(c))
        if gpv is None or rv is None or rv == 0:
            continue
        margins.append(gpv / rv)
    if not margins:
        warnings.append("Could not derive any fiscal gross margins.")
    return margins, warnings


def _moat_pass(margins: list[float]) -> bool | None:
    if len(margins) < 3:
        return None
    if any(m < MOAT_MIN_MARGIN for m in margins):
        return False
    mean = sum(margins) / len(margins)
    if mean <= MOAT_MIN_MARGIN:
        return False
    var = sum((m - mean) ** 2 for m in margins) / len(margins)
    std = math.sqrt(var)
    return bool(std <= MOAT_MAX_STDDEV)


def _nopat_ebit_tax(ebit: float | None, tax_prov: float | None, pretax: float | None) -> float | None:
    if ebit is None:
        return None
    if pretax is not None and pretax != 0 and tax_prov is not None:
        tr = tax_prov / pretax
        tr = max(0.0, min(0.35, tr))
        return ebit * (1.0 - tr)
    return ebit * 0.79  # fallback ~21% effective


def _roic_wacc_rows(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    *,
    beta: float | None,
    rf: float | None,
    info: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    out: list[dict[str, Any]] = []
    if financials is None or balance_sheet is None:
        warnings.append("Statements unavailable for ROIC/WACC.")
        return out, warnings

    ebit_s = _series_for_columns(financials, "EBIT")
    tax_s = _series_for_columns(financials, "Tax Provision")
    pretax_s = _series_for_columns(financials, "Pretax Income")
    interest_s = _series_for_columns(financials, "Interest Expense")
    ic_s = _series_for_columns(balance_sheet, "Invested Capital")
    debt_s = _series_for_columns(balance_sheet, "Total Debt")

    if ebit_s is None or ic_s is None:
        warnings.append("EBIT or Invested Capital missing for ROIC.")
        return out, warnings

    e_mc = _num(info.get("marketCap"))
    e_total_debt = _num(info.get("totalDebt"))
    b_eff = beta if beta is not None else 1.0
    rf_u = rf if rf is not None else 0.04
    re = rf_u + b_eff * EQUITY_RISK_PREMIUM

    cols = [c for c in ebit_s.index if c in ic_s.index][:5]
    for c in cols:
        ebit = _num(ebit_s.get(c))
        ic = _num(ic_s.get(c))
        tp = _num(tax_s.get(c)) if tax_s is not None else None
        pt = _num(pretax_s.get(c)) if pretax_s is not None else None
        nopat = _nopat_ebit_tax(ebit, tp, pt)
        roic = None if nopat is None or ic is None or ic == 0 else nopat / ic

        interest = _num(interest_s.get(c)) if interest_s is not None else None
        td = _num(debt_s.get(c)) if debt_s is not None else None
        rd_pre = None
        if interest is not None and td is not None and td != 0:
            rd_pre = abs(interest) / td

        tr_eff = 0.21
        if tp is not None and pt is not None and pt != 0:
            tr_eff = max(0.0, min(0.35, tp / pt))

        d_val = e_total_debt
        if d_val is None or d_val == 0:
            d_val = td
        e_val = e_mc
        if e_val is None or e_val <= 0:
            wacc = None
        elif d_val is None or rd_pre is None:
            wacc = re
        else:
            v = e_val + d_val
            wacc = (e_val / v) * re + (d_val / v) * rd_pre * (1.0 - tr_eff)

        fy = str(c.date()) if hasattr(c, "date") else str(c)
        out.append(
            {
                "fiscal_period_end": fy,
                "roic": roic,
                "wacc": wacc,
                "roic_pct": _pct_from_decimal(roic) if roic is not None else None,
                "wacc_pct": _pct_from_decimal(wacc) if wacc is not None else None,
                "roic_above_wacc": bool(roic is not None and wacc is not None and roic > wacc),
            }
        )

    return out, warnings


def _return_check_pass(rows: list[dict[str, Any]]) -> bool | None:
    usable = [r for r in rows if r.get("roic") is not None and r.get("wacc") is not None]
    if len(usable) < 2:
        return None
    last3 = usable[:3]
    return all(bool(r["roic_above_wacc"]) for r in last3)


def _owners_earnings_and_dcf(
    cashflow: pd.DataFrame | None,
    financials: pd.DataFrame | None,
    info: dict[str, Any],
    *,
    beta: float | None,
    rf: float | None,
    treasury_warnings: list[str],
) -> dict[str, Any]:
    warnings: list[str] = list(treasury_warnings)
    out: dict[str, Any] = {
        "operating_cashflow_ttm": None,
        "maintenance_capex": None,
        "owners_earnings_ttm": None,
        "intrinsic_value_per_share": None,
        "target_buy_price": None,
        "discount_rate_decimal": None,
        "discount_rate_pct": None,
        "risk_free_rate_decimal": None,
        "risk_free_rate_pct": None,
        "cost_of_equity_decimal": None,
        "stage_growth_decimal": DCF_STAGE_GROWTH,
        "terminal_growth_decimal": DCF_TERMINAL_GROWTH,
        "dcf_stage_years": DCF_STAGE_YEARS,
        "warnings": warnings,
    }

    if cashflow is None:
        warnings.append("Cash flow statement unavailable for owner's earnings.")
        return out

    ocf_s = _series_for_columns(cashflow, "Operating Cash Flow")
    capex_s = _series_for_columns(cashflow, "Capital Expenditure")
    dep_s = _series_for_columns(financials, "Reconciled Depreciation") if financials is not None else None

    if ocf_s is None:
        warnings.append("Operating Cash Flow row missing.")
        return out

    col = ocf_s.index[0]
    ocf = _num(ocf_s.get(col))
    capex = _num(capex_s.get(col)) if capex_s is not None else None
    dep = _num(dep_s.get(col)) if dep_s is not None else None

    out["operating_cashflow_ttm"] = ocf

    capex_abs = abs(capex) if capex is not None else None
    if capex_abs is not None and dep is not None:
        maint = min(capex_abs, dep)
    elif dep is not None:
        maint = dep
    elif capex_abs is not None:
        maint = capex_abs
    else:
        maint = None
        warnings.append("Could not estimate maintenance CapEx; using depreciation fallback failed.")

    out["maintenance_capex"] = maint

    if ocf is None or maint is None:
        warnings.append("Incomplete data for owner's earnings.")
        return out

    oe = ocf - maint
    out["owners_earnings_ttm"] = oe

    shares = _num(info.get("sharesOutstanding"))
    b_eff = beta if beta is not None else 1.0
    rf_u = rf if rf is not None else 0.04
    r = rf_u + b_eff * EQUITY_RISK_PREMIUM
    out["risk_free_rate_decimal"] = rf_u
    out["risk_free_rate_pct"] = _pct_from_decimal(rf_u)
    out["cost_of_equity_decimal"] = r
    out["discount_rate_decimal"] = r
    out["discount_rate_pct"] = _pct_from_decimal(r)

    if shares is None or shares <= 0:
        warnings.append("Shares outstanding missing; cannot compute per-share intrinsic value.")
        return out

    if r <= DCF_TERMINAL_GROWTH:
        warnings.append("Discount rate not above terminal growth; DCF not applied.")
        return out

    g = DCF_STAGE_GROWTH
    gt = DCF_TERMINAL_GROWTH
    years = DCF_STAGE_YEARS

    pv = 0.0
    oe_t = oe
    for t in range(1, years + 1):
        oe_t = oe_t * (1.0 + g)
        pv += oe_t / ((1.0 + r) ** t)

    oe_terminal_start = oe * ((1.0 + g) ** years) * (1.0 + gt)
    tv = oe_terminal_start / (r - gt) if (r - gt) > 0 else float("nan")
    if math.isnan(tv) or tv <= 0:
        warnings.append("Terminal value invalid.")
        return out

    pv += tv / ((1.0 + r) ** years)

    iv_ps = pv / shares
    if iv_ps <= 0 or math.isnan(iv_ps):
        warnings.append("Intrinsic value per share was not meaningful.")
        return out

    out["intrinsic_value_per_share"] = round(iv_ps, 4)
    out["target_buy_price"] = round(iv_ps * (1.0 - MARGIN_OF_SAFETY), 4)
    return out


def _magic_formula(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    info: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {"earnings_yield_decimal": None, "return_on_capital_decimal": None}
    extra_notes: list[str] = []
    ev = _num(info.get("enterpriseValue"))
    ebit_s = _series_for_columns(financials, "EBIT") if financials is not None else None
    wc_s = _series_for_columns(balance_sheet, "Working Capital") if balance_sheet is not None else None
    ppe_s = _series_for_columns(balance_sheet, "Net PPE") if balance_sheet is not None else None

    if ebit_s is not None and ev is not None and ev != 0:
        ebit = _num(ebit_s.iloc[0])
        if ebit is not None:
            out["earnings_yield_decimal"] = ebit / ev

    if ebit_s is not None and wc_s is not None and ppe_s is not None:
        col = ebit_s.index[0]
        if col in wc_s.index and col in ppe_s.index:
            ebit = _num(ebit_s.get(col))
            wc = _num(wc_s.get(col))
            ppe = _num(ppe_s.get(col))
            if wc is not None and wc < 0:
                extra_notes.append(
                    "Net working capital is negative; ROC using EBIT/(Working Capital+Net PPE) can read "
                    "very high versus historical industry baselines—interpret alongside peers."
                )
            denom = None
            if wc is not None and ppe is not None:
                denom = wc + ppe
            if ebit is not None and denom is not None and denom > 0:
                out["return_on_capital_decimal"] = ebit / denom

    notes = (
        "Earnings yield is EBIT / Enterprise Value; ROC is EBIT / (Working Capital + Net PPE), "
        "latest fiscal period aligned across statements."
    )
    if extra_notes:
        notes = notes + " " + " ".join(extra_notes)

    return {
        "earnings_yield_pct": _pct_from_decimal(out["earnings_yield_decimal"]),
        "return_on_capital_pct": _pct_from_decimal(out["return_on_capital_decimal"]),
        "earnings_yield_decimal": out["earnings_yield_decimal"],
        "return_on_capital_decimal": out["return_on_capital_decimal"],
        "notes": notes,
    }


def _eps_cagr_3y(financials: pd.DataFrame | None) -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    eps_s = _series_for_columns(financials, "Diluted EPS") if financials is not None else None
    if eps_s is None or len(eps_s) < 4:
        warnings.append("Need at least four fiscal periods for 3-year EPS CAGR.")
        return None, warnings
    eps_now = _num(eps_s.iloc[0])
    eps_old = _num(eps_s.iloc[3])
    if eps_now is None or eps_old is None or eps_old <= 0 or eps_now <= 0:
        warnings.append("Diluted EPS missing or non-positive for CAGR.")
        return None, warnings
    cagr = (eps_now / eps_old) ** (1.0 / 3.0) - 1.0
    return cagr, warnings


def _garp(fields: dict[str, Any], financials: pd.DataFrame | None) -> dict[str, Any]:
    warnings: list[str] = []
    pe = _num(fields.get("trailing_pe"))
    cagr, w = _eps_cagr_3y(financials)
    warnings.extend(w)

    peg = None
    growth_pct = _pct_from_decimal(cagr) if cagr is not None else None
    if pe is not None and cagr is not None and cagr > 0:
        peg = pe / (cagr * 100.0)

    signal: str | None = None
    if peg is not None:
        if peg < 1.0:
            signal = "Buy"
        elif peg > 2.0:
            signal = "Sell"
        else:
            signal = "Hold"

    return {
        "peg_ratio": round(peg, 4) if peg is not None else None,
        "trailing_pe": pe,
        "eps_cagr_3y_decimal": cagr,
        "eps_cagr_3y_pct": growth_pct,
        "signal": signal,
        "warnings": warnings,
    }


def _momentum_6m(history: pd.DataFrame | None, current_price: float | None) -> float | None:
    if history is None or history.empty or "Close" not in history.columns:
        return None
    close = history["Close"].dropna()
    if close.empty or len(close) < 2:
        return None
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    ref = current_price if current_price is not None else last
    if first == 0:
        return None
    return ref / first - 1.0


class StrategyFrameworksService:
    """Build structured strategy framework metrics for the full-analysis endpoint."""

    def build(
        self,
        *,
        ticker: yf.Ticker,
        normalized_symbol: str,
        fundamentals: dict[str, Any],
        stock: dict[str, Any],
    ) -> dict[str, Any]:
        fields = fundamentals.get("fields") or {}
        info: dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception:
            logger.warning("strategy_frameworks: ticker.info failed for %s", normalized_symbol)

        beta = _num(info.get("beta"))
        rf, rf_warnings = _fetch_risk_free_rate()

        financials = None
        balance_sheet = None
        cashflow = None
        hist_6m = None
        try:
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            cashflow = ticker.cashflow
            hist_6m = ticker.history(period="6mo", interval="1d", auto_adjust=False)
        except Exception:
            logger.exception("strategy_frameworks: statements/history failed for %s", normalized_symbol)

        margins, moat_w = _gross_margin_years(financials)
        moat_pass = _moat_pass(margins)

        roic_rows, roic_w = _roic_wacc_rows(financials, balance_sheet, beta=beta, rf=rf, info=info)
        ret_pass = _return_check_pass(roic_rows)

        dcf = _owners_earnings_and_dcf(
            cashflow,
            financials,
            info,
            beta=beta,
            rf=rf,
            treasury_warnings=rf_warnings,
        )

        magic = _magic_formula(financials, balance_sheet, info)

        garp = _garp(fields, financials)

        price = _num(stock.get("current_price"))
        mom = _momentum_6m(hist_6m, price)
        pb = _num(fields.get("price_to_book"))

        return {
            "buffett_quality_dcf": {
                "moat_check": {
                    "five_year_avg_gross_margin_pct": (
                        round(sum(margins) / len(margins) * 100.0, 4) if margins else None
                    ),
                    "gross_margin_std_pct_points": (
                        round(
                            math.sqrt(
                                sum((m - sum(margins) / len(margins)) ** 2 for m in margins)
                                / len(margins)
                            )
                            * 100.0,
                            4,
                        )
                        if len(margins) > 1
                        else None
                    ),
                    "yearly_gross_margins_pct": [round(m * 100.0, 4) for m in margins],
                    "pass": moat_pass,
                    "warnings": moat_w,
                },
                "return_check": {
                    "by_period": roic_rows,
                    "pass_roic_above_wacc_recent": ret_pass,
                    "warnings": roic_w,
                },
                "valuation_dcf": dcf,
            },
            "magic_formula": magic,
            "garp": garp,
            "factor_metrics": {
                "price_to_book": pb,
                "momentum_6m_decimal": mom,
                "momentum_6m_pct": _pct_from_decimal(mom) if mom is not None else None,
            },
        }


@lru_cache
def get_strategy_frameworks_service() -> StrategyFrameworksService:
    return StrategyFrameworksService()
