import time
from pathlib import Path
from typing import List, Tuple

from infrastructure.logging import HFTLoggerInterface


class TaskPersistenceManager:
    """Manages task persistence and recovery with atomic operations and state-based organization."""
    
    def __init__(self, logger: HFTLoggerInterface, base_path: str = "task_data"):
        self.logger = logger
        self.base_path = Path(base_path)
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directory structure."""
        dirs = ["active", "completed", "errored"]
        for dir_name in dirs:
            (self.base_path / dir_name).mkdir(parents=True, exist_ok=True)
    

    def save_context(self, task_id: str, status: str, raw_context: str) -> bool:
        """Save task context to appropriate directory based on state.
        
        Args:
            task_id: Unique task identifier
            context: Task context to save
            
        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            # Determine directory based on state
            if status == 'completed':
                dir_path = self.base_path / "completed"
            elif status in ['error', 'cancelled']:
                dir_path = self.base_path / "errored"
            else:
                dir_path = self.base_path / "active"

            # Atomic write with temp file
            temp_path = dir_path / f".{task_id}.tmp"
            final_path = dir_path / f"{task_id}.json"
            

            # Write atomically
            temp_path.write_text(raw_context)
            temp_path.rename(final_path)
            
            # Clean up old location if task moved directories
            self._cleanup_old_locations(task_id, dir_path)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save task {task_id}", error=str(e))
            return False

    def load_active_task_raw_context(self) -> List[Tuple[str, str]]:
        """Load all active task data for recovery.
        
        Returns:
            List[Tuple[str, str]]: List of (task_id, json_data) tuples
        """
        active_dir = self.base_path / "active"
        tasks = []
        
        for file_path in active_dir.glob("*.json"):
            try:
                task_id = file_path.stem
                data = file_path.read_text()
                tasks.append((task_id, data))
            except Exception as e:
                self.logger.error(f"Failed to load active task {file_path}", error=str(e))
        
        return tasks
    
    def _cleanup_old_locations(self, task_id: str, current_dir: Path):
        """Remove task files from other directories when moved.
        
        Args:
            task_id: Task identifier
            current_dir: Current directory where task is now stored
        """
        for dir_name in ["active", "completed", "errored"]:
            dir_path = self.base_path / dir_name
            if dir_path != current_dir:
                old_file = dir_path / f"{task_id}.json"
                if old_file.exists():
                    old_file.unlink()
    
    def cleanup_completed(self, max_age_hours: int = 24):
        """Remove old completed tasks.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        cutoff = time.time() - (max_age_hours * 3600)
        completed_dir = self.base_path / "completed"
        
        removed = 0
        for file_path in completed_dir.glob("*.json"):
            if file_path.stat().st_mtime < cutoff:
                file_path.unlink()
                removed += 1
        
        if removed > 0:
            self.logger.info(f"Cleaned up {removed} old completed tasks")