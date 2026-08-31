"""
SOW-TaskMaster State Store
============================
Simple JSON-based persistence for SOW cases.
Each case is stored as a separate JSON file in data/cases/.
"""

import json
import os
from pathlib import Path
from typing import Optional

from models import SOWCase
from config import DATA_DIR


class StateStore:
    """JSON file-based state store for SOW cases."""
    
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _file_path(self, case_id: str) -> Path:
        """Get the file path for a case."""
        return self.data_dir / f"{case_id}.json"
    
    def save(self, case: SOWCase) -> None:
        """Save a case to disk."""
        file_path = self._file_path(case.case_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(case.model_dump(), f, indent=2, default=str)
    
    def load(self, case_id: str) -> Optional[SOWCase]:
        """Load a case from disk."""
        file_path = self._file_path(case_id)
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SOWCase(**data)
    
    def list_cases(self) -> list[str]:
        """List all case IDs."""
        cases = []
        for f in self.data_dir.glob("*.json"):
            cases.append(f.stem)
        return sorted(cases)
    
    def delete(self, case_id: str) -> bool:
        """Delete a case file."""
        file_path = self._file_path(case_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False