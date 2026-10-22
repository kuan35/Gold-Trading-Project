"""Point-in-time context comparison with explicit per-axis rejection.

No fallback neighbors, learned weights, external model, or execution authority.
"""
from decimal import Decimal

from .context_rules import market_features, pair_metrics, evaluate_rows, LIMITS
from .dual_path_retrieval import DualPathIndex, _profit_sign, unavailable as dual_unavailable
from .candidate_retrieval import summarize_candidate_tier

METHOD = 'context_contract_v1'
THRESHOLDS = LIMITS['medium']
EVENT_LABELS = {
    'ABOVE':'收在近期區間上方', 'BELOW':'收在近期區間下方',
    'LOWER_RECLAIM':'跌出後收回區間', 'UPPER_RECLAIM':'突破後退回區間',
    'BOTH_RECLAIM':'兩側越界後回到區間', 'IN_RANGE':'區間內活動',
    'BOUNDARY_UNKNOWN':'邊界附近，階段未明確',
}
TAIL_LABELS = {'U':'上行', 'D':'下行', 'N':'變動不大'}
REJECTION_LABELS = {
    'five_path':'五分鐘完整路徑差距超過容忍', 'hour_path':'一小時完整路徑差距超過容忍',
    'tail_path':'最近半小時路徑差距超過容忍', 'tail_direction':'最近半小時方向明顯相反',
    'volatility':'波動倍率超過容忍', 'event_unknown':'事件階段不明確',
    'event_stage':'目前事件階段不同',
}


def description(features):
    return (f"五分鐘60根／一小時20根已收路徑｜目前階段：{EVENT_LABELS[features['event']]}｜"
            f"最近半小時：{TAIL_LABELS[features['tail_direction']]}｜"
            f"ATR／價格 {features['atr_pct']:.4f}%")


def unavailable(reason):
    result = dual_unavailable(reason)
    result.update(rule_status='INSUFFICIENT_DATA', similarity_sufficiency='INSUFFICIENT_DATA',
                  sufficiency=dict(status='insufficient',label='盤面資料不足',reasons=[reason],
                                   matched_groups=0,is_success_probability=False))
    result['comparison'].update(method=METHOD,basis='context_rules',thresholds=dict(THRESHOLDS),
                                parameters_validated=False,eligible_rows=0,passed_rows=0,
                                passed_unique=0,rejections={},rejection_labels=REJECTION_LABELS)
    return result


class ContextIndex(DualPathIndex):
    def __init__(self,cases,profiles):
        super().__init__(cases,profiles)
        self.features = {}
        for case in self.cases:
            try:
                self.features[case['id']] = market_features(profiles[case['id']])
            except (KeyError,TypeError,ValueError,ArithmeticError):
                self.invalid_profiles += 1
        self.cases = [case for case in self.cases if case['id'] in self.features]

    def retrieve(self,query,side,*,exclude_group=None,top_k=5):
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError('invalid top_k')
        try:
            q = market_features(query)
            pool,counts = self.eligible(query,side,exclude_group)
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
            return unavailable(str(exc) or 'CONTEXT_QUERY_UNAVAILABLE')
        measured = [dict(case_id=case['id'],group=case['group'],
                         **pair_metrics(q,self.features[case['id']])) for case in pool]
        evaluated = evaluate_rows(measured,self.descriptions,THRESHOLDS,top_k=len(pool) or 1)
        ranked = evaluated['rows']
        summary = summarize_candidate_tier(ranked,self.lookup)
        counts_out = summary['counts']; known = summary['total']-counts_out['unknown']
        status = ('UNCERTAIN_EVENT' if q['event']=='BOUNDARY_UNKNOWN' else
                  'NO_COMPARABLE_CASES' if not pool else 'PASSED' if ranked else 'NO_RULE_MATCH')
        reason = {
            'PASSED':'各項差距均通過目前試驗容忍；按最大標準化差距、合計及編號排序，群與盤面時點去重。',
            'NO_COMPARABLE_CASES':'沒有同方向、已成熟且觀察窗口不重疊的完整雙週期歷史案例。',
            'NO_RULE_MATCH':'有可比較的歷史案例，但沒有案例通過全部情境條件；未補入未通過的近鄰。',
            'UNCERTAIN_EVENT':'當前收盤位於參考區間邊界附近，事件階段尚不明確，暫不判定符合案例。',
        }[status]
        displayed = []
        for row in ranked[:top_k]:
            c = self.lookup[row['case_id']]; f = self.features[c['id']]
            safe = {k:v for k,v in c.items() if k not in (
                'size_profile','scope_private','market_profile','market','source_format','market_alignment_reason')}
            safe.update(distance=None,candidate_tier='full',retrieval_method=METHOD,
                reference_alignment='PROJECT_REFERENCE',clock_status='UNKNOWN',
                path_distance_pct=row['d5'],hour_path_distance_pct=row['d1h'],
                tail_path_distance_pct=row['dtail'],volatility_ratio=row['vol_ratio'],
                event_stage=f['event'],event_label=EVENT_LABELS[f['event']],
                query_event_stage=q['event'],query_event_label=EVENT_LABELS[q['event']],
                tail_direction=TAIL_LABELS[f['tail_direction']],query_tail_direction=TAIL_LABELS[q['tail_direction']],
                market_state_text=description(f),context_check=dict(passed=True,
                    score_max=row['score_max'],score_sum=row['score_sum'],thresholds=dict(THRESHOLDS)),
                match_reasons=['買賣方向相同','事件階段相同','末段方向不相反','雙週期與末段路徑、波動均通過試驗容忍'],
                differences=['通過自定試驗規則，不是經人工校準的相似機率',
                             '參考行情依來源時間模型定位；券商原始時鐘尚未獨立核實'])
            displayed.append(safe)
        passed = status=='PASSED'
        return dict(total=len(ranked),wins=counts_out['win'],losses=counts_out['loss'],flat=counts_out['flat'],
            unknown=counts_out['unknown'],win_rate=str((Decimal(counts_out['win'])*100/known).quantize(Decimal('.1'))) if known else None,
            cases=displayed,full_cases=displayed,five_minute_only_cases=[],five_minute_only_total=0,
            profit_cases=[c for c in displayed if _profit_sign(c)>0],loss_cases=[c for c in displayed if _profit_sign(c)<0],
            rule_status=status,similarity_sufficiency='RULE_PASSED' if passed else 'NO_MATCH',
            query_status='candidate_only',query_reason=None,candidate_market_unavailable_reason=None,
            comparison=dict(mode='candidate_market',method=METHOD,basis='context_rules',alignment_scope='PROJECT_REFERENCE',
                clock_status='UNKNOWN',independent_clock_verified=False,market_features_enabled=True,parameters_validated=False,
                thresholds=dict(THRESHOLDS),query_market_text=description(q),query_event_stage=q['event'],
                query_event_label=EVENT_LABELS[q['event']],query_tail_direction=TAIL_LABELS[q['tail_direction']],
                full_pool=len(pool),eligible_rows=len(pool),passed_rows=evaluated['passed_rows'],passed_unique=len(ranked),
                excluded_overlap_rows=counts['excluded_overlap_rows'],excluded_invalid_profiles=self.invalid_profiles,
                rejections=evaluated['rejections'],first_rejection=evaluated['first_rejection'],
                rejection_labels=REJECTION_LABELS,reason=reason),
            sufficiency=dict(status='limited' if passed else 'insufficient',label='符合試驗情境條件' if passed else '本次無符合案例',
                reasons=[reason,'容忍值尚未經新日期人工校準'],matched_groups=len(displayed),is_success_probability=False),
            limitations=['只使用進場前已收盤K線；手數、加倉及損益不參與排序',
                         '容忍值為試驗設定；通過率與排名不是人工相似準確率或未來獲利機率',
                         '歷史結果分布僅統計全部通過條件且去重的案例；原始時鐘尚未獨立核實'])
