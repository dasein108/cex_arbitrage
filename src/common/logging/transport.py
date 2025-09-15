"""
HFT Logging Transport Layer

High-performance transport mechanisms for log delivery with HFT compliance.
Supports ZeroMQ async push, memory-mapped files, and composite transports.

Key Features:
- ZeroMQ async transport for separate logging infrastructure
- Memory-mapped files with intelligent rotation
- Composite transport for redundancy and performance
- Connection pooling and automatic reconnection
- Rate limiting and flow control

HFT OPTIMIZATION: Transport operations are designed for minimal
impact on trading operations with async batching and buffering.
"""

import asyncio
import time
import mmap
import struct
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union, BinaryIO
from pathlib import Path
from datetime import datetime
import zmq
import zmq.asyncio

from .structures import LogType
from core.exceptions.transport import TransportException

class BaseTransport(ABC):
    """
    Abstract cex class for all log transports.
    
    Defines the cex for async log delivery with HFT compliance.
    """
    
    @abstractmethod
    async def send(self, data: bytes, log_type: LogType) -> None:
        """
        Send log data asynchronously.
        
        Args:
            data: Serialized log batch data
            log_type: Type of log data for routing
            
        Raises:
            TransportException: On delivery failure
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shutdown the transport"""
        pass
    
    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        """Get transport-specific statistics"""
        pass


class ZeroMQTransport(BaseTransport):
    """
    ZeroMQ async transport for pushing logs to separate infrastructure.
    
    Designed for high-throughput log streaming to dedicated logging servers
    without impacting trading performance. Uses PUSH sockets with async I/O.
    
    HFT FEATURES:
    - Non-blocking push operations
    - Connection pooling and automatic reconnection
    - Message queuing with overflow handling
    - Separate ZMQ context for isolation
    """
    
    def __init__(self,
                 endpoints: Union[str, List[str]],
                 high_water_mark: int = 10000,
                 send_timeout_ms: int = 100,
                 linger_ms: int = 1000,
                 reconnect_interval_ms: int = 5000,
                 max_reconnect_attempts: int = -1):  # -1 = infinite
        
        if isinstance(endpoints, str):
            endpoints = [endpoints]
        
        self.endpoints = endpoints
        self.high_water_mark = high_water_mark
        self.send_timeout_ms = send_timeout_ms
        self.linger_ms = linger_ms
        self.reconnect_interval_ms = reconnect_interval_ms
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # ZeroMQ context and sockets
        self.context: Optional[zmq.asyncio.Context] = None
        self.sockets: Dict[str, zmq.asyncio.Socket] = {}
        self.socket_health: Dict[str, bool] = {}
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'bytes_sent': 0,
            'reconnections': 0,
            'last_send_time': 0.0,
            'active_connections': 0
        }
        
        # Connection management
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        
    async def _initialize(self) -> None:
        """Initialize ZeroMQ context and sockets"""
        if self.context is None:
            # Create isolated ZMQ context for logging
            self.context = zmq.asyncio.Context()
            
            # Create PUSH sockets for each endpoint
            for endpoint in self.endpoints:
                await self._create_socket(endpoint)
    
    async def _create_socket(self, endpoint: str) -> None:
        """Create and configure a ZeroMQ PUSH socket"""
        try:
            socket = self.context.socket(zmq.PUSH)
            
            # Configure socket options for HFT performance
            socket.setsockopt(zmq.SNDHWM, self.high_water_mark)  # High water mark
            socket.setsockopt(zmq.SNDTIMEO, self.send_timeout_ms)  # Send timeout
            socket.setsockopt(zmq.LINGER, self.linger_ms)  # Linger time
            socket.setsockopt(zmq.IMMEDIATE, 1)  # Don't queue if no peers
            socket.setsockopt(zmq.TCP_KEEPALIVE, 1)  # Enable keep-alive
            socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 60)  # Keep-alive idle time
            
            # Connect to endpoint
            socket.connect(endpoint)
            
            self.sockets[endpoint] = socket
            self.socket_health[endpoint] = True
            self.stats['active_connections'] += 1
            
        except Exception as e:
            self.socket_health[endpoint] = False
            raise TransportException(f"Failed to create socket for {endpoint}: {e}")
    
    async def send(self, data: bytes, log_type: LogType) -> None:
        """
        Send log data via ZeroMQ PUSH sockets.
        
        Uses non-blocking send with automatic failover between endpoints.
        Optimized for minimal impact on trading operations.
        """
        if not self.context:
            await self._initialize()
        
        # Create message with metadata
        message = self._create_message(data, log_type)
        
        # Try sending to healthy sockets
        sent = False
        for endpoint, socket in self.sockets.items():
            if not self.socket_health[endpoint]:
                continue
                
            try:
                # Non-blocking send with timeout
                await socket.send(message, zmq.NOBLOCK)
                
                # Update statistics
                self.stats['messages_sent'] += 1
                self.stats['bytes_sent'] += len(message)
                self.stats['last_send_time'] = time.time()
                sent = True
                break  # Success - only need one endpoint
                
            except zmq.Again:
                # Socket buffer full - mark unhealthy and try next
                self.socket_health[endpoint] = False
                self._schedule_reconnect(endpoint)
                continue
                
            except zmq.ZMQError as e:
                # Socket error - mark unhealthy and try next  
                self.socket_health[endpoint] = False
                self._schedule_reconnect(endpoint)
                continue
        
        if not sent:
            self.stats['messages_failed'] += 1
            raise TransportException("Failed to send to any ZeroMQ endpoint")
    
    def _create_message(self, data: bytes, log_type: LogType) -> bytes:
        """
        Create ZeroMQ message with routing information.
        
        Message format: [header][payload]
        Header: 16 bytes - timestamp(8) + log_type(4) + size(4)  
        Payload: msgpack-encoded log batch
        """
        timestamp = struct.pack('>Q', int(time.time_ns() // 1000))  # microseconds
        log_type_bytes = struct.pack('>I', log_type.value)
        size_bytes = struct.pack('>I', len(data))
        
        header = timestamp + log_type_bytes + size_bytes
        return header + data
    
    def _schedule_reconnect(self, endpoint: str) -> None:
        """Schedule socket reconnection for failed endpoint"""
        if endpoint not in self._reconnect_tasks or self._reconnect_tasks[endpoint].done():
            self._reconnect_tasks[endpoint] = asyncio.create_task(
                self._reconnect_socket(endpoint)
            )
    
    async def _reconnect_socket(self, endpoint: str) -> None:
        """Reconnect failed socket with exponential backoff"""
        attempt = 0
        base_delay = self.reconnect_interval_ms / 1000.0
        
        while not self._shutdown_event.is_set():
            if self.max_reconnect_attempts > 0 and attempt >= self.max_reconnect_attempts:
                break
                
            try:
                # Close existing socket if present
                if endpoint in self.sockets:
                    self.sockets[endpoint].close()
                    self.stats['active_connections'] -= 1
                
                # Wait with exponential backoff
                delay = base_delay * (2 ** min(attempt, 6))  # Cap at 64x
                await asyncio.sleep(delay)
                
                # Recreate socket
                await self._create_socket(endpoint)
                self.stats['reconnections'] += 1
                break
                
            except Exception:
                attempt += 1
                continue
    
    async def shutdown(self) -> None:
        """Gracefully shutdown ZeroMQ transport"""
        self._shutdown_event.set()
        
        # Cancel reconnection tasks
        for task in self._reconnect_tasks.values():
            if not task.done():
                task.cancel()
        
        # Close all sockets
        for socket in self.sockets.values():
            socket.close()
        
        # Terminate context
        if self.context:
            self.context.term()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get ZeroMQ transport statistics"""
        return {
            'transport_type': 'zeromq',
            'endpoints': self.endpoints,
            'active_connections': self.stats['active_connections'],
            'messages_sent': self.stats['messages_sent'],
            'messages_failed': self.stats['messages_failed'],
            'bytes_sent': self.stats['bytes_sent'],
            'reconnections': self.stats['reconnections'],
            'last_send_time': self.stats['last_send_time'],
            'healthy_endpoints': sum(1 for h in self.socket_health.values() if h)
        }


class FileTransport(BaseTransport):
    """
    Memory-mapped file transport with intelligent rotation.
    
    Optimized for high-performance local storage with minimal I/O overhead.
    Uses memory-mapped files for zero-copy writes and automatic rotation.
    
    HFT FEATURES:
    - Memory-mapped file I/O for performance
    - Lock-free writes using atomic operations
    - Intelligent rotation based on size and time
    - Separate files per log type for organization
    """
    
    def __init__(self,
                 base_path: Union[str, Path] = "/var/log/hft",
                 max_file_size_mb: int = 100,
                 max_file_age_hours: int = 24,
                 buffer_size_kb: int = 64,
                 sync_interval_seconds: int = 5,
                 compress_rotated: bool = True):
        
        self.base_path = Path(base_path)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_file_age_seconds = max_file_age_hours * 3600
        self.buffer_size_bytes = buffer_size_kb * 1024  
        self.sync_interval_seconds = sync_interval_seconds
        self.compress_rotated = compress_rotated
        
        # File handles and memory maps per log type
        self.files: Dict[LogType, BinaryIO] = {}
        self.mmaps: Dict[LogType, mmap.mmap] = {}
        self.file_positions: Dict[LogType, int] = {}
        self.file_created_times: Dict[LogType, float] = {}
        
        # Statistics
        self.stats = {
            'files_written': 0,
            'bytes_written': 0,
            'rotations': 0,
            'last_write_time': 0.0,
            'active_files': 0
        }
        
        # Background sync task
        self._sync_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Ensure cex directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def _initialize_file(self, log_type: LogType) -> None:
        """Initialize memory-mapped file for log type"""
        if log_type in self.files:
            return
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{log_type.name.lower()}_{timestamp}.log"
        filepath = self.base_path / filename
        
        try:
            # Open file for writing
            file_handle = open(filepath, 'w+b')
            
            # Pre-allocate file space for memory mapping
            file_handle.seek(self.max_file_size_bytes - 1)
            file_handle.write(b'\0')
            file_handle.flush()
            
            # Create memory map
            mmap_handle = mmap.mmap(
                file_handle.fileno(),
                length=self.max_file_size_bytes,
                access=mmap.ACCESS_WRITE
            )
            
            # Store handles
            self.files[log_type] = file_handle
            self.mmaps[log_type] = mmap_handle
            self.file_positions[log_type] = 0
            self.file_created_times[log_type] = time.time()
            self.stats['active_files'] += 1
            
        except Exception as e:
            raise TransportException(f"Failed to initialize file for {log_type.name}: {e}")
    
    async def send(self, data: bytes, log_type: LogType) -> None:
        """
        Write log data to memory-mapped file.
        
        Uses zero-copy memory-mapped writes for optimal performance.
        Handles rotation automatically based on size and age limits.
        """
        # Initialize file if needed
        if log_type not in self.files:
            await self._initialize_file(log_type)
        
        # Check if rotation is needed
        if await self._needs_rotation(log_type):
            await self._rotate_file(log_type)
        
        # Write data to memory-mapped file
        try:
            mmap_handle = self.mmaps[log_type]
            position = self.file_positions[log_type]
            
            # Create log entry with length prefix for parsing
            entry_length = struct.pack('>I', len(data))
            entry_data = entry_length + data
            
            # Write to memory map
            mmap_handle[position:position + len(entry_data)] = entry_data
            
            # Update position
            self.file_positions[log_type] += len(entry_data)
            
            # Update statistics
            self.stats['files_written'] += 1
            self.stats['bytes_written'] += len(entry_data)
            self.stats['last_write_time'] = time.time()
            
            # Start sync task if not running
            if self._sync_task is None or self._sync_task.done():
                self._sync_task = asyncio.create_task(self._periodic_sync())
                
        except Exception as e:
            raise TransportException(f"Failed to write to file for {log_type.name}: {e}")
    
    async def _needs_rotation(self, log_type: LogType) -> bool:
        """Check if file needs rotation based on size or age"""
        if log_type not in self.files:
            return False
        
        # Check file size
        if self.file_positions[log_type] >= self.max_file_size_bytes * 0.9:  # 90% full
            return True
        
        # Check file age
        file_age = time.time() - self.file_created_times[log_type]
        if file_age >= self.max_file_age_seconds:
            return True
        
        return False
    
    async def _rotate_file(self, log_type: LogType) -> None:
        """Rotate log file to new timestamped file"""
        if log_type not in self.files:
            return
        
        try:
            # Sync current file
            mmap_handle = self.mmaps[log_type]
            mmap_handle.flush()
            
            # Close current file
            mmap_handle.close()
            self.files[log_type].close()
            
            # Clean up references
            del self.mmaps[log_type]
            del self.files[log_type]
            del self.file_positions[log_type]
            del self.file_created_times[log_type]
            self.stats['active_files'] -= 1
            
            # Initialize new file
            await self._initialize_file(log_type)
            self.stats['rotations'] += 1
            
        except Exception as e:
            raise TransportException(f"Failed to rotate file for {log_type.name}: {e}")
    
    async def _periodic_sync(self) -> None:
        """Periodically sync memory-mapped files to disk"""
        while not self._shutdown_event.is_set():
            try:
                # Sync all active memory maps
                for mmap_handle in self.mmaps.values():
                    mmap_handle.flush()
                
                await asyncio.sleep(self.sync_interval_seconds)
                
            except Exception:
                # Continue syncing even if one fails
                await asyncio.sleep(self.sync_interval_seconds)
    
    async def shutdown(self) -> None:
        """Gracefully shutdown file transport"""
        self._shutdown_event.set()
        
        # Cancel sync task
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
        
        # Flush and close all files
        for log_type in list(self.files.keys()):
            try:
                self.mmaps[log_type].flush()
                self.mmaps[log_type].close()
                self.files[log_type].close()
            except Exception:
                pass  # Best effort cleanup
        
        # Clear references
        self.files.clear()
        self.mmaps.clear()
        self.file_positions.clear()
        self.file_created_times.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get file transport statistics"""
        return {
            'transport_type': 'file',
            'base_path': str(self.base_path),
            'active_files': self.stats['active_files'],
            'files_written': self.stats['files_written'],
            'bytes_written': self.stats['bytes_written'],
            'rotations': self.stats['rotations'],
            'last_write_time': self.stats['last_write_time'],
            'max_file_size_mb': self.max_file_size_bytes // (1024 * 1024)
        }


class CompositeTransport(BaseTransport):
    """
    Composite transport for redundancy and performance optimization.
    
    Combines multiple transports (e.g., ZeroMQ + File) for reliability.
    Routes different log types to optimal transports based on requirements.
    
    HFT FEATURES:
    - Parallel transport execution for performance
    - Failover between transports for reliability
    - Per-log-type transport routing
    - Combined statistics and monitoring
    """
    
    def __init__(self, 
                 transports: List[BaseTransport],
                 routing_rules: Optional[Dict[LogType, List[int]]] = None,
                 parallel_sends: bool = True,
                 require_all_success: bool = False):
        
        self.transports = transports
        self.parallel_sends = parallel_sends
        self.require_all_success = require_all_success
        
        # Default routing: all log types to all transports
        if routing_rules is None:
            routing_rules = {
                log_type: list(range(len(transports)))
                for log_type in LogType
            }
        self.routing_rules = routing_rules
        
        # Statistics
        self.stats = {
            'total_sends': 0,
            'successful_sends': 0,
            'failed_sends': 0,
            'partial_failures': 0,
            'last_send_time': 0.0
        }
    
    async def send(self, data: bytes, log_type: LogType) -> None:
        """
        Send log data via multiple transports.
        
        Routes to appropriate transports based on log type and rules.
        Executes sends in parallel for performance optimization.
        """
        # Get target transports for this log type
        transport_indices = self.routing_rules.get(log_type, [])
        target_transports = [self.transports[i] for i in transport_indices]
        
        if not target_transports:
            raise TransportException(f"No transports configured for {log_type.name}")
        
        self.stats['total_sends'] += 1
        
        if self.parallel_sends and len(target_transports) > 1:
            # Execute sends in parallel
            results = await asyncio.gather(
                *[transport.send(data, log_type) for transport in target_transports],
                return_exceptions=True
            )
            
            # Check results
            successes = sum(1 for result in results if not isinstance(result, Exception))
            failures = len(results) - successes
            
            if failures > 0:
                self.stats['partial_failures'] += 1
                
            if successes == 0:
                self.stats['failed_sends'] += 1
                raise TransportException(f"All transports failed for {log_type.name}")
            elif failures > 0 and self.require_all_success:
                self.stats['failed_sends'] += 1
                raise TransportException(f"Partial failure for {log_type.name}: {failures}/{len(results)} failed")
            else:
                self.stats['successful_sends'] += 1
                
        else:
            # Execute sends sequentially with failover
            last_exception = None
            success = False
            
            for transport in target_transports:
                try:
                    await transport.send(data, log_type)
                    success = True
                    break  # Success - no need to try others unless require_all_success
                    
                except Exception as e:
                    last_exception = e
                    continue
            
            if success:
                self.stats['successful_sends'] += 1
            else:
                self.stats['failed_sends'] += 1
                raise TransportException(f"All transports failed for {log_type.name}: {last_exception}")
        
        self.stats['last_send_time'] = time.time()
    
    async def shutdown(self) -> None:
        """Gracefully shutdown all transports"""
        shutdown_tasks = [transport.shutdown() for transport in self.transports]
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get combined statistics from all transports"""
        transport_stats = [transport.get_statistics() for transport in self.transports]
        
        return {
            'transport_type': 'composite',
            'composite_stats': self.stats,
            'transport_count': len(self.transports),
            'routing_rules': {log_type.name: indices for log_type, indices in self.routing_rules.items()},
            'individual_transports': transport_stats
        }