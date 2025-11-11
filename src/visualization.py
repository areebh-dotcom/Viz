"""Utility helpers for rendering charts from aggregated chatbot results."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

try:  # pragma: no cover - optional dependency
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    matplotlib = None
    plt = None
    MaxNLocator = None

CHART_DIR = Path(__file__).resolve().parent.parent / "data" / "charts"


def _compose_labels(rows: List[Dict[str, object]], fields: List[str]) -> List[str]:
    labels: List[str] = []
    for row in rows:
        parts = [str(row.get(field, "")) for field in fields if row.get(field) is not None]
        label = " | ".join(part for part in parts if part) or "All"
        labels.append(label)
    return labels


def _as_numeric(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def render_chart(
    rows: List[Dict[str, object]],
    chart_type: str,
    x_fields: List[str],
    breakdowns: List[str],
    measures: List[Dict[str, str]],
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Render a static chart image and return the saved path.

    Parameters
    ----------
    rows:
        Result rows returned from executing the generated SQL query.
    chart_type:
        Requested chart type (bar, line, pie, heatmap, custom).
    x_fields:
        Ordered list of dimension columns used to build the X-axis labels.
    breakdowns:
        Additional categorical columns that expand the X-axis labels or heatmap pivots.
    measures:
        Sequence of measure definitions containing ``alias`` and ``label`` keys.
    output_dir:
        Optional custom directory for persisted chart images.
    """

    if plt is None or MaxNLocator is None:
        raise RuntimeError(
            "Matplotlib is required to render charts. Install it with `pip install matplotlib`."
        )

    if not rows or not measures:
        return None

    output_dir = output_dir or CHART_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    label_fields = [*x_fields, *breakdowns]
    labels = _compose_labels(rows, label_fields)

    data_by_measure: Dict[str, List[float]] = {}
    label_map: Dict[str, str] = {}
    for measure in measures:
        alias = measure["alias"]
        label_map[alias] = measure.get("label", alias)
        data_by_measure[alias] = [_as_numeric(row.get(alias)) for row in rows]

    filename = f"chart_{chart_type}_{uuid4().hex[:8]}.png"
    chart_path = (output_dir / filename).resolve()

    normalised_type = chart_type.lower()

    if normalised_type == "pie" and len(measures) == 1:
        alias = measures[0]["alias"]
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(
            data_by_measure[alias],
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
        )
        ax.set_title(label_map[alias])
        fig.tight_layout()
        fig.savefig(chart_path, dpi=150)
        plt.close(fig)
        return chart_path

    if normalised_type == "heatmap" and (breakdowns or len(x_fields) > 1):
        row_field = x_fields[0] if x_fields else breakdowns[0]
        col_field = breakdowns[0] if breakdowns else (x_fields[1] if len(x_fields) > 1 else None)
        if row_field and col_field:
            row_labels = sorted({str(row.get(row_field)) for row in rows})
            col_labels = sorted({str(row.get(col_field)) for row in rows})
            alias = measures[0]["alias"]
            matrix = [
                [
                    _as_numeric(
                        next(
                            (
                                row.get(alias)
                                for row in rows
                                if str(row.get(row_field)) == r_value
                                and str(row.get(col_field)) == c_value
                            ),
                            0.0,
                        )
                    )
                    for c_value in col_labels
                ]
                for r_value in row_labels
            ]
            fig, ax = plt.subplots(figsize=(6, 4))
            image = ax.imshow(matrix, aspect="auto", cmap="Blues")
            ax.set_xticks(range(len(col_labels)), labels=[str(item) for item in col_labels], rotation=45, ha="right")
            ax.set_yticks(range(len(row_labels)), labels=[str(item) for item in row_labels])
            ax.set_title(label_map[alias])
            fig.colorbar(image, ax=ax)
            fig.tight_layout()
            fig.savefig(chart_path, dpi=150)
            plt.close(fig)
            return chart_path

    indices = list(range(len(labels)))
    fig_width = max(6.0, len(labels) * 0.8)
    fig_height = 4.0 + max(0, len(measures) - 1) * 0.6
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    if normalised_type == "line":
        for measure in measures:
            alias = measure["alias"]
            ax.plot(indices, data_by_measure[alias], marker="o", label=label_map[alias])
    else:
        bar_width = 0.8 / max(1, len(measures))
        for idx, measure in enumerate(measures):
            alias = measure["alias"]
            offsets = [i + (idx - (len(measures) - 1) / 2) * bar_width for i in indices]
            ax.bar(offsets, data_by_measure[alias], width=bar_width, label=label_map[alias])
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    ax.set_xticks(indices, labels=labels, rotation=45, ha="right")
    ax.set_ylabel(
        ", ".join(label_map[measure["alias"]] for measure in measures)
        if len(measures) == 1
        else "Values"
    )
    ax.set_title(chart_type.title())
    if len(measures) > 1:
        ax.legend()
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)
    return chart_path
