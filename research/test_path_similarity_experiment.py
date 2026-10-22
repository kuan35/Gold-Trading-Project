"""Mechanism checks for offline path experiments; no financial accuracy claims."""
import numpy as np
import pytest

from research.path_similarity_experiment import band_dtw, percentile_rank, order_candidates


def reference_dtw(a, b, radius):
    grid = np.full((len(a)+1, len(b)+1), np.inf)
    grid[0, 0] = 0
    for i in range(1, len(a)+1):
        for j in range(max(1, i-radius), min(len(b), i+radius)+1):
            grid[i, j] = (a[i-1]-b[j-1])**2 + min(grid[i-1, j], grid[i, j-1], grid[i-1, j-1])
    return np.sqrt(grid[-1, -1] / len(a))


def test_zero_radius_is_pointwise_rmse_and_batch_matches_reference():
    q = np.array([0., .2, -.3, .7, .4])
    candidates = np.array([q, q+.3, q[::-1]])
    np.testing.assert_allclose(band_dtw(q, candidates, 0), np.sqrt(np.mean((candidates-q)**2, axis=1)))
    for radius in (1, 2):
        np.testing.assert_allclose(band_dtw(q, candidates, radius), [reference_dtw(q, c, radius) for c in candidates])
        for c, distance in zip(candidates, band_dtw(q, candidates, radius)):
            assert band_dtw(c, q[None, :], radius)[0] == pytest.approx(distance)


def test_small_shift_tolerated_but_fixed_endpoint_still_matters():
    q = np.array([0., 0, 1, 0, 0, 0])
    shift = np.array([0., 0, 0, 1, 0, 0])
    assert band_dtw(q, shift[None, :], 1)[0] == 0
    assert band_dtw(q, shift[None, :], 0)[0] > 0
    wrong_end = shift.copy(); wrong_end[-1] = 2
    assert band_dtw(q, wrong_end[None, :], 1)[0] > 0


@pytest.mark.parametrize('q,c,r', [([0,1], [[0,1]], -1), ([0,1], [[0]], 1),
                                  ([0,np.nan], [[0,1]], 1), ([0,1], [[0,np.inf]], 1)])
def test_invalid_sequences_rejected(q, c, r):
    with pytest.raises(ValueError): band_dtw(np.array(q), np.array(c), r)


def test_ties_have_equal_rank_and_stable_id_break():
    np.testing.assert_allclose(percentile_rank(np.array([2., 1, 1, 4])), [.5, 0, 0, .75])
    pool = [{'id': 'B', 'group': 'b'}, {'id': 'A', 'group': 'a'}]
    descriptions = {i: {'structure': 'IN_RANGE', 'end_5m': n, 'end_1h': n}
                    for n, i in enumerate(('A','B'))}
    rows = order_candidates(pool, descriptions, {'structure':'IN_RANGE'}, np.array([1.,1]), np.array([1.,1]), structure_first=False)
    assert [r['case_id'] for r in rows] == ['A','B']
    # Pool order and post-entry fields cannot enter these ranking inputs.
    rows2 = order_candidates(list(reversed(pool)), descriptions, {'structure':'IN_RANGE'}, np.array([1.,1]), np.array([1.,1]), structure_first=False)
    assert rows2 == rows


def test_structure_priority_and_group_window_dedupe():
    pool = [{'id':'near','group':'g1'}, {'id':'same','group':'g2'}, {'id':'dup','group':'g2'}, {'id':'window','group':'g3'}]
    descriptions = {i: {'structure': 'IN_RANGE' if i != 'near' else 'CLOSE_ABOVE',
                        'end_5m': n, 'end_1h': n}
                    for i,n in [('near',1),('same',2),('dup',3),('window',2)]}
    distances = np.array([0., 2, 3, 4])
    rows = order_candidates(pool, descriptions, {'structure':'IN_RANGE'}, distances, distances, structure_first=True)
    assert [r['case_id'] for r in rows] == ['same','near']
