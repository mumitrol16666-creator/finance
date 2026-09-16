# PR Notes — Financial Integrity v1

This branch intentionally focuses on ledger correctness before product/UI changes.

## Fixed

- concurrent transaction delete stale-read race;
- concurrent transaction update stale-read race;
- negative transaction edit amounts;
- cross-user account/category targets during edits;
- cross-currency transfer edits that previously replaced destination amount with the source nominal amount;
- concurrent deposit accrual duplication;
- unreachable AI `investing` stage.

## Regression gates

`scripts/check_backend_workflows.py` now also runs:

- `scripts/check_financial_integrity.py`;
- `scripts/check_deposit_accrual_concurrency.py`.

The integrity suite checks concurrent delete/update behavior, ownership validation, invalid amounts and FX ratio preservation.

## Intentionally not merged into this batch

- planned/recurring/debt occurrence idempotency;
- debt-history atomicity;
- HTTPS/reverse-proxy/session redesign;
- Flutter secure token storage;
- API/AppState decomposition.

Those are the next P0/P1 batches in `audit/FINANCIAL_INTEGRITY_WORKPLAN.md`.
