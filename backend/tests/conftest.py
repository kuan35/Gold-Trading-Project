"""Never let API fixture analyses write into the owner's real conversation history."""
import sys
import pytest
from backend.analysis_history import AnalysisHistory
from backend.trade_plans import TradePlanStore
from backend.trade_alerts import LocalAlerts,AlertMonitor

@pytest.fixture(autouse=True)
def isolated_analysis_history(tmp_path,monkeypatch):
    module=sys.modules.get('backend.app')
    if module is not None and hasattr(module,'analysis_history'):
        monkeypatch.setattr(module,'analysis_history',AnalysisHistory(tmp_path/'analysis-history'))
    if module is not None and hasattr(module,'trade_plans'):
        monkeypatch.setattr(module,'trade_plans',TradePlanStore(tmp_path/'trade-plans.sqlite'))
        alerts=LocalAlerts(tmp_path/'trade-alerts.sqlite')
        monitor=AlertMonitor(alerts,lambda:{})
        monkeypatch.setattr(monitor,'start',lambda:None)
        monkeypatch.setattr(module,'trade_alerts',alerts)
        monkeypatch.setattr(module,'alert_monitor',monitor)
