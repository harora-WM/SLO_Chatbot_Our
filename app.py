"""Streamlit web UI for SLO chatbot."""

import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Import our modules
from data.database.duckdb_manager import DuckDBManager
from data.ingestion.data_loader import DataLoader
from data.ingestion.opensearch_client import OpenSearchClient
from analytics.slo_calculator import SLOCalculator
from analytics.degradation_detector import DegradationDetector
from analytics.trend_analyzer import TrendAnalyzer
from analytics.metrics import MetricsAggregator
from agent.claude_client import ClaudeClient
from agent.function_tools import FunctionExecutor, TOOLS
from utils.config import PROJECT_ROOT
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="SLO Chatbot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .user-message {
        background-color: #e3f2fd;
    }
    .assistant-message {
        background-color: #f5f5f5;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def initialize_system():
    """Initialize all system components."""
    logger.info("Initializing SLO chatbot system")

    # Initialize database manager
    db_manager = DuckDBManager()

    # Initialize analytics components
    slo_calculator = SLOCalculator(db_manager)
    degradation_detector = DegradationDetector(db_manager)
    trend_analyzer = TrendAnalyzer(db_manager)
    metrics_aggregator = MetricsAggregator(db_manager)

    # Initialize function executor
    function_executor = FunctionExecutor(
        slo_calculator=slo_calculator,
        degradation_detector=degradation_detector,
        trend_analyzer=trend_analyzer,
        metrics_aggregator=metrics_aggregator
    )

    # Initialize Claude client
    claude_client = ClaudeClient()

    # Initialize data loader
    data_loader = DataLoader(db_manager)

    logger.info("System initialization complete")

    return {
        'db_manager': db_manager,
        'slo_calculator': slo_calculator,
        'degradation_detector': degradation_detector,
        'trend_analyzer': trend_analyzer,
        'metrics_aggregator': metrics_aggregator,
        'function_executor': function_executor,
        'claude_client': claude_client,
        'data_loader': data_loader
    }


# JSON file loading removed - data now only comes from OpenSearch
# def load_initial_data(data_loader):
#     """Load initial data from JSON files."""
#     service_logs_path = PROJECT_ROOT / "ServiceLogs7Amto11Am31Dec2025.json"
#     error_logs_path = PROJECT_ROOT / "ErrorLogs7Amto11Am31Dec2025.json"
#
#     if service_logs_path.exists() and error_logs_path.exists():
#         with st.spinner("Loading service and error logs..."):
#             data_loader.load_and_store_all(str(service_logs_path), str(error_logs_path))
#         st.success("Data loaded successfully!")
#         return True
#     else:
#         st.error("Log files not found!")
#         return False


def display_dashboard(components):
    """Display dashboard with key metrics."""
    st.markdown("<h2>Service Health Dashboard</h2>", unsafe_allow_html=True)

    # Get health overview
    health_overview = components['metrics_aggregator'].get_service_health_overview()

    # Display metrics in columns
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Services",
            health_overview['total_services'],
            help="Total number of services"
        )

    with col2:
        st.metric(
            "Healthy Services",
            health_overview['healthy_services'],
            f"{health_overview['health_percentage']:.1f}%",
            help="Services meeting SLO targets"
        )

    with col3:
        st.metric(
            "Degraded Services",
            health_overview['degraded_services'],
            help="Services approaching SLO limits"
        )

    with col4:
        st.metric(
            "Violated Services",
            health_overview['violated_services'],
            help="Services violating SLO"
        )

    # Overall metrics
    col1, col2 = st.columns(2)

    with col1:
        total_req = health_overview.get('total_requests', 0)
        st.metric(
            "Total Requests",
            f"{total_req:,}" if total_req else "0",
            help="Total request count"
        )

    with col2:
        error_rate = health_overview.get('overall_error_rate', 0)
        st.metric(
            "Overall Error Rate",
            f"{error_rate:.2f}%" if error_rate else "0.00%",
            help="System-wide error rate"
        )

    # Top services by volume
    st.markdown("<h3>Top Services by Volume</h3>", unsafe_allow_html=True)
    top_services = components['metrics_aggregator'].get_top_services_by_volume(limit=5)

    if top_services:
        df = pd.DataFrame(top_services)
        fig = px.bar(
            df,
            x='service_name',
            y='total_requests',
            title='Top 5 Services by Request Volume',
            labels={'service_name': 'Service', 'total_requests': 'Total Requests'}
        )
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # SLO violations
    violations = components['slo_calculator'].get_slo_violations()
    if violations:
        st.markdown("<h3>⚠️ Current SLO Violations</h3>", unsafe_allow_html=True)
        for violation in violations[:5]:
            with st.expander(f"🔴 {violation['service_name']}"):
                st.write(f"**Error Rate:** {violation['error_rate']:.2f}%")
                st.write(f"**Response Time:** {violation['response_time']:.3f}s")
                st.write("**Violations:**")
                for reason in violation['violations']:
                    st.write(f"- {reason}")


def display_chat(components):
    """Display chat interface."""
    st.markdown("<h2>💬 SLO Assistant</h2>", unsafe_allow_html=True)

    # Initialize chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # System prompt for Claude
    system_prompt = """You are a Conversational SLO & Reliability Analysis Assistant.

Your role is to analyze SERVICE logs and ERROR logs coming from an OpenSearch index and produce clear, reliable, and structured SLO insights.

You operate ONLY on the data provided by the user. Do not assume missing values.

========================
DATA UNDERSTANDING RULES
========================
You will receive two log types:

1) SERVICE LOGS
- Represent successful and total requests for a service
- Contain latency, success rate, SLO targets
- Key fields (may appear at root or under scripted_metric):
  - service_name
  - application_name
  - record_time (epoch millis or ISO)
  - total_req_count / total_count
  - success_count
  - error_count
  - success_rate
  - error_rate
  - response_time_avg / min / max
  - **response_time_p50 / p95 / p99** (CRITICAL: Use these for latency analysis, not averages!)
  - target_response_slo_sec
  - response_target_percent
  - resp_breach_count

2) ERROR LOGS
- Represent error or transaction-level behavior
- May include HTTP 4xx / 5xx or business errors
- Key fields:
  - wmApplicationId / wmApplicationName
  - wmTransactionName (readable transaction name)
  - errorCodes (HTTP status codes like 404, 500, etc.)
  - technical_error_count
  - business_error_count
  - error_count
  - responseTime_avg / min / max
  - responseTime_percentiles
  - **error_details** (full error log line with timestamps, IPs, URLs - use for debugging)
  - record_time

========================
ANALYSIS RESPONSIBILITIES
========================
For every user query, you must:

1) Identify the service(s) involved
2) Correlate SERVICE logs and ERROR logs using:
   - application_id / application_name
   - service_name / wmTransactionName
   - overlapping time windows
3) Calculate and explicitly state:
   - Total requests
   - Success count
   - Error count
   - Success rate (%)
   - Error rate (%)
   - **P50, P95, and P99 latency (PRIORITIZE THESE OVER AVERAGES)**
   - Average and Max latency (for context)
4) Evaluate SLO compliance:
   - **Use P95 or P99 for latency SLO checks** (not average - averages hide tail latencies)
   - Compare success rate vs response_target_percent
   - Flag services where P99 > target even if average is acceptable
5) Detect degradation signals:
   - **P95/P99 latency increases** (>20% = degrading)
   - Average latency increases (secondary signal)
   - Error spikes
   - Breach counts > 0
6) Clearly distinguish:
   - No-traffic scenarios
   - Healthy services (all metrics within targets)
   - Degrading services (P95/P99 trending up, even if not breached)
   - SLO violations (metrics exceeding targets)

========================
AVAILABLE TOOLS
========================
You have access to these analytics functions:
- get_degrading_services() - Detects P95/P99 latency degradation
- get_slowest_services() - Ranks by P99 latency
- get_service_summary() - Includes P50/P95/P99 metrics
- **get_error_details_by_code(error_code)** - Get full error log details for debugging
- get_top_errors() - Most common error codes
- And 10+ other analytics functions

**CRITICAL**: When users ask about error details or debugging, use get_error_details_by_code() to retrieve full error logs.

========================
OUTPUT FORMAT (STRICT)
========================
Your output MUST follow this structure exactly.
Do NOT break formatting.

------------------------
SERVICE HEALTH SUMMARY
------------------------
Service Name:
Application:
Time Window:

- Total Requests:
- Success Count:
- Error Count:
- Success Rate:
- Error Rate:
- **P50 Response Time:** (median - 50% of requests)
- **P95 Response Time:** (95% of requests)
- **P99 Response Time:** (99% of requests - MOST CRITICAL)
- Avg Response Time: (for reference)
- Max Response Time:

------------------------
SLO EVALUATION
------------------------
- Availability SLO Target:
- Observed Availability:
- **Latency SLO Target:** (compare against P95/P99, NOT average)
- **Observed P95 Latency:**
- **Observed P99 Latency:**
- Observed Avg Latency: (for context)
- SLO Status: (COMPLIANT / BREACHED / AT RISK / DEGRADING)

**Note**: If P99 > target but average is OK, flag as AT RISK (tail latency issue)

------------------------
ERROR ANALYSIS
------------------------
- Total Error Events:
- Technical Errors:
- Business Errors:
- Top Error Codes:
- Affected Endpoints:
- **Error Details** (if requested): Show transaction names, timestamps, and key details from error logs

------------------------
TRENDS & SIGNALS
------------------------
- Latency Trend:
- Error Trend:
- Traffic Trend:

------------------------
ACTIONABLE INSIGHTS
------------------------
- Key Observations:
- Probable Root Cause:
- Recommended Actions:

========================
IMPORTANT BEHAVIOR RULES
========================
- Always show numbers with units (%, seconds, counts)
- **ALWAYS prioritize P95/P99 over averages** for latency analysis
- If P50/P95/P99 are null, use average and mention "percentile data unavailable"
- If error_count = 0, explicitly say "No errors observed"
- If total requests are very low, warn about statistical insignificance
- Never hallucinate root causes — base them on observed metrics
- **Keep explanations concise and professional** - avoid overly long reports
- Prefer bullet points over paragraphs
- Never expose raw OpenSearch JSON unless asked
- **When debugging errors**, proactively use get_error_details_by_code() to show full error logs
- **Flag tail latency issues**: If P99 >> P95 or P95 >> P50, warn about inconsistent performance
- **LIMITED DATA HANDLING**: If asked for multi-day/time-of-day patterns but only have hours of data, respond: "Insufficient historical data. Need 7+ days for time-of-day analysis. Current data: [X hours]. Can analyze: current health, trends within available window."
- **AVOID TOOL OVERUSE**: Don't call more than 5-7 tools per query. If question requires extensive analysis beyond available data, explain limitation instead of calling every possible tool.

========================
DEFAULT TONE
========================
Professional SRE / Reliability Engineer
Clear, calm, data-driven
No emojis, no casual language

========================
EXAMPLES OF GOOD ANALYSIS
========================

GOOD: "Service X has P99 latency of 250ms (target: 200ms) - BREACHED. However, P95 is 150ms and average is 80ms, indicating occasional tail latency spikes affecting 1% of requests."

BAD: "Service X has average latency of 80ms (target: 200ms) - COMPLIANT" (WRONG - misses the P99 breach!)

GOOD: "get_degrading_services() shows Service Y P95 increased 50% (100ms → 150ms) in last 30min. This is degrading even though average only rose 10%."

BAD: "Service looks fine, average latency is stable" (WRONG - ignores percentile degradation!)


"""

    # Chat input
    if prompt := st.chat_input("Ask about service health, SLOs, or degradation..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        # Get Claude response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                try:
                    response = components['claude_client'].chat(
                        user_message=prompt,
                        tools=TOOLS,
                        tool_executor=components['function_executor'],
                        system_prompt=system_prompt
                    )

                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})

                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    logger.error(f"Chat error: {e}")


def main():
    """Main application."""
    # Title
    st.markdown("<div class='main-header'>📊 SLO Chatbot</div>", unsafe_allow_html=True)
    st.markdown("**AI-powered Service Level Objective monitoring and analysis**")

    # Initialize system
    components = initialize_system()

    # Sidebar
    with st.sidebar:
        st.markdown("## 🔧 Configuration")

        # Data loading from OpenSearch only
        st.markdown("### Data Management")
        st.info("📊 Data is loaded from OpenSearch only")

        st.markdown("#### OpenSearch Options")

        # Time range selection
        time_range_option = st.selectbox(
            "Time Range",
            ["Last 4 hours", "Custom"],
            index=0
        )

        # Custom time range inputs
        if time_range_option == "Custom":
            st.info("⚠️ Maximum time range is 4 hours")
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
                start_time = st.time_input("Start Time")
            with col2:
                end_date = st.date_input("End Date")
                end_time = st.time_input("End Time")

        max_results = st.number_input(
            "Max Results",
            min_value=100,
            max_value=10000,
            value=1000,
            step=100,
            help="Maximum results to fetch from OpenSearch"
        )

        if st.button("🔄 Refresh from OpenSearch"):
            with st.spinner("Fetching logs from OpenSearch..."):
                try:
                    os_client = OpenSearchClient()

                    # Calculate time range
                    from datetime import datetime, timedelta
                    end_time_dt = datetime.now()

                    if time_range_option == "Last 4 hours":
                        start_time_dt = end_time_dt - timedelta(hours=4)
                    else:  # Custom
                        start_time_dt = datetime.combine(start_date, start_time)
                        end_time_dt = datetime.combine(end_date, end_time)

                        # Validate that time range doesn't exceed 4 hours
                        time_diff = end_time_dt - start_time_dt
                        if time_diff > timedelta(hours=4):
                            st.error("❌ Time range cannot exceed 4 hours. Please adjust your selection.")
                            st.stop()
                        elif time_diff <= timedelta(0):
                            st.error("❌ End time must be after start time.")
                            st.stop()

                    st.info(f"Fetching data from {start_time_dt} to {end_time_dt}")

                    # Fetch logs without scroll API
                    service_logs = os_client.query_service_logs(
                        start_time=start_time_dt,
                        end_time=end_time_dt,
                        size=max_results,
                        use_scroll=False
                    )

                    error_logs = os_client.query_error_logs(
                        start_time=start_time_dt,
                        end_time=end_time_dt,
                        size=max_results,
                        use_scroll=False
                    )

                    # Load into database
                    import tempfile
                    import os
                    import json

                    with tempfile.NamedTemporaryFile(mode='w', suffix='_service.json', delete=False) as f:
                        json.dump(service_logs, f)
                        service_temp_path = f.name

                    with tempfile.NamedTemporaryFile(mode='w', suffix='_error.json', delete=False) as f:
                        json.dump(error_logs, f)
                        error_temp_path = f.name

                    try:
                        components['data_loader'].load_and_store_all(service_temp_path, error_temp_path)
                        service_count = len(service_logs.get('hits', {}).get('hits', []))
                        error_count = len(error_logs.get('hits', {}).get('hits', []))
                        st.success(f"✅ Loaded {service_count:,} service logs and {error_count:,} error logs")
                    finally:
                        os.unlink(service_temp_path)
                        os.unlink(error_temp_path)

                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    st.error(f"Failed to fetch from OpenSearch: {str(e)}")
                    with st.expander("View Error Details"):
                        st.code(error_details)
                    logger.error(f"OpenSearch fetch error: {error_details}")

        # Data info
        try:
            time_range = components['db_manager'].get_time_range()
            if time_range['min_time'] and time_range['max_time']:
                st.markdown("### 📅 Data Time Range")
                st.write(f"**From:** {time_range['min_time']}")
                st.write(f"**To:** {time_range['max_time']}")

            all_services = components['db_manager'].get_all_services()
            st.markdown(f"### 📊 Total Services: {len(all_services)}")

        except Exception as e:
            st.warning("No data loaded yet. Please load data first.")

        # Clear chat
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            components['claude_client'].clear_history()
            st.success("Chat history cleared!")

        # Sample questions
        st.markdown("### 💡 Sample Questions")
        st.markdown("""
        - Which services are degrading over the past 30 minutes?
        - Show the volume and error code distribution for degrading services
        - Which services are expected to have issues today?
        - What's the current error rate for all services?
        - Show me services violating their SLO
        - Calculate error budget for [service name]
        - What are the slowest services?
        """)

    # Main content tabs
    tab1, tab2 = st.tabs(["📊 Dashboard", "💬 Chat"])

    with tab1:
        try:
            display_dashboard(components)
        except Exception as e:
            st.error(f"Dashboard error: {str(e)}")
            st.info("Please load data first using the sidebar button.")

    with tab2:
        display_chat(components)


if __name__ == "__main__":
    main()
