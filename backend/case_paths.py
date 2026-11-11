"""Select a verified, isolated case-data root without touching account journals."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def case_data_root(root: Path | None = None) -> Path:
    private = ((Path(root) if root is not None else ROOT) / 'private').resolve()
    selected = os.environ.get('GOLD_CASE_DATA_FOLDER', '').strip()
    if not selected:
        return private
    if Path(selected).is_absolute() or '..' in Path(selected).parts:
        raise ValueError('INVALID_PERSONAL_CASE_FOLDER')
    folder = (private / selected).resolve()
    if not folder.is_relative_to((private / 'personal_history').resolve()):
        raise ValueError('INVALID_PERSONAL_CASE_FOLDER')
    status = json.loads((folder / 'personal_history_status.json').read_text(encoding='utf-8'))
    if status.get('status') not in ('READY', 'PARTIAL') or status.get('usable_profiles', 0) < 1:
        raise ValueError('PERSONAL_CASE_INDEX_NOT_READY')
    if not (folder / 'cases.json').is_file():
        raise ValueError('PERSONAL_CASES_MISSING')
    return folder
