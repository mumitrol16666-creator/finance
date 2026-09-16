# Financial Integrity Refactor Work Plan

Branch: `refactor/financial-integrity-v1`

Full product/technical roadmap: `audit/PRODUCT_TECHNICAL_ANALYSIS_AND_ROADMAP.md`

## P0 — ledger correctness

- [x] Serialize deposit interest accrual before reading accrual markers.
- [x] Add a regression script for concurrent deposit accrual.
- [x] Move transaction update/delete reads inside the write lock.
- [x] Preserve destination amount / FX ratio when editing cross-currency transfers.
- [x] Validate ownership of account/category targets before balance mutations.
- [x] Guard debt-linked ledger transactions from generic update/delete flows.
- [ ] Add idempotency keys for planned, recurring, debt-payment and deposit occurrences.
- [ ] Make planned execution a single atomic command.
- [ ] Make recurring execution a single atomic command.
- [ ] Make debt payment, transaction and debt history mutations one atomic command.
- [ ] Define explicit reversal flow for debt payments.
- [ ] Remove deposit accrual mutations from GET endpoints and run them through a scheduled/application command.

## P0 — transport and sessions

- [ ] Remove plain HTTP API usage from Flutter.
- [ ] Put API behind HTTPS reverse proxy and bind the app server to loopback.
- [ ] Close direct external access to backend/web service ports.
- [ ] Run production services under an unprivileged service user.
- [ ] Replace long-lived bearer-only sessions with short-lived access + revocable refresh/session records.
- [ ] Store mobile credentials/tokens in secure storage rather than SharedPreferences.
- [ ] Add authentication rate limiting and explicit session revoke/logout.

## P1 — test gate

- [x] Add concurrency/invariant checks to the existing backend CI gate.
- [ ] Add debt/planned/recurring idempotency regression tests.
- [ ] Add rollback tests for composite financial commands.
- [ ] Add timezone/budget-cycle boundary tests.
- [ ] Add real Flutter widget/integration tests and remove template counter test.
- [ ] Run `flutter analyze` and Flutter tests in CI.

## P1 — backend architecture

- [ ] Introduce explicit application commands for all money-changing operations.
- [ ] Route Telegram, API and scheduler money mutations through the same application services.
- [ ] Split the monolithic API router into feature routers after command extraction.
- [ ] Separate transport validation from financial/domain validation.
- [ ] Standardize typed domain errors returned to API/Telegram clients.

## P1 — Flutter architecture

- [ ] Introduce a centralized `ApiClient` with auth, error mapping, timeout and refresh handling.
- [ ] Split `AppState` into auth / finance / planning / settings / Premium / AI state.
- [ ] Introduce client repositories for accounts, transactions, planning, debts, analytics and AI.
- [ ] Stop swallowing non-200/network errors in mutation methods.
- [ ] Make retries automatic only for safe/idempotent requests.

## P2 — analytics

- [ ] Unify all periods around backend timezone-aware period calculation.
- [ ] Unify all analytics in user's base currency.
- [ ] Add deterministic free-cash / obligations / runway calculations.
- [ ] Add forward cash-flow forecast from current funds + expected income - obligations.
- [ ] Restructure dashboard into current position / happened / coming / attention / next action.
- [ ] Ensure personal/business mode is separated by backend data fields rather than client display heuristics.

## P2 — AI and product cleanup

- [x] Fix unreachable `investing` AI stage.
- [ ] Debounce/queue AI profile recomputation instead of spawning per-ledger-row tasks.
- [ ] Make AI consume deterministic calculated metrics instead of acting as a financial calculator.
- [ ] Add recommendation lifecycle: reason, metric, target, status, expiry/re-evaluation.
- [ ] Finish localization so selected language controls Flutter locale.
- [ ] Simplify product navigation around Home / Analytics / Add / Plan-Obligations / Advisor.

## Deliberately deferred

Until P0/P1 are stable, do not prioritize:

- cosmetic redesign without workflow benefit;
- additional chart variants;
- bank scraping/open-banking integrations;
- brokerage/investment integrations;
- shared/family accounts;
- large new gamification systems;
- additional AI personas/models;
- migration away from SQLite unless measured load/concurrency justifies it.

## Execution order

1. Finish transaction/FX integrity PR.
2. Planned/recurring/debt idempotency and atomic commands.
3. Deposit command and read-only GET endpoints.
4. HTTPS and session hardening.
5. Expand financial CI coverage.
6. Extract shared application services and split API routers.
7. Refactor Flutter networking/state.
8. Rebuild analytics around position, obligations and forecast.
9. Move AI to event-driven explanation/coaching.
10. UX/navigation/localization cleanup.
