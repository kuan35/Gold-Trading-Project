"""Descriptive results of the complete admitted, deduplicated case pool."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import re
from .trade_result import trade_result


def amount(value):
    try:
        value=Decimal(str(value))
        return value if value.is_finite() else None
    except (InvalidOperation,TypeError,ValueError):return None


def mean(values,places=2):
    return format(sum(values,Decimal(0))/len(values),f'.{places}f') if values else None


def summarize_original_trades(rows):
    wins=losses=flat=unknown=unknown_currency=0
    returns=[];moves=[];currencies=defaultdict(list)
    for row in rows:
        pnl=amount(row.get('profit'))
        if pnl is None:unknown+=1
        else:
            wins+=pnl>0;losses+=pnl<0;flat+=pnl==0
            currency=row.get('currency')
            currency=currency.strip().upper() if isinstance(currency,str) else ''
            if re.fullmatch('[A-Z]{3}',currency):currencies[currency].append(pnl)
            else:unknown_currency+=1
        result=trade_result(row)
        if result['status']=='AVAILABLE':
            returns.append(Decimal(result['price_return_pct']));moves.append(Decimal(result['move_per_oz']))
    known=wins+losses+flat
    return dict(status='AVAILABLE' if rows else 'EMPTY',total=len(rows),known_results=known,
        wins=wins,losses=losses,flat=flat,unknown_results=unknown,
        win_rate_pct=format(Decimal(wins)*100/known,'.2f') if known else None,
        price_results_count=len(returns),mean_price_return_pct=mean(returns,4),mean_move_per_oz=mean(moves,4),
        unknown_currency_results=unknown_currency,
        pnl_by_currency=[dict(currency=c,count=len(v),mean_pnl=mean(v),
            mean_win=mean([p for p in v if p>0]),mean_loss=mean([p for p in v if p<0])) for c,v in sorted(currencies.items())],
        basis='FULL_MATCHED_POOL_ONE_REPRESENTATIVE_PER_GROUP',
        return_basis='DIRECTION_ADJUSTED_PRICE_BEFORE_FEES')


def aggregate_fact(summary):
    values=dict(pool_total=str(summary['total']),pool_known=str(summary['known_results']),
        pool_wins=str(summary['wins']),pool_unknown=str(summary['unknown_results']),
        pool_win_rate=summary['win_rate_pct'] or '資料不足',pool_price_count=str(summary['price_results_count']),
        pool_mean_return=summary['mean_price_return_pct'] or '資料不足',pool_mean_move=summary['mean_move_per_oz'] or '資料不足')
    r=amount(summary['mean_price_return_pct'])
    values['pool_return_state']='平均價格報酬為正' if r is not None and r>0 else '平均價格報酬為負' if r is not None and r<0 else '平均價格報酬為零' if r is not None else '平均價格報酬未知'
    text='全部符合的相似案例{{pool_total}}組，每組取一筆代表原單。'
    text+=('有效報表損益{{pool_known}}筆中{{pool_wins}}筆獲利，歷史獲利比例{{pool_win_rate}}%；另{{pool_unknown}}筆缺損益。'
           if summary['known_results'] else '缺少有效報表損益，無法計算歷史獲利比例。')
    text+=('依{{pool_price_count}}筆有效原單進出價，平均價格報酬{{pool_mean_return}}%（未扣成本），方向調整後每盎司平均價差{{pool_mean_move}}美元。'
           if summary['price_results_count'] else '缺少合法原單進出價，無法計算平均價格報酬及每盎司價差。')
    for i,row in enumerate(summary['pnl_by_currency'][:3]):
        p=f'pool_money{i}_'
        m=Decimal(row['mean_pnl'])
        values.update({p+'currency_state':row['currency'],p+'count':str(row['count']),p+'mean':row['mean_pnl'],
                       p+'result_state':'平均損益為正' if m>0 else '平均損益為負' if m<0 else '平均損益為零'})
        text+='{{'+p+'currency_state}}損益依{{'+p+'count}}筆計算，平均每筆{{'+p+'mean}}。'
    if summary['unknown_currency_results']:
        text+='部分原報表幣別未載，沒有混合計算平均金額。'
    text+='這是全部匹配池的原單歷史描述，並非當前交易預測；不是只取畫面前五例。'
    return dict(id='history.aggregate',text=text,values=values)
