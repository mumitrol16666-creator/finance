import sys

file_path = "app/domain/services/ai_consultant_service.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = "async def discover_recurring_candidates(db: aiosqlite.Connection, user_id: int, days: int = 90) -> list[dict]:"

if target not in content:
    print("Target function start not found!")
    sys.exit(1)

parts = content.split(target)
if len(parts) != 2:
    print(f"Target found {len(parts)-1} times, expected exactly 1!")
    sys.exit(1)

new_func = """async def discover_recurring_candidates(db: aiosqlite.Connection, user_id: int, days: int = 90) -> list[dict]:
    \"\"\"Finds potential recurring transactions in history using a strict mathematical algorithm:
    Must be present 3 months in a row, strictly once a month, same amount, same name, same day of month (+/- 5 days tolerance),
    and must not overlap with existing recurring templates or active debts.
    \"\"\"
    from datetime import datetime, timedelta, timezone
    
    # 1. Fetch existing recurring templates & debts
    existing_expenses = await list_recurring_expenses(db, user_id)
    existing_incomes = await list_recurring_incomes(db, user_id)
    existing_debts = await list_active_debts(db, user_id)

    existing_exp_titles = {str(r[1]).strip().lower() for r in existing_expenses if r[1]}
    existing_inc_titles = {str(r[1]).strip().lower() for r in existing_incomes if r[1]}
    existing_debt_titles = {str(r[1]).strip().lower() for r in existing_debts if r[1]}

    # Fetch transactions from the last 100 days
    start_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    cur = await db.execute(
        \"\"\"
        SELECT t.type, t.amount, COALESCE(t.note, '') as note, c.name as category_name, t.category_id, t.account_id, t.ts
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.ts >= ? AND t.deleted_at IS NULL AND t.type IN ('expense', 'income')
        ORDER BY t.ts ASC
        \"\"\",
        (user_id, start_date)
    )
    rows = await cur.fetchall()

    # Group by (type, amount, note_cleaned)
    groups = {}
    for r in rows:
        ttype = r[0]
        amount = abs(int(r[1]))
        note = r[2].strip()
        if not note:
            continue
        note_lower = note.lower()

        # Duplicate checking
        is_dup = False
        if ttype == "expense":
            if note_lower in existing_exp_titles:
                is_dup = True
            for t in existing_exp_titles:
                if t in note_lower or note_lower in t:
                    is_dup = True
        elif ttype == "income":
            if note_lower in existing_inc_titles:
                is_dup = True
            for t in existing_inc_titles:
                if t in note_lower or note_lower in t:
                    is_dup = True
        
        for dt in existing_debt_titles:
            if dt in note_lower or note_lower in dt:
                is_dup = True
                
        if is_dup:
            continue

        key = (ttype, amount, note_lower)
        if key not in groups:
            groups[key] = {
                "title": note,
                "category_id": r[4],
                "account_id": r[5],
                "dates": [],
                "rows": []
            }
        
        try:
            dt = datetime.fromisoformat(r[6].replace("Z", "+00:00"))
            groups[key]["dates"].append(dt)
            groups[key]["rows"].append(r)
        except Exception:
            continue

    final_candidates = []
    for (ttype, amount, note_lower), g in groups.items():
        dates = g["dates"]
        if len(dates) < 3:
            continue
        
        # Group dates by calendar month: (year, month) -> list of days
        months = {}
        for dt in dates:
            m_key = (dt.year, dt.month)
            if m_key not in months:
                months[m_key] = []
            months[m_key].append(dt.day)
        
        # Sort keys
        m_keys = sorted(months.keys())
        if len(m_keys) < 3:
            continue
        
        found_consecutive = False
        consecutive_keys = []
        for i in range(len(m_keys) - 2):
            k1, k2, k3 = m_keys[i], m_keys[i+1], m_keys[i+2]
            
            y1, mo1 = k1
            y2, mo2 = k2
            y3, mo3 = k3
            
            # Verify they are consecutive calendar months
            diff1 = (y2 - y1) * 12 + (mo2 - mo1)
            diff2 = (y3 - y2) * 12 + (mo3 - mo2)
            
            if diff1 == 1 and diff2 == 1:
                # Strictly once a month check
                if len(months[k1]) == 1 and len(months[k2]) == 1 and len(months[k3]) == 1:
                    d1 = months[k1][0]
                    d2 = months[k2][0]
                    d3 = months[k3][0]
                    
                    # Preferably in the same day (tolerance <= 5 days)
                    if max(d1, d2, d3) - min(d1, d2, d3) <= 5:
                        found_consecutive = True
                        consecutive_keys = [k1, k2, k3]
                        break
        
        if not found_consecutive:
            continue
            
        d1 = months[consecutive_keys[0]][0]
        d2 = months[consecutive_keys[1]][0]
        d3 = months[consecutive_keys[2]][0]
        day_of_month = int(round((d1 + d2 + d3) / 3))
        
        # Day of month should be between 1 and 28
        day_of_month = max(1, min(day_of_month, 28))
        
        import hashlib
        cid = hashlib.md5(f"{g['title']}{amount}{ttype}".encode()).hexdigest()[:12]
        
        last_row = g["rows"][-1]
        
        final_candidates.append({
            "cid": cid,
            "title": g["title"],
            "type": ttype,
            "amount": amount,
            "category_id": last_row[4],
            "account_id": last_row[5],
            "day_of_month": day_of_month,
            "reason": "3 months in a row"
        })
            
    # Sort alphabetically by title
    final_candidates.sort(key=lambda x: x["title"])
    return final_candidates[:10]
"""

content = parts[0] + new_func

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully replaced!")
