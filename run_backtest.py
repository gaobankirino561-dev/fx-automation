#!/usr/bin/env python3
# auto-generated wrapper — delegates to detected entry
import os, sys, subprocess
ENTRY = r'ci/backtest_stub.py'
sys.exit(subprocess.call([sys.executable, ENTRY] + sys.argv[1:]))
