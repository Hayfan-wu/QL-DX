"""
中国电信话费自动化 - 配置管理
=============================
从 .env 文件和环境变量读取配置，
支持青龙面板环境变量注入。
"""

import os
from pathlib import Path
from typing import Optional


def _env(key: str, default: str = "") -> str:
    """读取环境变量，优先 .env 文件"""
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = True) -> bool:
    """读取布尔型环境变量"""
    val = _env(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")


def _env_int(key: str, default: int = 0) -> int:
    """读取整型环境变量"""
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


# ==================== 电信账号 ====================
PHONE: str = _env("DX_PHONE")
PASSWORD: str = _env("DX_PASSWORD")

# ==================== 青龙面板 ====================
QL_URL: str = _env("QL_URL", "http://127.0.0.1:5700")
QL_CLIENT_ID: str = _env("QL_CLIENT_ID")
QL_CLIENT_SECRET: str = _env("QL_CLIENT_SECRET")

# ==================== 功能开关 ====================
ENABLE_SIGNIN: bool = _env_bool("DX_ENABLE_SIGNIN", True)
ENABLE_EXCHANGE: bool = _env_bool("DX_ENABLE_EXCHANGE", True)
ENABLE_ACTIVITY: bool = _env_bool("DX_ENABLE_ACTIVITY", True)
ENABLE_FLASH_SALE: bool = _env_bool("DX_ENABLE_FLASH_SALE", True)

# ==================== 兑换阈值 ====================
MIN_BEANS_TO_EXCHANGE: int = _env_int("DX_MIN_BEANS_TO_EXCHANGE", 100)

# ==================== 秒杀时间 ====================
FLASH_SALE_TIME: str = _env("DX_FLASH_SALE_TIME", "10:00:00")

# ==================== 浏览器配置 ====================
HEADLESS: bool = _env_bool("DX_HEADLESS", True)
TIMEOUT: int = _env_int("DX_TIMEOUT", 30)
PAGE_LOAD_WAIT: int = 3

# ==================== 项目路径 ====================
PROJECT_DIR: Path = Path(__file__).resolve().parent
COOKIE_FILE: Path = PROJECT_DIR / "cookies.json"
LOG_FILE: Path = PROJECT_DIR / "dx_telecom.log"
SCREENSHOT_DIR: Path = PROJECT_DIR / "screenshots"

# ==================== 活动URL ====================
URL_189_HOME: str = "https://www.189.cn"
URL_LOGIN: str = "https://www.189.cn/login/"

# 签到活动页
URL_SIGNIN: str = "https://wapact.189.cn:9001/mas-pub-ui/spm/Spring2024?activityCode=ACTCODE20240119MNXBTVOB"

# 金豆抽奖
URL_BEAN_LOTTERY: str = "https://wapact.189.cn:9001/JinDouMall/JinDouMall_luckDraw.html"

# 见面礼
URL_GREETING: str = "https://wappark.189.cn/resources/shortMessage/rearendMoneyWap.html"

# 积分商城
URL_JF_MALL: str = "https://jf.189.cn"

# 口令兑换
URL_CODE_EXCHANGE: str = "https://wapact.189.cn:9001/flcj/index.html?welfareId=61ad82d62118ed64c88ec7e6"

# 兑换码入口
URL_REDEEM: str = "https://wapact.189.cn:9001/InvitationCode/inviteesNew4.html"

# 所有活动页面列表
ACTIVITY_URLS: list = [
    URL_SIGNIN,
    URL_BEAN_LOTTERY,
    URL_GREETING,
    URL_CODE_EXCHANGE,
    URL_REDEEM,
]


def validate() -> bool:
    """校验必要配置"""
    errors = []
    if not PHONE:
        errors.append("DX_PHONE 未设置")
    if not PASSWORD:
        errors.append("DX_PASSWORD 未设置")
    if errors:
        print("[配置错误] " + "; ".join(errors))
        return False
    return True