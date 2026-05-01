# Attribute Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the Portals portfolio report so it explains which gifts may be valuable and why.

**Architecture:** Keep the existing Typer command, but split row construction into testable helper functions. A report row will contain collection/model/symbol/backdrop floors, best signal, confidence, and suggested action.

**Tech Stack:** Python 3.12, Typer, Rich tables, SQLAlchemy models, pytest.

---

### Task 1: Report Row Model And Matching

**Files:**
- Modify: `app/cli/markets.py`
- Modify: `tests/unit/test_portals_portfolio_report.py`

- [ ] **Step 1: Add tests for row construction**

Add tests that construct one `Gift`, matching `MarketFloor` rows for collection/model/symbol/backdrop, and assert:

```python
row.collection_floor_ton == 7.0
row.model_floor_ton == 12.0
row.symbol_floor_ton == 30.0
row.backdrop_floor_ton == 5.0
row.best_signal == "symbol"
row.best_floor_ton == 30.0
row.confidence == "medium"
row.action == "check exact listings before sale"
```

- [ ] **Step 2: Implement report row helpers**

In `app/cli/markets.py`, add:

```python
@dataclass(frozen=True)
class PortfolioReportRow:
    gift_id: int | None
    title: str
    slug: str | None
    model: str | None
    backdrop: str | None
    symbol: str | None
    collection_floor_ton: float | None
    model_floor_ton: float | None
    symbol_floor_ton: float | None
    backdrop_floor_ton: float | None
    best_signal: str
    best_floor_ton: float | None
    confidence: str
    action: str
```

Also add `_latest_collection_floor_index`, `_build_portfolio_report_rows`,
`_build_portfolio_report_row`, `_floor_ton`, `_confidence_for_signal`, and
`_action_for_confidence`.

- [ ] **Step 3: Run targeted tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_portals_portfolio_report.py -q
```

Expected: tests pass.

### Task 2: Improved Terminal Report

**Files:**
- Modify: `app/cli/markets.py`

- [ ] **Step 1: Update command to use report rows**

Change `_portals_portfolio_report` to build `PortfolioReportRow` values instead
of `(Gift, attrs, MarketFloor, source)` tuples.

- [ ] **Step 2: Update Rich table columns**

The table columns should be:

```text
ID, Gift, Slug, Model, Backdrop, Symbol, Collection, Model Floor, Symbol Floor,
Backdrop Floor, Best, Confidence, Action
```

- [ ] **Step 3: Run the live report**

Run:

```bash
.venv/bin/gifts-sales markets portals portfolio-report --owner-peer @segamegahigh --limit 20
```

Expected: output explains per-attribute floors and the suggested action.

### Task 3: Documentation And Verification

**Files:**
- Modify: `docs/project-checkpoint.md`
- Modify: `README.md` if the command description needs clearer language.

- [ ] **Step 1: Document report meaning**

Update docs to say the improved report is an attribute-floor research report and
Telegram internal market still needs to be added as a second pricing source.

- [ ] **Step 2: Run full checks**

Run:

```bash
.venv/bin/ruff check app tests
.venv/bin/pytest -q
```

Expected: ruff passes and all tests pass.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add app/cli/markets.py tests/unit/test_portals_portfolio_report.py docs/project-checkpoint.md README.md docs/superpowers/plans/2026-05-01-attribute-report.md
git commit -m "Improve Portals attribute report"
git push origin main
```
