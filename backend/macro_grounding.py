"""Reject concrete macro outcomes absent from this release's source capability."""
import re

def validate_macro_claims(sections):
 if not isinstance(sections,list):raise ValueError('invalid macro output')
 for section in sections:
  text=str(section.get('title',''))+' '+str(section.get('text','')) if isinstance(section,dict) else ''
  if re.search(r'(?:已(?:經)?(?:決定|宣布|實施)?|本次(?:決議|決策)(?:是|為)?)(?:升息|降息|加息|減息)|(?:美元|美債殖利率|實質利率)(?:目前|現在|正在|已經|已)',text):raise ValueError('unsupported current macro claim')
  for sentence in re.split(r'[。！？；\n]',text):
   if re.search(r'(?:高於|低於|超出|優於|符合|不如).{0,8}(?:預期|共識)',sentence) and not re.search(r'若|如果|假如|倘若|假設|無法判定|不能判定|尚未判定|不能說',sentence):raise ValueError('missing actual or consensus')
