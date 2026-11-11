#!/bin/zsh
cd "${0:A:h}"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python server.py
else
  echo "请先使用 Python 3.10+ 建立 .venv，并安装 requirements.txt。"
  read "?按回车关闭"
fi
