"""Curated, conditional transmission channels; never a gold direction forecast."""
import re

WGC='https://www.gold.org/goldhub/research/the-impact-of-monetary-policy-on-gold'
FED='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOPICS={
 'GENERAL':('黃金價格因素','黃金同時受到利率與美元、景氣、風險及資金動能影響；各因素可能互相抵銷。','實質利率或美元回落，或避險需求升高時，可能支持黃金。','實質利率或美元上升，或避險需求減弱時，可能壓抑黃金。','這是一般傳導機制；沒有當次行情與可信消息，不能判定現在應做多或做空。'),
 'FOMC':('聯準會利率決策','政策決策與措辭會改變利率預期，並可能透過實質利率、美元與持有黃金的機會成本影響金價。','政策比市場原先預期寬鬆，且實質利率或美元回落時，可能有利黃金。','政策比原先預期緊縮，且實質利率或美元走強時，可能壓抑黃金。','會議日期不代表一定升息或降息；即使降息，若已被市場充分預期，金價也未必上升。'),
 'FED_SPEECH':('聯準會官員發言','發言可能改變市場對後續政策路徑的理解，效果取決於新資訊及當時美元、利率反應。','措辭比原先預期寬鬆，且市場下修利率路徑時，可能支持黃金。','措辭比原先預期緊縮，且市場上修利率路徑時，可能壓抑黃金。','單一官員發言不是委員會已作出的決策；未讀取完整原文時不判定鷹鴿。'),
 'CPI':('美國消費者物價指數','通膨數據可能改變聯準會政策預期，經由實質利率、美元與通膨避險需求影響黃金。','通膨低於可靠共識，且市場轉向較寬鬆政策、實質利率或美元回落時，可能支持黃金。','通膨高於可靠共識，且市場上修利率路徑、美元或實質利率走高時，可能壓抑黃金。','通膨避險需求也可能支持黃金；核心與總體、同比與環比可能不同，不能只看到高通膨就判定利多或利空。'),
 'PCE':('美國個人消費支出物價','PCE通膨資料是政策觀察的一部分，可透過利率預期及美元改變持有黃金的相對吸引力。','通膨降溫幅度超出可靠共識，且實質利率或美元回落時，可能支持黃金。','通膨黏性高於可靠共識，且市場提高緊縮預期時，可能對黃金形成壓力。','核心與總體、環比與同比要分開；公布前不能知道實際結果，沒有共識也無法判斷驚喜。'),
 'EMPLOYMENT':('美國就業報告','非農、失業率及薪資會影響市場對景氣與利率的預期，進而可能影響黃金。','就業或薪資比可靠共識疲弱，且市場下修利率路徑，可能有利黃金；避險需求也可能增加。','就業與薪資比可靠共識強，且美元或實質利率上升，可能壓抑黃金。','非農、失業率、薪資及前期修訂可能互相矛盾，不能只用單一數字給出金價方向。'),
 'GDP':('美國經濟成長','成長數據影響景氣、政策與風險偏好，也可能影響美元及利率，對黃金有多條傳導路徑。','成長弱於可靠共識，且市場下修利率或避險需求升高時，可能支持黃金。','成長強於可靠共識，且美元或實質利率走高時，可能壓抑黃金。','通膨與成長可能發出不同訊號；初值、修訂值及年化口徑不能混為一談。'),
 'PPI':('美國生產者物價','生產端價格可能影響通膨與政策預期，但不等於消費者價格或金價的直接預測。','價格壓力弱於可靠共識，且政策預期轉寬鬆時，可能支持黃金。','價格壓力強於可靠共識，且美元或實質利率上升時，可能壓抑黃金。','PPI到CPI的傳導並非一比一，仍須看其他通膨資料及市場反應。'),
}

def relationship(topic):
 title,mechanism,bullish,bearish,unknown=TOPICS.get(topic,TOPICS['FED_SPEECH'])
 return dict(title=title,mechanism=mechanism,bullish=bullish,bearish=bearish,unknown=unknown,sources=[WGC,FED])

def detect_topic(text):
 for pattern,topic in [(r'\bgdp\b|gross domestic|經濟成長','GDP'),(r'\bcpi\b|consumer price|消費者物價','CPI'),(r'\bpce\b|personal income|personal consumption|個人消費支出|個人所得','PCE'),(r'非農|失業率|薪資|employment situation|job openings|就業','EMPLOYMENT'),(r'\bppi\b|producer price|生產者物價','PPI'),(r'利率|升息|降息|fomc|議息','FOMC')]:
  if re.search(pattern,text,re.I):return topic
 return 'FED_SPEECH' if re.search(r'聯準會|官員|發言|fed',text,re.I) else 'GENERAL'

def question_kind(text):
 if re.search(r'我想.*(?:做多|做空|買|賣)|如果.*(?:做多|做空)',text):return None
 if re.search(r'(?:買進|買入|賣出|下單|做多|做空).*\d|(?:修改|改成|設為|設定).*(?:手數|停損|停利|限價)|(?:停損|停利|手數|限價)\s*\d',text,re.I):return None
 relevant=re.search(r'黃金|CPI|PCE|GDP|PPI|非農|聯準會|FOMC|總經|經濟事件|利率|升息|降息|保證金|槓桿|限價單|市價單|停損|停利|tick|成交量|消息|新聞|行事曆',text,re.I)
 if not relevant:return None
 if re.search(r'今天|今晚|本週|這週|下週|最近|最新|目前',text) and re.search(r'新聞|消息|公告|發言|聲明',text):return 'news'
 if re.search(r'盤面|走勢|報價|K線',text,re.I) and not re.search(r'CPI|PCE|GDP|PPI|非農|聯準會|FOMC|事件|新聞|消息',text,re.I):return None
 if re.search(r'是什麼|什麼是|意思|為什麼|如何影響|怎麼影響|有何關聯|有什麼關係|差別|知識|解釋|新手|入門|先了解',text):return 'knowledge'
 if re.search(r'新聞|消息|公告|發言|聲明',text):return 'news'
 if re.search(r'事件|行事曆|日曆|公布|發布|今天|今晚|本週|這週|下次|下週|何時|什麼時候',text):return 'calendar'
 return 'knowledge' if re.search(r'CPI|PCE|GDP|PPI|非農|FOMC|聯準會|利率|升息|降息|保證金|槓桿|限價單|市價單|停損|停利',text,re.I) else None

def knowledge(text):
 if re.search(r'新手|入門|先了解',text):return dict(title='先懂委託，再討論盤面',explanation='先分清做多與做空，以及市價單立即依可成交報價執行、限價單等待指定價格條件。手數決定每次價格波動承擔的盈虧，停損用來限制不利情境，但仍可能滑價。可先用DEMO練習：討論盤面、檢查相似案例及差異、填寫草稿，再核對風險並親自確認。案例的歷史結果不等於這次會重演；填寫草稿不會直接成交。',source='https://help.ctrader.com/trading-with-ctrader/orders/')
 if re.search(r'保證金|槓桿',text):return dict(title='槓桿與保證金',explanation='保證金是持有部位所需的資金，不是最大損失。槓桿讓較少資金承擔較大名目部位，盈虧仍依部位、價差與成本變化；實際規則以你的券商商品及帳戶為準。',source='https://help.ctrader.com/trading-with-ctrader/conditions/')
 if re.search(r'tick|成交量|量能',text,re.I):return dict(title='tick量與成交量',explanation='tick量表示券商報價更新的活躍度，不代表全球黃金實際成交手數。較活躍可能伴隨更多價格更新，但不能只靠tick量推論資金淨流入或未來方向。',source='https://help.ctrader.com/open-api/model-messages/')
 if re.search(r'限價單|市價單|停損|停利',text):return dict(title='委託與風險',explanation='市價單依可成交報價執行，限價單等待指定價格條件。停損用來管理不利變動，但跳空與滑價仍可能使成交價不同；委託與修改都要核對方向、手數與價格後由你確認。',source='https://help.ctrader.com/trading-with-ctrader/orders/')
 topic=detect_topic(text);r=relationship(topic)
 definitions={'CPI':'CPI衡量消費者購買的一籃子商品與服務價格變化，總體與排除部分項目的核心指標須分開看。','PCE':'PCE物價指數觀察個人消費支出的價格變化，與CPI的涵蓋及權重方法不同。','EMPLOYMENT':'美國就業報告包含新增非農就業、失業率與薪資等不同指標。','GDP':'GDP觀察一段期間的經濟產出，初步估計與後續修訂可能不同。','PPI':'PPI觀察生產者端的價格變化，不能直接當作消費者價格變化。'}
 return dict(title=r['title']+'與黃金',explanation=definitions.get(topic,'')+r['mechanism'],source=WGC)
