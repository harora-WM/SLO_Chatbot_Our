# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# First-time setup
pip install -r requirements.txt
cp .env.example .env  # Then edit .env with your credentials

# Activate virtual environment (if using one)
source venv/bin/activate

# Run the application
streamlit run app.py

# Run tests
python test_system.py

# Inspect database contents
python check_data.py

# Debug OpenSearch connection
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
   - `claude_client.py`: AWS Bedrock integration with conversation history and tool use handling
   - `function_tools.py`: 14 analytics functions exposed to Claude via tool calling. The `FunctionExecutor` class dispatches tool calls to appropriate analytics modules.

4. **UI Layer**
   - `app.py`: Streamlit web interface with dashboard and chat tabs. Uses `@st.cache_resource` to initialize system components once.

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

### JSON Serialization Pattern for Claude Tool Results

**ALWAYS** use the custom `DateTimeEncoder` when serializing tool results to send to Claude:

```python
import json
from agent.claude_client import DateTimeEncoder

# ✅ CORRECT - Handles pandas Timestamp, datetime, numpy types
result = {"timestamp": pd.Timestamp.now(), "value": np.int64(42)}
json_str = json.dumps(result, cls=DateTimeEncoder)

# ❌ WRONG - Will crash with "Object of type Timestamp is not JSON serializable"
json_str = json.dumps(result)
```

**What the DateTimeEncoder handles**:
- `pd.Timestamp` → ISO format string
- `datetime/date` → ISO format string
- `np.integer` → Python int
- `np.floating` → Python float
- `np.ndarray` → Python list
- `pd.NA/np.nan` → `null`

This is critical in `agent/claude_client.py` (lines 147, 157) where tool results are serialized to send back to Claude.

### DuckDB INSERT Pattern

**ALWAYS** use this pattern when inserting DataFrames into DuckDB:

```python
# ✅ CORRECT approach
df = df.reset_index(drop=True)  # Reset index after any dropna() operations
self.conn.execute("DELETE FROM service_logs")

# Register DataFrame explicitly to avoid caching issues
self.conn.register('temp_service_df', df)
self.conn.execute("INSERT INTO service_logs SELECT * FROM temp_service_df")
self.conn.unregister('temp_service_df')
```

**Why this is critical**:
1. After using `dropna()` or filtering, pandas DataFrames have non-contiguous indices (e.g., 0, 1, 3, 5, ...)
2. DuckDB expects continuous indices (0, 1, 2, 3, ...)
3. Using `register()` explicitly registers the DataFrame with DuckDB, avoiding stale references
4. Without this, large datasets (>1000 rows) may throw `IndexError: index N is out of bounds`

**DO NOT** use `INSERT OR REPLACE` with multiple constraints. Use `DELETE + INSERT` instead.

This pattern is in `data/database/duckdb_manager.py` (lines 123-132 for service logs, 168-177 for error logs).

## Configuration

All configuration is centralized in `utils/config.py`:

```python
# SLO Thresholds
DEFAULT_ERROR_SLO_THRESHOLD = 1.0      # 1% error rate target
DEFAULT_RESPONSE_TIME_SLO = 1.0        # 1 second target
DEGRADATION_WINDOW_MINUTES = 30        # Time window for degradation detection
DEGRADATION_THRESHOLD_PERCENT = 20     # 20% change = degradation
```

All credentials are configured in `.env` (never commit this file):
```
# AWS Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0

# OpenSearch
OPENSEARCH_HOST=...
OPENSEARCH_PORT=9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=...
OPENSEARCH_USE_SSL=False
OPENSEARCH_INDEX_SERVICE=hourly_wm_wmplatform_31854
OPENSEARCH_INDEX_ERROR=hourly_wm_wmplatform_31854_error
```

Use `.env.example` as a template for new setup.

## Analytics Functions

Claude has access to 14 analytics functions via tool calling (defined in `agent/function_tools.py`). The tool calling mechanism works as follows:

1. User sends a message via Streamlit chat
2. Claude receives the message along with `TOOLS` list (tool definitions)
3. Claude decides which tools to call and returns `tool_use` content blocks
4. `FunctionExecutor.execute()` dispatches the call to the appropriate analytics module
5. Tool results are sent back to Claude in the next message
6. Claude synthesizes the results into a natural language response

Available functions:

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

### Streamlit Not Picking Up Code Changes

**Root cause:** Streamlit uses `@st.cache_resource` to cache initialized components (DuckDBManager, Claude client, etc.). Code changes to cached classes won't apply until restart.

**Solution:**
1. Stop Streamlit (Ctrl+C)
2. Clear Python cache: `find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true`
3. Restart: `streamlit run app.py`

Alternatively, use Streamlit's "Rerun" button in the UI, but this doesn't clear `@st.cache_resource` cached objects.

### IndexError: index N is out of bounds for axis 0 with size N

**Root cause:** DataFrame index is non-contiguous after `dropna()` operations. DuckDB expects continuous indices.

**Solution:** Always call `df.reset_index(drop=True)` before inserting into DuckDB. See "DuckDB INSERT Pattern" above.

### Only 1 service appearing despite 200+ in data

**Root cause:** Data is in `_source.scripted_metric` not `fields`. This was fixed in `data/ingestion/data_loader.py` to check both locations.

### NaN to integer conversion errors

**Root cause:** Missing `pd.notna()` checks. See "NaN Handling Pattern" above.

### DuckDB constraint errors with INSERT OR REPLACE

**Root cause:** Multiple constraints on table. Use `DELETE + INSERT` instead.

### IndexError during data parsing with large datasets

**Root cause:** Missing error handling in data parsing loop. Wrap each record parse in try/except.

### "Object of type Timestamp is not JSON serializable"

**Root cause:** Analytics functions return pandas Timestamp or numpy types that can't be serialized to JSON for Claude.

**Solution:** Use the custom `DateTimeEncoder` class when calling `json.dumps()`. See "JSON Serialization Pattern" above.

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
1. Add method to appropriate analytics module (returns dict/list)
2. Add wrapper method to `FunctionExecutor` in `agent/function_tools.py` (e.g., `_get_my_function`)
3. Add function name to `function_map` dict in `FunctionExecutor.execute()`
4. Add tool definition to `TOOLS` list with name, description, and input_schema
5. Test with sample queries through chat interface

Example tool definition structure:
```python
{
    "name": "my_function",
    "description": "What this function does for Claude to understand",
    "input_schema": {
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string",
                "description": "What this parameter means"
            }
        },
        "required": ["param_name"]  # Optional
    }
}
```
