"""Build private historical post-reference windows without changing retrieval."""
from pathlib import Path
import argparse,json,sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.forward_outcomes import build_sidecar


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root',type=Path,default=PRODUCT/'private')
    args=parser.parse_args()
    print(json.dumps(build_sidecar(args.private_root),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
