"""Offline v2 reference execution-history builder. No network or broker calls."""
import argparse,json
from pathlib import Path
from backend.execution_store import build


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root',type=Path,default=Path(__file__).resolve().parents[1]/'private')
    args=parser.parse_args()
    result=build(args.private_root)
    # Only aggregate counts in stdout; source paths and cases stay local.
    print(json.dumps({key:value for key,value in result.items() if key!='path'},ensure_ascii=False))


if __name__=='__main__':main()
