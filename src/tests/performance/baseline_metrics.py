"""
Performance Baseline Metrics Storage and Management

This module provides persistent storage and management of performance baselines
for regression detection and performance tracking over time.

Key Features:
- Persistent baseline storage
- Historical performance tracking
- Automated regression alerts
- Performance trend analysis
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from infrastructure.logging import get_logger


@dataclass
class BaselineRecord:
    """Record of a performance baseline measurement."""
    timestamp: float
    architecture: str
    latency_avg_us: float
    latency_p95_us: float
    latency_p99_us: float
    throughput_msg_per_sec: float
    memory_allocations: int
    test_config: Dict[str, Any]
    git_commit: Optional[str] = None
    environment: Optional[str] = None


class BaselineMetricsManager:
    """Manager for performance baseline metrics storage and analysis."""
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize baseline metrics manager.
        
        Args:
            storage_path: Path to store baseline metrics (default: project root)
        """
        self.logger = get_logger("performance.baseline", tags=["performance", "baseline"])
        
        # Default storage path
        if storage_path is None:
            project_root = Path(__file__).parent.parent.parent.parent.parent
            storage_path = project_root / "performance_baselines.json"
        
        self.storage_path = Path(storage_path)
        self.baselines: Dict[str, List[BaselineRecord]] = self._load_baselines()
    
    def _load_baselines(self) -> Dict[str, List[BaselineRecord]]:
        """Load existing baselines from storage."""
        if not self.storage_path.exists():
            self.logger.info("No existing baseline file found, starting fresh",
                           storage_path=str(self.storage_path))
            return {"legacy": [], "direct": []}
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            baselines = {}
            for arch, records in data.items():
                baselines[arch] = [
                    BaselineRecord(**record) for record in records
                ]
            
            self.logger.info("Loaded existing baselines",
                           storage_path=str(self.storage_path),
                           architectures=list(baselines.keys()),
                           total_records=sum(len(records) for records in baselines.values()))
            
            return baselines
            
        except Exception as e:
            self.logger.error("Failed to load baselines, starting fresh",
                            error=str(e),
                            storage_path=str(self.storage_path))
            return {"legacy": [], "direct": []}
    
    def _save_baselines(self) -> None:
        """Save baselines to persistent storage."""
        try:
            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            data = {}
            for arch, records in self.baselines.items():
                data[arch] = [asdict(record) for record in records]
            
            # Write to file
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug("Baselines saved successfully",
                            storage_path=str(self.storage_path))
            
        except Exception as e:
            self.logger.error("Failed to save baselines",
                            error=str(e),
                            storage_path=str(self.storage_path))
    
    def record_baseline(
        self,
        architecture: str,
        metrics: Dict[str, Any],
        test_config: Dict[str, Any],
        git_commit: Optional[str] = None,
        environment: Optional[str] = None
    ) -> BaselineRecord:
        """
        Record a new baseline measurement.
        
        Args:
            architecture: Architecture type (legacy/direct)
            metrics: Performance metrics from test
            test_config: Test configuration used
            git_commit: Git commit hash
            environment: Environment name (dev/staging/prod)
            
        Returns:
            BaselineRecord instance
        """
        record = BaselineRecord(
            timestamp=time.time(),
            architecture=architecture,
            latency_avg_us=metrics.get('latency_avg_us', 0),
            latency_p95_us=metrics.get('latency_p95_us', 0),
            latency_p99_us=metrics.get('latency_p99_us', 0),
            throughput_msg_per_sec=metrics.get('throughput_msg_per_sec', 0),
            memory_allocations=metrics.get('memory_allocations', 0),
            test_config=test_config,
            git_commit=git_commit,
            environment=environment or "unknown"
        )
        
        # Add to baselines
        if architecture not in self.baselines:
            self.baselines[architecture] = []
        
        self.baselines[architecture].append(record)
        
        # Save to persistent storage
        self._save_baselines()
        
        self.logger.info("New baseline recorded",
                        architecture=architecture,
                        latency_avg_us=record.latency_avg_us,
                        throughput_msg_per_sec=record.throughput_msg_per_sec,
                        environment=environment)
        
        return record
    
    def get_latest_baseline(self, architecture: str) -> Optional[BaselineRecord]:
        """Get the most recent baseline for an architecture."""
        if architecture not in self.baselines or not self.baselines[architecture]:
            return None
        
        return max(self.baselines[architecture], key=lambda r: r.timestamp)
    
    def get_baseline_history(
        self,
        architecture: str,
        days: int = 30
    ) -> List[BaselineRecord]:
        """
        Get baseline history for an architecture.
        
        Args:
            architecture: Architecture type
            days: Number of days of history to return
            
        Returns:
            List of baseline records within the time period
        """
        if architecture not in self.baselines:
            return []
        
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        return [
            record for record in self.baselines[architecture]
            if record.timestamp >= cutoff_time
        ]
    
    def analyze_performance_trend(
        self,
        architecture: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze performance trends over time.
        
        Args:
            architecture: Architecture type
            days: Number of days to analyze
            
        Returns:
            Trend analysis results
        """
        history = self.get_baseline_history(architecture, days)
        
        if len(history) < 2:
            return {
                'trend': 'insufficient_data',
                'records_count': len(history),
                'analysis': 'Need at least 2 baseline records for trend analysis'
            }
        
        # Sort by timestamp
        history.sort(key=lambda r: r.timestamp)
        
        # Calculate trends
        latencies = [r.latency_avg_us for r in history]
        throughputs = [r.throughput_msg_per_sec for r in history]
        
        # Simple linear trend calculation
        latency_trend = self._calculate_trend(latencies)
        throughput_trend = self._calculate_trend(throughputs)
        
        # Performance evaluation
        latest = history[-1]
        oldest = history[0]
        
        latency_change_pct = (
            (latest.latency_avg_us - oldest.latency_avg_us) / oldest.latency_avg_us * 100
            if oldest.latency_avg_us > 0 else 0
        )
        
        throughput_change_pct = (
            (latest.throughput_msg_per_sec - oldest.throughput_msg_per_sec) / oldest.throughput_msg_per_sec * 100
            if oldest.throughput_msg_per_sec > 0 else 0
        )
        
        return {\n            'trend': 'improving' if latency_trend < 0 and throughput_trend > 0 else 'degrading' if latency_trend > 0 or throughput_trend < 0 else 'stable',\n            'records_count': len(history),\n            'time_span_days': (latest.timestamp - oldest.timestamp) / (24 * 60 * 60),\n            'latency_trend': {\n                'direction': 'decreasing' if latency_trend < 0 else 'increasing' if latency_trend > 0 else 'stable',\n                'change_pct': latency_change_pct,\n                'current_avg_us': latest.latency_avg_us,\n                'baseline_avg_us': oldest.latency_avg_us\n            },\n            'throughput_trend': {\n                'direction': 'increasing' if throughput_trend > 0 else 'decreasing' if throughput_trend < 0 else 'stable',\n                'change_pct': throughput_change_pct,\n                'current_msg_per_sec': latest.throughput_msg_per_sec,\n                'baseline_msg_per_sec': oldest.throughput_msg_per_sec\n            }\n        }\n    \n    def _calculate_trend(self, values: List[float]) -> float:\n        \"\"\"Calculate simple linear trend (positive = increasing, negative = decreasing).\"\"\"\n        if len(values) < 2:\n            return 0.0\n        \n        n = len(values)\n        x_sum = sum(range(n))\n        y_sum = sum(values)\n        xy_sum = sum(i * values[i] for i in range(n))\n        x2_sum = sum(i * i for i in range(n))\n        \n        # Linear regression slope\n        slope = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)\n        return slope\n    \n    def detect_regression(\n        self,\n        current_metrics: Dict[str, Any],\n        architecture: str,\n        regression_threshold_pct: float = 10.0\n    ) -> Dict[str, Any]:\n        \"\"\"Detect performance regression against latest baseline.\"\"\"\n        \n        latest_baseline = self.get_latest_baseline(architecture)\n        \n        if not latest_baseline:\n            return {\n                'has_regression': False,\n                'reason': 'no_baseline_available',\n                'recommendation': f'Establish baseline for {architecture} architecture'\n            }\n        \n        # Calculate performance changes\n        latency_change_pct = (\n            (current_metrics.get('latency_avg_us', 0) - latest_baseline.latency_avg_us) / \n            latest_baseline.latency_avg_us * 100\n            if latest_baseline.latency_avg_us > 0 else 0\n        )\n        \n        throughput_change_pct = (\n            (latest_baseline.throughput_msg_per_sec - current_metrics.get('throughput_msg_per_sec', 0)) / \n            latest_baseline.throughput_msg_per_sec * 100\n            if latest_baseline.throughput_msg_per_sec > 0 else 0\n        )\n        \n        # Detect regressions\n        regressions = []\n        \n        if latency_change_pct > regression_threshold_pct:\n            regressions.append({\n                'metric': 'latency',\n                'change_pct': latency_change_pct,\n                'current_value': current_metrics.get('latency_avg_us', 0),\n                'baseline_value': latest_baseline.latency_avg_us,\n                'threshold_pct': regression_threshold_pct\n            })\n        \n        if throughput_change_pct > regression_threshold_pct:\n            regressions.append({\n                'metric': 'throughput',\n                'change_pct': throughput_change_pct,\n                'current_value': current_metrics.get('throughput_msg_per_sec', 0),\n                'baseline_value': latest_baseline.throughput_msg_per_sec,\n                'threshold_pct': regression_threshold_pct\n            })\n        \n        has_regression = len(regressions) > 0\n        \n        result = {\n            'has_regression': has_regression,\n            'regressions': regressions,\n            'baseline_timestamp': latest_baseline.timestamp,\n            'baseline_age_hours': (time.time() - latest_baseline.timestamp) / 3600,\n            'changes': {\n                'latency_change_pct': latency_change_pct,\n                'throughput_change_pct': throughput_change_pct\n            }\n        }\n        \n        if has_regression:\n            self.logger.warning(\"Performance regression detected\",\n                              architecture=architecture,\n                              regressions=regressions)\n        else:\n            self.logger.info(\"No performance regression detected\",\n                           architecture=architecture,\n                           latency_change_pct=latency_change_pct,\n                           throughput_change_pct=throughput_change_pct)\n        \n        return result\n    \n    def get_performance_summary(self) -> Dict[str, Any]:\n        \"\"\"Get comprehensive performance summary across all architectures.\"\"\"\n        summary = {\n            'total_baselines': sum(len(records) for records in self.baselines.values()),\n            'architectures': {},\n            'overall_status': 'healthy',\n            'last_updated': max(\n                record.timestamp \n                for records in self.baselines.values() \n                for record in records\n            ) if any(self.baselines.values()) else None\n        }\n        \n        for arch, records in self.baselines.items():\n            if not records:\n                summary['architectures'][arch] = {\n                    'status': 'no_data',\n                    'records_count': 0\n                }\n                continue\n            \n            latest = max(records, key=lambda r: r.timestamp)\n            trend = self.analyze_performance_trend(arch, days=7)\n            \n            summary['architectures'][arch] = {\n                'status': 'healthy',\n                'records_count': len(records),\n                'latest_baseline': {\n                    'timestamp': latest.timestamp,\n                    'latency_avg_us': latest.latency_avg_us,\n                    'throughput_msg_per_sec': latest.throughput_msg_per_sec,\n                    'age_hours': (time.time() - latest.timestamp) / 3600\n                },\n                'trend': trend['trend'],\n                'performance_change_7d': {\n                    'latency_change_pct': trend.get('latency_trend', {}).get('change_pct', 0),\n                    'throughput_change_pct': trend.get('throughput_trend', {}).get('change_pct', 0)\n                }\n            }\n        \n        return summary\n\n\n# Global baseline manager instance\n_baseline_manager = None\n\n\ndef get_baseline_manager() -> BaselineMetricsManager:\n    \"\"\"Get global baseline manager instance.\"\"\"\n    global _baseline_manager\n    if _baseline_manager is None:\n        _baseline_manager = BaselineMetricsManager()\n    return _baseline_manager\n\n\n# Convenience functions\ndef record_performance_baseline(\n    architecture: str,\n    metrics: Dict[str, Any],\n    test_config: Dict[str, Any],\n    git_commit: Optional[str] = None\n) -> BaselineRecord:\n    \"\"\"Record a performance baseline using the global manager.\"\"\"\n    manager = get_baseline_manager()\n    return manager.record_baseline(architecture, metrics, test_config, git_commit)\n\n\ndef check_for_regression(\n    current_metrics: Dict[str, Any],\n    architecture: str,\n    threshold_pct: float = 10.0\n) -> bool:\n    \"\"\"Check if current metrics represent a performance regression.\"\"\"\n    manager = get_baseline_manager()\n    result = manager.detect_regression(current_metrics, architecture, threshold_pct)\n    return result['has_regression']\n\n\nif __name__ == \"__main__\":\n    # Example usage\n    manager = BaselineMetricsManager()\n    \n    # Get performance summary\n    summary = manager.get_performance_summary()\n    print(f\"Performance Summary: {json.dumps(summary, indent=2)}\")\n    \n    # Analyze trends if data exists\n    for arch in ['legacy', 'direct']:\n        trend = manager.analyze_performance_trend(arch)\n        print(f\"{arch.title()} Architecture Trend: {trend['trend']}\")\n        if trend['trend'] != 'insufficient_data':\n            print(f\"  Latency trend: {trend['latency_trend']['direction']} ({trend['latency_trend']['change_pct']:.1f}%)\")\n            print(f\"  Throughput trend: {trend['throughput_trend']['direction']} ({trend['throughput_trend']['change_pct']:.1f}%)\")"