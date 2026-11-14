#!/bin/zsh
cd "${0:A:h}"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python server.py
else
  echo "Create .venv with Python 3.10+ and install the dependencies in requirements.txt first."
  read "?Press Return to close."
fi
