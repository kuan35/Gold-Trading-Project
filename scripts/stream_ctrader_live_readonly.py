"""Separate LIVE process, explicit account, no stdin/order dispatcher."""
from scripts.live_readonly_policy import load_live_config
from scripts.stream_ctrader_demo import run,emit


def main():
    try:config=load_live_config()
    except ValueError as e:
        emit('status',{'status':str(e)});return 2
    try:run(config,readonly_live=True)
    except Exception:
        emit('status',{'status':'LIVE_READONLY_CONNECTION_ERROR'});return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
