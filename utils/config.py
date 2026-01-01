"""Configuration management for the SLO chatbot."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration
DUCKDB_PATH = DATABASE_DIR / "slo_analytics.duckdb"

# AWS Bedrock configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")

# OpenSearch configuration
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "")
OPENSEARCH_USE_SSL = os.getenv("OPENSEARCH_USE_SSL", "False").lower() == "true"
OPENSEARCH_INDEX_SERVICE = os.getenv("OPENSEARCH_INDEX_SERVICE", "hourly_wm_wmplatform_31854")
OPENSEARCH_INDEX_ERROR = os.getenv("OPENSEARCH_INDEX_ERROR", "hourly_wm_wmplatform_31854_error")

# SLO Thresholds (configurable)
DEFAULT_ERROR_SLO_THRESHOLD = 1.0  # 1% error rate
DEFAULT_RESPONSE_TIME_SLO = 1.0    # 1 second
DEFAULT_SLO_TARGET_PERCENT = 98    # 98% of requests must meet SLO

# Analytics configuration
DEGRADATION_WINDOW_MINUTES = 30
DEGRADATION_THRESHOLD_PERCENT = 20  # 20% increase is considered degradation

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
