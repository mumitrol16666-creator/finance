import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from app.ui.i18n import t_category

# Colors matching the premium dark theme
CHART_BG_COLOR = "#0B0F19"
TEXT_COLOR = "#F8FAFC"
COLORS = [
    "#3B82F6",  # blue
    "#10B981",  # emerald
    "#F59E0B",  # amber
    "#EF4444",  # red
    "#8B5CF6",  # violet
    "#06B6D4",  # cyan
    "#EC4899",  # pink
    "#14B8A6",  # teal
    "#F43F5E",  # rose
    "#64748B"   # slate (for Other)
]

def draw_expense_donut_chart(
    cats: list[tuple[str | None, str | None, int]],
    expense_total: int,
    formatted_total: str,
    lang: str = "ru"
) -> io.BytesIO:
    """Draw a beautiful donut chart of top categories using matplotlib.
    Groups categories after index 4 (top 5) into 'Other'.
    Returns a BytesIO containing the PNG image bytes.
    """
    labels = []
    sizes = []
    
    top_n = 5
    other_total = 0
    
    for i, row in enumerate(cats):
        name, emoji, total = row[0], row[1], row[2]
        val = int(total or 0)
        if val <= 0:
            continue
            
        if i < top_n:
            translated_name = t_category((name or "").strip(), lang) or name or ""
            labels.append(translated_name)
            sizes.append(val)
        else:
            other_total += val
            
    if other_total > 0:
        other_label = {
            "ru": "Другое",
            "en": "Other",
            "kk": "Басқа"
        }.get(lang, "Другое")
        labels.append(other_label)
        sizes.append(other_total)

    if not sizes:
        # Fallback if no sizes
        labels.append("No data")
        sizes.append(1)

    # Setup matplotlib plot
    fig, ax = plt.subplots(figsize=(6, 5), dpi=180, facecolor=CHART_BG_COLOR)
    ax.set_facecolor(CHART_BG_COLOR)

    # Plot donut chart
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct='%1.1f%%',
        startangle=90,
        colors=COLORS[:len(sizes)],
        textprops=dict(color=TEXT_COLOR, fontsize=9, fontweight='bold'),
        pctdistance=0.75,
        wedgeprops=dict(width=0.35, edgecolor=CHART_BG_COLOR, linewidth=2)  # Creates the donut hole
    )

    # Clean text colors
    for text in texts:
        text.set_color(TEXT_COLOR)
        text.set_fontsize(9)
    for autotext in autotexts:
        autotext.set_color(TEXT_COLOR)
        autotext.set_fontsize(8)

    # Center text inside the donut hole
    center_title = {
        "ru": "Расход",
        "en": "Expense",
        "kk": "Шығыс"
    }.get(lang, "Расход")
    
    ax.text(
        0, 0, f"{center_title}\n{formatted_total}",
        ha='center', va='center',
        color=TEXT_COLOR,
        fontsize=12, fontweight='bold',
        linespacing=1.3
    )

    ax.axis('equal')  
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    buf.seek(0)
    
    plt.close(fig)
    return buf
