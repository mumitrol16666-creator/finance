# Financial Integrity v1 — Change Log

## Completed in this branch

1. Deposit accrual is serialized with `BEGIN IMMEDIATE` before reading deposit markers, preventing concurrent dashboard/account reads from posting the same interest period twice.
2. Deposit account updates are additionally scoped by `user_id`.
3. A dedicated deposit concurrency regression script was added at `scripts/check_deposit_accrual_concurrency.py`.
4. Transaction delete/update now acquire the SQLite write lock before reading the ledger row, preventing stale-read double reverts and double deltas.
5. Transaction edits reject non-positive amounts and reject target accounts/categories that do not belong to the current user.
6. Cross-currency transfer edits preserve the original destination/source amount ratio instead of replacing both sides with the same nominal number.
7. Moving transfer sides to accounts with a different currency is rejected until an explicit new FX amount/rate model is introduced.
8. `scripts/check_financial_integrity.py` now covers concurrent delete, concurrent edit, invalid negative edits, cross-user account moves and FX edit preservation.
9. The existing backend validation gate now runs both the transaction integrity checks and the deposit concurrency check.
10. AI stage ordering was corrected so the stricter `investing` condition is evaluated before `budgeting` and is reachable.
11. A tracked work plan is maintained in `audit/FINANCIAL_INTEGRITY_WORKPLAN.md`.

## Next P0 batch

- idempotent planned execution;
- idempotent recurring execution;
- debt payment + transaction + debt history as one atomic command;
- explicit occurrence/idempotency keys for money-producing background actions;
- HTTPS-only application transport and revocable sessions.
