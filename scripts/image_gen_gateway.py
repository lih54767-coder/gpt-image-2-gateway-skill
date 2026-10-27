#!/usr/bin/env python3
"""Gateway-only Image 2 / 2.5 entrypoint (the official bundled CLI remains unmodified)."""
from gateway_image2 import main
import sys

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Provider exceptions may embed prompt/image/key data. Only report type/status/code.
        if isinstance(exc, (ValueError, FileNotFoundError, FileExistsError)):
            print(f'Error: {exc}', file=sys.stderr)
        else:
            code = getattr(exc, 'code', None)
            code = code if isinstance(code, str) and code.replace('_', '').replace('-', '').isalnum() and len(code) <= 64 else 'none'
            print(f'Error: {type(exc).__name__} status={getattr(exc, "status_code", "unknown")} code={code} (no provider fallback)', file=sys.stderr)
        raise SystemExit(1)
