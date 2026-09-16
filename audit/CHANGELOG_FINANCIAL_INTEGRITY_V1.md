# Financial Integrity v1 — Change Log

## Completed in this branch

1. Deposit accrual is now serialized with `BEGIN IMMEDIATE` before reading deposit markers, preventing concurrent dashboard/account reads from posting the same interest period twice.
2. Deposit account updates are additionally scoped by `user_id`.
3. A dedicated concurrency regression script was added at `scripts/check_deposit_accrual_concurrency.py`.
4. AI stage ordering was corrected so the stricter `investing` condition is evaluated before `budgeting` and is therefore reachable.
5. A tracked work plan was added in `audit/FINANCIAL_INTEGRITY_WORKPLAN.md`.

## Next P0 batch

- transaction update/delete stale-read races;
- cross-currency transfer edit integrity;
- target account/category ownership validation;
- idempotent planned/debt/recurring execution.
