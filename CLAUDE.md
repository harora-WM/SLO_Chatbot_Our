# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run the application
streamlit run app.py

# Run tests
python test_system.py

# Inspect database
python check_data.py

# Debug OpenSearch
python debug_opensearch.py
```

## Architecture Overview

This is a conversational SLO (Service Level Objective) chatbot using **Claude Sonnet 4.5 via AWS Bedrock**. The system analyzes service and error logs using a **function calling architecture** where Claude has access to 14 analytics functions.

### Core Data Flow

```
OpenSearch → DataLoader → DuckDB → Analytics Functions → Claude → User
```

**Critical architectural decision**: This system uses **DuckDB (OLAP)** instead of vector databases because SLO data is highly structured with time-series metrics (error_rate, response_time, request_count). Structured data benefits from SQL aggregations, not semantic search.

### Component Layers

1. **Data Layer** (`data/`)
   - `data_loader.py`: Parses OpenSearch JSON responses into pandas DataFrames
   - `opensearch_client.py`: Queries OpenSearch with Scroll API support for >10k results
   - `duckdb_manager.py`: OLAP database for fast analytical queries

2. **Analytics Layer** (`analytics/`)
   - `slo_calculator.py`: SLI/SLO metrics, error budgets, burn rates
   - `degradation_detector.py`: Detects services with declining performance over time windows
   - `trend_analyzer.py`: Predictive analysis using linear regression
   - `metrics.py`: Aggregated metrics (top services, slowest services, etc.)

3. **Agent Layer** (`agent/`)
   - `claude_client.py`: AWS Bedrock integration with message history
   - `function_tools.py`: 14 analytics functions exposed to Claude via tool calling

4. **UI Layer**
   - `app.py`: Streamlit web interface with dashboard and chat tabs

## Critical Code Patterns

### NaN Handling Pattern

**ALWAYS** use `pd.notna()` checks before converting to integers. This is critical throughout the codebase:

```python
# ❌ WRONG - Will crash on NaN
total_requests = int(row['total_requests'])

# ✅ CORRECT - Handles NaN safely
total_req = row['total_requests']
total_requests = int(total_req) if pd.notna(total_req) else 0
```

This pattern appears in:
- `analytics/degradation_detector.py` (lines 108-119, 194-204, 262-271)
- `analytics/trend_analyzer.py` (lines 138-148, 198-206, 246-259)
- `analytics/slo_calculator.py` (lines 98-110, 158-168)
- `analytics/metrics.py` (lines 48-54, 85-92, 194-204, 234-247)
- `app.py` (lines 163-176)

### OpenSearch Data Extraction Pattern

OpenSearch returns data in **two possible locations**. Always check both:

```python
# Extract from OpenSearch response
source = hit.get('_source', {})
fields = hit.get('fields', {})
scripted_metric = source.get('scripted_metric', {})

# Try scripted_metric first (live OpenSearch), fallback to fields (JSON export)
service_name = scripted_metric.get('service_name') or self._extract_first(fields.get('service_name'))
```

This pattern is in `data/ingestion/data_loader.py` (lines 50-72 for service logs, 112-130 for error logs).

### DuckDB INSERT Pattern

**DO NOT** use `INSERT OR REPLACE` with multiple constraints. Use `DELETE + INSERT`:

```python
# ✅ CORRECT approach
self.conn.execute("DELETE FROM service_logs")
self.conn.execute("INSERT INTO service_logs SELECT * FROM df")
```

This is in `data/database/duckdb_manager.py` (lines 123-125, 165-167).

## Configuration

All configuration is centralized in `utils/config.py`:

```python
# SLO Thresholds
DEFAULT_ERROR_SLO_THRESHOLD = 1.0      # 1% error rate target
DEFAULT_RESPONSE_TIME_SLO = 1.0        # 1 second target
DEGRADATION_WINDOW_MINUTES = 30        # Time window for degradation detection
DEGRADATION_THRESHOLD_PERCENT = 20     # 20% change = degradation
```

AWS credentials are in `.env`:
```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0
```

OpenSearch credentials are hardcoded in `data/ingestion/opensearch_client.py` (lines 18-24).

## Analytics Functions

Claude has access to 14 analytics functions via tool calling (defined in `agent/function_tools.py`):

**Service Health:**
- `get_degrading_services(time_window_minutes=30)` - Detects services with declining metrics
- `get_slo_violations()` - Services currently violating SLO
- `get_service_health_overview()` - System-wide health metrics

**Error Analysis:**
- `get_error_code_distribution(service_name, time_window_minutes)` - HTTP error breakdown
- `get_top_errors(limit=10)` - Most common errors
- `get_error_prone_services(limit=10)` - Services with highest error rates

**Performance:**
- `get_slowest_services(limit=10)` - Services by response time
- `get_top_services_by_volume(limit=10)` - High-traffic services
- `get_volume_trends(service_name, time_window_minutes)` - Request volume patterns

**SLO Metrics:**
- `get_current_sli(service_name)` - Current service level indicators
- `calculate_error_budget(service_name, time_window_hours)` - Error budget tracking
- `get_service_summary(service_name)` - Comprehensive service analysis

**Predictions:**
- `predict_issues_today()` - Services likely to have issues (using trend analysis)
- `get_historical_patterns(service_name)` - Historical statistical analysis

## Time-Series Analysis

The degradation detector compares two time windows:

```
Baseline Window          Recent Window
[----------]             [----------]
  30 mins                  30 mins
                  ^
                  |
           comparison point
```

**How it works** (`analytics/degradation_detector.py`):
1. Define recent window: last N minutes from max timestamp
2. Define baseline window: N minutes before recent window
3. Calculate metrics for both windows (AVG error_rate, response_time, etc.)
4. Compare using percentage change: `((current - baseline) / baseline) * 100`
5. Flag as degrading if change > threshold (default 20%)

## OpenSearch Scroll API

For datasets >10,000 entries, use the Scroll API (`data/ingestion/opensearch_client.py:236-298`):

```python
# Standard query (max 10,000)
response = client.query_service_logs(size=1000, use_scroll=False)

# Scroll API (unlimited)
response = client.query_service_logs(size=1000, use_scroll=True)
```

**How Scroll API works:**
1. Initial search returns scroll_id and first batch
2. Subsequent scroll calls using scroll_id return next batches
3. Keep context alive with 2-minute scroll timeout
4. Clear scroll_id when done

## Testing

Run all tests with:
```bash
python test_system.py
```

This tests:
1. Data loading from JSON files
2. SLO calculations
3. Degradation detection
4. Trend analysis
5. Metrics aggregation

Expected output: 5/5 tests passing with ~60-70 services loaded.

## Common Issues

### Only 1 service appearing despite 200+ in data

**Root cause:** Data is in `_source.scripted_metric` not `fields`. This was fixed in `data/ingestion/data_loader.py` to check both locations.

### NaN to integer conversion errors

**Root cause:** Missing `pd.notna()` checks. See "NaN Handling Pattern" above.

### DuckDB constraint errors with INSERT OR REPLACE

**Root cause:** Multiple constraints on table. Use `DELETE + INSERT` instead.

### IndexError with large datasets

**Root cause:** Missing error handling in data parsing loop. Wrap each record parse in try/except.

## File Organization

```
analytics/     - 4 analytics modules (SLO, degradation, trends, metrics)
agent/         - 2 files (Claude client, function definitions)
data/          - 2 subfolders (ingestion, database)
utils/         - 2 files (config, logger)
app.py         - 437 lines, main Streamlit UI
test_system.py - Complete test suite
```

## Streamlit App Structure

The app has two tabs:
1. **Dashboard Tab** - Displays metrics, charts, SLO violations
2. **Chat Tab** - Conversational interface with Claude

State management:
- `st.session_state.messages` - Chat history
- `@st.cache_resource` - Caches initialized components (DB, analytics, Claude client)

## Development Notes

When modifying analytics functions:
1. Always add NaN checks for integer conversions
2. Test with `test_system.py`
3. Verify both OpenSearch (scripted_metric) and JSON (fields) data paths
4. Use `pd.notna()` before any `int()` conversion
5. Return consistent dictionary structures for Claude to parse

When adding new analytics:
1. Add method to appropriate analytics module
2. Add wrapper to `FunctionExecutor` in `agent/function_tools.py`
3. Add tool definition to `TOOLS` list in same file
4. Test with sample queries through chat interface
