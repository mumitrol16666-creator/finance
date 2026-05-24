from __future__ import annotations
import io
import aiosqlite
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.config.settings import settings

router = Router()

@router.message(Command("admin_export"))
async def admin_export_stats(m: Message, bot: Bot, db: aiosqlite.Connection):
    """
    Export global user stats and account details into a multi-sheet Excel file.
    Accessible only to Telegram IDs present in ADMIN_IDS.
    """
    # 1. Security Check
    if m.from_user.id not in settings.admin_ids:
        # Ignore silently for security
        return

    # 2. SQL Queries
    users_query = """
        SELECT 
            u.user_id, 
            u.username, 
            u.first_name, 
            u.full_access, 
            u.created_at,
            s.lang, 
            s.timezone,
            (SELECT COUNT(*) FROM accounts a WHERE a.user_id = u.user_id AND a.deleted_at IS NULL) as accounts_count,
            (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.user_id AND t.deleted_at IS NULL) as tx_count,
            (SELECT COUNT(*) FROM debts d WHERE d.user_id = u.user_id AND d.closed_at IS NULL) as active_debts
        FROM users u
        LEFT JOIN settings s ON u.user_id = s.user_id
        ORDER BY u.created_at DESC
    """
    
    accounts_query = """
        SELECT 
            a.user_id, 
            u.username, 
            a.name, 
            a.balance, 
            a.currency, 
            a.is_saving
        FROM accounts a
        JOIN users u ON a.user_id = u.user_id
        WHERE a.deleted_at IS NULL
        ORDER BY a.user_id, a.name
    """

    try:
        async with db.execute(users_query) as cursor:
            users = await cursor.fetchall()
            
        async with db.execute(accounts_query) as cursor:
            accounts = await cursor.fetchall()
    except Exception as e:
        await m.reply(f"❌ Ошибка выполнения запросов к БД: {e}")
        return

    # 3. Create Workbook
    wb = Workbook()
    
    # Fonts and Fills (Premium Deep Blue/Slate theme)
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    # ==========================================
    # Sheet 1: Users
    # ==========================================
    ws_users = wb.active
    ws_users.title = "Пользователи"
    
    headers_users = [
        "Telegram ID", "Юзернейм", "Имя", "Premium (Full Access)", 
        "Дата регистрации", "Язык", "Часовой пояс", "Кол-во счетов", 
        "Кол-во операций", "Активные долги"
    ]
    
    ws_users.append(headers_users)
    for col_idx in range(1, len(headers_users) + 1):
        cell = ws_users.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        
    for row_idx, u in enumerate(users, start=2):
        is_premium = "Да 👑" if u[3] == 1 else "Нет"
        row_data = [
            u[0], f"@{u[1]}" if u[1] else "—", u[2] or "—", is_premium,
            u[4] or "—", (u[5] or "ru").upper(), u[6] or "—", u[7], u[8], u[9]
        ]
        ws_users.append(row_data)
        for col_idx in range(1, len(headers_users) + 1):
            cell = ws_users.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            # Align numeric fields to right, text to left
            if col_idx in (1, 8, 9, 10):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (4, 6, 7):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # ==========================================
    # Sheet 2: Accounts
    # ==========================================
    ws_accounts = wb.create_sheet(title="Счета пользователей")
    
    headers_accounts = [
        "Telegram ID владельца", "Юзернейм владельца", "Название счета", 
        "Баланс", "Валюта", "Накопительный?"
    ]
    
    ws_accounts.append(headers_accounts)
    for col_idx in range(1, len(headers_accounts) + 1):
        cell = ws_accounts.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        
    for row_idx, acc in enumerate(accounts, start=2):
        is_saving = "Да 🎯" if acc[5] == 1 else "Нет 💳"
        row_data = [
            acc[0], f"@{acc[1]}" if acc[1] else "—", acc[2],
            acc[3], acc[4], is_saving
        ]
        ws_accounts.append(row_data)
        for col_idx in range(1, len(headers_accounts) + 1):
            cell = ws_accounts.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            # Align fields
            if col_idx in (1, 4):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (5, 6):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Auto-adjust column widths for both sheets
    for ws in (ws_users, ws_accounts):
        ws.row_dimensions[1].height = 28
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val_str = str(cell.value or "")
                # Exclude long header text lengths if they blow up width too much
                if cell.row == 1:
                    max_len = max(max_len, min(len(val_str), 15))
                else:
                    max_len = max(max_len, len(val_str))
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
            # Apply padding height to data rows
            for cell in col:
                if cell.row > 1:
                    ws.row_dimensions[cell.row].height = 20

    # 4. Save to buffer and send
    try:
        file_stream = io.BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)
        xlsx_bytes = file_stream.read()
    except Exception as e:
        await m.reply(f"❌ Ошибка формирования Excel файла: {e}")
        return

    await m.reply_document(
        BufferedInputFile(xlsx_bytes, filename="admin_global_stats.xlsx"),
        caption="📊 <b>Глобальная статистика пользователей и счетов</b>"
    )
