#!/usr/bin/env python3
"""Helper: calls hermes web_extract from subprocess context."""
import json, sys
sys.path.insert(0, "/home/lee/hermes-agent")
sys.path.insert(0, "/home/lee/hermes-venv/lib/python3.12/site-packages")

urls = json.loads(sys.argv[1])
from hermes_tools import web_extract
results = web_extract(urls)
print(json.dumps(results, ensure_ascii=False))
