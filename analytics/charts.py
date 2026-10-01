import io
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analytics.market_stats import get_neighborhood_stats

def generate_neighborhood_price_chart() -> io.BytesIO | None:
    """Generating diagram showing average price per square meter in Osijek."""
    stats = get_neighborhood_stats()
    if not stats:
        return None

    valid_stats = [s for s in stats if s.get("avg_sqm_price")]
    if not valid_stats:
        return None

    valid_stats.sort(key=lambda x: x["avg_sqm_price"])

    neighborhoods = [s["neighborhood"] for s in valid_stats]
    sqm_prices = [s["avg_sqm_price"] for s in valid_stats]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(neighborhoods, sqm_prices, color="#2ecc71", edgecolor="#27ae60", height=0.6)

    ax.set_xlabel("Prosječna cijena (€/m²)", fontsize=11, fontweight="bold")
    ax.set_title("Usporedba prosječne cijene najma po m² u Osijeku", fontsize=13, fontweight="bold", pad=15)
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + 0.15,
            bar.get_y() + bar.get_height() / 2,
            f"{width:.2f} €/m²",
            va="center",
            ha="left",
            fontsize=9,
            fontweight="bold"
        )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=200)
    buf.seek(0)
    plt.close(fig)

    return buf