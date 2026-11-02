"""Never let API fixture analyses write into the owner's real conversation history."""
import sys
import pytest
from backend.analysis_history import AnalysisHistory

@pytest.fixture(autouse=True)
def isolated_analysis_history(tmp_path,monkeypatch):
    module=sys.modules.get('backend.app')
    if module is not None and hasattr(module,'analysis_history'):
        monkeypatch.setattr(module,'analysis_history',AnalysisHistory(tmp_path/'analysis-history'))
