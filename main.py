"""
中国电信话费自动化 - 脚本入口
==============================
纯宿主机部署，支持 crontab 定时 + QQ 机器人手动触发。

crontab 配置:
  0 8,12,18 * * * cd /opt/QL-DX && python3 main.py >> /opt/QL-DX/cron.log 2>&1
"""

import os
import sys

# 加载 .env 文件
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip().strip("\"'")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from config import validate
from telecom_api import run_all


def main():
    """脚本入口"""
    print("=" * 50)
    print("  中国电信话费自动化")
    print("=" * 50)

    if not validate():
        print("请先配置环境变量后重试")
        print("必要变量: DX_ACCOUNT（格式: 手机号#密码）")
        return

    result = asyncio.run(run_all())

    if result.get("error"):
        print(f"\n❌ 执行失败: {result['error']}")
    else:
        signin_msg = result.get("signin", {}).get("msg", "-")
        print(f"\n📋 签到: {signin_msg}")
        print(f"📋 活动: 扫描 {len(result.get('activities', []))} 个")


if __name__ == "__main__":
    main()