-- Finance Tracker: read-only integrity checks
-- Generated 2026-08-28. This script contains no INSERT/UPDATE/DELETE statements.
-- Recommended use: run against a backup or an immutable read-only copy first.

PRAGMA query_only = ON;

-- 1. SQLite-level foreign-key violations.
PRAGMA foreign_key_check;

-- 2. Account balance versus the sum of all active ledger rows.
-- Any returned row is a materialized-balance drift candidate.
SELECT
    a.user_id,
    a.id AS account_id,
    a.name AS account_name,
    a.currency,
    a.balance AS stored_balance,
    COALESCE(SUM(CASE WHEN t.deleted_at IS NULL THEN t.amount ELSE 0 END), 0) AS ledger_balance,
    a.balance - COALESCE(SUM(CASE WHEN t.deleted_at IS NULL THEN t.amount ELSE 0 END), 0) AS drift
FROM accounts AS a
LEFT JOIN transactions AS t
  ON t.account_id = a.id
 AND t.user_id = a.user_id
GROUP BY a.user_id, a.id, a.name, a.currency, a.balance
HAVING drift <> 0
ORDER BY ABS(drift) DESC, a.user_id, a.id;

-- 3. Transactions referencing an account owned by another user.
SELECT
    t.id AS transaction_id,
    t.user_id AS transaction_user_id,
    t.account_id,
    a.user_id AS account_owner_user_id,
    t.type,
    t.amount,
    t.deleted_at
FROM transactions AS t
JOIN accounts AS a ON a.id = t.account_id
WHERE t.user_id <> a.user_id
ORDER BY t.id;

-- 4. Transactions referencing a category owned by another user.
SELECT
    t.id AS transaction_id,
    t.user_id AS transaction_user_id,
    t.category_id,
    c.user_id AS category_owner_user_id,
    t.type,
    t.amount,
    t.deleted_at
FROM transactions AS t
JOIN categories AS c ON c.id = t.category_id
WHERE t.user_id <> c.user_id
ORDER BY t.id;

-- 5. Invalid signs in active income/expense ledger rows.
SELECT id, user_id, type, amount, account_id, ts, note
FROM transactions
WHERE deleted_at IS NULL
  AND (
       (type = 'expense' AND amount >= 0)
    OR (type = 'income' AND amount <= 0)
  )
ORDER BY id;

-- 6. Broken or asymmetric transfer pairs.
SELECT
    t.id,
    t.user_id,
    t.amount,
    t.account_id,
    t.related_tx_id,
    r.id AS related_id,
    r.user_id AS related_user_id,
    r.amount AS related_amount,
    r.account_id AS related_account_id,
    r.related_tx_id AS related_back_reference,
    t.deleted_at,
    r.deleted_at AS related_deleted_at
FROM transactions AS t
LEFT JOIN transactions AS r ON r.id = t.related_tx_id
WHERE t.type = 'transfer'
  AND (
       t.related_tx_id IS NULL
    OR r.id IS NULL
    OR r.type <> 'transfer'
    OR r.user_id <> t.user_id
    OR r.related_tx_id <> t.id
    OR (t.amount < 0 AND r.amount <= 0)
    OR (t.amount > 0 AND r.amount >= 0)
    OR COALESCE(t.deleted_at, '') <> COALESCE(r.deleted_at, '')
  )
ORDER BY t.id;

-- 7. Duplicate deposit-interest rows for the same account and accrual timestamp.
SELECT
    user_id,
    account_id,
    ts,
    amount,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(id) AS transaction_ids
FROM transactions
WHERE deleted_at IS NULL
  AND type = 'income'
  AND note = 'Проценты по депозиту'
GROUP BY user_id, account_id, ts, amount
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, ts;

-- 8. Debt payment history whose linked transaction is absent, deleted,
-- belongs to another user, or points to another account.
SELECT
    p.id AS payment_id,
    p.user_id,
    p.debt_id,
    p.tx_id,
    p.account_id AS payment_account_id,
    p.amount AS debt_amount_base_currency,
    t.account_id AS transaction_account_id,
    t.amount AS transaction_amount_account_currency,
    t.deleted_at
FROM debt_payments AS p
LEFT JOIN transactions AS t ON t.id = p.tx_id
WHERE p.tx_id IS NOT NULL
  AND (
       t.id IS NULL
    OR t.deleted_at IS NOT NULL
    OR t.user_id <> p.user_id
    OR (p.account_id IS NOT NULL AND t.account_id <> p.account_id)
  )
ORDER BY p.id;

-- 9. Suspicious duplicate debt payment records.
-- Review manually: two legitimate same-day equal payments are possible.
SELECT
    user_id,
    debt_id,
    payment_date,
    amount,
    account_id,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(id) AS payment_ids
FROM debt_payments
GROUP BY user_id, debt_id, payment_date, amount, account_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, payment_date;

-- 10. Suspicious duplicate active transactions in the same second.
-- This is a review queue, not proof of an error.
SELECT
    user_id,
    account_id,
    type,
    amount,
    SUBSTR(ts, 1, 19) AS ts_second,
    COALESCE(note, '') AS note,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(id) AS transaction_ids
FROM transactions
WHERE deleted_at IS NULL
GROUP BY user_id, account_id, type, amount, ts_second, COALESCE(note, '')
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, ts_second;

-- 11. Closed/active debt state contradictions.
SELECT id, user_id, title, remaining_amount, is_active, status, closed_at
FROM debts
WHERE (is_active = 0 AND COALESCE(remaining_amount, 0) <> 0)
   OR (is_active = 1 AND COALESCE(remaining_amount, 0) <= 0)
   OR (is_active = 0 AND status <> 'closed')
ORDER BY user_id, id;

-- 12. Invalid or stale exchange-rate rows.
SELECT currency, rate_to_usd, updated_at
FROM exchange_rates
WHERE rate_to_usd IS NULL
   OR rate_to_usd <= 0
   OR datetime(updated_at) IS NULL
   OR datetime(updated_at) < datetime('now', '-48 hours')
ORDER BY currency;

-- 13. Invalid active account amounts that cannot be represented safely by the UI policy.
SELECT id, user_id, name, currency, balance
FROM accounts
WHERE ABS(balance) > 1000000000
ORDER BY ABS(balance) DESC;

PRAGMA query_only = OFF;
