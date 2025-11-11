"""Conversational flow utilities for the Viz data exploration assistant."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .dataset_registry import Dataset, get_dataset, list_datasets


FilterValue = Tuple[str, ...] | str | float | int


@dataclass
class MeasureSpec:
    """Captures the definition of an aggregated metric."""

    column: str
    aggregation: str
    alias: str

    def label(self) -> str:
        """Return a human-friendly label for display and chart legends."""

        readable_agg = self.aggregation.title()
        return f"{readable_agg} of {self.column}"


@dataclass
class AgentState:
    """Represents the mutable state of an interactive session."""

    dataset: Optional[Dataset] = None
    filters: Dict[str, FilterValue] = field(default_factory=dict)
    visualization: Dict[str, object] = field(default_factory=dict)
    dimensions: List[str] = field(default_factory=list)
    measure_specs: List[MeasureSpec] = field(default_factory=list)

    def reset(self) -> None:
        self.dataset = None
        self.filters.clear()
        self.visualization.clear()
        self.dimensions.clear()
        self.measure_specs.clear()


class DataAgent:
    """Implements the multi-step conversational flow described in the spec."""

    def __init__(self) -> None:
        self.state = AgentState()

    # Step 1 - domain selection -------------------------------------------------
    def get_domain_options(self) -> List[str]:
        """Return the list of available dataset names for prompting."""

        return list_datasets()

    def select_dataset(self, dataset_name: str) -> Dataset:
        """Select a dataset and reset stateful filters for a new exploration."""

        dataset = get_dataset(dataset_name)
        self.state.dataset = dataset
        self.state.filters.clear()
        self.state.visualization.clear()
        self.state.dimensions.clear()
        self.state.measure_specs.clear()
        return dataset

    # Step 2 - data slicing -----------------------------------------------------
    def suggest_filters(self) -> List[str]:
        """Suggest filter prompts based on the active dataset schema."""

        dataset = self._require_dataset()
        suggestions: List[str] = []
        for column in dataset.columns:
            if column.role == "temporal":
                suggestions.append(f"Filter by {column.name} date range")
            elif column.role == "category":
                suggestions.append(f"Filter by {column.name} category")
            elif column.role == "measure":
                suggestions.append(f"Filter by {column.name} numeric range")
        return suggestions

    def add_filter(self, column_name: str, value: FilterValue) -> None:
        """Record a conversational filter selection."""

        dataset = self._require_dataset()
        column_names = {column.name for column in dataset.columns}
        if column_name not in column_names:
            raise ValueError(
                f"Column '{column_name}' is not available on dataset '{dataset.name}'."
            )
        self.state.filters[column_name] = value

    def build_where_clause(self) -> str:
        """Construct a SQL WHERE clause for the collected filters."""

        if not self.state.filters:
            return ""

        clauses: List[str] = []
        for column, value in self.state.filters.items():
            if isinstance(value, tuple):
                if len(value) == 2:
                    clauses.append(f"{column} BETWEEN '{value[0]}' AND '{value[1]}'")
                else:
                    quoted = ", ".join(f"'{item}'" for item in value)
                    clauses.append(f"{column} IN ({quoted})")
            elif isinstance(value, str):
                clauses.append(f"{column} = '{value}'")
            else:
                clauses.append(f"{column} = {value}")
        return " WHERE " + " AND ".join(clauses)

    def build_sql_query(self, limit: int = 100) -> str:
        """Return a SQL statement that reflects the current state."""

        dataset = self._require_dataset()
        where_clause = self.build_where_clause()

        if self.state.measure_specs:
            select_parts: List[str] = []
            if self.state.dimensions:
                select_parts.extend(self.state.dimensions)

            for spec in self.state.measure_specs:
                select_parts.append(f"{spec.aggregation}({spec.column}) AS {spec.alias}")

            select_clause = ", ".join(select_parts) if select_parts else "*"
            group_clause = (
                f" GROUP BY {', '.join(self.state.dimensions)}" if self.state.dimensions else ""
            )
            order_clause = (
                f" ORDER BY {', '.join(self.state.dimensions)}" if self.state.dimensions else ""
            )
            return (
                f"SELECT {select_clause} FROM {dataset.table}{where_clause}{group_clause}{order_clause}"
                f" LIMIT {limit};"
            )

        order_clause = f" ORDER BY {dataset.default_order_by}" if dataset.default_order_by else ""
        return f"SELECT * FROM {dataset.table}{where_clause}{order_clause} LIMIT {limit};"

    # Step 3 - data enrichment ---------------------------------------------------
    def suggest_enrichments(self) -> List[str]:
        """Suggest related datasets for potential joins."""

        dataset = self._require_dataset()
        if not dataset.related:
            return []
        return [f"Compare with {related}" for related in dataset.related]

    # Step 4 - visualization -----------------------------------------------------
    def set_visualization(
        self,
        chart_type: str,
        x_fields: List[str],
        y_measures: List[str],
        breakdowns: Optional[List[str]] = None,
        options: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        """Persist the visualization selection for downstream rendering."""

        dataset = self._require_dataset()
        allowed_columns = {column.name for column in dataset.columns}

        if not x_fields:
            raise ValueError("At least one dimension must be provided for the X axis.")
        if not y_measures:
            raise ValueError(
                "Specify at least one measure for the Y axis (e.g. 'sum:monthly_spend')."
            )

        invalid_dims = [column for column in x_fields if column not in allowed_columns]
        if invalid_dims:
            raise ValueError(
                f"Unknown dimension columns: {', '.join(invalid_dims)} on dataset '{dataset.name}'."
            )

        breakdowns = breakdowns or []
        invalid_breakdowns = [column for column in breakdowns if column not in allowed_columns]
        if invalid_breakdowns:
            raise ValueError(
                f"Unknown breakdown columns: {', '.join(invalid_breakdowns)} on dataset '{dataset.name}'."
            )

        measure_specs: List[MeasureSpec] = []
        existing_aliases: set[str] = set()
        allowed_aggs = {"sum", "avg", "count", "min", "max"}

        for raw in y_measures:
            if ":" in raw:
                agg, column = [item.strip() for item in raw.split(":", 1)]
            else:
                agg, column = "sum", raw.strip()

            if column not in allowed_columns:
                raise ValueError(
                    f"Column '{column}' is not available on dataset '{dataset.name}'."
                )

            agg_lower = agg.lower()
            if agg_lower not in allowed_aggs:
                raise ValueError(
                    "Aggregation must be one of 'sum', 'avg', 'count', 'min', or 'max'."
                )

            alias_base = f"{agg_lower}_{column}"
            alias = alias_base
            counter = 2
            while alias in existing_aliases:
                alias = f"{alias_base}_{counter}"
                counter += 1

            measure_specs.append(
                MeasureSpec(column=column, aggregation=agg_lower.upper(), alias=alias)
            )
            existing_aliases.add(alias)

        merged_dimensions = list(dict.fromkeys([*x_fields, *breakdowns]))

        spec: Dict[str, object] = {
            "chart_type": chart_type,
            "x_fields": x_fields,
            "y_measures": [spec.alias for spec in measure_specs],
            "breakdowns": breakdowns,
        }
        if options:
            spec["options"] = options

        self.state.visualization = spec
        self.state.dimensions = merged_dimensions
        self.state.measure_specs = measure_specs
        return spec

    def get_visualization(self) -> Dict[str, object]:
        """Return the persisted visualization specification."""

        return dict(self.state.visualization)

    # Step 5 - summary -----------------------------------------------------------
    def describe_state(self) -> Dict[str, object]:
        """Return a JSON-serialisable representation of the current session."""

        dataset = self._require_dataset()
        return {
            "dataset": dataset.name,
            "filters": dict(self.state.filters),
            "visualization": dict(self.state.visualization),
            "dimensions": list(self.state.dimensions),
            "metrics": [
                {
                    "column": spec.column,
                    "aggregation": spec.aggregation,
                    "alias": spec.alias,
                }
                for spec in self.state.measure_specs
            ],
            "sql": self.build_sql_query(),
        }

    # Utilities -----------------------------------------------------------------
    def _require_dataset(self) -> Dataset:
        if not self.state.dataset:
            raise RuntimeError("A dataset must be selected before performing this operation.")
        return self.state.dataset


def demo() -> Dict[str, object]:
    """Demonstrate a simple end-to-end flow for documentation and testing."""

    agent = DataAgent()
    agent.select_dataset("subscribers")
    agent.add_filter("join_date", ("2025-10-01", "2025-11-01"))
    agent.add_filter("region", "India")
    agent.add_filter("plan_type", "Premium")
    agent.set_visualization(
        chart_type="bar",
        x_fields=["region", "plan_type"],
        y_measures=["sum:monthly_spend"],
        breakdowns=["status"],
    )
    return agent.describe_state()


if __name__ == "__main__":
    import json

    print(json.dumps(demo(), indent=2))
