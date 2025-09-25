"""
Database configuration validator.

Provides validation capabilities for database configuration including:
- Connectivity testing
- Performance settings validation
- HFT-specific requirements validation
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from ..structs import DatabaseConfig
from infrastructure.exceptions.exchange import ConfigurationError


class DatabaseConfigValidator:
    """Validates database configuration and connectivity."""
    
    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self._logger = logging.getLogger(__name__)
    
    async def validate_connectivity(self, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Test database connectivity with comprehensive diagnostics.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Dictionary with connection test results
            
        Raises:
            ConfigurationError: If database connection fails
        """
        connection_info = {
            "success": False,
            "connection_time_ms": 0.0,
            "server_version": None,
            "error": None
        }
        
        try:
            # Try to import asyncpg
            try:
                import asyncpg
            except ImportError:
                raise ConfigurationError(
                    "asyncpg is required for database connectivity validation. Install with: pip install asyncpg",
                    "database.connectivity"
                )
            
            # Test connection with timing
            import time
            start_time = time.perf_counter()
            
            conn = await asyncpg.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                database=self.db_config.database,
                user=self.db_config.username,
                password=self.db_config.password,
                timeout=timeout
            )
            
            connection_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
            
            # Get server version
            server_version = await conn.fetchval("SELECT version()")
            
            await conn.close()
            
            connection_info.update({
                "success": True,
                "connection_time_ms": connection_time,
                "server_version": server_version
            })
            
            self._logger.info(f"Database connection successful in {connection_time:.2f}ms")
            
            # Validate connection time for HFT requirements
            if connection_time > 1000:  # 1 second
                self._logger.warning(f"Database connection time {connection_time:.2f}ms exceeds HFT requirements")
            
        except asyncio.TimeoutError:
            error_msg = f"Database connection timeout after {timeout}s"
            connection_info["error"] = error_msg
            self._logger.error(error_msg)
            raise ConfigurationError(error_msg, "database.connectivity")
        except Exception as e:
            error_msg = f"Database connection failed: {e}"
            connection_info["error"] = str(e)
            self._logger.error(error_msg)
            raise ConfigurationError(error_msg, "database.connectivity") from e
        
        return connection_info
    
    def validate_pool_settings(self) -> List[str]:
        """
        Validate connection pool settings and return warnings.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Pool size validation
        if self.db_config.max_pool_size > 100:
            warnings.append(
                f"max_pool_size ({self.db_config.max_pool_size}) > 100 may cause severe resource exhaustion"
            )
        elif self.db_config.max_pool_size > 50:
            warnings.append(
                f"max_pool_size ({self.db_config.max_pool_size}) > 50 may cause resource exhaustion"
            )
        
        if self.db_config.min_pool_size < 3:
            warnings.append(
                f"min_pool_size ({self.db_config.min_pool_size}) < 3 may cause connection delays in HFT operations"
            )
        elif self.db_config.min_pool_size < 5:
            warnings.append(
                f"min_pool_size ({self.db_config.min_pool_size}) < 5 may cause connection delays"
            )
        
        # Pool efficiency warnings
        pool_ratio = self.db_config.min_pool_size / self.db_config.max_pool_size
        if pool_ratio < 0.2:
            warnings.append(
                f"Pool ratio ({pool_ratio:.2f}) < 0.2 may cause frequent pool scaling"
            )
        
        # Query capacity validation
        if self.db_config.max_queries < 5000:
            warnings.append(
                f"max_queries ({self.db_config.max_queries}) < 5000 may severely limit HFT performance"
            )
        elif self.db_config.max_queries < 10000:
            warnings.append(
                f"max_queries ({self.db_config.max_queries}) < 10000 may limit HFT performance"
            )
        
        return warnings
    
    def validate_performance_settings(self) -> List[str]:
        """
        Validate settings for HFT performance requirements.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Connection lifetime validation
        if self.db_config.max_inactive_connection_lifetime > 1800:  # 30 minutes
            warnings.append(
                f"max_inactive_connection_lifetime ({self.db_config.max_inactive_connection_lifetime}s) > 30min may waste resources"
            )
        elif self.db_config.max_inactive_connection_lifetime > 600:  # 10 minutes
            warnings.append(
                f"max_inactive_connection_lifetime ({self.db_config.max_inactive_connection_lifetime}s) > 10min may waste resources"
            )
        
        # Command timeout validation for HFT
        if self.db_config.command_timeout > 60:
            warnings.append(
                f"command_timeout ({self.db_config.command_timeout}s) > 60s may cause HFT trading delays"
            )
        elif self.db_config.command_timeout > 30:
            warnings.append(
                f"command_timeout ({self.db_config.command_timeout}s) > 30s may impact HFT latency requirements"
            )
        
        if self.db_config.command_timeout < 5:
            warnings.append(
                f"command_timeout ({self.db_config.command_timeout}s) < 5s may cause query timeouts"
            )
        
        # Statement cache validation
        if self.db_config.statement_cache_size < 512:
            warnings.append(
                f"statement_cache_size ({self.db_config.statement_cache_size}) < 512 may impact query performance"
            )
        elif self.db_config.statement_cache_size > 4096:
            warnings.append(
                f"statement_cache_size ({self.db_config.statement_cache_size}) > 4096 may waste memory"
            )
        
        return warnings
    
    def validate_hft_compliance(self) -> Dict[str, Any]:
        """
        Comprehensive validation for HFT compliance.
        
        Returns:
            Dictionary with compliance results and recommendations
        """
        compliance_result = {
            "compliant": True,
            "critical_issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Critical issues that would prevent HFT operation
        if self.db_config.max_queries < 1000:
            compliance_result["critical_issues"].append(
                "max_queries < 1000 will severely limit HFT throughput"
            )
            compliance_result["compliant"] = False
        
        if self.db_config.command_timeout > 120:
            compliance_result["critical_issues"].append(
                "command_timeout > 2min will cause unacceptable trading delays"
            )
            compliance_result["compliant"] = False
        
        if self.db_config.max_pool_size < 5:
            compliance_result["critical_issues"].append(
                "max_pool_size < 5 insufficient for concurrent HFT operations"
            )
            compliance_result["compliant"] = False
        
        # Collect all warnings
        pool_warnings = self.validate_pool_settings()
        performance_warnings = self.validate_performance_settings()
        compliance_result["warnings"] = pool_warnings + performance_warnings
        
        # HFT-specific recommendations
        recommendations = []
        
        if self.db_config.max_pool_size < 20:
            recommendations.append("Consider increasing max_pool_size to 20+ for optimal HFT performance")
        
        if self.db_config.statement_cache_size < 1024:
            recommendations.append("Consider increasing statement_cache_size to 1024+ for better query performance")
        
        if self.db_config.max_queries < 50000:
            recommendations.append("Consider increasing max_queries to 50000+ for high-frequency operations")
        
        compliance_result["recommendations"] = recommendations
        
        return compliance_result
    
    async def run_comprehensive_validation(self) -> Dict[str, Any]:
        """
        Run complete database validation suite.
        
        Returns:
            Dictionary with complete validation results
        """
        validation_results = {
            "database_config": {
                "host": self.db_config.host,
                "port": self.db_config.port,
                "database": self.db_config.database,
                "username": self.db_config.username
            },
            "connectivity": {},
            "hft_compliance": {},
            "overall_status": "unknown"
        }
        
        try:
            # Test connectivity
            connectivity_result = await self.validate_connectivity()
            validation_results["connectivity"] = connectivity_result
            
            # Check HFT compliance
            hft_compliance = self.validate_hft_compliance()
            validation_results["hft_compliance"] = hft_compliance
            
            # Determine overall status
            if connectivity_result["success"] and hft_compliance["compliant"]:
                validation_results["overall_status"] = "ready"
            elif connectivity_result["success"]:
                validation_results["overall_status"] = "connected_but_not_optimized"
            else:
                validation_results["overall_status"] = "connection_failed"
                
        except Exception as e:
            validation_results["overall_status"] = "validation_failed"
            validation_results["error"] = str(e)
            self._logger.error(f"Comprehensive validation failed: {e}")
        
        return validation_results
    
    def get_optimization_suggestions(self) -> List[str]:
        """
        Get specific optimization suggestions for the current configuration.
        
        Returns:
            List of optimization suggestions
        """
        suggestions = []
        
        # Connection pool optimization
        if self.db_config.max_pool_size < 20:
            suggestions.append("Increase max_pool_size to 20-30 for better concurrent request handling")
        
        if self.db_config.min_pool_size < 10:
            suggestions.append("Increase min_pool_size to 10-15 to reduce connection startup overhead")
        
        # Performance optimization
        if self.db_config.command_timeout > 30:
            suggestions.append("Reduce command_timeout to 15-30 seconds for faster failure detection")
        
        if self.db_config.statement_cache_size < 1024:
            suggestions.append("Increase statement_cache_size to 1024-2048 for better query performance")
        
        # HFT-specific optimization
        if self.db_config.max_queries < 50000:
            suggestions.append("Increase max_queries to 50000+ for high-frequency trading operations")
        
        if self.db_config.max_inactive_connection_lifetime > 300:
            suggestions.append("Consider reducing max_inactive_connection_lifetime to 300s or less")
        
        # Environment-specific suggestions
        suggestions.append("Consider setting up connection pooling at application level for optimal performance")
        suggestions.append("Enable statement-level connection pooling for repeated queries")
        suggestions.append("Monitor database performance metrics in production environment")
        
        return suggestions