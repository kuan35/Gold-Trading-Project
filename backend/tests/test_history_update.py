from scripts.update_history_library import history_tasks
import pytest
def test_weekly_pages_are_half_open_closed_and_bounded():
    tasks=history_tasks(1775000000,1779000123)
    assert tasks and tasks[-1]['end']==1779000000
    assert all(t['interval']=='5m' and t['end']-t['start']<=7*86400 for t in tasks)
    assert all(a['end']==b['start'] for a,b in zip(tasks,tasks[1:]))
    with pytest.raises(ValueError):history_tasks(1700000000,1800000000)
    with pytest.raises(ValueError):history_tasks(1800000000,1700000000)
