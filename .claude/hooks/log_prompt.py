#!/usr/bin/env python3
"""UserPromptSubmit hook: append the user's prompt verbatim to prompts.txt."""

import json
import os
import sys

HEADER = (
    "# prompts.txt — All Claude Code prompts used during the live test\n"
    "# Prompts are logged automatically, in order, by .claude/hooks/log_prompt.py\n"
)

data = json.load(sys.stdin)
prompt = (data.get("prompt") or "").strip()
if not prompt:
    sys.exit(0)

root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
path = os.path.join(root, "prompts.txt")

n = 1
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        n = sum(1 for line in f if line.startswith("=== PROMPT ")) + 1
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)

with open(path, "a", encoding="utf-8") as f:
    f.write(f"\n=== PROMPT {n} ===\n{prompt}\n")
