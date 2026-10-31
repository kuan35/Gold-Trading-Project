from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest


MODULE = Path(__file__).with_name('native_volume_ablation.py')


def implementation():
    assert MODULE.exists(), 'offline native-volume ablation is not implemented'
    spec = importlib.util.spec_from_file_location('native_ablation', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference(ratio='1', **updates):
    result = dict(source_key='native', frames={'5m': dict(status='AVAILABLE',
        volume_basis='broker_native_tick_count', relative_volume_ratio=ratio,
        prior20_mean='100', gap_count=0, bars_closed_before_asof=True)})
    result.update(updates)
    return result


def test_filter_all_passed_rows_then_dedupe_and_refill_beyond_original_top5():
    m = implementation()
    rows = [dict(case_id=str(i), group='same' if i < 2 else str(i),
                 score_max=i / 10, score_sum=i / 10) for i in range(8)]
    descriptions = {str(i): dict(end_5m=i, end_1h=i) for i in range(8)}
    refs = {str(i): reference('4' if i in (0, 2, 3) else '1') for i in range(8)}
    result = m.filter_passed(rows, descriptions, reference(), refs, Decimal('2'))
    assert [r['case_id'] for r in result['rows']] == ['1', '4', '5', '6', '7']
    assert result['retained_rows'] == 5
    assert result['rejections'] == {'TICK_RATIO_EXCEEDS_LIMIT': 3}


@pytest.mark.parametrize('mutation,reason', [
    ({'relative_volume_ratio': None}, 'MISSING_TICK_RATIO'),
    ({'relative_volume_ratio': '0'}, 'ZERO_TICK_RATIO'),
    ({'prior20_mean': '0'}, 'ZERO_BASELINE'),
    ({'status': 'INSUFFICIENT_OR_STALE'}, 'INSUFFICIENT_OR_STALE'),
    ({'relative_volume_ratio': 'NaN'}, 'INVALID_TICK_RATIO'),
    ({'bars_closed_before_asof': False}, 'FUTURE_VOLUME_BAR'),
])
def test_invalid_volume_never_becomes_zero_or_a_match(mutation, reason):
    m = implementation()
    candidate = reference()
    candidate['frames']['5m'].update(mutation)
    assert m.volume_value(candidate, 'native')[1] == reason


def test_source_identity_and_gap_sensitivity_are_explicit():
    m = implementation()
    assert m.volume_value(reference(source_key='foreign'), 'native')[1] == 'SOURCE_MISMATCH'
    r = reference()
    r['frames']['5m']['gap_count'] = 1
    assert m.volume_value(r, 'native')[0] == Decimal('1')
    assert m.volume_value(r, 'native', exclude_gaps=True)[1] == 'VOLUME_BASELINE_GAP'


def test_ratio_limit_is_symmetric_inclusive_and_hourly_is_not_a_hidden_weight():
    m = implementation()
    refs = {'a': reference('2'), 'b': reference('.5'), 'c': reference('2.00001')}
    refs['a']['frames']['1h'] = {'relative_volume_ratio': '999999'}
    rows = [dict(case_id=c, group=c, score_max=0, score_sum=0) for c in refs]
    desc = {c: dict(end_5m=i, end_1h=i) for i, c in enumerate(refs)}
    result = m.filter_passed(rows, desc, reference(), refs, Decimal('2'))
    assert [r['case_id'] for r in result['rows']] == ['a', 'b']


def test_native_profile_uses_only_closed_fresh_bars_and_original_prices():
    m = implementation()
    def bars(count, span):
        return {i * span: dict(time=i * span, open='100', high='102', low='99',
                              close='101', volume=100) for i in range(count)}
    indices = {'5m': bars(242, 300), '1h': bars(22, 3600)}
    times = {iv: sorted(index) for iv, index in indices.items()}
    p = m.native_profile(indices, times, 72000, 'native')
    assert p['status'] == 'candidate_only'
    assert len(p['pre_entry_bars']['5m']) == 60
    assert len(p['pre_entry_bars']['1h']) == 20
    assert p['pre_entry_bars']['5m'][-1]['time'] == 71700
    assert p['pre_entry_bars']['5m'][-1]['close'] == '101'
    assert p['source_key'] == 'native'
    assert m.native_profile(indices, times, 80000, 'native')['status'] == 'insufficient'


def test_fixed_denominator_missing_output_and_empty_sets_are_not_perfect_stability():
    m = implementation()
    records = [dict(methods={'no_volume': dict(rows=[], retained_rows=0, unique_groups=0),
                            'tick_2': dict(rows=[], retained_rows=0, unique_groups=0)})
               for _ in range(30)]
    summary = m.summarize(records)
    assert summary['tick_2']['queries'] == 30
    assert summary['tick_2']['coverage'] == 0
    assert summary['tick_2']['top1_changed_both_output'] == 0
    assert summary['tick_2']['both_output_queries'] == 0
    assert summary['tick_2']['top5_intersection_mean_both_output'] is None
    with pytest.raises(ValueError, match='FIXED_30_REQUIRED'):
        m.summarize(records[:-1])


def test_volume_is_rebuilt_from_closed_native_counts_and_gap_kept_visible():
    m = implementation()
    stamps = [i * 300 for i in range(22) if i != 5]
    index = {t: dict(time=t, volume=100 if i < 20 else 200)
             for i, t in enumerate(stamps)}
    # A forming or later bar cannot enter either denominator or numerator.
    index[6600] = dict(time=6600, volume=999999)
    frame = m.native_volume_frame(index, sorted(index), 6600, '5m')
    assert frame['relative_volume_ratio'] == '2'
    assert frame['prior20_mean'] == '100'
    assert frame['gap_count'] == 1
    assert frame['last_volume'] == 200
    assert frame['bars_closed_before_asof'] is True


def test_csv_provenance_mismatch_is_rejected_even_with_matching_source_label(tmp_path):
    m = implementation()
    bar = dict(time=0, open='100', high='101', low='99', close='100', volume=100)
    chunks = {}
    for iv in ('5m', '1h'):
        name = iv + '.json'
        content = json.dumps(dict(source_key='native', interval=iv,
            volume_basis='broker_native_tick_count', bars=[bar])).encode()
        (tmp_path / name).write_bytes(content)
        chunks[name] = sha256(content).hexdigest()
        (tmp_path / ('native_' + iv + '.csv')).write_text(
            'time,open,high,low,close,volume\n0,100,101,99,100,100\n', encoding='utf8')
    refs = dict(source_key='native', chunk_hashes=chunks)
    assert len(m.load_native(tmp_path, refs)[0]['5m']) == 1
    (tmp_path/'native_5m.csv').write_text(
        'time,open,high,low,close,volume\n0,100,101,99,100,101\n', encoding='utf8')
    with pytest.raises(ValueError, match='CSV_CHUNK_MISMATCH'):
        m.load_native(tmp_path, refs)
