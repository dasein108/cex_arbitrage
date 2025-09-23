"""
File Backend for Persistent Logging

High-performance file logging with async I/O, rotation, and structured formats.
Handles warnings, errors, and audit logs with full context preservation.

HFT COMPLIANT: Async I/O, minimal blocking, error resilience.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import aiofiles
import aiofiles.os

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType


class FileBackend(LogBackend):
    """
    High-performance file logging backend.
    
    Features:
    - Async I/O for non-blocking writes
    - Configurable format (text/JSON)
    - Automatic directory creation
    - Error resilience with fallback
    - File rotation support
    """
    
    def __init__(self, name: str = "file", config: Dict[str, Any] = None):
        super().__init__(name, config)
        
        # Configuration
        config = config or {}
        self.file_path = Path(config.get('file_path', 'logs/hft.log'))
        self.format_type = config.get('format', 'text')  # 'text' or 'json'
        min_level_config = config.get('min_level', LogLevel.WARNING)
        if isinstance(min_level_config, str):
            self.min_level = LogLevel[min_level_config.upper()]
        else:
            self.min_level = LogLevel(min_level_config)
        self.include_types = set(config.get('include_types', [LogType.TEXT, LogType.AUDIT]))
        self.max_file_size = config.get('max_file_size_mb', 100) * 1024 * 1024  # Convert to bytes
        self.backup_count = config.get('backup_count', 5)
        self.buffer_size = config.get('buffer_size', 8192)
        self.flush_interval = config.get('flush_interval', 5.0)  # seconds
        
        # Ensure log directory exists
        self._ensure_directory()
        
        # Buffering for performance
        self._write_buffer = []
        self._last_flush = time.time()
        self._lock = asyncio.Lock()
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle warnings/errors and audit logs."""
        if not self.enabled:
            return False
        
        # Check level threshold
        if record.level < self.min_level:
            return False
        
        # Check log type
        if record.log_type not in self.include_types:
            return False
        
        return True
    
    async def write(self, record: LogRecord) -> None:
        """Write record to file with buffering."""
        try:
            # Format the record
            if self.format_type == 'json':
                formatted = self._format_json(record)
            else:
                formatted = self._format_text(record)
            
            # Add to buffer
            async with self._lock:
                self._write_buffer.append(formatted)
                
                # Check if we should flush
                should_flush = (
                    len(self._write_buffer) >= 50 or  # Buffer size
                    time.time() - self._last_flush > self.flush_interval or  # Time-based
                    record.level >= LogLevel.ERROR  # Immediate flush for errors
                )
                
                if should_flush:
                    await self._flush_buffer()
        
        except Exception as e:
            # Handle file errors gracefully
            self._handle_error(e)
            # Fallback to console
            print(f"FileBackend error: {e}")
            print(f"{record.level.name}: {record.logger_name}: {record.message}")
    
    async def flush(self) -> None:
        """Flush buffered data to file."""
        async with self._lock:
            await self._flush_buffer()
    
    async def _flush_buffer(self) -> None:
        """Internal method to flush write buffer."""
        if not self._write_buffer:
            return
        
        try:
            # Check file rotation
            await self._check_rotation()
            
            # Write all buffered lines
            async with aiofiles.open(self.file_path, 'a', buffering=self.buffer_size) as f:
                for line in self._write_buffer:
                    await f.write(line + '\n')
            
            # Clear buffer
            self._write_buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            # File write failed
            self._handle_error(e)
            # Clear buffer to prevent memory growth
            self._write_buffer.clear()
    
    async def _check_rotation(self) -> None:
        """Check if file needs rotation."""
        try:
            if await aiofiles.os.path.exists(self.file_path):
                stat = await aiofiles.os.stat(self.file_path)
                if stat.st_size > self.max_file_size:
                    await self._rotate_file()
        except Exception as e:
            # Rotation failed, continue with current file
            print(f"File rotation error: {e}")
    
    async def _rotate_file(self) -> None:
        """Rotate log file."""
        try:
            # Move existing backups
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = self.file_path.with_suffix(f'.{i}{self.file_path.suffix}')
                new_backup = self.file_path.with_suffix(f'.{i+1}{self.file_path.suffix}')
                
                if await aiofiles.os.path.exists(old_backup):
                    if await aiofiles.os.path.exists(new_backup):
                        await aiofiles.os.remove(new_backup)
                    await aiofiles.os.rename(old_backup, new_backup)
            
            # Move current file to .1
            backup_path = self.file_path.with_suffix(f'.1{self.file_path.suffix}')
            if await aiofiles.os.path.exists(self.file_path):
                await aiofiles.os.rename(self.file_path, backup_path)
                
        except Exception as e:
            print(f"File rotation error: {e}")
    
    def _ensure_directory(self) -> None:
        """Ensure log directory exists."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Failed to create log directory: {e}")
            # Try to use current directory as fallback
            self.file_path = Path(self.file_path.name)
    
    def _format_text(self, record: LogRecord) -> str:
        """Format record as human-readable text."""
        # Timestamp
        dt = datetime.fromtimestamp(record.timestamp)
        timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Millisecond precision
        
        # Level and logger
        level_str = record.level.name.ljust(8)
        logger_str = record.logger_name
        
        # Base message
        message = f"{timestamp_str} {level_str} {logger_str}: {record.message}"
        
        # Add context
        if record.context:
            context_parts = []
            for key, value in record.context.items():
                # Handle complex values
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, separators=(',', ':'))
                else:
                    value_str = str(value)
                
                # Limit length
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."
                
                context_parts.append(f"{key}={value_str}")
            
            if context_parts:
                message += f" | {', '.join(context_parts)}"
        
        # Add correlation info
        correlation_parts = []
        if record.correlation_id:
            correlation_parts.append(f"correlation_id={record.correlation_id}")
        if record.exchange:
            correlation_parts.append(f"exchange={record.exchange}")
        if record.symbol:
            correlation_parts.append(f"symbol={record.symbol}")
        
        if correlation_parts:
            message += f" | {', '.join(correlation_parts)}"
        
        # Add log type for non-text logs
        if record.log_type != LogType.TEXT:
            message += f" | type={record.log_type.name}"
        
        return message
    
    def _format_json(self, record: LogRecord) -> str:
        """Format record as JSON for structured logging."""
        data = {
            'timestamp': record.timestamp,
            'iso_timestamp': datetime.fromtimestamp(record.timestamp).isoformat(),
            'level': record.level.name,
            'type': record.log_type.name,
            'logger': record.logger_name,
            'message': record.message
        }
        
        # Add context
        if record.context:
            data['context'] = record.context
        
        # Add correlation tracking
        if record.correlation_id:
            data['correlation_id'] = record.correlation_id
        if record.exchange:
            data['exchange'] = record.exchange
        if record.symbol:
            data['symbol'] = record.symbol
        
        # Add metric data for metrics
        if record.log_type == LogType.METRIC and record.metric_name:
            data['metric'] = {
                'name': record.metric_name,
                'value': record.metric_value,
                'tags': record.metric_tags
            }
        
        try:
            return json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        except Exception as e:
            # JSON encoding failed, fallback to text
            return self._format_text(record)


class RotatingFileBackend(FileBackend):
    """
    File backend with time-based rotation.
    
    Creates new files based on time intervals (daily, hourly, etc.)
    """
    
    def __init__(self, name: str = "rotating_file", config: Dict[str, Any] = None):
        config = config or {}
        
        # Time-based rotation settings
        self.rotation_interval = config.get('rotation_interval', 'daily')  # 'hourly', 'daily', 'weekly'
        self.date_format = config.get('date_format', '%Y-%m-%d')
        
        # Modify file path to include date
        base_path = Path(config.get('file_path', 'logs/hft.log'))
        self._base_path = base_path
        self._current_date = None
        
        # Update config with current dated path
        config['file_path'] = str(self._get_current_file_path())
        
        super().__init__(name, config)
    
    def _get_current_file_path(self) -> Path:
        """Get file path with current date."""
        now = datetime.now()
        
        if self.rotation_interval == 'hourly':
            date_str = now.strftime('%Y-%m-%d_%H')
        elif self.rotation_interval == 'daily':
            date_str = now.strftime('%Y-%m-%d')
        elif self.rotation_interval == 'weekly':
            # Get Monday of current week
            monday = now - datetime.timedelta(days=now.weekday())
            date_str = monday.strftime('%Y-%m-%d_week')
        else:
            date_str = now.strftime('%Y-%m-%d')
        
        # Insert date before file extension
        stem = self._base_path.stem
        suffix = self._base_path.suffix
        return self._base_path.with_name(f"{stem}_{date_str}{suffix}")
    
    async def _check_rotation(self) -> None:
        """Check if we need to rotate to a new file."""
        current_path = self._get_current_file_path()
        
        if current_path != self.file_path:
            # Date changed, switch to new file
            self.file_path = current_path
            self._ensure_directory()


class AuditFileBackend(FileBackend):
    """
    Specialized file backend for audit logs.
    
    Always uses JSON format and includes additional audit metadata.
    """
    
    def __init__(self, name: str = "audit_file", config: Dict[str, Any] = None):
        config = config or {}
        
        # Force audit-specific settings
        config['format'] = 'json'
        config['file_path'] = config.get('file_path', 'logs/audit.log')
        config['include_types'] = [LogType.AUDIT]
        config['min_level'] = LogLevel.INFO
        
        super().__init__(name, config)
    
    def _format_json(self, record: LogRecord) -> str:
        """Enhanced JSON format for audit logs."""
        data = super()._format_json(record)
        
        # Parse back to dict to add audit metadata
        try:
            audit_data = json.loads(data)
            
            # Add audit-specific fields
            audit_data['audit_version'] = '1.0'
            audit_data['process_id'] = os.getpid()
            audit_data['hostname'] = os.uname().nodename if hasattr(os, 'uname') else 'unknown'
            
            # Add sequence number for ordering
            if not hasattr(self, '_sequence_counter'):
                self._sequence_counter = 0
            self._sequence_counter += 1
            audit_data['sequence'] = self._sequence_counter
            
            return json.dumps(audit_data, separators=(',', ':'))
            
        except Exception:
            # Fallback to original data
            return data