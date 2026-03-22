#!/usr/bin/env python3
import os
import sys
with open("/tmp/smriti_env.log", "w") as f:
    for k, v in os.environ.items():
        if "STARTUP" in k or "DESKTOP" in k:
            f.write(f"{k}={v}\n")
from smriti_recorder import main
if __name__ == "__main__":
    raise SystemExit(main())
