#!/usr/bin/env python3
"""Write GitHub-provided secrets without shell interpolation or logging."""
import json
import os
from pathlib import Path
import sys
from config import REQUIRED

os.umask(0o077)
path = Path(sys.argv[1])
keys = ('ARENA_ENV', 'CADDY_BIND_IP') + REQUIRED
with path.open('x') as output:
    for key in keys:
        value = os.environ.get(key, '')
        if not value or any(c in value for c in '\r\n\x00'):
            print(key + ' must be set to a single-line value', file=sys.stderr)
            sys.exit(1)
        output.write(key + '=' + json.dumps(value.replace('$', '$$')) + '\n')
path.chmod(0o600)
