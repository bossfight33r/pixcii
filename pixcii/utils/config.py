import json
from pathlib import Path

_RC = Path.home() / ".pixciirc"

def load_dotconfig():
    if not _RC.exists(): return {}
    try: return json.loads(_RC.read_text())
    except Exception: return {}
