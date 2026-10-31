"""Metadata-only by default. No inference command is exposed here."""
import json
from backend.codex_local import configuration
if __name__=='__main__':print(json.dumps(dict(configuration(),inference_requested=False),ensure_ascii=False))
