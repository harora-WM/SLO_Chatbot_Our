"""Metrics aggregation and utilities."""

import pandas as pd
from typing import Dict, Any, List, Optional
from data.database.duckdb_manager import DuckDBManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MetricsAggregator:
    """Aggregator for service metrics."""

    def __init__(self, db_manager: DuckDBManager):
        """Initialize metrics aggregator.

        Args:
            db_manager: DuckDB manager instance
        """
        self.db_manager = db_manager

    def get_top_services_by_volume(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top services by request volume.

        Args:
            limit: Number of top services to return

        Returns:
            List of top services
        """
        sql = f"""
            SELECT
                service_name,
                SUM(total_count) as total_requests,
                AVG(error_rate) as avg_error_rate,
                AVG(response_time_avg) as avg_response_time
            FROM service_logs
            GROUP BY service_name
            ORDER BY total_requests DESC
            LIMIT {limit}
        """

        df = self.db_manager.query(sql)

        results = []
        for _, row in df.iterrows():
            # Handle NaN values safely
            total_req = row['total_requests']
            results.append({
                'service_name': row['service_name'],
                'total_requests': int(total_req) if pd.notna(total_req) else 0,
                'avg_error_rate': row['avg_error_rate'] if pd.notna(row['avg_error_rate']) else 0.0,
                'avg_response_time': row['avg_response_time'] if pd.notna(row['avg_response_time']) else 0.0
            })

        return results

    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top error codes by frequency.

        Args:
            limit: Number of top errors to return

        Returns:
            List of top errors
        """
        sql = f"""
            SELECT
                error_codes,
                COUNT(*) as occurrence_count,
                SUM(error_count) as total_errors,
                AVG(response_time_avg) as avg_response_time
            FROM error_logs
            WHERE error_count > 0
            GROUP BY error_codes
            ORDER BY total_errors DESC
            LIMIT {limit}
        """

        df = self.db_manager.query(sql)

        results = []
        for _, row in df.iterrows():
            # Handle NaN values safely
            occ_count = row['occurrence_count']
            tot_errors = row['total_errors']
            results.append({
                'error_code': row['error_codes'],
                'occurrence_count': int(occ_count) if pd.notna(occ_count) else 0,
                'total_errors': int(tot_errors) if pd.notna(tot_errors) else 0,
                'avg_response_time': row['avg_response_time'] if pd.notna(row['avg_response_time']) else 0.0
            })

        return results

    def get_service_health_overview(self) -> Dict[str, Any]:
        """Get overall service health overview.

        Returns:
            Dictionary with health metrics
        """
        # Total services
        total_services = len(self.db_manager.get_all_services())

        # Services meeting SLO
        slo_sql = """
            SELECT
                service_name,
                AVG(error_rate) as avg_error_rate,
                AVG(response_time_avg) as avg_response_time,
                MAX(target_error_slo_perc) as error_slo_target,
                MAX(target_response_slo_sec) as response_slo_target
            FROM service_logs
            GROUP BY service_name
        """

        df = self.db_manager.query(slo_sql)

        healthy_count = 0
        degraded_count = 0
        violated_count = 0

        for _, row in df.iterrows():
            error_slo_met = row['avg_error_rate'] <= row['error_slo_target']
            response_slo_met = row['avg_response_time'] <= row['response_slo_target']

            if error_slo_met and response_slo_met:
                healthy_count += 1
            elif not error_slo_met or not response_slo_met:
                if row['avg_error_rate'] > row['error_slo_target'] * 0.8 or \
                   row['avg_response_time'] > row['response_slo_target'] * 0.8:
                    degraded_count += 1
                else:
                    violated_count += 1

        # Total requests and errors
        totals_sql = """
            SELECT
                SUM(total_count) as total_requests,
                SUM(error_count) as total_errors
            FROM service_logs
        """

        totals_df = self.db_manager.query(totals_sql)

        # Handle NaN values from empty table
        if not totals_df.empty and pd.notna(totals_df['total_requests'].iloc[0]):
            total_requests = int(totals_df['total_requests'].iloc[0])
            total_errors = int(totals_df['total_errors'].iloc[0])
        else:
            total_requests = 0
            total_errors = 0

        overall_error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

        return {
            'total_services': total_services,
            'healthy_services': healthy_count,
            'degraded_services': degraded_count,
            'violated_services': violated_count,
            'total_requests': total_requests,
            'total_errors': total_errors,
            'overall_error_rate': overall_error_rate,
            'health_percentage': (healthy_count / total_services * 100) if total_services > 0 else 0
        }

    def get_slowest_services(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get slowest services by P99 latency (or average if P99 unavailable).

        Args:
            limit: Number of slowest services to return

        Returns:
            List of slowest services
        """
        sql = f"""
            SELECT
                service_name,
                AVG(response_time_avg) as avg_response_time,
                AVG(response_time_p50) as avg_p50,
                AVG(response_time_p95) as avg_p95,
                AVG(response_time_p99) as avg_p99,
                MAX(response_time_max) as max_response_time,
                MAX(target_response_slo_sec) as response_slo_target,
                SUM(total_count) as total_requests
            FROM service_logs
            GROUP BY service_name
            ORDER BY COALESCE(avg_p99, avg_response_time) DESC
            LIMIT {limit}
        """

        df = self.db_manager.query(sql)

        results = []
        for _, row in df.iterrows():
            # Handle NaN values safely
            total_req = row['total_requests']
            avg_rt = row['avg_response_time']
            avg_p99 = row['avg_p99']
            avg_p95 = row['avg_p95']
            avg_p50 = row['avg_p50']
            slo_target = row['response_slo_target']

            # Use P99 for SLO check if available, otherwise use average
            check_value = avg_p99 if pd.notna(avg_p99) else avg_rt

            results.append({
                'service_name': row['service_name'],
                'avg_response_time': avg_rt if pd.notna(avg_rt) else 0.0,
                'response_time_p50': avg_p50 if pd.notna(avg_p50) else None,
                'response_time_p95': avg_p95 if pd.notna(avg_p95) else None,
                'response_time_p99': avg_p99 if pd.notna(avg_p99) else None,
                'max_response_time': row['max_response_time'] if pd.notna(row['max_response_time']) else 0.0,
                'response_slo_target': slo_target if pd.notna(slo_target) else 1.0,
                'total_requests': int(total_req) if pd.notna(total_req) else 0,
                'slo_met': (check_value <= slo_target) if (pd.notna(check_value) and pd.notna(slo_target)) else True
            })

        return results

    def get_error_prone_services(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get services with highest error rates.

        Args:
            limit: Number of services to return

        Returns:
            List of error-prone services
        """
        sql = f"""
            SELECT
                service_name,
                AVG(error_rate) as avg_error_rate,
                SUM(error_count) as total_errors,
                SUM(total_count) as total_requests,
                MAX(target_error_slo_perc) as error_slo_target
            FROM service_logs
            GROUP BY service_name
            HAVING avg_error_rate > 0
            ORDER BY avg_error_rate DESC
            LIMIT {limit}
        """

        df = self.db_manager.query(sql)

        results = []
        for _, row in df.iterrows():
            # Handle NaN values safely
            total_errors = row['total_errors']
            total_requests = row['total_requests']
            avg_err_rate = row['avg_error_rate']
            slo_target = row['error_slo_target']
            results.append({
                'service_name': row['service_name'],
                'avg_error_rate': avg_err_rate if pd.notna(avg_err_rate) else 0.0,
                'total_errors': int(total_errors) if pd.notna(total_errors) else 0,
                'total_requests': int(total_requests) if pd.notna(total_requests) else 0,
                'error_slo_target': slo_target if pd.notna(slo_target) else 0.0,
                'slo_met': (avg_err_rate <= slo_target) if (pd.notna(avg_err_rate) and pd.notna(slo_target)) else True
            })

        return results

    def get_error_details_by_code(self, error_code: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get detailed error logs for a specific error code.

        Args:
            error_code: Error code to search for
            limit: Number of error details to return

        Returns:
            List of error details with full log information
        """
        sql = f"""
            SELECT
                wm_transaction_name,
                error_codes,
                error_details,
                response_time_avg,
                record_time,
                wm_application_name
            FROM error_logs
            WHERE error_codes = '{error_code}'
                AND error_details IS NOT NULL
            ORDER BY record_time DESC
            LIMIT {limit}
        """

        df = self.db_manager.query(sql)

        results = []
        for _, row in df.iterrows():
            results.append({
                'transaction_name': row['wm_transaction_name'] if pd.notna(row['wm_transaction_name']) else 'Unknown',
                'error_code': row['error_codes'],
                'error_details': row['error_details'] if pd.notna(row['error_details']) else 'No details available',
                'response_time': row['response_time_avg'] if pd.notna(row['response_time_avg']) else 0.0,
                'timestamp': str(row['record_time']),
                'application': row['wm_application_name'] if pd.notna(row['wm_application_name']) else 'Unknown'
            })

        return results
