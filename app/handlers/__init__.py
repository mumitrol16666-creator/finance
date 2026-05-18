from app.handlers.common import router as common_router
from app.handlers.onboarding import router as onboarding_router
from app.handlers.transactions import router as transactions_router
from app.handlers.reports import router as reports_router
from app.handlers.history import router as history_router
from app.handlers.settings_categories_limits import router as settings_categories_limits_router
from app.handlers.settings import router as settings_router
from app.handlers.lang import router as lang_router
from app.handlers.quick_add import router as quick_add_router
from app.handlers.budgets import router as budgets_router
from app.handlers.debts import router as debts_router
from app.handlers.ai_consultant import router as ai_consultant_router
from app.handlers.recurring_expenses import router as recurring_expenses_router
from app.handlers.recurring_incomes import router as recurring_incomes_router
from app.handlers.planned import router as planned_router
from app.handlers.planning_smart import router as planning_smart_router
from app.handlers.export import router as export_router
from app.handlers.charts import router as charts_router

def get_routers():
    return [
        common_router,
        onboarding_router,
        debts_router,
        ai_consultant_router,
        recurring_expenses_router,
        recurring_incomes_router,
        planned_router,
        planning_smart_router,
        transactions_router,
        settings_categories_limits_router,
        budgets_router,
        reports_router,
        history_router,
        export_router,
        charts_router,
        settings_router,
        lang_router,
        quick_add_router,
    ]
