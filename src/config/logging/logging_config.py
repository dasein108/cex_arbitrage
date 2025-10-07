"""
Logging configuration manager.

Simplified logging config manager with "trust config, fail fast" philosophy.
"""

from typing import Dict, Any


class LoggingConfigManager:
    """Simple logging configuration manager."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration from config.yaml. Trust config, fail fast."""
        return self.config_data.get('logging', self._get_default_config())
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Simple default configuration."""
        return {
            'backends': {
                'console': {
                    'enabled': True,
                    'level': 'DEBUG',
                    'colored_output': True
                },
                'file': {
                    'enabled': True,
                    'level': 'INFO',
                    'file_path': 'logs/hft.log'
                }
            },
            'hft_settings': {
                'ring_buffer_size': 10000,
                'batch_size': 50
            }
        }
    
