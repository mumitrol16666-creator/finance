# Finance Tracker — Product & Technical Analysis / Roadmap

Branch: `refactor/financial-integrity-v1`  
Purpose: describe the current product, identify structural risks, and define exactly what will be changed before new feature expansion.

## 1. Current product state

Finance Tracker is no longer just a Telegram bot. It is already a multi-client financial product with:

- Telegram bot for fast input, reminders, reports and Premium flows;
- FastAPI backend used by the Flutter client;
- Flutter application targeting mobile and web;
- SQLite/WAL persistence;
- accounts, balances, categories and transfers;
- multi-currency support;
- budgets and limits;
- debts and payment history;
- recurring expenses/incomes;
- planned transactions;
- deposits with automatic interest accrual;
- reports and XLSX export;
- AI financial profile, insights and chat;
- onboarding, tutorial and Premium feature gating;
- automated deployment with GitHub Actions and systemd.

The functional scope is already large enough that the main engineering problem is no longer feature shortage. The main problem is that money-changing behavior is spread across API endpoints, Telegram handlers, repositories, services, scheduler code and Flutter orchestration. That creates multiple implementations of the same financial action and makes regressions possible when one path is fixed but another is not.

The application should therefore move from a feature-first architecture to a finance-core-first architecture.

---

## 2. Main problems found

### 2.1 Financial integrity is not yet a single invariant-driven system

The ledger and account balance are both persisted. This is acceptable, but only if every mutation guarantees that they stay synchronized.

Current risks include:

- stale-read races during concurrent writes;
- repeated execution of planned/recurring/debt/deposit actions;
- composite operations split across several commits;
- debt state and transaction history becoming inconsistent;
- multiple clients implementing different versions of the same money rule;
- FX transfers depending on two linked rows without a first-class transfer object;
- mutation logic being mixed with UI/handler concerns.

Several transaction and deposit issues are already fixed in the current refactor branch, but the same design rule must now be applied to all money-changing operations.

### 2.2 API and Telegram are not purely transport layers

Both layers currently contain business decisions. That means the same action can have slightly different behavior depending on whether it was initiated from Telegram or Flutter.

Target state:

`Telegram / Flutter / Scheduler -> Application Command -> Financial Domain -> Repository`

The transport must collect input and render a result. It must not decide how balances, debt, FX, idempotency or ledger rows are calculated.

### 2.3 The Flutter client has become too stateful and centralized

`AppState` currently combines:

- authentication;
- session storage;
- API networking;
- accounts;
- transactions;
- categories;
- exchange rates;
- budgets;
- debts;
- recurring/planned items;
- AI chat;
- settings;
- Premium state;
- UI loading state.

This makes changes risky and makes network failures easy to hide. Some methods log errors and return without propagating them, which can leave the UI believing an operation succeeded.

### 2.4 Security is below the target level for financial data

The mobile client currently uses a plain HTTP API endpoint and long-lived bearer tokens. Tokens are persisted using SharedPreferences. The API service is bound to `0.0.0.0` and systemd units run as root.

This is acceptable only as temporary internal infrastructure. It is not the desired production design.

### 2.5 Tests do not yet define the product's financial contract

The project now has some workflow and integrity checks, but the suite still needs to become the formal specification of financial invariants.

Required invariants include:

- one financial event changes balance exactly once;
- retrying the same command does not change money twice;
- deleting/editing a linked operation cannot silently corrupt a related domain object;
- a user's operation can never target another user's account/category/debt;
- cross-currency transfers preserve explicit source/destination amounts and rate semantics;
- every composite action is all-or-nothing;
- UI/network retries are safe.

### 2.6 AI is useful, but currently too tightly coupled to individual ledger writes

AI recomputation is triggered from transaction creation. One logical action can create multiple rows, which can trigger multiple recomputations. There is also a fixed delay used to wait for commits.

AI should consume committed financial events asynchronously. It should never be part of the correctness path of a financial transaction.

### 2.7 Product structure is becoming crowded

The app already contains many financial tools. Adding more screens now would increase complexity faster than user value unless navigation and core concepts are simplified.

The product should center around a small number of user concepts:

- current financial position;
- money movement;
- obligations and future cash flow;
- budgets/limits;
- analysis/advice.

Everything else should support one of those concepts rather than becoming another isolated section.

---

## 3. What will be changed

## Phase P0-A — Financial Core

### Transactions

Change:

- all reads required for a mutation occur after acquiring the write lock;
- amount validation is centralized;
- account/category ownership validation is mandatory;
- linked debt/system transactions cannot be mutated through the generic transaction editor;
- create/update/delete operations expose explicit domain errors instead of silent partial behavior.

Already completed in current branch:

- concurrent transaction delete protection;
- concurrent transaction update protection;
- non-positive edit rejection;
- ownership validation for transaction edit targets;
- debt-linked transaction mutation guard.

Expected result:

Generic transaction CRUD can no longer produce balance/ledger drift under concurrent requests or mutate linked financial workflows accidentally.

### Transfers and FX

Change:

- preserve source and destination amounts independently;
- preserve/recalculate FX ratio explicitly;
- forbid implicit currency reinterpretation when moving either side of a transfer;
- later introduce a first-class transfer/financial-operation identifier so the pair of ledger rows is clearly one logical action.

Already completed in current branch:

- FX edit no longer replaces the destination amount with the source amount;
- transfer account changes that would silently change currency semantics are rejected.

Expected result:

A transfer such as `100 USD -> 45,000 KZT` stays an FX transfer after editing and cannot silently become `200 USD -> 200 KZT`.

### Planned operations

Change:

- execution must acquire the lock before reading active state;
- planned execution gets a unique execution/occurrence key;
- state transition to executed and ledger mutation happen in one transaction;
- repeated HTTP callbacks, Telegram callbacks or client retries return the existing result instead of creating another transaction;
- manual completion and money execution are treated as separate explicit commands.

Expected result:

One planned item can produce at most one financial execution for one occurrence.

### Recurring operations

Change:

- introduce occurrence identity such as `(recurring_id, due_date)`;
- API and Telegram use one shared execution service;
- retry-safe `paid/received/execute` behavior;
- notification acknowledgement must not itself imply a second financial execution;
- archive/reschedule behavior is separated from ledger creation.

Expected result:

A monthly recurring item cannot be charged twice because of a double tap, retry or two active clients.

### Debts

Change:

- move debt payment logic into one application service;
- lock and re-read debt inside the write transaction;
- create account transaction, update remaining debt and insert payment history atomically;
- add payment idempotency key;
- define reversal rules for debt payments instead of allowing generic transaction delete/edit;
- unify Telegram and API FX handling for debt payments;
- make overpayment behavior explicit.

Expected result:

Debt balance, account balance, payment history and ledger always describe the same event.

### Deposits

Change:

- keep serialized accrual;
- move accrual out of GET endpoints;
- scheduler/application service becomes responsible for accrual;
- add a persistent unique accrual identity per account/period;
- GET dashboard/accounts becomes read-only.

Already completed in current branch:

- deposit state is locked before reading accrual markers;
- concurrent accrual regression test added.

Expected result:

Reading a screen never creates money, and one accrual period can only be posted once.

---

## Phase P0-B — Transport and Security

### HTTPS / network boundary

Change:

- Flutter base URL becomes configurable and HTTPS-only for production;
- reverse proxy terminates TLS;
- Uvicorn binds to `127.0.0.1` instead of external `0.0.0.0` where applicable;
- direct API/web ports are closed externally;
- static Flutter web assets are served by the reverse proxy instead of Python `http.server` in the final production setup;
- services run under a dedicated unprivileged user.

Expected result:

Passwords, bearer tokens and financial data are not transmitted over plain HTTP and backend ports are not directly exposed.

### Authentication and sessions

Change:

- replace 90-day bearer-only token design with short-lived access tokens plus revocable refresh/session records;
- add logout/session revoke;
- optional device/session list;
- rate-limit auth endpoints;
- move token storage on mobile to secure storage;
- SharedPreferences retains only non-sensitive preferences.

Expected result:

A leaked access token has a limited lifetime and a session can be revoked server-side.

---

## Phase P1-A — Test Gate and Release Safety

### Backend test suite

Change:

Create deterministic temporary-database regression tests for:

- concurrent transaction edit/delete;
- FX transfers;
- planned execution retries;
- recurring occurrence retries;
- debt payment retries and reversals;
- deposit accrual;
- ownership boundaries;
- timezone/budget-cycle boundaries;
- composite-operation rollback.

Financial integrity tests become mandatory CI checks.

### Flutter tests

Change:

- remove the template counter test;
- add login/session tests;
- add transaction form validation tests;
- add API error propagation tests;
- add planned/debt retry UX tests;
- run `flutter analyze` and tests in CI.

### Deployment

Change:

- PR checks must pass before merge;
- production deployment remains tied to master only;
- migrations remain backup-protected;
- add smoke checks for API and web after deploy;
- later add a staging deployment if usage grows.

Expected result:

Financial regressions are blocked before production rather than discovered through user balances.

---

## Phase P1-B — Backend Architecture

### Application services / commands

Introduce explicit commands such as:

- `CreateTransaction`;
- `UpdateTransaction`;
- `DeleteTransaction`;
- `CreateTransfer`;
- `ExecutePlannedOperation`;
- `ExecuteRecurringOccurrence`;
- `PayDebt`;
- `ReverseDebtPayment`;
- `AccrueDepositPeriod`.

Each command owns:

1. validation;
2. authorization/ownership;
3. transaction boundary;
4. idempotency;
5. ledger mutation;
6. related domain mutation;
7. returned result/event.

### API split

Split `api_server.py` into feature routers:

- auth;
- accounts;
- transactions;
- transfers;
- budgets;
- debts;
- planned;
- recurring;
- analytics;
- AI;
- settings;
- export.

The split is not cosmetic: routers should call application services rather than contain business logic.

### Telegram cleanup

Telegram handlers should stop calling low-level repositories for money mutations. They should call the same commands used by FastAPI.

Expected result:

There is one implementation of each financial rule regardless of client.

---

## Phase P1-C — Flutter Architecture

### Networking

Introduce a centralized `ApiClient` responsible for:

- base URL;
- authorization headers;
- refresh flow;
- structured API errors;
- timeouts;
- retry policy only for safe/idempotent actions.

### Repositories

Create client repositories such as:

- `AuthRepository`;
- `AccountsRepository`;
- `TransactionsRepository`;
- `PlanningRepository`;
- `DebtsRepository`;
- `AnalyticsRepository`;
- `AiRepository`.

### State

Split global state into smaller concerns:

- auth/session state;
- finance/dashboard state;
- planning/obligation state;
- settings state;
- Premium/access state;
- AI state.

### Error semantics

Change methods that currently swallow network/non-200 errors so UI receives a typed failure and does not display false success.

Expected result:

The Flutter client becomes easier to change without accidentally coupling authentication, finance logic and UI state.

---

## Phase P2-A — Analytics redesign

The current analytics should evolve from charts into decision support.

### Core analytics model

Unify calculations around the user's base currency and timezone.

Primary metrics:

- current net liquid balance;
- income / expense / net cash flow;
- savings rate;
- burn rate;
- runway;
- fixed obligations due before next income/cycle end;
- free cash after obligations;
- debt load;
- category deviation vs normal baseline;
- budget usage;
- upcoming recurring/planned cash flow.

### Period model

All clients should use one backend period engine for:

- today;
- week;
- month;
- custom range;
- budget cycle.

No client should independently guess UTC/local boundaries.

### Dashboard

Change the dashboard from a collection of cards into a hierarchy:

1. **Where I am now** — balances/net position;
2. **What happened** — current period income/expense/net;
3. **What is coming** — obligations/planned/recurring;
4. **What needs attention** — budget/debt/anomaly alerts;
5. **What to do next** — one concise actionable recommendation.

### Forecast

Add a deterministic forecast before using AI:

`current available funds + expected incomes - required planned payments - recurring obligations`

Show projected balance at cycle end / next 30 days.

AI may explain the forecast, but must not be the source of the numbers.

Expected result:

Analytics answers practical questions such as "how much is actually free to spend?", "will I cover all obligations?" and "what changed?" rather than only presenting charts.

---

## Phase P2-B — AI redesign

### Event-driven recomputation

Change:

- do not launch AI analysis for every ledger row;
- publish/record a committed finance event;
- debounce profile recomputation per user;
- worker recalculates after a burst of operations;
- AI failures never affect transaction success.

### Deterministic numbers, AI explanation

All calculations remain deterministic backend functions. The LLM receives computed facts and explains them.

AI should not calculate balances, FX, debt remaining amounts or budget totals from raw text when those values already exist in structured data.

### Advice lifecycle

Each recommendation should contain:

- reason;
- evidence/metric;
- action;
- target;
- expiry/re-evaluation point;
- status: active/completed/expired/dismissed.

Expected result:

The AI becomes a financial coach built on verified data rather than another calculation engine.

---

## Phase P2-C — Product and UX cleanup

### Navigation

Keep the main experience focused. Proposed top-level concepts:

- Home;
- Analytics;
- Add operation;
- Plan / Obligations;
- AI / Advisor.

Accounts, categories, settings, exports and technical tools remain secondary screens.

### Fast operation entry

The fastest flow should remain one of the product's strongest features:

`amount -> category -> account -> save`

Optional fields remain optional.

Quick templates and AI parsing can accelerate this but must ultimately call the same backend command.

### Personal vs business mode

If both modes stay in the product, data separation should be explicit in backend queries and analytics. Filtering by display names or client-side heuristics should not define financial boundaries.

### Localization

Change:

- selected language controls Flutter locale;
- backend/user preference remains the source of truth;
- RU/KK/EN financial terminology is kept consistent between Telegram and app.

Expected result:

The application feels like one coherent product rather than a set of separately added features.

---

## 4. Priorities

### P0 — must be completed before aggressive product expansion

- transaction/ledger integrity;
- FX integrity;
- planned idempotency;
- recurring idempotency;
- debt payment atomicity/idempotency;
- deposit accrual command + idempotency;
- HTTPS;
- safer session/token model.

### P1 — complete before broader public scale

- full financial regression suite;
- Flutter test coverage;
- shared application-service layer;
- split API routers;
- Flutter state/network decomposition;
- structured error handling;
- deploy/release gates.

### P2 — product quality and differentiation

- analytics redesign;
- forecasting;
- event-driven AI;
- recommendation lifecycle;
- navigation simplification;
- localization completion;
- UX polish.

---

## 5. Expected state after roadmap

After P0:

- retries and double taps cannot duplicate money movements;
- related debt/planned/recurring records cannot drift from ledger state;
- FX operations have stable semantics;
- production traffic is encrypted;
- sessions can be revoked.

After P1:

- all clients use the same financial commands;
- financial invariants are enforced by CI;
- backend and Flutter are substantially easier to maintain;
- new features no longer require copying business logic into several places.

After P2:

- the product explains current position, future obligations and free cash clearly;
- AI is based on verified deterministic metrics;
- UX is centered on decisions rather than feature count;
- Telegram becomes a fast companion interface rather than a separate implementation of the finance engine.

---

## 6. What we are intentionally not changing yet

Until P0/P1 are stable, do not spend major development time on:

- visual redesign for its own sake;
- additional chart types;
- investment brokerage integrations;
- bank scraping/open-banking integrations;
- complex social/gamification systems;
- family/shared accounts;
- new AI personalities/models;
- many additional Premium features;
- large database migration away from SQLite solely for prestige/scalability concerns.

SQLite can remain while write volume is modest if financial commands are correctly serialized, tested and designed. A PostgreSQL migration should be driven by measured concurrency/operational needs, not by architecture fashion.

---

## 7. Execution order

1. Finish financial integrity v1 PR.
2. Planned/recurring/debt idempotency and atomic commands.
3. Deposit command + remove mutations from GET.
4. HTTPS and session hardening.
5. Expand financial regression CI.
6. Extract shared application services and split API routes.
7. Refactor Flutter networking/state.
8. Rebuild analytics around position / cash flow / obligations / forecast.
9. Move AI to event-driven explanation and recommendation lifecycle.
10. UX/navigation cleanup and localization completion.

This order is deliberate: correctness first, then architecture, then product expansion.
