# SLO Chatbot

AI-powered Service Level Objective (SLO) monitoring and analysis chatbot using Claude Sonnet 4.5 via AWS Bedrock.

## Features

- **Real-time Service Analysis**: Monitor service health, error rates, and response times
- **Degradation Detection**: Identify services degrading over configurable time windows
- **Predictive Analysis**: Predict which services are likely to have issues
- **Error Budget Tracking**: Calculate and monitor error budget consumption
- **Conversational Interface**: Natural language queries powered by Claude Sonnet 4.5
- **Interactive Dashboard**: Visualize service health metrics and trends
- **OpenSearch Integration**: Stream real-time logs from OpenSearch

## Architecture

```
┌─────────────────────┐
│   Streamlit UI      │
│   (Web Interface)   │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   Claude Sonnet 4.5 │
│   (AWS Bedrock)     │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Function Executor  │
│  (Tool Calling)     │
└──────────┬──────────┘
           │
┌──────────▼──────────────────────────┐
│         Analytics Engine             │
├──────────────────────────────────────┤
│  • SLO Calculator                    │
│  • Degradation Detector              │
│  • Trend Analyzer                    │
│  • Metrics Aggregator                │
└──────────┬───────────────────────────┘
           │
┌──────────▼──────────┐
│     DuckDB          │
│  (OLAP Database)    │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   OpenSearch        │
│   (Data Source)     │
└─────────────────────┘
```

## Important Documentation

- **README.md** (this file) - Main documentation
- **QUICKSTART.md** - Quick start guide with examples
- **DATA_LIMITS_GUIDE.md** - ⭐ **OpenSearch data limits and large dataset handling**
- **PROJECT_SUMMARY.md** - Complete project overview

## Installation

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure environment variables** in `.env`:
```
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ap-south-1
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-5-20250929-v1:0

OPENSEARCH_HOST=your_opensearch_host
OPENSEARCH_PORT=9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=your_password
OPENSEARCH_INDEX_SERVICE=your_service_index
OPENSEARCH_INDEX_ERROR=your_error_index
```

## Usage

### Start the Chatbot

```bash
streamlit run app.py
```

The web interface will open at `http://localhost:8501`

### Using the Dashboard

1. **Load Data**: Click "🔄 Refresh from OpenSearch" in the sidebar to fetch data
2. **View Metrics**: Check the dashboard for service health overview
3. **Chat**: Switch to the Chat tab to ask questions

### Sample Questions

- "Which services are degrading over the past 30 minutes?"
- "Show the volume and error code distribution for degrading services"
- "Which services are expected to have issues today?"
- "What's the current SLI for all services?"
- "Show me services violating their SLO"
- "Calculate error budget for [service name]"
- "What are the top errors?"
- "Show me the slowest services"

## Components

### Data Layer
- **DuckDBManager**: OLAP database for fast analytical queries
- **DataLoader**: Parse JSON logs into structured format
- **OpenSearchClient**: Real-time log ingestion

### Analytics Layer
- **SLOCalculator**: SLI/SLO calculations, error budgets, burn rates
- **DegradationDetector**: Identify degrading services using time-series analysis
- **TrendAnalyzer**: Predictive analysis and historical patterns
- **MetricsAggregator**: Service metrics and aggregations

### Agent Layer
- **ClaudeClient**: AWS Bedrock integration
- **FunctionExecutor**: Execute analytics functions via tool calling
- **TOOLS**: 14+ analytics functions for Claude to call

### UI Layer
- **Streamlit App**: Web-based chat interface and dashboard

## Analytics Functions

The chatbot has access to 14 analytics functions:

1. `get_degrading_services` - Find services with declining performance
2. `get_error_code_distribution` - Error code breakdown
3. `get_current_sli` - Current service level indicators
4. `predict_issues_today` - Predictive issue detection
5. `get_service_summary` - Comprehensive service analysis
6. `get_slo_violations` - Current SLO violations
7. `calculate_error_budget` - Error budget tracking
8. `get_volume_trends` - Request volume patterns
9. `get_service_health_overview` - Overall system health
10. `get_top_services_by_volume` - High-traffic services
11. `get_slowest_services` - Latency leaders
12. `get_error_prone_services` - High error rate services
13. `get_top_errors` - Most common errors
14. `get_historical_patterns` - Historical analysis

## Configuration

Edit `utils/config.py` to customize:
- SLO thresholds
- Degradation detection parameters
- Time windows
- Database paths

## No Vector Database Needed!

This implementation **does NOT use Pinecone or vector embeddings** because:

✅ **Structured data**: Logs have well-defined metrics (error_rate, response_time)
✅ **Time-series queries**: Need aggregations, not semantic search
✅ **Fast analytics**: DuckDB is optimized for OLAP workloads
✅ **Simpler architecture**: Direct SQL queries are faster and more precise

Vector databases are for **unstructured text** semantic search. Our SLO data is **highly structured** and benefits from traditional OLAP engines.

## Data Retrieval Limits

### OpenSearch Query Limits

The application is configured to fetch data within a **maximum 4-hour time window** to ensure optimal performance and stay within OpenSearch limits.

### Configurable Options in UI

✅ **Time Range Selection**:
- Last 4 hours (default)
- Custom date/time range (max 4 hours)

✅ **Max Results**: 100 to 10,000 results per query

**Note**: The 4-hour limit ensures data stays under the 10,000 result limit without requiring Scroll API.

## Future Enhancements

- [ ] Real-time OpenSearch streaming with background sync
- [ ] Alerting system for SLO violations
- [ ] Custom SLO definitions per service
- [ ] Export dashboard reports (PDF, CSV)
- [ ] Multi-user authentication
- [ ] Historical data retention policies

## License

MIT
