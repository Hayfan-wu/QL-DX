#!/bin/bash
# QL-DX 更新脚本
# 用法: cd /opt/QL-DX && bash update.sh

set -e

echo "更新 QL-DX..."

git pull

# 检查依赖是否有变化
if git diff --name-only HEAD@{1} HEAD | grep -q "requirements.txt"; then
    echo "依赖有更新，重新安装..."
    pip install -r requirements.txt --break-system-packages
fi

echo "更新完成"
echo "如需重启 QL-Bot 使插件生效: systemctl restart wps-bot"