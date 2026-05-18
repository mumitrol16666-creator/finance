from app.ui.i18n import t_category

print("Test RU Еда:", t_category("Еда", "ru"))
print("Test EN Еда:", t_category("Еда", "en"))
print("Test KK Еда:", t_category("Еда", "kk"))
print("Test EN Зарплата:", t_category("Зарплата", "en"))
print("Test KK Зарплата:", t_category("Зарплата", "kk"))
print("Test Custom name:", t_category("Custom Cafe", "en"))
print("Test None:", t_category(None, "en"))
