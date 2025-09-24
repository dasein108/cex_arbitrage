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
from typing import Optional
import aiofiles
import aiofiles.os

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType
from ..structs import FileBackendConfig, AuditBackendConfig


class FileBackend(LogBackend):
    """
    High-performance file logging backend.
    
    Features:
    - Async I/O for non-blocking writes
    - Configurable format (text/JSON)
    - Automatic directory creation
    - Error resilience with fallback
    - File rotation support
    
    Accepts only FileBackendConfig struct for configuration.
    """
    
    def __init__(self, config: FileBackendConfig, name: str = "file"):
        """
        Initialize file backend with struct configuration.
        
        Args:
            name: Backend name
            config: FileBackendConfig struct (required)
        """
        if not isinstance(config, FileBackendConfig):
            raise TypeError(f"Expected FileBackendConfig, got {type(config)}")
        
        super().__init__(name, {})  # Empty dict for composite class compatibility
        
        # Store struct config
        self.config = config
        
        # Configuration from struct
        self.file_path = Path(config.path)
        self.format_type = config.format  # 'text' or 'json'
        if isinstance(config.min_level, str):
            self.min_level = LogLevel[config.min_level.upper()]
        else:
            self.min_level = LogLevel(config.min_level)
        self.include_types = set([LogType.TEXT, LogType.AUDIT])  # Default types
        self.max_file_size = config.max_size_mb * 1024 * 1024  # Convert to bytes
        self.backup_count = config.backup_count
        self.buffer_size = config.buffer_size
        self.flush_interval = config.flush_interval
        
        # Enable based on struct config
        self.enabled = config.enabled
        
        # Ensure log directory exists
        if self.enabled:
            self._ensure_directory()
        
        # Buffering for performance
        self._write_buffer = []
        self._last_flush = time.time()
        self._lock = asyncio.Lock()
    
    def should_handle(self, record: LogRecord) -> bool:
        """
        Handle warnings, errors, and audit logs.
        
        Fast filtering - called in hot path.
        """
        if not self.enabled:
            return False
        
        # Check level threshold
        if record.level < self.min_level:
            return False
        
        # Handle warnings/errors and audit logs
        return (
            record.level >= LogLevel.WARNING or 
            record.log_type in self.include_types
        )
    
    async def write(self, record: LogRecord) -> None:
        """Async write with buffering for performance."""
        if not self.enabled:
            return
        
        async with self._lock:
            # Format message
            if self.format_type == 'json':
                formatted = self._format_json(record)
            else:
                formatted = self._format_text(record)
            
            # Add to buffer
            self._write_buffer.append(formatted)
            
            # Flush if buffer is full or time interval reached
            current_time = time.time()
            should_flush = (
                len(self._write_buffer) >= self.buffer_size or
                (current_time - self._last_flush) >= self.flush_interval
            )
            
            if should_flush:
                await self._flush_buffer()
    
    async def flush(self) -> None:
        """Force flush of buffered messages."""
        if not self.enabled:
            return
        
        async with self._lock:
            await self._flush_buffer()
    
    async def _flush_buffer(self) -> None:
        """Internal buffer flush implementation."""
        if not self._write_buffer:
            return
        
        try:
            # Check file rotation before writing
            await self._check_rotation()
            
            # Write all buffered messages
            async with aiofiles.open(self.file_path, 'a', encoding='utf-8') as f:
                for message in self._write_buffer:
                    await f.write(message + '\n')
                
            # Clear buffer and update flush time
            self._write_buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            # Log error but don't fail
            print(f"FileBackend flush error: {e}")
    
    def _ensure_directory(self) -> None:
        """Ensure log directory exists."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"FileBackend directory creation error: {e}")
    
    async def _check_rotation(self) -> None:
        """Check if file rotation is needed."""
        try:
            if not self.file_path.exists():
                return
            
            # Check file size
            file_size = await aiofiles.os.path.getsize(self.file_path)
            if file_size >= self.max_file_size:
                await self._rotate_file()
                
        except Exception as e:
            print(f"FileBackend rotation check error: {e}")
    
    async def _rotate_file(self) -> None:
        """Rotate log files when max size is reached."""
        try:
            # Rotate backup files
            for i in range(self.backup_count - 1, 0, -1):
                old_file = self.file_path.with_suffix(f'.{i}')
                new_file = self.file_path.with_suffix(f'.{i + 1}')
                
                if old_file.exists():
                    if new_file.exists():
                        new_file.unlink()  # Remove oldest backup
                    old_file.rename(new_file)
            
            # Move current file to .1
            if self.file_path.exists():
                backup_file = self.file_path.with_suffix('.1')
                if backup_file.exists():
                    backup_file.unlink()
                self.file_path.rename(backup_file)
                
        except Exception as e:
            print(f"FileBackend rotation error: {e}")
    
    def _format_text(self, record: LogRecord) -> str:
        """Format as readable text."""
        timestamp = datetime.fromtimestamp(record.timestamp).isoformat()
        
        message = f"[{timestamp}] {record.level.name} {record.logger_name}: {record.message}"
        
        # Add context
        if record.context:
            context_parts = [f"{k}={v}" for k, v in record.context.items()]
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
        
        return message
    
    def _format_json(self, record: LogRecord) -> str:
        """Format as JSON for structured logging."""
        data = {
            'timestamp': record.timestamp,
            'level': record.level.name,
            'type': record.log_type.name,
            'logger': record.logger_name,
            'message': record.message
        }
        
        # Add context
        if record.context:
            data['context'] = record.context
        
        # Add correlation info
        if record.correlation_id:
            data['correlation_id'] = record.correlation_id
        if record.exchange:
            data['exchange'] = record.exchange
        if record.symbol:
            data['symbol'] = record.symbol
        
        # Add metric info for metrics
        if record.log_type == LogType.METRIC:
            data['metric'] = {
                'name': record.metric_name,
                'value': record.metric_value,
                'tags': record.metric_tags
            }
        
        return json.dumps(data, separators=(',', ':'))


class AuditFileBackend(FileBackend):
    """
    Specialized file backend for audit logs.
    
    Always uses JSON format and includes additional audit metadata.
    Accepts only AuditBackendConfig struct for configuration.
    """
    
    def __init__(self, config: AuditBackendConfig, name: str = "audit_file"):
        """
        Initialize audit file backend with struct configuration.
        
        Args:
            name: Backend name
            config: AuditBackendConfig struct (required)
        """
        if not isinstance(config, AuditBackendConfig):
            raise TypeError(f"Expected AuditBackendConfig, got {type(config)}")
        
        # Convert to FileBackendConfig for parent class
        file_config = FileBackendConfig(
            enabled=config.enabled,
            min_level=config.min_level,
            environment=config.environment,
            path=config.path,
            format=config.format,
            max_size_mb=100,  # Use reasonable default
            backup_count=10,  # More backups for audit logs
            buffer_size=1024,
            flush_interval=1.0  # Faster flush for audit
        )
        
        super().__init__(file_config, name)
        
        # Store audit config
        self.audit_config = config
        self.include_all_context = config.include_all_context
        self.immutable = config.immutable
        
        # Override include types for audit
        self.include_types = set([LogType.AUDIT])
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle audit logs only."""
        if not self.enabled:
            return False
        
        # Check level threshold
        if record.level < self.min_level:
            return False
        
        # Handle audit logs only
        return record.log_type == LogType.AUDIT
    
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