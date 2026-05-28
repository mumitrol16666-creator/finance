from __future__ import annotations

import asyncio
import os
import tempfile
import time
import re
import aiosqlite

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.fsm.states import QuickAddFlow, IncomeFlow, ExpenseFlow
from app.ui.keyboards import quick_pick_type_kb, main_menu
from app.db.repositories.settings_repo import get_lang
from app.domain.services.quick_parser import parse_quick
from app.domain.money import get_user_currency, fmt_money, parse_money
from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.tx_repo import list_last, delete_tx
from app.db.repositories.categories_repo import (
    find_category_by_name_ci,
    find_category_by_note_hint,
)
# ПУБЛИЧНЫЕ точки входа из transactions.py
from app.handlers.common import cancel_to_main_menu, build_main_menu_markup, neutralize_keyboard, deny_feature_message
from app.domain.services.access_service import FEATURE_AI, can_use_feature
from app.handlers.transactions import (
    start_prefilled_expense,
    start_prefilled_income,
    inc_amount,
    exp_amount,
    add_expense_v2,
    add_income,
)
from app.domain.services.ai_llm_service import parse_quick_add_ai, transcribe_audio_ai, has_openai_key

router = Router()

DRAFT_TTL_SECONDS = 300


from app.ui.i18n import t as _i18n_t


def _L(lang: str) -> dict[str, str]:
    """Adapter that pulls the quick-add strings from the central i18n dict.

    The historical contract was a lowercase-keyed dict, so we keep the old keys
    pointing at the new UPPER_CASE i18n entries.
    """
    lang = (lang or "ru").lower()
    return {
        "draft_expired":       _i18n_t(lang, "DRAFT_EXPIRED"),
        "draft_expired_retry": _i18n_t(lang, "DRAFT_EXPIRED_RETRY"),
        "draft_build_error":   _i18n_t(lang, "DRAFT_BUILD_ERROR"),
        "draft_build_retry":   _i18n_t(lang, "DRAFT_BUILD_RETRY"),
        "pick_type":           _i18n_t(lang, "PICK_TYPE"),
        "busy":                _i18n_t(lang, "BUSY"),
        "format":              _i18n_t(lang, "QUICK_FORMAT"),
        "bad_type":            _i18n_t(lang, "BAD_TYPE"),
        "empty_draft":         _i18n_t(lang, "EMPTY_DRAFT"),
        "nothing_undo":        _i18n_t(lang, "NOTHING_UNDO"),
        "undo_ok":             _i18n_t(lang, "UNDO_OK"),
        "undo_fail":           _i18n_t(lang, "UNDO_FAIL"),
    }


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
    category_hint = (data.get("category_hint") or "").strip()

    if kind not in ("income", "expense"):
        return

    # --- 1. Try category_hint first (from AI voice/text parsing) ---
    if category_hint:
        hint_hit = await find_category_by_name_ci(db, user_id, kind, category_hint)
        if not hint_hit:
            hint_hit = await find_category_by_note_hint(db, user_id, kind, category_hint)
        if hint_hit:
            cid, cname, cemoji = hint_hit
            # When matched via category_hint, keep note intact as user comment
            await state.update_data(
                category_id=cid,
                category_name=cname,
                category_emoji=(cemoji or ""),
            )
            return

    # --- 2. Fallback: match via note field (original behavior) ---
    if note:
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



# Transliteration map for common account name aliases (user language -> stored name)
_ACCOUNT_ALIASES: dict[str, str] = {
    "каспи": "kaspi",
    "каспий": "kaspi",
    "kaspi": "kaspi",
    "халык": "halyk",
    "halyk": "halyk",
    "наличные": "наличные",
    "нал": "наличные",
    "cash": "наличные",
    "карта": "карта",
    "card": "карта",
    "jusan": "jusan",
    "жусан": "jusan",
    "форте": "forte",
    "forte": "forte",
}


async def _autopick_account(db, user_id: int, state: FSMContext):
    """Try to auto-select an account based on AI-provided account_hint."""
    data = await state.get_data()
    hint = (data.get("account_hint") or "").strip().lower()
    if not hint:
        return

    accounts = await list_accounts(db, user_id)
    if not accounts:
        return

    # Normalize the hint through alias map
    normalized_hint = _ACCOUNT_ALIASES.get(hint, hint)

    for acc in accounts:
        acc_id = acc[0]
        acc_name = (acc[1] or "").strip()
        acc_name_lower = acc_name.lower()

        # Exact match
        if acc_name_lower == hint or acc_name_lower == normalized_hint:
            await state.update_data(account_id=acc_id)
            return

    # Substring match as fallback
    for acc in accounts:
        acc_id = acc[0]
        acc_name = (acc[1] or "").strip().lower()
        if hint in acc_name or normalized_hint in acc_name or acc_name in hint:
            await state.update_data(account_id=acc_id)
            return


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
                reply_markup=await build_main_menu_markup(db, target.from_user.id, lang),
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
                reply_markup=await build_main_menu_markup(db, target.from_user.id, lang),
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

@router.message(F.text.regexp(r"\d{2,}") & ~F.text.startswith("/"))
async def quick_autostart(m: Message, state: FSMContext, db):
    current_state = await state.get_state()
    if current_state is not None and current_state not in (IncomeFlow.amount.state, ExpenseFlow.amount.state):
        return

    # 1. Проверяем, стоит ли использовать AI (если есть ключ и текст сложный)
    # Сложный = много слов или есть намеки на несколько сумм
    is_complex = len((m.text or "").split()) > 3 or len(re.findall(r"\d+", m.text or "")) > 1
    
    if has_openai_key() and is_complex:
        # Показываем статус "печатает" (магия...)
        try:
            await m.bot.send_chat_action(m.chat.id, "typing")
        except Exception:
            pass
            
        drafts = await parse_quick_add_ai(m.text)
        if drafts:
            if len(drafts) > 1:
                await state.set_state(QuickAddFlow.batch_confirm)
                await state.update_data(drafts=drafts, quick_started_at=time.time())
                lang = await get_lang(db, m.from_user.id)
                text = await _render_batch_preview(drafts, lang)
                kb = _batch_confirm_kb(lang)
                sent = await m.answer(text, reply_markup=kb, parse_mode="HTML")
                await state.update_data(flow_message_id=sent.message_id)
                return
            else:
                # Один черновик из AI — пробрасываем в обычный флоу
                d = drafts[0]
                await state.set_state(QuickAddFlow.draft)
                await state.update_data(
                    amount=d["amount"],
                    note=d["note"],
                    kind=d["kind"],
                    category_hint=d.get("category_hint"),
                    account_hint=d.get("account_hint"),
                    date_offset=d.get("date_offset", 0),
                    quick_started_at=time.time(),
                )
                await _autopick_if_possible(db, m.from_user.id, state)
                await _autopick_account(db, m.from_user.id, state)
                await _handoff_to_transactions(m, state, db)
                return

    # 2. Если не AI или AI ничего не нашел — используем старый добрый regex
    currency = await get_user_currency(db, m.from_user.id)
    parsed = parse_quick(m.text, currency=currency)
    if not parsed:
        return

    # Bare amount + unknown kind: guided «Доход»/«Расход»
    if parsed.kind is None and not (parsed.note or "").strip():
        await asyncio.sleep(0.05)
        st = await state.get_state()
        if st == IncomeFlow.amount.state:
            await inc_amount(m, state, db)
            return
        if st == ExpenseFlow.amount.state:
            await exp_amount(m, state, db)
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
    currency = await get_user_currency(db, m.from_user.id)
    parsed = parse_quick(arg, currency=currency)
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


@router.callback_query(F.data == "qa:batch:save", QuickAddFlow.batch_confirm)
async def qa_batch_save(c: CallbackQuery, state: FSMContext, db):
    lang = await get_lang(db, c.from_user.id)
    data = await state.get_data()
    drafts = data.get("drafts", [])
    
    if not drafts:
        await c.answer("Drafts empty")
        await state.clear()
        return

    await neutralize_keyboard(c)
    
    # 1. Получаем дефолтный счет и категории для подстраховки
    from app.db.repositories.accounts_repo import get_default_account
    default_acc = await get_default_account(db, c.from_user.id)
    if not default_acc:
        await c.message.answer("Сначала добавь хотя бы один счёт.")
        await state.clear()
        return
    
    acc_id = default_acc[0]
    
    # 2. Сохраняем всё в цикле
    success_count = 0
    for d in drafts:
        kind = d.get("kind", "expense")
        amount = int(d.get("amount", 0))
        note = d.get("note")
        
        # Попытка найти категорию по хинту
        cat_hit = None
        hint = d.get("category_hint")
        if hint:
            cat_hit = await find_category_by_name_ci(db, c.from_user.id, kind, hint)
        
        # Если не нашли - ставим NULL (будет "Без категории")
        cat_id = cat_hit[0] if cat_hit else None

        try:
            if kind == "expense":
                await add_expense_v2(db, c.from_user.id, amount, acc_id, cat_id, note)
            else:
                await add_income(db, c.from_user.id, amount, acc_id, cat_id, note)
            success_count += 1
        except Exception:
            continue

    await db.commit()
    await state.clear()
    
    text = f"✅ <b>Магия сработала!</b>\nДобавлено операций: <b>{success_count}</b>"
    if lang == "en":
        text = f"✅ <b>Magic worked!</b>\nTransactions added: <b>{success_count}</b>"
    elif lang == "kk":
        text = f"✅ <b>Сиқыр орындалды!</b>\nҚосылған операциялар: <b>{success_count}</b>"

    await c.message.answer(text, reply_markup=await build_main_menu_markup(db, c.from_user.id, lang), parse_mode="HTML")
    await c.answer()


@router.callback_query(F.data == "qa:batch:cancel", QuickAddFlow.batch_confirm)
async def qa_batch_cancel(c: CallbackQuery, state: FSMContext, db):
    await cancel_to_main_menu(c, state, db)


# =========================================================
# Helpers
# =========================================================

async def _render_batch_preview(drafts: list[dict], lang: str) -> str:
    title = "🧙‍♂️ <b>Магия AI распознала:</b>"
    if lang == "en": title = "🧙‍♂️ <b>AI Magic parsed:</b>"
    elif lang == "kk": title = "🧙‍♂️ <b>AI сиқыры таныды:</b>"
    
    lines = [title, ""]
    for i, d in enumerate(drafts, 1):
        emoji = "💸" if d["kind"] == "expense" else "💰"
        sign = "-" if d["kind"] == "expense" else "+"
        cat = d.get("category_hint") or "???"
        lines.append(f"{i}. {emoji} {cat}: <b>{sign}{fmt_money(d['amount'])}</b>")
        if d.get("note"):
            lines.append(f"   <i>{d['note']}</i>")
    
    lines.append("")
    footer = "Всё верно? Сохраняем?"
    if lang == "en": footer = "Is everything correct? Save?"
    elif lang == "kk": footer = "Бәрі дұрыс па? Сақтаймыз ба?"
    lines.append(footer)
    
    return "\n".join(lines)


def _batch_confirm_kb(lang: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    
    yes = "✅ Да, сохранить всё"
    no = "❌ Отмена"
    if lang == "en":
        yes, no = "✅ Yes, save all", "❌ Cancel"
    elif lang == "kk":
        yes, no = "✅ Иә, бәрін сақтау", "❌ Бас тарту"
        
    kb.button(text=yes, callback_data="qa:batch:save")
    kb.button(text=no, callback_data="qa:batch:cancel")
    kb.adjust(1)
    return kb.as_markup()


# =========================================================
# Voice Input Handler
# =========================================================

@router.message(F.voice)
async def voice_quick_add(m: Message, state: FSMContext, db):
    """Handle voice messages: transcribe via Whisper, parse via AI, prefill transaction."""
    if not await can_use_feature(db, m.from_user.id, FEATURE_AI):
        await deny_feature_message(m, db, m.from_user.id)
        return

    lang = await get_lang(db, m.from_user.id)

    if not has_openai_key():
        no_key_text = {
            "ru": "⚠️ Голосовой ввод недоступен: не настроен OpenAI API ключ.",
            "en": "⚠️ Voice input unavailable: OpenAI API key not configured.",
            "kk": "⚠️ Дауыстық енгізу қолжетімсіз: OpenAI API кілті орнатылмаған.",
        }
        await m.answer(no_key_text.get(lang, no_key_text["ru"]))
        return

    # Show "recording" chat action while we work
    try:
        await m.bot.send_chat_action(m.chat.id, "upload_voice")
    except Exception:
        pass

    # Download voice file to a temp location
    tmp_path = None
    try:
        voice_file = await m.bot.get_file(m.voice.file_id)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".ogg")
        os.close(tmp_fd)
        await m.bot.download_file(voice_file.file_path, tmp_path)

        # Transcribe
        text = await transcribe_audio_ai(tmp_path)
    except Exception as exc:
        from loguru import logger
        logger.warning("Voice download/transcribe error: {}", exc)
        text = ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not text:
        fail_text = {
            "ru": "😕 Не удалось распознать голосовое сообщение. Попробуйте ещё раз.",
            "en": "😕 Could not recognize the voice message. Please try again.",
            "kk": "😕 Дауыстық хабарламаны тану мүмкін болмады. Қайталап көріңіз.",
        }
        await m.answer(fail_text.get(lang, fail_text["ru"]))
        return

    # Show recognized text
    preview_text = {
        "ru": f'🗣️ Распознано: "<i>{text}</i>"',
        "en": f'🗣️ Recognized: "<i>{text}</i>"',
        "kk": f'🗣️ Танылды: "<i>{text}</i>"',
    }
    await m.answer(preview_text.get(lang, preview_text["ru"]), parse_mode="HTML")

    # Parse via AI
    try:
        await m.bot.send_chat_action(m.chat.id, "typing")
    except Exception:
        pass

    drafts = await parse_quick_add_ai(text)
    if not drafts:
        no_draft_text = {
            "ru": "🤔 Не удалось распознать транзакцию. Попробуйте сказать, например:\n<i>\"Расход 2000 кофе Каспи Купил кофе\"</i>",
            "en": '🤔 Could not parse a transaction. Try saying, e.g.:\n<i>"Expense 2000 coffee Kaspi Bought coffee"</i>',
            "kk": '🤔 Транзакцияны тану мүмкін болмады. Мысалы, айтыңыз:\n<i>"Шығын 2000 кофе Каспи Кофе сатып алдым"</i>',
        }
        await m.answer(no_draft_text.get(lang, no_draft_text["ru"]), parse_mode="HTML")
        return

    # Multiple drafts -> batch confirm
    if len(drafts) > 1:
        await state.set_state(QuickAddFlow.batch_confirm)
        await state.update_data(drafts=drafts, quick_started_at=time.time())
        preview = await _render_batch_preview(drafts, lang)
        kb = _batch_confirm_kb(lang)
        sent = await m.answer(preview, reply_markup=kb, parse_mode="HTML")
        await state.update_data(flow_message_id=sent.message_id)
        return

    # Single draft -> prefill and handoff
    d = drafts[0]
    await state.set_state(QuickAddFlow.draft)
    await state.update_data(
        amount=d["amount"],
        note=d.get("note"),
        kind=d.get("kind", "expense"),
        category_hint=d.get("category_hint"),
        account_hint=d.get("account_hint"),
        date_offset=d.get("date_offset", 0),
        quick_started_at=time.time(),
    )
    await _autopick_if_possible(db, m.from_user.id, state)
    await _autopick_account(db, m.from_user.id, state)
    await _handoff_to_transactions(m, state, db)