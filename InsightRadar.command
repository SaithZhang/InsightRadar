#!/bin/bash
cd "$(dirname "$0")" || exit 1
./scripts/macos.sh "$@"
result=$?
if [ "$result" -ne 0 ] && [ -t 0 ]; then
  read -r -p "启动未完成。请查看上方提示，按回车关闭。"
fi
exit "$result"
