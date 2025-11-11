"""Command-line chatbot that orchestrates the Viz conversational data agent."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .data_agent import DataAgent
from .dataset_registry import Dataset
from .database import execute_query, initialise_database
from .visualization import render_chart


class ConversationStage(enum.Enum):
    GREETING = "greeting"
    DATASET = "dataset"
    FILTERS = "filters"
    VISUALISATION = "visualisation"
    SUMMARY = "summary"
    ADJUST = "adjust"


@dataclass
class ConversationContext:
    agent: DataAgent = field(default_factory=DataAgent)
    stage: ConversationStage = ConversationStage.GREETING
    chart_path: Optional[Path] = None


class ChatSession:
    """Very small rule-based dialogue manager for the demo CLI."""

    def __init__(self) -> None:
        initialise_database()
        self.context = ConversationContext()

    # Public API -----------------------------------------------------------------
    def start(self) -> str:
        self.context.stage = ConversationStage.DATASET
        options = ", ".join(self.context.agent.get_domain_options())
        return (
            "👋 Hi! I can help you explore your metrics.\n"
            "Pick a dataset to begin (type the name):\n"
            f"→ {options}\n"
            "Type 'help' for guidance or 'quit' to exit."
        )

    def handle_input(self, message: str) -> str:
        text = message.strip()
        if not text:
            return "I didn't catch that. Please type something."

        lowered = text.lower()
        if lowered in {"quit", "exit"}:
            return "Goodbye!"
        if lowered in {"help", "?"}:
            return self._help_message()
        if lowered in {"reset", "restart"}:
            self.context = ConversationContext()
            return self.start()

        stage = self.context.stage
        if stage == ConversationStage.DATASET:
            return self._handle_dataset_selection(text)
        if stage == ConversationStage.FILTERS:
            return self._handle_filtering(text)
        if stage == ConversationStage.VISUALISATION:
            return self._handle_visualisation(text)
        if stage == ConversationStage.SUMMARY:
            return self._handle_summary_follow_up(text)
        if stage == ConversationStage.ADJUST:
            return self._handle_adjustment(text)
        return "Let's begin by choosing a dataset."

    # Internal handlers -----------------------------------------------------------
    def _handle_dataset_selection(self, text: str) -> str:
        dataset_name = self._match_dataset(text)
        if not dataset_name:
            options = ", ".join(self.context.agent.get_domain_options())
            return (
                "I couldn't find that dataset.\n"
                f"Available options: {options}.\n"
                "Please type one of the dataset names."
            )

        dataset = self.context.agent.select_dataset(dataset_name)
        self.context.stage = ConversationStage.FILTERS
        suggestions = self.context.agent.suggest_filters()
        enrichment = self.context.agent.suggest_enrichments()
        suggestion_text = "\n".join(f"• {item}" for item in suggestions) or "• No predefined filters"
        enrichment_text = (
            "\nRelated datasets you can mention later: " + ", ".join(enrichment)
        ) if enrichment else ""
        return (
            f"Great! We'll explore **{dataset.name}**.\n"
            "You can add filters in the form `column=value` or `column between start and end`.\n"
            "Type 'done' when you're ready to move on.\n"
            f"Suggested filters:\n{suggestion_text}{enrichment_text}"
        )

    def _handle_filtering(self, text: str) -> str:
        lowered = text.lower()
        if lowered in {"done", "next", "visual"}:
            self.context.stage = ConversationStage.VISUALISATION
            return self._visualisation_prompt()

        parsed = self._parse_filter(text)
        if not parsed:
            return (
                "I didn't understand that filter.\n"
                "Use `column=value`, `column=value1,value2`, or `column between start and end`.\n"
                "Type 'done' when finished."
            )

        column, value = parsed
        try:
            self.context.agent.add_filter(column, value)
        except ValueError as exc:  # invalid column name
            return str(exc)

        filters = self.context.agent.state.filters
        filter_lines = "\n".join(f"• {key}: {val}" for key, val in filters.items())
        return (
            f"Added filter on **{column}**. Current filters:\n{filter_lines or '• (none)'}\n"
            "Add another filter or type 'done' to continue."
        )

    def _handle_visualisation(self, text: str) -> str:
        parsed = self._parse_visualisation(text)
        if not parsed:
            return (
                "Let's describe the chart. Use `chart=bar x=region,plan_type y=sum:monthly_spend,avg:login_count"
                " breakdowns=status`.\n"
                "Available chart types: bar, line, pie, heatmap, custom."
            )

        try:
            self.context.agent.set_visualization(**parsed)
        except ValueError as exc:
            return str(exc)

        self.context.stage = ConversationStage.SUMMARY
        return self._summarise_results()

    def _handle_summary_follow_up(self, text: str) -> str:
        lowered = text.lower()
        if lowered in {"again", "restart", "reset", "new"}:
            self.context = ConversationContext()
            return self.start()
        return self._handle_adjustment(text)

    def _handle_adjustment(self, text: str) -> str:
        lowered = text.lower()
        if lowered in {"again", "restart", "reset", "new"}:
            self.context = ConversationContext()
            return self.start()
        if lowered in {"refresh", "show", "show chart", "render", "update"}:
            return self._summarise_results()
        if any(token in lowered for token in {"chart=", "x=", "y=", "metrics=", "dimensions=", "breakdowns="}):
            self.context.stage = ConversationStage.VISUALISATION
            return self._handle_visualisation(text)
        if lowered.startswith("filter "):
            filter_text = text.split(" ", 1)[1]
            parsed = self._parse_filter(filter_text)
            if not parsed:
                return (
                    "I couldn't understand that filter tweak. Use `filter column=value` or"
                    " `filter column between start and end`."
                )
            column, value = parsed
            try:
                self.context.agent.add_filter(column, value)
            except ValueError as exc:
                return str(exc)
            acknowledgement = f"Added filter on **{column}**. Regenerating summary…\n"
            return acknowledgement + self._summarise_results()
        if lowered == "filters":
            filters = self.context.agent.state.filters
            filter_lines = "\n".join(f"• {key}: {val}" for key, val in filters.items()) or "• (none)"
            return f"Current filters:\n{filter_lines}\nType `filter column=value` to add more or `restart` to reset."
        if lowered == "chart":
            if not self.context.chart_path:
                return "No chart has been generated yet. Try `refresh` first."
            return f"The latest chart is saved at: {self.context.chart_path}"
        return (
            "You can tweak the chart with commands like `chart=bar x=region y=sum:monthly_spend`.\n"
            "Use `filter column=value` to refine data, `refresh` to regenerate,"
            " or 'restart' to begin again."
        )

    # Helpers --------------------------------------------------------------------
    def _match_dataset(self, text: str) -> Optional[str]:
        options = {name.lower(): name for name in self.context.agent.get_domain_options()}
        words = re.split(r"[^a-z0-9_]+", text.lower())
        for word in words:
            if word in options:
                return options[word]
        if text.lower() in options:
            return options[text.lower()]
        return None

    def _parse_filter(self, text: str) -> Optional[Tuple[str, object]]:
        dataset = self.context.agent.state.dataset
        if not dataset:
            return None

        between_pattern = re.compile(
            r"(?P<column>[a-zA-Z_][\w]*)\s+between\s+(?P<start>[^\s]+)\s+and\s+(?P<end>[^\s]+)",
            re.IGNORECASE,
        )
        match = between_pattern.search(text)
        if match:
            column = match.group("column")
            start = match.group("start")
            end = match.group("end")
            return column, self._cast_value(dataset, column, (start, end))

        if "=" in text:
            column, raw_value = [part.strip() for part in text.split("=", 1)]
        elif ":" in text:
            column, raw_value = [part.strip() for part in text.split(":", 1)]
        else:
            return None

        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        if not values:
            return None
        if len(values) == 1:
            value: object = self._cast_value(dataset, column, values[0])
        else:
            value = tuple(self._cast_value(dataset, column, item) for item in values)
        return column, value

    def _cast_value(self, dataset: Dataset, column_name: str, value: object) -> object:
        column = next((col for col in dataset.columns if col.name == column_name), None)
        if not column:
            return value

        if isinstance(value, tuple):
            return tuple(self._cast_value(dataset, column_name, item) for item in value)

        if column.type == "numeric":
            try:
                if "." in str(value):
                    return float(value)
                return int(value)
            except ValueError:
                return value
        return value

    def _parse_visualisation(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        parts = re.findall(r"([a-z_]+)\s*=\s*([^\s]+)", text.lower())
        if not parts:
            return None

        parameters: Dict[str, Optional[str]] = {key: value for key, value in parts}
        chart_type = parameters.get("chart") or parameters.get("type")
        x_value = parameters.get("x") or parameters.get("dimensions")
        y_value = parameters.get("y") or parameters.get("metrics")
        if not chart_type or not x_value or not y_value:
            return None

        if chart_type not in {"bar", "line", "pie", "heatmap", "custom"}:
            return None

        x_fields = [item.strip() for item in x_value.split(",") if item.strip()]
        y_measures = [item.strip() for item in y_value.split(",") if item.strip()]
        breakdown_value = parameters.get("breakdowns") or parameters.get("group_by")
        breakdowns = (
            [item.strip() for item in breakdown_value.split(",") if item.strip()]
            if breakdown_value
            else []
        )
        recognised_keys = {
            "chart",
            "type",
            "x",
            "dimensions",
            "y",
            "metrics",
            "breakdowns",
            "group_by",
        }
        options = {
            key: value
            for key, value in parameters.items()
            if key not in recognised_keys
        }

        payload: Dict[str, object] = {
            "chart_type": chart_type,
            "x_fields": x_fields,
            "y_measures": y_measures,
        }
        if breakdowns:
            payload["breakdowns"] = breakdowns
        if options:
            payload["options"] = options
        return payload

    def _visualisation_prompt(self) -> str:
        dataset = self.context.agent.state.dataset
        columns = ", ".join(column.name for column in dataset.columns) if dataset else ""
        return (
            "Great, let's design a chart.\n"
            f"Available columns: {columns}.\n"
            "Try something like `chart=bar x=region,plan_type y=sum:monthly_spend,avg:login_count"
            " breakdowns=status`.\n"
            "You can also set options such as `style=stacked`."
        )

    def _summarise_results(self) -> str:
        summary = self.context.agent.describe_state()
        sql = summary["sql"]
        rows = execute_query(sql)
        preview = self._format_preview(rows)

        metrics = summary.get("metrics", [])
        metrics_text = (
            ", ".join(
                f"{item['aggregation']}({item['column']}) → {item['alias']}"
                for item in metrics
            )
            or "(none)"
        )
        dimensions_text = ", ".join(summary.get("dimensions", [])) or "(none)"
        filters = summary.get("filters", {})
        filter_lines = (
            "\n".join(f"• {key}: {value}" for key, value in filters.items())
            if filters
            else "• (none)"
        )

        viz = summary.get("visualization", {})
        chart_info = ""
        render_error: Optional[str] = None
        measure_specs = [
            {
                "alias": spec.alias,
                "label": spec.label(),
                "column": spec.column,
                "aggregation": spec.aggregation,
            }
            for spec in self.context.agent.state.measure_specs
        ]
        try:
            chart_path = render_chart(
                rows,
                chart_type=str(viz.get("chart_type", "bar")),
                x_fields=[str(field) for field in viz.get("x_fields", [])],
                breakdowns=[str(field) for field in viz.get("breakdowns", [])],
                measures=measure_specs,
            )
        except Exception as exc:  # pragma: no cover - visualisation safety
            chart_path = None
            render_error = str(exc)

        if render_error:
            self.context.chart_path = None
            chart_info = f"⚠️ Unable to render chart: {render_error}"
        elif chart_path:
            self.context.chart_path = chart_path
            chart_info = f"Chart saved to: {chart_path}"
        else:
            self.context.chart_path = None
            chart_info = "No chart generated (no result rows or metrics)."

        self.context.stage = ConversationStage.ADJUST

        return (
            "Here's the summary of your exploration:\n"
            f"Dataset: {summary['dataset']}\n"
            f"Filters:\n{filter_lines}\n"
            f"Dimensions: {dimensions_text}\n"
            f"Metrics: {metrics_text}\n"
            f"Visualization: {viz}\n"
            f"SQL: {sql}\n\n"
            f"Top rows:\n{preview}\n\n"
            f"{chart_info}\n"
            "Type commands like `chart=...` to adjust, `filter column=value` to refine,"
            " `refresh` to re-run, or 'restart' to start over."
        )

    def _format_preview(self, rows: List[Dict[str, object]], max_rows: int = 5) -> str:
        if not rows:
            return "(no results)"

        truncated = rows[:max_rows]
        columns = list(truncated[0].keys())
        widths: Dict[str, int] = {}
        for column in columns:
            cell_lengths = [len(str(row[column])) for row in truncated]
            widths[column] = max(len(column), *(cell_lengths or [0]))

        header = " | ".join(column.ljust(widths[column]) for column in columns)
        separator = "-+-".join("-" * widths[column] for column in columns)
        lines = [header, separator]
        for row in truncated:
            line = " | ".join(str(row[column]).ljust(widths[column]) for column in columns)
            lines.append(line)
        if len(rows) > max_rows:
            lines.append(f"… ({len(rows) - max_rows} more rows)")
        return "\n".join(lines)

    def _help_message(self) -> str:
        return (
            "Workflow overview:\n"
            "1. Pick a dataset by typing its name.\n"
            "2. Add filters using `column=value` or `column between start and end`.\n"
            "3. Type 'done' to design a chart with commands like `chart=bar x=region,plan_type"
            " y=sum:monthly_spend`.\n"
            "4. Review the summary, open the generated chart image, and tweak using `chart=...`,"
            " `filter ...`, or `refresh`.\n"
            "Commands: 'help', 'reset', 'restart', 'quit'."
        )


def run_cli() -> None:
    """Entry point for `python -m src.chatbot`."""

    session = ChatSession()
    print(session.start())
    while True:
        try:
            message = input("You: ")
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - CLI convenience
            print("\nGoodbye!")
            break

        response = session.handle_input(message)
        print(f"Bot: {response}")
        if response.strip().lower() == "goodbye!":
            break


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    run_cli()

