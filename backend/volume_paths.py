import os,re
def volume_folder(private):
 name=os.getenv('GOLD_NATIVE_VOLUME_FOLDER','ctrader_history_volume_20261030')
 if re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name) is None:raise ValueError('無效本機量能資料夾')
 return private/name
