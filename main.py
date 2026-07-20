"""
中国电信话费自动化 - 脚本入口
==============================
纯宿主机 + 青龙面板通用入口。

⚠️ 重要：青龙面板只需创建这一个任务！不要拉取其他 .py/.js 文件为任务。

青龙定时任务:
  任务名: DX-Telecom
  命令: task /opt/QL-DX/main.py
  定时: 0 8,12,18 * * *

crontab 定时:
  0 8,12,18 * * * cd /opt/QL-DX && python3 main.py >> /opt/QL-DX/cron.log 2>&1

依赖安装:
  pip install httpx execjs pycryptodome requests --break-system-packages
  (需要 Node.js 运行时支持 execjs)
"""

import os
import sys
import traceback

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


def main():
    """脚本入口"""
    print("=" * 50)
    print("  中国电信话费自动化 v3.0 (API直调)")
    print("=" * 50)

    # 检查依赖
    try:
        from config import validate
        from telecom_api import run_all
    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        print("请运行: pip install httpx PyExecJS pycryptodome requests --break-system-packages")
        return

    if not validate():
        print("请先配置环境变量后重试")
        print("必要变量: DX_ACCOUNT（格式: 手机号#密码）")
        return

    import argparse
    parser = argparse.ArgumentParser(description="中国电信话费自动化")
    parser.add_argument("--signin-only", action="store_true", help="仅签到")
    args = parser.parse_args()

    try:
        result = run_all(signin_only=args.signin_only)

        if result.get("error"):
            print(f"\n❌ 执行失败: {result['error']}")
        else:
            signin_msg = result.get("signin", {}).get("msg", "-")
            print(f"\n📋 签到: {signin_msg}")
            print(f"📋 活动: {len(result.get('activities', []))} 个")
            items = result.get("items", [])
            if items:
                items_str = " | ".join(f'{i["type"]}:{i["value"]}' for i in items)
                print(f"📦 产物: {items_str}")

    except Exception as e:
        print(f"❌ 未知错误: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()