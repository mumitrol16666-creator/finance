# Current Dashboard UX / Product Analysis

Date: 2026-09-16  
Branch: `refactor/financial-integrity-v1`

This document is based on the current production dashboard screenshot and complements `PRODUCT_TECHNICAL_ANALYSIS_AND_ROADMAP.md`.

## 1. What the current screen does well

The dashboard already exposes the main product building blocks in one place:

- personal/business mode switch;
- total balance;
- period expenses;
- savings/deposits/account count;
- quick operations;
- activity streak;
- category limits;
- balance forecast;
- latest operations;
- bottom navigation with direct add button.

The visual language is coherent: dark theme, clear primary accent, compact cards, and a persistent add action. The problem is not lack of information. The problem is hierarchy: low-value widgets currently receive more screen space and visual priority than the information needed for financial decisions.

## 2. Problems visible on the current dashboard

### 2.1 The main balance card wastes the most valuable screen area

The largest card contains only a few numbers and a large empty region. It shows the current balance and period spending but does not explain whether the balance is healthy, sufficient, committed, or free to spend.

### 2.2 The dashboard reports balances, but not financial position

`43 410 ₸` is visible, but the user cannot answer from the home screen:

- how much of it is already committed to upcoming obligations;
- how much is truly free to spend;
- what income is expected before the end of the cycle;
- whether the current pace of spending is safe;
- what the projected end-of-cycle balance will be.

### 2.3 Personal/business mode consumes too much vertical space

The mode switch spans nearly the full width and behaves visually like a primary content block. It is a context selector, not the main purpose of the screen.

Target: compact segmented control in the header or inside the balance header area.

### 2.4 Quick operations are useful but over-prioritized

Coffee, taxi and lunch shortcuts are convenient, but they appear before any useful financial interpretation. They should remain fast, but should not push financial status lower on the page.

### 2.5 Activity streak is gamification without financial meaning

The streak shows that the user logged data, not whether the financial situation improved. It currently occupies a full-width block.

Target: compress it into a small secondary widget or move it into a habit/progress area. It must not compete with cash-flow, obligations, or alerts.

### 2.6 Category limit cards show misleading `spent / 0 ₸` states

Examples on the current screen display values such as `1 590 ₸ / 0 ₸` and `5 000 ₸ / 0 ₸`. A zero denominator visually looks like an exceeded budget even when no limit was configured.

Target behavior:

- if no limit is set, show `1 590 ₸ spent` + `Set limit`;
- only render progress bars/percentages when a positive limit exists;
- categories without limits should not be styled as failed/over-budget.

### 2.7 The forecast card is currently not useful

The forecast says the balance in 30 days will remain `43 410 ₸` with `+0 ₸` change. That means it is effectively projecting no known future cash flow and does not help the user make a decision.

Target: forecast must include known recurring income/expenses, planned operations, debts and required obligations. If there is not enough data, explicitly say that the forecast is incomplete instead of showing a false neutral forecast.

### 2.8 Savings display has an invalid/unclear state

The savings area appears to show placeholder-like dots instead of a useful number. This needs a defined empty/loading/error state.

Target states:

- `0 ₸` when the value is truly zero;
- `—` only when the metric is unavailable;
- skeleton/loading while fetching;
- explicit error only when the request failed.

### 2.9 Too much of the screen is descriptive, not actionable

The dashboard contains many blocks, but does not clearly tell the user what needs attention now.

Target: one concise "Needs attention" block generated from deterministic rules, for example:

- payment due in 2 days;
- food budget at 85%;
- spending pace above normal;
- free cash below upcoming obligations;
- no financial issue requiring action.

### 2.10 The current HTTP deployment is visibly exposed in the browser

The screenshot shows the site opened directly through an IP address and the browser marks it as insecure. This matches the transport/security issue already tracked in the technical roadmap.

Target: production must be served from HTTPS on a domain; API must not be directly exposed over plain HTTP.

## 3. New dashboard hierarchy

The home screen will be reorganized into five decision layers.

### A. Financial position — first screen block

Primary figures:

- total liquid balance;
- free cash after obligations;
- savings/deposits;
- debt balance if relevant.

Example:

```text
Available now       43 410 ₸
Committed           18 000 ₸
Free to spend       25 410 ₸
Savings             0 ₸
```

### B. Current cycle

Show:

- income;
- expenses;
- net cash flow;
- savings rate;
- days left in cycle;
- spending pace vs expected pace.

Example:

```text
Income              0 ₸
Expenses            6 590 ₸
Net                 -6 590 ₸
Cycle               6 / 30 days
Spending pace       Normal / High / Low
```

### C. What is coming

Aggregate the next obligations:

- recurring payments;
- planned operations;
- debt payments;
- expected recurring income.

Show nearest items and total amount before cycle end.

### D. Attention / risk

One compact block, ranked by severity.

Examples:

- `Food budget: 82% used with 18 days left`;
- `12 000 ₸ payment due tomorrow`;
- `Free cash after obligations: 8 400 ₸`;
- `No urgent issues`.

### E. Actions and history

After the financial state is visible:

- quick operations;
- latest transactions;
- link to full analytics;
- secondary gamification.

## 4. Changes to current widgets

### Main balance card

Replace the mostly empty card with a compact financial position summary plus current-cycle cash flow.

### Personal/business switch

Move to a smaller header segmented control. The selected mode must affect every backend query and metric consistently.

### Quick operations

Keep them, but move below the financial position/attention blocks. Allow horizontal scrolling on mobile and compact layout on desktop.

### Activity streak

Reduce visual height substantially. Keep as optional motivation, not a primary financial KPI.

### Category limits

Split categories into:

- configured budgets;
- categories without limits.

Only configured budgets receive progress bars and warning colors.

### Forecast

Replace the current simplistic 30-day card with a backend-driven deterministic forecast:

`current free balance + expected income - recurring obligations - planned required expenses - debt payments`

Show two values where useful:

- projected end-of-cycle balance;
- projected free cash after known obligations.

### Latest operations

Keep on home, but limit to the latest 5-8 items and prioritize readability over card decoration.

## 5. Analytics screen changes

The Analytics tab should stop being just a chart page. It should answer:

1. Where did money go?
2. What changed compared with the previous comparable period?
3. Which categories are abnormal?
4. Is spending sustainable at the current pace?
5. How much can be safely spent before the next cycle/income?

Required sections:

- cash-flow trend;
- category structure;
- period comparison;
- fixed vs discretionary expenses;
- obligations vs free cash;
- savings rate;
- debt load;
- runway;
- forecast;
- deterministic insights;
- optional AI explanation based on those computed metrics.

## 6. Implementation order for dashboard/analytics

### P0 dependency

Do not rebuild the UI around metrics until the financial core is trustworthy. Complete idempotency/atomicity for planned, recurring, debts and deposits first.

### P1 analytics backend

Create a single dashboard/analytics projection service that returns normalized metrics in base currency and user timezone.

Suggested API response groups:

- `position`;
- `cycle`;
- `obligations`;
- `forecast`;
- `attention`;
- `budgets`;
- `recentTransactions`.

### P1 Flutter dashboard

Rebuild `DashboardScreen` around the new hierarchy and remove duplicated client-side financial calculations where backend-projected values exist.

### P2 polish

After the new information architecture works:

- responsive desktop layout;
- compact mobile cards;
- better empty states;
- animation only where it communicates change;
- accessibility/contrast review;
- final typography/spacing cleanup.

## 7. What not to add yet

Do not add more decorative charts, more gamification widgets, more AI cards, or more home-screen sections until the five core questions are answered clearly:

1. How much money do I have now?
2. How much is actually free?
3. What happened this cycle?
4. What is coming next?
5. What needs my attention?

That becomes the design contract for the home screen.
