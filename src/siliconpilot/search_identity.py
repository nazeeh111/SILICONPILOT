"""Stable identifier for live search candidate directories."""
import hashlib
import json
from typing import Any


def live_candidate_id(config: Any) -> str:
    return 'live-' + hashlib.sha256(json.dumps(config.to_dict(), sort_keys=True).encode()).hexdigest()[:10]
