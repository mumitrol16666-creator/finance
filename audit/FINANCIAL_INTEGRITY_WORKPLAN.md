# Financial Integrity Refactor Work Plan

Branch: `refactor/financial-integrity-v1`

## P0 — ledger correctness

- [x] Serialize deposit interest accrual before reading accrual markers.
- [x] Add a regression script for concurrent deposit accrual.
- [ ] Move transaction update/delete reads inside the write lock.
- [ ] Preserve destination amount / FX rate when editing cross-currency transfers.
- [ ] Validate ownership of account/category targets before balance mutations.
- [ ] Add idempotency keys for planned, recurring, debt-payment and deposit occurrences.
- [ ] Make debt payment, transaction and debt history mutations one atomic command.

## P0 — transport and sessions

- [ ] Remove plain HTTP API usage from Flutter.
- [ ] Put API behind HTTPS reverse proxy and bind the app server to loopback.
- [ ] Replace long-lived bearer-only sessions with revocable sessions / refresh tokens.
- [ ] Store mobile credentials/tokens in secure storage rather than SharedPreferences.

## P1 — test gate

- [ ] Add concurrency/invariant checks to CI before deploy.
- [ ] Add transaction/transfer/debt/planned regression tests.
- [ ] Add real Flutter widget/integration tests and remove template counter test.

## P1 — architecture

- [ ] Split the monolithic API router into feature routers.
- [ ] Route Telegram, API and scheduler money mutations through the same application services.
- [ ] Split Flutter `AppState` into API/repository/state layers.

## P2 — AI and product cleanup

- [x] Fix unreachable `investing` AI stage.
- [ ] Debounce/queue AI profile recomputation instead of spawning per-ledger-row tasks.
- [ ] Finish localization so selected language controls Flutter locale.
