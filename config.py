"""
中国电信话费自动化 - 配置管理
=============================
从 .env 文件和环境变量读取配置，
支持青龙面板环境变量注入。

改造说明: 从 Playwright 浏览器模式迁移到 API 直调模式，
不再需要 Chromium，只需 execjs + httpx + pycryptodome。
"""

import os
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = True) -> bool:
    val = _env(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


# ==================== 电信账号 ====================
# 环境变量名: chinaTelecomAccount (原始脚本) 或 DX_ACCOUNT (兼容)
# 格式: 手机号#服务密码
_ACCOUNT_RAW: str = _env("chinaTelecomAccount") or _env("DX_ACCOUNT")
if _ACCOUNT_RAW and "#" in _ACCOUNT_RAW:
    PHONE, PASSWORD = _ACCOUNT_RAW.split("#", 1)
else:
    PHONE = ""
    PASSWORD = ""

# ==================== 青龙面板 ====================
QL_URL: str = _env("QL_URL", "http://127.0.0.1:5700")
QL_CLIENT_ID: str = _env("QL_CLIENT_ID")
QL_CLIENT_SECRET: str = _env("QL_CLIENT_SECRET")

# ==================== 功能开关 ====================
ENABLE_SIGNIN: bool = _env_bool("DX_ENABLE_SIGNIN", True)
ENABLE_ACTIVITY: bool = _env_bool("DX_ENABLE_ACTIVITY", True)
ENABLE_FLASH_SALE: bool = _env_bool("DX_ENABLE_FLASH_SALE", False)

# ==================== 秒杀时间 ====================
FLASH_SALE_TIME: str = _env("DX_FLASH_SALE_TIME", "10:00:00")

# ==================== 运行配置 ====================
HEADLESS: bool = _env_bool("DX_HEADLESS", True)  # 保留兼容
TIMEOUT: int = _env_int("DX_TIMEOUT", 30)

# ==================== 项目路径 ====================
PROJECT_DIR: Path = Path(__file__).resolve().parent
COOKIE_FILE: Path = PROJECT_DIR / "cookies.json"
LOG_FILE: Path = PROJECT_DIR / "dx_telecom.log"
RESULT_FILE: Path = PROJECT_DIR / "result.json"
SCREENSHOT_DIR: Path = PROJECT_DIR / "screenshots"


def validate() -> bool:
    """校验必要配置"""
    if not PHONE or not PASSWORD:
        print("[配置错误] DX_ACCOUNT 未设置（格式: 手机号#密码）")
        return False
    return True