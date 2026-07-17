"""
中国电信话费自动化 - 配置管理
=============================
纯宿主机部署，从 .env 文件和环境变量读取配置。

活动入口共 5 个（2个网页可自动化 + 3个APP专属仅供参考）
"""

import os
from pathlib import Path
from typing import Optional


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
# DX_ACCOUNT 格式: 手机号#密码
_ACCOUNT_RAW: str = _env("DX_ACCOUNT")
if _ACCOUNT_RAW and "#" in _ACCOUNT_RAW:
    PHONE, PASSWORD = _ACCOUNT_RAW.split("#", 1)
else:
    PHONE = ""
    PASSWORD = ""

# ==================== 功能开关 ====================
ENABLE_SIGNIN: bool = _env_bool("DX_ENABLE_SIGNIN", True)
ENABLE_ACTIVITY: bool = _env_bool("DX_ENABLE_ACTIVITY", True)
ENABLE_FLASH_SALE: bool = _env_bool("DX_ENABLE_FLASH_SALE", True)

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

# ==================== 基础URL ====================
URL_189_HOME: str = "https://www.189.cn"
URL_LOGIN: str = "https://www.189.cn/login/"

# ===================================================================
#  全部 5 个活动入口（含产物说明）
# ===================================================================

# ── 一、网页自动化活动（2个）──

# ① 签到翻牌抽奖
#    产物: 话费(0.1~100元)、金豆(20~1500)、流量包、生肖卡
URL_SIGNIN = "https://wapact.189.cn:9001/mas-pub-ui/spm/Spring2024?activityCode=ACTCODE20240119MNXBTVOB"

# ② 口令兑换
#    产物: 话费(0.66~100元)
URL_CODE_EXCHANGE = "https://wapact.189.cn:9001/flcj/index.html?welfareId=61ad82d62118ed64c88ec7e6"


# ── 二、APP专属活动（3个，网页无法自动化，仅供参考）──

# ③ 每日签到领金豆 (APP首页 → 签到)
#    产物: 金豆(20~35个/天)、连续签到额外抽奖机会

# ④ 金豆秒杀0.5元话费 (APP金豆商城 → 兑换区)
#    产物: 0.5元话费 (100金豆兑换，每日10:00限量)

# ⑤ 金豆秒杀1元话费 (APP金豆商城 → 兑换区)
#    产物: 1元话费 (200金豆兑换，每日14:00限量)


# ===================================================================
#  实际自动化执行的活动列表（2个核心活动）
# ===================================================================
ACTIVITY_URLS: list = [
    URL_SIGNIN,           # ① 签到翻牌 → 话费/金豆/流量
    URL_CODE_EXCHANGE,    # ② 口令兑换 → 0.66~100元话费
]


def validate() -> bool:
    """校验必要配置"""
    if not PHONE or not PASSWORD:
        print("[配置错误] DX_ACCOUNT 未设置（格式: 手机号#密码）")
        return False
    return True