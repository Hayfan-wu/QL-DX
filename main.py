"""
中国电信话费自动化 - 青龙面板入口
================================
青龙面板定时任务配置:
  task DX-Telecom/main.py
  cron: 0 8,12,18 * * *
"""

import os
import sys

# 加载 .env 文件（青龙面板兼容）
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip().strip("\"'")

# 确保项目目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from config import validate
from telecom_api import run_all


def main():
    """青龙面板入口"""
    print("=" * 50)
    print("  中国电信话费自动化 - 青龙面板")
    print("=" * 50)

    if not validate():
        print("请先配置环境变量后重试")
        print("必要变量: DX_PHONE, DX_PASSWORD")
        return

    result = asyncio.run(run_all())

    # 输出青龙面板通知格式
    if result.get("error"):
        print(f"\n❌ 执行失败: {result['error']}")
    else:
        signin_msg = result.get("signin", {}).get("msg", "-")
        exchange_msg = result.get("exchange", {}).get("msg", "-")
        print(f"\n📋 签到: {signin_msg}")
        print(f"📋 兑换: {exchange_msg}")
        print(f"📋 活动: 扫描 {len(result.get('activities', []))} 个")


if __name__ == "__main__":
    main()