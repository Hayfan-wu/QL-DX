"""
中国电信话费自动化 - 配置管理
=============================
从 .env 文件和环境变量读取配置，
支持青龙面板环境变量注入。

活动入口共 10 个（7个网页可自动化 + 3个APP专属仅供参考）
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

# ==================== 基础URL ====================
URL_189_HOME: str = "https://www.189.cn"
URL_LOGIN: str = "https://www.189.cn/login/"

# ===================================================================
#  全部 10 个活动入口（含产物说明）
# ===================================================================

# ── 一、网页自动化活动（7个）──

# ① 签到翻牌抽奖
#    产物: 话费(0.1~100元)、金豆(20~1500)、流量包、生肖卡
URL_SIGNIN = "https://wapact.189.cn:9001/mas-pub-ui/spm/Spring2024?activityCode=ACTCODE20240119MNXBTVOB"

# ② 金豆商城转盘抽奖
#    产物: 话费、金豆、优惠券
URL_BEAN_LOTTERY = "https://wapact.189.cn:9001/JinDouMall/JinDouMall_luckDraw.html"

# ③ 见面礼-暖心福利包
#    产物: 200金豆、翼回收20元加价券
#    时间: 2026.7.1 - 2026.7.31
URL_GREETING = "https://wappark.189.cn/resources/shortMessage/rearendMoneyWap.html"

# ④ 见面礼短链接
#    产物: 同③（重定向）
URL_GREETING_SHORT = "http://a.189.cn/NeYzRQ"

# ⑤ 积分商城
#    产物: 话费、流量包、实物礼品
URL_JF_MALL = "https://jf.189.cn"

# ⑥ 积分商城备用域名
#    产物: 同⑤
URL_JF_MALL_ALT = "http://jf.ct10000.com/"

# ⑦ 口令兑换
#    产物: 话费(0.66~100元)
URL_CODE_EXCHANGE = "https://wapact.189.cn:9001/flcj/index.html?welfareId=61ad82d62118ed64c88ec7e6"


# ── 二、APP专属活动（3个，网页无法自动化，仅供参考）──

# ⑧ 每日签到领金豆 (APP首页 → 签到)
#    产物: 金豆(20~35个/天)、连续签到额外抽奖机会

# ⑨ 金豆秒杀0.5元话费 (APP金豆商城 → 兑换区)
#    产物: 0.5元话费 (100金豆兑换，每日10:00限量)

# ⑩ 金豆秒杀1元话费 (APP金豆商城 → 兑换区)
#    产物: 1元话费 (200金豆兑换，每日14:00限量)


# ===================================================================
#  实际自动化执行的活动列表（5个核心活动）
# ===================================================================
ACTIVITY_URLS: list = [
    URL_SIGNIN,           # ① 签到翻牌 → 话费/金豆/流量
    URL_BEAN_LOTTERY,     # ② 金豆抽奖 → 话费/金豆/优惠券
    URL_GREETING,         # ③ 见面礼   → 200金豆
    URL_JF_MALL,          # ⑤ 积分商城 → 话费/流量/实物
    URL_CODE_EXCHANGE,    # ⑦ 口令兑换 → 0.66~100元话费
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