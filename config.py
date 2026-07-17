"""
中国电信话费自动化 - 配置管理
=============================
从 .env 文件和环境变量读取配置，
支持青龙面板环境变量注入。

活动入口共 17 个，分三类：
  ✅ 保留 = 全国通用、网页可直接自动化
  ⚠️ 过滤 = 地区限制 / 需APP / 需兑换码 / 过期
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
#  全部 17 个活动入口（含保留/过滤标注）
# ===================================================================

# ── 一、核心活动（✅ 保留，全国通用，网页可自动化）──

# ① 签到活动页（翻牌抽话费/金豆）
URL_SIGNIN = "https://wapact.189.cn:9001/mas-pub-ui/spm/Spring2024?activityCode=ACTCODE20240119MNXBTVOB"

# ② 金豆商城转盘抽奖
URL_BEAN_LOTTERY = "https://wapact.189.cn:9001/JinDouMall/JinDouMall_luckDraw.html"

# ③ 见面礼 - 暖心福利包（登录领200金豆，至2026.7.31）
URL_GREETING = "https://wappark.189.cn/resources/shortMessage/rearendMoneyWap.html"

# ④ 见面礼短链接（重定向到③）
URL_GREETING_SHORT = "http://a.189.cn/NeYzRQ"

# ⑤ 积分商城（积分兑话费/流量）
URL_JF_MALL = "https://jf.189.cn"

# ⑥ 积分商城备用域名
URL_JF_MALL_ALT = "http://jf.ct10000.com/"

# ⑦ 口令兑换（输入省份口令抽话费，0.66~100元）
URL_CODE_EXCHANGE = "https://wapact.189.cn:9001/flcj/index.html?welfareId=61ad82d62118ed64c88ec7e6"


# ── 二、过滤活动（⚠️ 需兑换码/地区限制/已过期，默认不启用）──

# ⑧ 兑换码兑奖入口 — ⚠️ 需提前获取兑换码，无自动获取途径
URL_REDEEM = "https://wapact.189.cn:9001/InvitationCode/inviteesNew4.html"

# ⑨ 天津 - 充值抽奖（每充20元抽1次，至2026.7.31）— ⚠️ 地区限制+需充值
URL_TJ_RECHARGE_DRAW = "https://waptj.189.cn/tj/wap/rechargeDraw.html"

# ⑩ 安徽 - 权益会员日翻牌（每周三~周五）— ⚠️ 地区限制
URL_AH_MEMBER_DAY = "https://qy.ah.189.cn/member/qyMemberDay/index.html"

# ⑪ 河北 - 周三宠粉日转盘（消耗100翼豆）— ⚠️ 地区限制
URL_HE_WEDNESDAY = "http://hyzx.he.189.cn/qyportal/static/qy/qypt/Wednesday/wednesday.html"

# ⑫ 湖南 - 聚合权益流量包赠6元话费（首次订购）— ⚠️ 地区限制+需订购
URL_HN_FLOW_PACK = "https://qy.hn.189.cn/h5app/equity/#/polymerize-equity-flow-index"

# ⑬ 江苏 - 人人有礼 — ⚠️ 地区限制
URL_JS_EVERYONE_GIFT = "http://wapjs.189.cn/mall/pages/jhAll/index.html"

# ⑭ 江苏 - 签到领流量（已迁移至APP）— ⚠️ 已过期/迁移
URL_JS_SIGNIN = "http://wapjs.189.cn/mall/pages/signinActivity/index.html"


# ── 三、APP专属活动（⚠️ 仅在APP内，网页无法自动化，仅供参考）──

# ⑮ 每日签到领金豆（20-35金豆/天）— APP首页 → 签到
# ⑯ 金豆兑换话费秒杀（100金豆兑0.5元，每日10:00）— APP金豆商城 → 兑换区
# ⑰ 金豆兑换话费秒杀（200金豆兑1元，每日14:00）— APP金豆商城 → 兑换区


# ===================================================================
#  实际自动化执行的活动列表（仅保留 ✅ 核心活动）
# ===================================================================
ACTIVITY_URLS: list = [
    URL_SIGNIN,           # ① 签到翻牌
    URL_BEAN_LOTTERY,     # ② 金豆抽奖
    URL_GREETING,         # ③ 见面礼
    URL_JF_MALL,          # ⑤ 积分商城
    URL_CODE_EXCHANGE,    # ⑦ 口令兑换
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