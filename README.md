# Viz

A lightweight prototype of a conversational data exploration agent. The agent follows the
multi-step flow described in the product spec:

1. **Domain selection** – surface available datasets sourced from `src/dataset_registry.py`.
2. **Data slicing** – suggest filters based on column metadata and build SQL clauses with
   the collected selections.
3. **Data enrichment** – recommend related datasets for potential comparisons and joins.
4. **Visualization setup** – capture the user's preferred chart configuration for a
   downstream renderer.
5. **Output** – expose the current dataset, filters, visualization spec, and SQL query as a
   serialisable payload for the UI.

## Running the end-to-end chatbot

An interactive chatbot is available via the module `src.chatbot`. It guides you through the
full workflow, executes the generated SQL against an on-disk SQLite database, and prints a
preview table of the results. Each run now also generates a chart image (saved beneath
`data/charts/`) so you can iterate on multi-dimensional visuals directly from the CLI.

```bash
python -m src.chatbot
```

> **Note:** Chart rendering requires [Matplotlib](https://matplotlib.org/). Install it with
> `pip install matplotlib` if it is not already available in your Python environment.

Example session:

```
👋 Hi! I can help you explore your metrics.
Pick a dataset to begin (type the name):
→ business_units, logins, payments, subscribers, tickets
Type 'help' for guidance or 'quit' to exit.
You: subscribers
Bot: Great! We'll explore **subscribers**.
You: join_date between 2025-08-01 and 2025-10-15
Bot: Added filter on **join_date**. Current filters:
• join_date: ('2025-08-01', '2025-10-15')
Add another filter or type 'done' to continue.
You: done
Bot: Great, let's design a chart.
You: chart=bar x=region,plan_type y=sum:monthly_spend breakdowns=status
Bot: Here's the summary of your exploration:
Dataset: subscribers
Filters:
• join_date: ('2025-08-01', '2025-10-15')
Dimensions: region, plan_type, status
Metrics: SUM(monthly_spend) → sum_monthly_spend
Visualization: {'chart_type': 'bar', 'x_fields': ['region', 'plan_type'], 'y_measures': ['sum_monthly_spend'], 'breakdowns': ['status']}
SQL: SELECT region, plan_type, status, SUM(monthly_spend) AS sum_monthly_spend FROM subscribers WHERE join_date BETWEEN '2025-08-01' AND '2025-10-15' GROUP BY region, plan_type, status ORDER BY region, plan_type, status LIMIT 100;

Top rows:
region         | plan_type | status | sum_monthly_spend
----------------+-----------+--------+-------------------
India          | Premium   | paused | 119.0
North America  | Premium   | active | 129.0

Chart saved to: data/charts/chart_bar_<id>.png
Type commands like `chart=...` to adjust, `filter column=value` to refine, `refresh` to re-run, or 'restart' to start over.
```

The CLI persists your selections across turns, suggests filters, keeps track of a
multi-field visualization specification, and regenerates the chart image whenever you tweak
dimensions, breakdowns, metrics, or filters. Open the saved PNG files with any image viewer
to inspect the multi-series output side by side with the CLI transcript.

## Sample database

The SQLite database is stored at `data/viz.db`. When the chatbot starts it will automatically
create the required tables (subscribers, payments, logins, tickets, business_units) and fill
them with illustrative dummy rows. You can inspect the data manually from a Python shell:

```python
from src.database import list_rows

list_rows("subscribers")
```

The agent's SQL output can therefore be executed locally without any additional setup.

## Programmatic usage

The original `DataAgent` object remains available for integration tests and custom flows. The
module exposes a `demo()` helper which you can invoke directly:

```bash
python -m src.data_agent
```
