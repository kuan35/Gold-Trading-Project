from research.backtest_compact_retrieval import aggregate, select_queries


def test_query_cohort_keeps_all_groups_but_marks_duplicate_market_windows():
    cases = [dict(id='b', group='g2', side='BUY'),
             dict(id='a', group='g1', side='BUY'),
             dict(id='later', group='g1', side='BUY'),
             dict(id='limited', group='g3', side='SELL')]
    descriptions = {key: dict(tier='full', as_of=1704067200,
                              end_5m=1704067200, end_1h=1704067200)
                    for key in ('a', 'b', 'later')}
    descriptions['later']['as_of'] += 300
    descriptions['limited'] = dict(tier='5m_only', as_of=1704067200)
    result = select_queries(cases, descriptions)
    assert [r['case_id'] for r in result] == ['a', 'b']
    assert [r['primary'] for r in result] == [True, False]
    assert all(r['period'] == 'evaluation_2024_2025' for r in result)


def test_summary_preserves_zero_match_queries_in_coverage_denominator():
    row = dict(agreement=3, fields=dict(structure=True, hour=False),
               path_5m_rmse_pct=.1, path_1h_rmse_pct=.2, volatility_ratio=1.1)
    records = [dict(primary=True, methods={'full': [row]}),
               dict(primary=True, methods={'full': []}),
               dict(primary=False, methods={'full': [dict(row, agreement=4)]})]
    result = aggregate(records, 'full')
    assert result['queries'] == 2 and result['with_results'] == 1
    assert result['any_same_template'] == 0
    assert result['mean_agreement'] == 3
