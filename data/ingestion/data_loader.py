"""Data loader for parsing and loading JSON logs into DuckDB."""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any
from utils.logger import setup_logger
from data.database.duckdb_manager import DuckDBManager

logger = setup_logger(__name__)


class DataLoader:
    """Loader for service and error logs."""

    def __init__(self, db_manager: DuckDBManager):
        """Initialize data loader.

        Args:
            db_manager: DuckDB manager instance
        """
        self.db_manager = db_manager

    def load_service_logs_from_json(self, json_path: str) -> pd.DataFrame:
        """Load service logs from JSON file.

        Args:
            json_path: Path to service logs JSON file

        Returns:
            DataFrame with parsed service logs
        """
        logger.info(f"Loading service logs from {json_path}")

        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            # Extract hits from Elasticsearch response
            hits = data.get('hits', {}).get('hits', [])
            logger.info(f"Found {len(hits)} service log entries")

            # Parse each entry
            records = []
            for idx, hit in enumerate(hits):
                try:
                    source = hit.get('_source', {})
                    fields = hit.get('fields', {})

                    # Check if data is in scripted_metric (from OpenSearch) or fields (from JSON export)
                    scripted_metric = source.get('scripted_metric', {})

                    # Extract percentiles from the nested structure
                    percentiles = source.get('percentiles_response_time_max', {})

                    # Extract and flatten the data - prefer scripted_metric, fallback to fields
                    record = {
                        'id': hit.get('_id'),
                        'app_id': source.get('app_id'),
                        'sid': source.get('sid'),
                        'service_name': scripted_metric.get('service_name') or self._extract_first(fields.get('service_name')),
                        'record_time': source.get('record_time'),
                        'total_count': scripted_metric.get('total_count') or self._extract_first(fields.get('total_count')),
                        'success_count': scripted_metric.get('success_count') or self._extract_first(fields.get('success_count')),
                        'error_count': scripted_metric.get('error_count') or self._extract_first(fields.get('error_count')),
                        'na_error_count': scripted_metric.get('na_error_count') or self._extract_first(fields.get('na_error_count')),
                        'success_rate': scripted_metric.get('success_rate') or self._extract_first(fields.get('success_rate')),
                        'error_rate': scripted_metric.get('error_rate') or self._extract_first(fields.get('error_rate')),
                        'response_time_avg': source.get('response_time_avg'),
                        'response_time_min': source.get('response_time_min'),
                        'response_time_max': source.get('response_time_max'),
                        'response_time_p25': percentiles.get('25.0'),
                        'response_time_p50': percentiles.get('50.0'),
                        'response_time_p75': percentiles.get('75.0'),
                        'response_time_p80': percentiles.get('80.0'),
                        'response_time_p85': percentiles.get('85.0'),
                        'response_time_p90': percentiles.get('90.0'),
                        'response_time_p95': percentiles.get('95.0'),
                        'response_time_p99': percentiles.get('99.0'),
                        'target_error_slo_perc': scripted_metric.get('target_error_slo_perc') or self._extract_first(fields.get('target_error_slo_perc')),
                        'target_response_slo_sec': scripted_metric.get('target_response_slo_sec') or self._extract_first(fields.get('target_response_slo_sec')),
                        'response_target_percent': scripted_metric.get('response_target_percent') or self._extract_first(fields.get('response_target_percent'))
                    }
                    records.append(record)
                except Exception as e:
                    logger.warning(f"Skipping service log entry {idx} due to error: {e}")
                    continue

            df = pd.DataFrame(records)
            # Ensure continuous index for DuckDB compatibility
            df = df.reset_index(drop=True)
            logger.info(f"Parsed {len(df)} service log records")
            return df

        except Exception as e:
            logger.error(f"Failed to load service logs: {e}")
            raise

    def load_error_logs_from_json(self, json_path: str) -> pd.DataFrame:
        """Load error logs from JSON file.

        Args:
            json_path: Path to error logs JSON file

        Returns:
            DataFrame with parsed error logs
        """
        logger.info(f"Loading error logs from {json_path}")

        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            # Extract hits from Elasticsearch response
            hits = data.get('hits', {}).get('hits', [])
            logger.info(f"Found {len(hits)} error log entries")

            # Parse each entry
            records = []
            for idx, hit in enumerate(hits):
                try:
                    source = hit.get('_source', {})
                    fields = hit.get('fields', {})

                    # Check if data is in scripted_metric (from OpenSearch) or fields (from JSON export)
                    scripted_metric = source.get('scripted_metric', {})

                    # Extract and flatten the data - prefer scripted_metric, fallback to fields
                    record = {
                        'id': hit.get('_id'),
                        'wm_application_id': source.get('wmApplicationId'),
                        'wm_application_name': source.get('wmApplicationName'),
                        'wm_transaction_id': source.get('wmTransactionId'),
                        'wm_transaction_name': scripted_metric.get('wmTransactionName') or self._extract_first(fields.get('wmTransactionName')),
                        'error_codes': source.get('errorCodes'),
                        'error_count': scripted_metric.get('error_count') or source.get('error_count'),
                        'total_count': source.get('total_count'),
                        'technical_error_count': scripted_metric.get('technical_error_count') or self._extract_first(fields.get('technical_error_count')),
                        'business_error_count': scripted_metric.get('business_error_count') or self._extract_first(fields.get('business_error_count')),
                        'response_time_avg': source.get('responseTime_avg'),
                        'response_time_min': source.get('responseTime_min'),
                        'response_time_max': source.get('responseTime_max'),
                        'error_details': scripted_metric.get('error_details') or self._extract_first(fields.get('error_details')),
                        'record_time': source.get('record_time')
                    }
                    records.append(record)
                except Exception as e:
                    logger.warning(f"Skipping error log entry {idx} due to error: {e}")
                    continue

            df = pd.DataFrame(records)
            # Ensure continuous index for DuckDB compatibility
            df = df.reset_index(drop=True)
            logger.info(f"Parsed {len(df)} error log records")
            return df

        except Exception as e:
            logger.error(f"Failed to load error logs: {e}")
            raise

    def load_and_store_all(self, service_logs_path: str, error_logs_path: str):
        """Load and store both service and error logs.

        Args:
            service_logs_path: Path to service logs JSON
            error_logs_path: Path to error logs JSON
        """
        # Load service logs
        service_df = self.load_service_logs_from_json(service_logs_path)
        self.db_manager.insert_service_logs(service_df)

        # Load error logs
        error_df = self.load_error_logs_from_json(error_logs_path)
        self.db_manager.insert_error_logs(error_df)

        logger.info("All logs loaded successfully")

        # Print summary
        time_range = self.db_manager.get_time_range()
        all_services = self.db_manager.get_all_services()

        logger.info(f"Data time range: {time_range['min_time']} to {time_range['max_time']}")
        logger.info(f"Total unique services: {len(all_services)}")

    @staticmethod
    def _extract_first(value):
        """Extract first element from list or return value as-is.

        Args:
            value: Value to extract from

        Returns:
            First element if list, otherwise value itself
        """
        if isinstance(value, list) and len(value) > 0:
            return value[0]
        return value
