"""Read-only feasibility audit; output contains aggregate counts, no trade rows."""
import csv
import hashlib
import json
import re
import zipfile
from html.parser import HTMLParser
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / 'product'
TERMS = {
    'margin': r'(?i)margin|保證金|保证金',
    'leverage': r'(?i)leverage|槓桿|杠杆',
    'balance': r'(?i)balance|餘額|余额',
    'commission': r'(?i)commission|佣金|手續費|手续费',
}


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def valid_price(value):
    try:
        d = Decimal(str(value))
        return d.is_finite() and d > 0
    except (InvalidOperation, ValueError):
        return False


def source_text(path):
    if path.suffix.lower() == '.xlsx':
        texts = []
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name == 'xl/sharedStrings.xml' or re.match(r'xl/worksheets/sheet\d+\.xml$', name):
                    tree = ET.fromstring(z.read(name))
                    texts.extend(e.text or '' for e in tree.iter() if e.tag.endswith('}t'))
        return '\n'.join(texts)
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        return '\n'.join(p.extract_text() or '' for p in PdfReader(str(path)).pages)
    raw = path.read_bytes()
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp950', 'latin-1')
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeError:
            pass
    raise ValueError('unable to read source')


def main():
    cases = json.loads((PRODUCT / 'private/cases.json').read_text(encoding='utf-8'))['cases']
    profiles = json.loads((PRODUCT / 'private/case_candidate_market_profiles.json').read_text(encoding='utf-8'))['profiles']
    profiles = list(profiles.values()) if isinstance(profiles, dict) else profiles
    raw_files = sorted(p for p in (ROOT / '交易員資料').rglob('*') if p.is_file())
    mentions, visible_mentions, failures = Counter(), Counter(), Counter()
    for path in raw_files:
        try:
            text = source_text(path)
            visible = text
            if path.suffix.lower() == '.html':
                parser = VisibleHTML()
                parser.feed(text)
                visible = '\n'.join(parser.parts)
            for key, pattern in TERMS.items():
                if re.search(pattern, text):
                    mentions[key] += 1
                if re.search(pattern, visible):
                    visible_mentions[key] += 1
        except Exception as exc:
            failures[type(exc).__name__] += 1
    bars = Counter()
    for profile in profiles:
        for interval, rows in (profile.get('pre_entry_bars') or {}).items():
            for row in rows:
                bars[interval + '_occurrences'] += 1
                if row.get('volume') is not None:
                    bars[interval + '_volume_present'] += 1
    audit = ROOT / 'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv'
    fees = Counter()
    with audit.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            fees['rows'] += 1
            for key in ('commission', 'swap'):
                if row.get(key, '').strip():
                    fees[key + '_nonblank'] += 1
    result = {
        'case_count': len(cases),
        'valid_side_entry_exit': sum(c.get('side') in ('BUY', 'SELL') and valid_price(c.get('entry')) and valid_price(c.get('exit')) for c in cases),
        'case_capital_fields_present': {k: sum(c.get(k) is not None for c in cases) for k in ('margin', 'used_margin', 'initial_margin', 'equity', 'balance', 'leverage', 'commission', 'swap')},
        'raw_source_count': len(raw_files),
        'raw_source_types': dict(Counter(p.suffix.lower() for p in raw_files)),
        'raw_files_with_keyword_mentions': dict(mentions),
        'raw_files_with_visible_keyword_mentions': {k: visible_mentions[k] for k in TERMS},
        'raw_reader_failures': dict(failures),
        'profile_count': len(profiles), 'bar_occurrences': dict(bars),
        'audited_gold_rows_fee_coverage': dict(fees),
        'conclusions': [
            'Keyword mentions do not establish per-trade initial margin or a linked cash-flow ledger.',
            'Current product cases do not support historical margin ROI; source-to-trade linkage requires further audit.',
            'Direction-adjusted price return is computable from valid per-trade entry/exit, before fees.',
            'Bar occurrence counts include overlapping windows; absent volume cannot be imputed as zero.',
        ],
        'input_sha256': {name: hashlib.sha256((PRODUCT / 'private' / name).read_bytes()).hexdigest() for name in ('cases.json', 'case_candidate_market_profiles.json')},
    }
    # Keep hashes private; the public-capable summary contains aggregate counts only.
    private = PRODUCT / 'private/meeting_changes_20261029'
    private.mkdir(exist_ok=True)
    (private / 'data_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    public = {k: v for k, v in result.items() if k != 'input_sha256'}
    (PRODUCT / 'docs/meeting_data_feasibility_20261029.json').write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(public, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
