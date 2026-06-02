import os
from app.domain.services.chart_service import draw_expense_donut_chart

# Create a test list of categories (name, emoji, total)
test_cats = [
    ("Продукты", "🍕", 15000),
    ("Транспорт", "🚕", 8000),
    ("Дом", "🏠", 22000),
    ("Развлечения", "🍿", 5500),
    ("Здоровье", "💊", 3000),
    ("Одежда", "👕", 4500),
    ("Обучение", "📚", 1200),
]

expense_total = sum(row[2] for row in test_cats)
formatted_total = "59 200 ₸"

print("Generating chart...")
chart_buf = draw_expense_donut_chart(test_cats, expense_total, formatted_total, lang="ru")

# Save to scratch/sample_chart.png
output_dir = "scratch"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "sample_chart.png")

with open(output_path, "wb") as f:
    f.write(chart_buf.getvalue())

print(f"Chart successfully saved to {output_path}!")
