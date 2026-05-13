from __future__ import annotations

import time
import aiosqlite

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.fsm.states import QuickAddFlow
from app.ui.keyboards import quick_pick_type_kb, main_menu
from app.db.repositories.settings_repo import get_lang
from app.domain.services.quick_parser import parse_quick
from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.tx_repo import list_last, delete_tx
from app.db.repositories.categories_repo import (
    find_category_by_name_ci,
    find_category_by_note_hint,
)
# ПУБЛИЧНЫЕ точки входа из transactions.py
from app.handlers.common import cancel_to_main_menu, build_main_menu_markup
from app.handlers.transactions import (
    start_prefilled_expense,
    start_prefilled_income,
)

router = Router()

DRAFT_TTL_SECONDS = 300


def _L(lang: str) -> dict[str, str]:
    lang=(lang or "ru").lower()
    if lang=="en":
        return {"draft_expired":"Draft expired","draft_expired_retry":"Draft expired. Enter the operation again.","draft_build_error":"Could not build draft","draft_build_retry":"Could not build draft. Enter it again.","pick_type":"Is this income or expense?","busy":"Another step is active now. Finish it or cancel.","format":"Format: /q coffee 1200 or /q +120000 salary","bad_type":"Invalid type","empty_draft":"Draft is empty","nothing_undo":"Nothing to undo.","undo_ok":"Rolled back.","undo_fail":"Could not roll back."}
    if lang=="kk":
        return {"draft_expired":"Черновик ескірді","draft_expired_retry":"Черновик ескірді. Операцияны қайта енгізіңіз.","draft_build_error":"Черновикті жинау мүмкін болмады","draft_build_retry":"Черновикті жинау мүмкін болмады. Қайта енгізіңіз.","pick_type":"Бұл кіріс пе әлде шығыс па?","busy":"Қазір басқа қадам белсенді. Аяқтаңыз немесе болдырмаңыз.","format":"Формат: /q кофе 1200 немесе /q +120000 жалақы","bad_type":"Қате түр","empty_draft":"Черновик бос","nothing_undo":"Кері қайтаратын ештеңе жоқ.","undo_ok":"Қайтарылды.","undo_fail":"Қайтару сәтсіз."}
    return {"draft_expired":"Черновик устарел","draft_expired_retry":"Черновик устарел. Введи операцию заново.","draft_build_error":"Не удалось собрать черновик","draft_build_retry":"Не удалось собрать черновик. Введи заново.","pick_type":"Это доход или расход?","busy":"Сейчас активен другой шаг. Заверши его или отмени.","format":"Формат: /q кофе 1200 или /q +120000 зарплата","bad_type":"Некорректный тип","empty_draft":"Черновик пуст","nothing_undo":"Нечего отменять.","undo_ok":"Откатил.","undo_fail":"Не смог откатить."}


async def _ensure_quick_alive(state: FSMContext) -> bool:
    data = await state.get_data()
    started = data.get("quick_started_at")
    if not started:
        return True

    try:
        started = float(started)
    except Exception:
        return True

    if time.time() - started <= DRAFT_TTL_SECONDS:
        return True

    await state.clear()
    return False


async def _autopick_if_possible(db, user_id: int, state: FSMContext):
    data = await state.get_data()
    kind = data.get("kind")
    note = (data.get("note") or "").strip()

    if kind in ("income", "expense") and note:
        exact_hit = await find_category_by_name_ci(db, user_id, kind, note)
        hit = exact_hit

        if not hit:
            hit = await find_category_by_note_hint(db, user_id, kind, note)

        if hit:
            cid, cname, cemoji = hit

            update_payload = {
                "category_id": cid,
                "category_name": cname,
                "category_emoji": (cemoji or ""),
            }

            # если весь текст после суммы — это просто категория,
            # не тащим его в комментарий
            if exact_hit:
                update_payload["note"] = None

            await state.update_data(**update_payload)




async def _handoff_to_transactions(
    target: Message | CallbackQuery,
    state: FSMContext,
    db,
):
    if not await _ensure_quick_alive(state):
        if isinstance(target, CallbackQuery):
            lang = await get_lang(db, target.from_user.id)
            await target.answer(_L(lang)["draft_expired"], show_alert=True)
        else:
            lang = await get_lang(db, target.from_user.id)
            await target.answer(
                _L(lang)["draft_expired_retry"],
                reply_markup=await build_main_menu_markup(db, m.from_user.id, lang),
            )
        return

    data = await state.get_data()

    kind = data.get("kind")
    amount = int(data.get("amount") or 0)
    note = (data.get("note") or "").strip() or None
    account_id = data.get("account_id")
    category_id = data.get("category_id")
    category_name = (data.get("category_name") or "").strip()

    # страховка от кейса:
    # "-4500 развлечения" -> категория уже найдена,
    # но то же слово осталось в комментарии
    if note and category_id is not None and category_name:
        if note.casefold() == category_name.casefold():
            note = None
            await state.update_data(note=None)

    if kind not in ("income", "expense") or amount <= 0:
        await state.clear()
        if isinstance(target, CallbackQuery):
            lang = await get_lang(db, target.from_user.id)
            await target.answer(_L(lang)["draft_build_error"], show_alert=True)
        else:
            lang = await get_lang(db, target.from_user.id)
            await target.answer(
                _L(lang)["draft_build_retry"],
                reply_markup=await build_main_menu_markup(db, m.from_user.id, lang),
            )
        return

    can_skip_note_prompt = (
            note is None
            and account_id is not None
            and category_id is not None
    )

    if kind == "expense":
        await start_prefilled_expense(
            target,
            state,
            db,
            amount=amount,
            note=note,
            account_id=int(account_id) if account_id is not None else None,
            category_id=int(category_id) if category_id is not None else None,
            skip_note_prompt=can_skip_note_prompt,
        )
    else:
        await start_prefilled_income(
            target,
            state,
            db,
            amount=amount,
            note=note,
            account_id=int(account_id) if account_id is not None else None,
            category_id=int(category_id) if category_id is not None else None,
            skip_note_prompt=can_skip_note_prompt,
        )

@router.message(F.text.regexp(r".*\d.*") & ~F.text.startswith("/"))
async def quick_autostart(m: Message, state: FSMContext, db):
    if await state.get_state():
        return

    parsed = parse_quick(m.text)
    if not parsed:
        return

    await state.set_state(QuickAddFlow.pick_type if parsed.kind is None else QuickAddFlow.draft)
    await state.update_data(
        amount=parsed.amount,
        note=parsed.note,
        kind=parsed.kind,
        quick_started_at=time.time(),
    )

    if parsed.kind is None:
        lang = await get_lang(db, m.from_user.id)
        sent = await m.answer(_L(lang)["pick_type"], reply_markup=quick_pick_type_kb(lang))
        await state.update_data(flow_message_id=sent.message_id)
        return

    await _autopick_if_possible(db, m.from_user.id, state)
    await _handoff_to_transactions(m, state, db)


@router.message(Command("q"))
async def quick_start(m: Message, state: FSMContext, db):
    if await state.get_state():
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_L(lang)["busy"], reply_markup=await build_main_menu_markup(db, m.from_user.id, lang))

    arg = m.text.partition(" ")[2].strip()
    parsed = parse_quick(arg)
    if not parsed:
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_L(lang)["format"])

    await state.set_state(QuickAddFlow.pick_type if parsed.kind is None else QuickAddFlow.draft)
    await state.update_data(
        amount=parsed.amount,
        note=parsed.note,
        kind=parsed.kind,
        quick_started_at=time.time(),
    )

    if parsed.kind is None:
        lang = await get_lang(db, m.from_user.id)
        sent = await m.answer(_L(lang)["pick_type"], reply_markup=quick_pick_type_kb(lang))
        await state.update_data(flow_message_id=sent.message_id)
        return

    await _autopick_if_possible(db, m.from_user.id, state)
    await _handoff_to_transactions(m, state, db)


@router.callback_query(F.data.startswith("qa:type:"))
async def qa_pick_type(c: CallbackQuery, state: FSMContext, db):
    if not await _ensure_quick_alive(state):
        lang = await get_lang(db, c.from_user.id)
        await c.answer(_L(lang)["draft_expired"], show_alert=True)
        return

    kind = c.data.split(":")[2]
    if kind not in ("income", "expense"):
        lang = await get_lang(db, c.from_user.id)
        await c.answer(_L(lang)["bad_type"], show_alert=True)
        return

    data = await state.get_data()
    if not data.get("amount"):
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.answer(_L(lang)["empty_draft"], show_alert=True)
        return

    await state.set_state(QuickAddFlow.draft)
    await state.update_data(kind=kind)

    await _autopick_if_possible(db, c.from_user.id, state)
    await _handoff_to_transactions(c, state, db)

    try:
        await c.answer()
    except Exception:
        pass


@router.callback_query(F.data == "qa:cancel")
async def qa_cancel(c: CallbackQuery, state: FSMContext, db):
    await cancel_to_main_menu(c, state, db)


@router.message(Command("undo"))
async def qa_undo_cmd(m: Message, db: aiosqlite.Connection):
    last = await list_last(db, m.from_user.id, limit=1)
    if not last:
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_L(lang)["nothing_undo"])

    tx_id = int(last[0][0])

    try:
        ok, _ = await delete_tx(db, m.from_user.id, tx_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    lang = await get_lang(db, m.from_user.id)
    await m.answer(_L(lang)["undo_ok"] if ok else _L(lang)["undo_fail"])