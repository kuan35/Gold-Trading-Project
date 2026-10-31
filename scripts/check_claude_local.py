"""Explicit opt-in diagnostic using a fixed synthetic fact, never private files."""
import argparse
import json
from backend.claude_code import configuration,complete
from backend.live_assistant import LIVE_SYSTEM,writer_facts,render_model_sections

FACTS=[dict(id='f5.trend',text='合成測試盤面的五分鐘趨勢為{{f5_bias}}。',values={'f5_bias':'上行'})]
QUESTION='這只是合成連線測試。請用一段白話說明給定趨勢，不提供交易建議；使用既有占位符與fact_ids。'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview',action='store_true',help='只顯示固定合成payload，不檢查登入或呼叫模型')
    parser.add_argument('--allow-external',action='store_true',help='同意將上述固定合成內容送給官方Claude Code，最多啟動一次推論')
    args=parser.parse_args(argv)
    payload=dict(mode='synthetic_connection_test',facts=writer_facts(FACTS))
    if args.preview:
        print(json.dumps(dict(question=QUESTION,context=payload),ensure_ascii=False,indent=2));return 0
    info=configuration()
    if not args.allow_external:
        print(json.dumps(dict(**info,inference_requested=False),ensure_ascii=False));return 0 if info['authenticated'] else 2
    if not info['authenticated']:
        print(json.dumps(dict(**info,inference_requested=False),ensure_ascii=False));return 2
    response=complete(LIVE_SYSTEM,QUESTION+'\ncontext:\n'+json.dumps(payload,ensure_ascii=False),json_output=True)
    output=dict(status=response['status'],model=response['model'],inference_requested=True,private_data_sent=False)
    if response['status']=='ok':
        try:
            sections,repaired=render_model_sections(json.loads(response['text'])['sections'],FACTS)
            output.update(status='partial_grounding' if repaired else 'ok',sections=sections)
        except (ValueError,KeyError,TypeError):output['status']='invalid_grounding'
    print(json.dumps(output,ensure_ascii=False,indent=2))
    return 0 if output['status']=='ok' else 1


if __name__=='__main__':raise SystemExit(main())
