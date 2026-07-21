"""
中国电信话费自动化 - 单文件自包含脚本 (青龙面板 / API直调版)
================================================================
基于 execjs + httpx 实现，无需 Playwright/Chromium。
直接调用电信 API 完成登录、签到、兑换等全部操作。

核心功能:
- 瑞数反爬绕过 (execjs 执行 JS 挑战)
- 服务密码登录 (RSA 加密)
- 每日签到 + 翻牌
- 连签奖励兑换 (7天/15天/28天)
- 首页任务 (领取奖励/看视频/聚合任务)
- 宠物乐园 (喂食/升级/兑换话费)
- 金豆余额查询
- Token 缓存 (避免重复登录)
- 产物记录 (result.json)

青龙定时任务:
  任务名: DX-Telecom
  命令: task dx_auto.py
  定时: 0 8,12,18 * * *

依赖安装:
  pip install httpx PyExecJS pycryptodome --break-system-packages
  (需要 Node.js 运行时支持 PyExecJS)
"""

import base64
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import execjs
import httpx
from Crypto.Cipher import AES, PKCS1_v1_5, DES3
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

# ==================== .env 自动加载 ====================
_PROJECT_DIR = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_DIR / ".env"
if _ENV_FILE.exists():
    with open(str(_ENV_FILE), "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                # 系统变量优先，.env 文件不覆盖已有值
                if _key.strip() not in os.environ:
                    os.environ.setdefault(_key.strip(), _val.strip().strip("\"'"))

# ==================== 配置 (原 config.py) ====================

PROJECT_DIR = Path(__file__).resolve().parent

# DX_ACCOUNT 格式: 手机号#密码
_ACCOUNT_RAW = os.environ.get("DX_ACCOUNT", "")
if _ACCOUNT_RAW and "#" in _ACCOUNT_RAW:
    PHONE, PASSWORD = _ACCOUNT_RAW.split("#", 1)
else:
    PHONE = ""
    PASSWORD = ""

ENABLE_SIGNIN = os.environ.get("DX_ENABLE_SIGNIN", "true").lower() in ("true", "1", "yes", "on")
ENABLE_ACTIVITY = os.environ.get("DX_ENABLE_ACTIVITY", "true").lower() in ("true", "1", "yes", "on")
ENABLE_FLASH_SALE = os.environ.get("DX_ENABLE_FLASH_SALE", "false").lower() in ("true", "1", "yes", "on")
FLASH_SALE_TIME = os.environ.get("DX_FLASH_SALE_TIME", "10:00:00")

RESULT_FILE = PROJECT_DIR / "result.json"
LOG_FILE = PROJECT_DIR / "dx_telecom.log"
CACHE_FILE = PROJECT_DIR / "chinaTelecom_cache.json"
RS_CORE_JS = PROJECT_DIR / "rs_core.js"
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"

# ==================== 加密常量 ====================

# 登录 RSA 公钥 (加密密码)
LOGIN_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDBkLT15ThVgz6/NOl6s8GNPofd"
    "WzWbCkWnkaAm7O2LjkM1H7dMvzkiqdxU02jamGRHLX/ZNMCXHnPcW/sDhiFCBN18"
    "qFvy8g6VYb9QtroI09e176s+ZCtiv7hbin2cCTj99iUpnEloZm19lwHyo69u5UMi"
    "PMpq0/XKBO8lYhN/gwIDAQAB"
)

# para 加密 RSA 公钥 (wappark API 请求体加密)
PARA_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+ugG5A8cZ3FqUKDwM57GM4io6"
    "JGcStivT8UdGt67PEOihLZTw3P7371+N47PrmsCpnTRzbTgcupKtUv8ImZalYk65"
    "dU8rjC/ridwhw9ffW2LBwvkEnDkkKKRi2liWIItDftJVBiWOh17o6gfbPoNrWORc"
    "Adcbpk2L+udld5kZNwIDAQAB"
)

# 3DES 密钥和 IV (用于 ticket 加密)
DES3_KEY = b'1234567`90koiuyhgtfrdews'
DES3_IV = b'\0\0\0\0\0\0\0\0'

# AES 密钥 (用于签到数据加密)
AES_KEY = b'34d7cb0bcdf07523'

# API 基础 URL
LOGIN_API = "https://appgologin.189.cn:9031/login/client/userLoginNormal"
TICKET_API = "https://appgologin.189.cn:9031/map/clientXML"
SSO_SIGN_API = "https://wappark.189.cn/jt-sign/ssoHomLogin"
SIGN_API = "https://wappark.189.cn/jt-sign/webSign/sign"
USER_STATUS_API = "https://wappark.189.cn/jt-sign/api/home/userStatusInfo"
USER_COIN_API = "https://wappark.189.cn/jt-sign/api/home/userCoinInfo"
CONTINUE_SIGN_API = "https://wappark.189.cn/jt-sign/webSign/continueSignDays"
CONTINUE_RECORDS_API = "https://wappark.189.cn/jt-sign/webSign/continueSignRecords"
EXCHANGE_PRIZE_API = "https://wappark.189.cn/jt-sign/webSign/exchangePrize"
HOMEPAGE_API = "https://wappark.189.cn/jt-sign/webSign/homepage"
RECEIVE_REWARD_API = "https://wappark.189.cn/jt-sign/paradise/receiveReward"
OPEN_MSG_API = "https://wappark.189.cn/jt-sign/paradise/openMsg"
POLYMERIZE_API = "https://wappark.189.cn/jt-sign/webSign/polymerize"
FOOD_API = "https://wappark.189.cn/jt-sign/paradise/food"
PARADISE_INFO_API = "https://wappark.189.cn/jt-sign/paradise/getParadiseInfo"
GET_LEVEL_RIGHTS_API = "https://wappark.189.cn/jt-sign/paradise/getLevelRightsList"
GET_CONVERSION_API = "https://wappark.189.cn/jt-sign/paradise/getConversionRights"
CONVERSION_RIGHTS_API = "https://wappark.189.cn/jt-sign/paradise/conversionRights"

# 瑞数初始化 URL
RS_INIT_URL = "https://wappark.189.cn/jt-sign/webSign/homepage"

# User-Agent
UA = (
    "Mozilla/5.0 (Linux; U; Android 12; zh-cn; ONEPLUS A9000 "
    "Build/QKQ1.190716.003) AppleWebKit/533.1 (KHTML, like Gecko) "
    "Version/5.0 Mobile Safari/533.1"
)

# ==================== 日志 ====================
SCREENSHOT_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DX-Telecom")


# ==================== 产物记录 ====================
def _load_results() -> dict:
    if RESULT_FILE.exists():
        try:
            return json.loads(RESULT_FILE.read_text())
        except Exception:
            pass
    return {"total": {}, "history": []}


def _save_result(run_result: dict):
    records = _load_results()
    run_result["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records["history"].append(run_result)
    for item in run_result.get("items", []):
        key = item.get("type", "其他")
        val = item.get("value", "")
        if key not in records["total"]:
            records["total"][key] = []
        records["total"][key].append({"time": run_result["time"], "value": val})
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))


def query_results() -> str:
    """查询所有历史任务产物 (供 bot 插件调用)"""
    records = _load_results()
    total = records.get("total", {})
    history = records.get("history", [])
    if not history:
        return "暂无任务执行记录，请先执行 电信签到 或 电信执行"
    last = history[-1]
    lines = [
        "电信任务产物查询",
        "==================================",
        f"最近执行: {last.get('time', '未知')}",
        f"累计执行: {len(history)} 次",
        "==================================",
        "累计获得产物:",
    ]
    if total:
        for key, items in total.items():
            lines.append(f"  {key}: {len(items)} 次")
            for item in items[-3:]:
                lines.append(f"    - {item['time']}: {item['value']}")
    else:
        lines.append("  (暂无产物记录)")
    lines.append("==================================")
    lines.append("最近一次详情:")
    for item in last.get("items", []):
        lines.append(f"  {item.get('type', '?')}: {item.get('value', '?')}")
    if last.get("signin"):
        lines.append(f"  签到: {last['signin'].get('msg', '-')}")
    if last.get("error"):
        lines.append(f"  [错误] {last['error']}")
    return "\n".join(lines)


# ==================== 缓存管理 ====================
def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ==================== 加密工具 ====================
def _rsa_encrypt(data: str, public_key_pem: str) -> str:
    """RSA PKCS1 加密，返回 hex 字符串
    支持纯 base64 字符串自动包装 PEM 格式
    """
    # 自动包装 PEM 格式
    if "BEGIN" not in public_key_pem:
        lines = [public_key_pem[i:i+64] for i in range(0, len(public_key_pem), 64)]
        pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"
    else:
        pem = public_key_pem
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(data.encode())
    return encrypted.hex()


def _des3_encrypt(text: str) -> str:
    """3DES CBC 加密，返回 hex 字符串"""
    cipher = DES3.new(DES3_KEY, DES3.MODE_CBC, DES3_IV)
    ciphertext = cipher.encrypt(pad(text.encode(), DES3.block_size))
    return ciphertext.hex()


def _des3_decrypt(hex_text: str) -> str:
    """3DES CBC 解密"""
    from Crypto.Util.Padding import unpad
    ciphertext = bytes.fromhex(hex_text)
    cipher = DES3.new(DES3_KEY, DES3.MODE_CBC, DES3_IV)
    plaintext = unpad(cipher.decrypt(ciphertext), DES3.block_size)
    return plaintext.decode()


def _aes_encrypt(data: str) -> str:
    """AES-ECB-Pkcs7 加密，返回 hex 字符串"""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    ciphertext = cipher.encrypt(pad(data.encode(), AES.block_size))
    return ciphertext.hex()


def _encode_phone(phone: str) -> str:
    """手机号编码：每个字符 ASCII +2"""
    return "".join(chr(ord(c) + 2) for c in phone)


def _encode_password(password: str) -> str:
    """密码编码：每个字符 ASCII +2"""
    return "".join(chr(ord(c) + 2) for c in password)


def _encrypt_para(data: dict) -> str:
    """加密 wappark API 请求参数 (RSA + hex)"""
    return _rsa_encrypt(json.dumps(data, separators=(",", ":")), PARA_PUBLIC_KEY)


def _generate_uuid() -> list:
    """生成 UUID v4 格式数组（与原始 JS 脚本一致）
    返回: [8位, 4位, '4xxx', 4位, 12位]
    """
    hex_chars = "abcdef0123456789"
    def _rand(pattern: str) -> str:
        return "".join(
            c if c != "x" else random.choice(hex_chars)
            for c in pattern
        )
    return [
        _rand("xxxxxxxx"),      # 8位
        _rand("xxxx"),          # 4位
        _rand("4xxx"),          # 4位，第一位固定为4
        _rand("xxxx"),          # 4位
        _rand("xxxxxxxxxxxx"),  # 12位
    ]


def _random_delay(a: float = 0.5, b: float = 2.0):
    time.sleep(random.uniform(a, b))


# ==================== HTTP 客户端 ====================
class TelecomClient:
    """电信 API HTTP 客户端"""

    def __init__(self):
        self.client = httpx.Client(
            timeout=30,
            verify=False,
            follow_redirects=False,
            headers={
                "User-Agent": UA,
                "Connection": "keep-alive",
            },
        )
        self.rs_cookies: dict = {}
        self.sign: str = ""
        self.ticket: str = ""
        self.token: str = ""
        self.userId: str = ""
        self.phone: str = ""
        self._rs_js_ctx = None

    def close(self):
        self.client.close()

    # ---------- 瑞数绕过 ----------
    def _init_rs_cookies(self, url: str = RS_INIT_URL) -> dict:
        """初始化瑞数反爬 Cookie"""
        logger.info("=" * 50)
        logger.info("初始化瑞数反爬 Cookie...")

        try:
            # 1. 请求目标页面
            resp = self.client.post(url)
            if resp.status_code != 200:
                logger.warning(f"瑞数初始化返回 {resp.status_code}")
                return {}

            # 提取 Set-Cookie (yiUIIlbdQT3fO)
            yiUIIlbdQT3fO = ""
            if "set-cookie" in resp.headers:
                for ck in resp.headers.get_list("set-cookie"):
                    if "yiUIIlbdQT3fO" in ck:
                        yiUIIlbdQT3fO = ck.split(";")[0].split("=")[1]
                        break

            # 2. 提取 content code
            text = resp.text
            content_match = re.search(r' content="([^"]*)" r=', text)
            if not content_match:
                logger.warning("未找到 content code")
                return {}
            content_code = content_match.group(1)

            # 3. 提取 ts code
            ts_match = re.search(r'\$_ts=window([^<]*)</script><script', text)
            if not ts_match:
                logger.warning("未找到 ts code")
                return {}
            ts_code = "$_ts=window" + ts_match.group(1)

            # 4. 提取外部 JS URL
            js_url_match = re.search(
                r'\$_ts\.lcd\(\);</script><script[^>]*src="([^"]*)"',
                text
            )
            if not js_url_match:
                logger.warning("未找到外部 JS URL")
                return {}
            js_path = js_url_match.group(1)
            parsed = urlparse(url)
            js_full_url = f"{parsed.scheme}://{parsed.netloc}{js_path}"

            # 5. 下载外部 JS
            js_resp = self.client.get(js_full_url)
            if js_resp.status_code != 200:
                logger.warning(f"下载外部 JS 失败: {js_resp.status_code}")
                return {}
            external_js = js_resp.text

            # 6. 组装并执行 JS (读取同目录下的 rs_core.js)
            rs_template = RS_CORE_JS.read_text(encoding="utf-8")
            combined_js = rs_template.replace(
                '"CONTENT_PLACEHOLDER"', json.dumps(content_code)
            ).replace(
                "// TS_CODE_PLACEHOLDER", ts_code + "\n" + external_js
            )

            ctx = execjs.compile(combined_js)
            cookie_result = ctx.call("main")
            yiUIIlbdQT3fP = cookie_result.split("=")[1] if "=" in cookie_result else ""

            self._rs_js_ctx = ctx
            self.rs_cookies = {
                "yiUIIlbdQT3fO": yiUIIlbdQT3fO,
                "yiUIIlbdQT3fP": yiUIIlbdQT3fP,
            }

            logger.info("瑞数 Cookie 初始化成功")
            return self.rs_cookies

        except Exception as e:
            logger.error(f"瑞数初始化异常: {e}")
            return {}

    def _get_rs_headers(self) -> dict:
        """获取带瑞数 Cookie 的请求头"""
        if not self.rs_cookies:
            self._init_rs_cookies()
        ck = self.rs_cookies
        cookie_str = ""
        if ck.get("yiUIIlbdQT3fP"):
            cookie_str += f"yiUIIlbdQT3fP={ck['yiUIIlbdQT3fP']}; "
        if ck.get("yiUIIlbdQT3fO"):
            cookie_str += f"yiUIIlbdQT3fO={ck['yiUIIlbdQT3fO']}"
        return {
            "User-Agent": UA,
            "Cookie": cookie_str.strip(),
            "sign": self.sign,
        }

    # ---------- 登录 ----------
    def login(self, phone: str, password: str) -> bool:
        """服务密码登录，获取 token 和 userId"""
        logger.info("=" * 50)
        logger.info(f"开始登录: {phone[:3]}****{phone[-4:]}")

        # 检查缓存
        cache = _load_cache()
        if phone in cache:
            entry = cache[phone]
            if entry.get("token") and entry.get("userId"):
                age = (time.time() * 1000 - entry.get("t", 0)) / 1000
                if age < 86400:  # 24小时内有效
                    self.token = entry["token"]
                    self.userId = entry["userId"]
                    self.phone = phone
                    logger.info("从缓存恢复登录状态")
                    return True

        self.phone = phone
        uuid_arr = _generate_uuid()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # 构造登录加密串 (uuid.slice(0, 2).join(""))
        uuid_prefix = "".join(uuid_arr[:2])  # 12位
        login_str = (
            f"iPhone 14 15.4.{uuid_prefix}{phone}{timestamp}{password}0$$$0."
        )
        encrypted = _rsa_encrypt(login_str, LOGIN_PUBLIC_KEY)

        payload = {
            "headerInfos": {
                "code": "userLoginNormal",
                "timestamp": timestamp,
                "broadAccount": "",
                "broadToken": "",
                "clientType": "#10.5.0#channel50#iPhone 14 Pro Max#",
                "shopId": "20002",
                "source": "110003",
                "sourcePassword": "Sid98s",
                "token": "",
                "userLoginName": _encode_phone(phone),
            },
            "content": {
                "attach": "test",
                "fieldData": {
                    "loginType": "4",
                    "accountType": "",
                    "loginAuthCipherAsymmertric": encrypted,
                    "deviceUid": "".join(uuid_arr[:3]),  # 16位
                    "phoneNum": _encode_phone(phone),
                    "isChinatelecom": "0",
                    "systemVersion": "15.4.0",
                    "authentication": _encode_password(password),
                },
            },
        }

        try:
            resp = self.client.post(
                LOGIN_API,
                json=payload,
                headers={"User-Agent": UA},
            )
            logger.info(f"登录响应状态: {resp.status_code}")

            if not resp.text:
                logger.error("登录响应为空")
                return False

            try:
                data = resp.json()
            except Exception:
                logger.error(f"登录响应非JSON: {resp.text[:500]}")
                return False

            if not isinstance(data, dict):
                logger.error(f"登录响应非dict: {type(data)}, 内容: {str(data)[:300]}")
                return False

            resp_data = data.get("responseData") or {}
            result_code = resp_data.get("resultCode", -1) if isinstance(resp_data, dict) else str(resp_data)

            logger.info(f"登录响应码: {result_code}")

            if result_code == "0000":
                # 正常登录成功
                login_result = (resp_data.get("data") or {}).get("loginSuccessResult") or {}
                self.userId = login_result.get("userId", "")
                self.token = login_result.get("token", "")

                if self.token:
                    logger.info(f"登录成功 [{result_code}]")
                    cache[phone] = {
                        "token": self.token,
                        "userId": self.userId,
                        "t": int(time.time() * 1000),
                    }
                    _save_cache(cache)
                    return True
                else:
                    logger.error(f"登录返回 [{result_code}] 但无 token")
                    return False
            elif result_code == "3006":
                # 3006 通常表示需要短信验证/密码过期/账号异常，并非真正登录成功
                result_desc = resp_data.get("resultDesc", "") if isinstance(resp_data, dict) else ""
                logger.error(f"登录失败 [{result_code}]: {result_desc or '可能需要短信验证或密码已过期，请手动登录电信APP确认账号状态'}")
                logger.debug(f"完整响应: {json.dumps(data, ensure_ascii=False)[:500]}")
                return False
            else:
                msg = (
                    data.get("msg", "")
                    or (resp_data.get("resultDesc", "") if isinstance(resp_data, dict) else "")
                    or (data.get("headerInfos") or {}).get("reason", "")
                )
                logger.error(f"登录失败 [{result_code}]: {msg}")
                return False

        except Exception as e:
            logger.error(f"登录异常: {e}")
            return False

    # ---------- 获取 Ticket ----------
    def get_ticket(self) -> bool:
        """获取 ticket"""
        logger.info("获取 ticket...")

        if not self.token or not self.userId:
            logger.error("未登录，无法获取 ticket")
            return False

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        encrypted_user_id = _des3_encrypt(self.userId)

        # 构造 XML 请求体
        xml_body = (
            '<Request>'
            '<HeaderInfos>'
            f'<Code>getSingle</Code>'
            f'<Timestamp>{timestamp}</Timestamp>'
            f'<Token>{self.token}</Token>'
            f'<SourcePassword>Sid98s</SourcePassword>'
            f'<Source>110003</Source>'
            f'<ShopId>20002</ShopId>'
            f'<ClientType>#9.6.1#channel50#iPhone 14 Pro Max#</ClientType>'
            f'<BroadToken></BroadToken>'
            f'<BroadAccount></BroadAccount>'
            f'<UserLoginName>{self.phone}</UserLoginName>'
            '</HeaderInfos>'
            '<Content>'
            '<Attach>test</Attach>'
            '<FieldData>'
            f'<TargetId>{encrypted_user_id}</TargetId>'
            f'<Url>4a686283754b154</Url>'
            f'<Request/>'
            '</FieldData>'
            '</Content>'
            '</Request>'
        )

        try:
            resp = self.client.post(
                TICKET_API,
                content=xml_body,
                headers={
                    "User-Agent": UA,
                    "Content-Type": "text/xml",
                },
            )
            text = resp.text

            # 提取加密的 ticket
            ticket_match = re.search(r"<Ticket>(\w+)</Ticket>", text)
            if ticket_match:
                encrypted_ticket = ticket_match.group(1)
                self.ticket = _des3_decrypt(encrypted_ticket)
                logger.info("获取 ticket 成功")
                return True
            else:
                logger.warning("未找到 ticket，尝试重新登录")
                if self.login(self.phone, PASSWORD):
                    return self.get_ticket()
                return False

        except Exception as e:
            logger.error(f"获取 ticket 异常: {e}")
            return False

    # ---------- 获取 Sign ----------
    def get_sign(self) -> bool:
        """获取 sign token"""
        logger.info("获取 sign...")

        if not self.ticket:
            logger.error("无 ticket")
            return False

        params = {"ticket": self.ticket}

        try:
            resp = self.client.get(
                SSO_SIGN_API,
                params=params,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                self.sign = data.get("sign", "")
                logger.info("获取 sign 成功")
                return True
            else:
                logger.error(f"获取 sign 失败 [{result_code}]: {data}")
                return False

        except Exception as e:
            logger.error(f"获取 sign 异常: {e}")
            return False

    # ---------- 金豆查询 ----------
    def user_coin_info(self, notify: bool = False) -> dict:
        """查询金豆余额"""
        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                USER_COIN_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                coin = data.get("totalCoin", 0)
                if notify:
                    logger.info(f"金豆余额: {coin}")
                    if data.get("amountEx"):
                        expire_date = datetime.fromtimestamp(
                            data.get("expireDate", 0) / 1000
                        ).strftime("%Y-%m-%d")
                        logger.info(
                            f"-- [{expire_date}将过期] {data['amountEx']}金豆"
                        )
                return {"ok": True, "coin": coin}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"查询金豆失败 [{result_code}]: {msg}")
                return {"ok": False, "msg": msg}

        except Exception as e:
            logger.error(f"查询金豆异常: {e}")
            return {"ok": False, "msg": str(e)}

    # ---------- 签到状态 + 签到 ----------
    def user_status_info(self) -> dict:
        """查询签到状态，未签则签到"""
        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                USER_STATUS_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                is_sign = data.get("data", {}).get("isSign", False)
                if is_sign:
                    logger.info("今日已签到")
                    return {"ok": True, "signed": True, "msg": "今日已签到"}

                # 未签到，执行签到
                return self.do_sign()
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"查询签到状态失败 [{result_code}]: {msg}")
                return {"ok": False, "msg": msg}

        except Exception as e:
            logger.error(f"查询签到状态异常: {e}")
            return {"ok": False, "msg": str(e)}

    def do_sign(self) -> dict:
        """执行签到"""
        logger.info("执行签到...")

        try:
            sign_data = {
                "phone": self.phone,
                "date": int(time.time() * 1000),
                "sysType": "20002",
            }
            encoded = _aes_encrypt(json.dumps(sign_data, separators=(",", ":")))

            payload = {"encode": encoded}
            resp = self.client.post(
                SIGN_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                inner_code = data.get("data", {}).get("code", -1)
                if inner_code == 1:
                    coin = data.get("data", {}).get("coin", 0)
                    msg = f"签到成功，获得{coin}金豆"
                    logger.info(msg)
                    return {"ok": True, "signed": True, "msg": msg, "coin": coin}
                else:
                    msg = data.get("data", {}).get("msg", "签到失败")
                    logger.warning(f"签到失败 [{inner_code}]: {msg}")
                    return {"ok": False, "msg": msg}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"签到失败 [{result_code}]: {msg}")
                return {"ok": False, "msg": msg}

        except Exception as e:
            logger.error(f"签到异常: {e}")
            return {"ok": False, "msg": str(e)}

    # ---------- 连签记录 + 兑换 ----------
    def continue_sign_records(self) -> dict:
        """查询连签记录并兑换奖励"""
        logger.info("查询连签记录...")
        results = []

        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                CONTINUE_RECORDS_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                if data.get("continue15List", {}).get("length"):
                    logger.info("兑换 15 天连签奖励")
                    r = self.exchange_prize("15")
                    results.append(r)
                if data.get("continue28List", {}).get("length"):
                    logger.info("兑换 28 天连签奖励")
                    r = self.exchange_prize("28")
                    results.append(r)
                return {"ok": True, "records": results}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"查询连签记录失败 [{result_code}]: {msg}")
                return {"ok": False, "msg": msg}

        except Exception as e:
            logger.error(f"查询连签记录异常: {e}")
            return {"ok": False, "msg": str(e)}

    def exchange_prize(self, prize_type: str = "7") -> dict:
        """兑换连签奖励"""
        logger.info(f"兑换 {prize_type} 天连签奖励...")

        try:
            payload = {
                "para": _encrypt_para({
                    "phone": self.phone,
                    "type": prize_type,
                })
            }
            resp = self.client.post(
                EXCHANGE_PRIZE_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                inner_code = data.get("prizeDetail", {}).get("code", -1)
                if inner_code == 0:
                    prize_title = (
                        data.get("prizeDetail", {})
                        .get("biz", {})
                        .get("winTitle", "未知")
                    )
                    msg = f"连签{prize_type}天抽奖: {prize_title}"
                    logger.info(msg)
                    return {"ok": True, "msg": msg, "prize": prize_title}
                else:
                    err = data.get("prizeDetail", {}).get("err", "")
                    msg = f"连签{prize_type}天抽奖失败 [{inner_code}]: {err}"
                    logger.warning(msg)
                    return {"ok": False, "msg": msg}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"兑换失败 [{result_code}]: {msg}")
                return {"ok": False, "msg": msg}

        except Exception as e:
            logger.error(f"兑换异常: {e}")
            return {"ok": False, "msg": str(e)}

    # ---------- 首页任务 ----------
    def homepage(self, shop_type: str = "hg_dq_rzwj") -> dict:
        """获取首页任务列表并完成"""
        logger.info("获取首页任务...")
        completed = []

        try:
            payload = {
                "para": _encrypt_para({
                    "phone": self.phone,
                    "shopId": "20001",
                    "type": shop_type,
                })
            }
            resp = self.client.post(
                HOMEPAGE_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code != 0:
                logger.warning(f"获取任务列表失败 [{result_code}]")
                return {"ok": False, "msg": f"获取任务列表失败 [{result_code}]"}

            head_code = data.get("data", {}).get("head", {}).get("code", -1)
            if head_code != 0:
                err = data.get("data", {}).get("head", {}).get("err", "")
                logger.warning(f"获取任务列表失败 [{head_code}]: {err}")
                return {"ok": False, "msg": err}

            ad_items = data.get("data", {}).get("biz", {}).get("adItems", [])
            for item in ad_items:
                task_state = item.get("taskState", "")
                if task_state not in ("0", "1"):
                    continue

                content_one = item.get("contentOne", "")
                title = item.get("title", "").split(" ")[0]

                if content_one == "3":  # 领取奖励
                    if item.get("rewardId"):
                        logger.info(f"领取任务 [{title}] 奖励")
                        r = self._receive_reward(item.get("rewardId", ""), title)
                        completed.append(r)
                elif content_one == "5":  # 打开消息
                    logger.info(f"完成任务 [{title}]: 打开消息")
                    r = self._open_msg(title)
                    completed.append(r)
                elif content_one == "6":  # 分享
                    logger.info(f"完成任务 [{title}]: 分享")
                    completed.append("分享")
                elif content_one in ("10", "13"):  # 看直播
                    logger.info(f"跳过任务 [{title}]: 看直播(需xtoken)")
                    continue
                elif content_one == "18":  # 聚合任务
                    logger.info(f"完成聚合任务 [{title}]")
                    r = self._polymerize(item.get("taskId", ""), title)
                    completed.append(r)

            return {"ok": True, "completed": completed}

        except Exception as e:
            logger.error(f"首页任务异常: {e}")
            return {"ok": False, "msg": str(e)}

    def _receive_reward(self, reward_id: str, title: str) -> dict:
        """领取奖励"""
        try:
            payload = {
                "para": _encrypt_para({
                    "phone": self.phone,
                    "rewardId": reward_id,
                })
            }
            resp = self.client.post(
                RECEIVE_REWARD_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                msg = data.get("resoultMsg", "")
                logger.info(f"领取任务 [{title}] 奖励成功: {msg}")
                return {"ok": True, "title": title, "msg": msg}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"领取任务 [{title}] 奖励失败 [{result_code}]: {msg}")
                return {"ok": False, "title": title, "msg": msg}

        except Exception as e:
            return {"ok": False, "title": title, "msg": str(e)}

    def _open_msg(self, title: str) -> dict:
        """打开消息完成任务"""
        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                OPEN_MSG_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                logger.info(f"完成任务 [{title}]: {data.get('resoultMsg', '')}")
                return {"ok": True, "title": title}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"完成任务 [{title}] 失败 [{result_code}]: {msg}")
                return {"ok": False, "title": title, "msg": msg}

        except Exception as e:
            return {"ok": False, "title": title, "msg": str(e)}

    def _polymerize(self, job_id: str, title: str) -> dict:
        """聚合任务"""
        try:
            payload = {
                "para": _encrypt_para({
                    "phone": self.phone,
                    "jobId": job_id,
                })
            }
            resp = self.client.post(
                POLYMERIZE_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                logger.info(f"完成聚合任务 [{title}]: {data.get('resoultMsg', '')}")
                return {"ok": True, "title": title}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"聚合任务 [{title}] 失败 [{result_code}]: {msg}")
                return {"ok": False, "title": title, "msg": msg}

        except Exception as e:
            return {"ok": False, "title": title, "msg": str(e)}

    # ---------- 宠物乐园 ----------
    def get_paradise_info(self) -> dict:
        """查询宠物乐园信息并喂食"""
        logger.info("查询宠物乐园...")
        can_feed = True
        feed_results = []

        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                PARADISE_INFO_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code != 0:
                logger.warning(f"查询宠物等级失败 [{result_code}]")
                return {"ok": False, "msg": f"查询失败 [{result_code}]"}

            # 喂食 (最多10次)
            for i in range(1, 11):
                if not can_feed:
                    break
                r = self._food(i)
                feed_results.append(r)
                if not r.get("can_continue", True):
                    can_feed = False
                _random_delay(0.5, 1.5)

            # 查询宠物等级
            resp2 = self.client.post(
                PARADISE_INFO_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data2 = resp2.json() if resp2.text else {}
            result_code2 = data2.get("resoultCode", -1)

            if result_code2 == 0:
                level_info = data2.get("userInfo", {}).get("levelInfoMap", {})
                level = level_info.get("level", 0)
                growth = level_info.get("growthValue", 0)
                full_growth = level_info.get("fullGrowthCoinValue", 0)
                logger.info(
                    f"宠物等级 [Lv.{level}], 升级进度: {growth}/{full_growth}"
                )

            return {"ok": True, "feed": feed_results}

        except Exception as e:
            logger.error(f"宠物乐园异常: {e}")
            return {"ok": False, "msg": str(e)}

    def _food(self, count: int) -> dict:
        """喂食"""
        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                FOOD_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                msg = data.get("resoultMsg", "成功")
                logger.info(f"第{count}次喂食: {msg}")
                if data.get("levelUp"):
                    reward = data.get("currLevelRightList", [{}])[0]
                    level = reward.get("level", "?")
                    name = reward.get("rightsName", "?")
                    logger.info(f"宠物已升级到 [LV.{level}], 获得: {name}")
                return {"ok": True, "count": count, "can_continue": True}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                if "最大喂食次数" in msg:
                    logger.info(f"第{count}次喂食: 已达最大次数")
                    return {"ok": False, "count": count, "can_continue": False}
                logger.warning(f"第{count}次喂食失败 [{result_code}]: {msg}")
                return {"ok": False, "count": count, "can_continue": True}

        except Exception as e:
            return {"ok": False, "count": count, "can_continue": True, "msg": str(e)}

    def get_level_rights(self) -> dict:
        """查询兑换权益并兑换话费"""
        logger.info("查询宠物兑换权益...")
        results = []

        try:
            payload = {"para": _encrypt_para({"phone": self.phone})}
            resp = self.client.post(
                GET_LEVEL_RIGHTS_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}

            current_level = data.get("currentLevel", 6)
            level_key = f"V{current_level}"
            items = data.get(level_key, [])

            coin_info = self.user_coin_info()
            coin = coin_info.get("coin", 0)

            for item in items:
                rights_name = item.get("rightsName", "")
                if coin < item.get("costCoin", 0):
                    continue
                if re.search(r"\d+元话费", rights_name) or re.search(
                    r"专享\d+金豆", rights_name
                ):
                    logger.info(f"兑换权益: {rights_name}")
                    r = self._conversion_rights(item)
                    results.append(r)

            return {"ok": True, "results": results}

        except Exception as e:
            logger.error(f"兑换权益异常: {e}")
            return {"ok": False, "msg": str(e)}

    def _conversion_rights(self, item: dict) -> dict:
        """兑换权益"""
        name = item.get("rightsName", "")
        try:
            payload = {
                "para": _encrypt_para({
                    "phone": self.phone,
                    "rightsId": item.get("id", ""),
                })
            }
            resp = self.client.post(
                CONVERSION_RIGHTS_API,
                json=payload,
                headers=self._get_rs_headers(),
            )
            data = resp.json() if resp.text else {}
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                logger.info(f"兑换权益 [{name}] 成功")
                return {"ok": True, "name": name}
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "")
                logger.warning(f"兑换权益 [{name}] 失败 [{result_code}]: {msg}")
                return {"ok": False, "name": name, "msg": msg}

        except Exception as e:
            return {"ok": False, "name": name, "msg": str(e)}


# ==================== 主流程 ====================
def run_all(signin_only: bool = False) -> dict:
    """执行全部自动化任务，返回结果汇总 (供 bot 插件调用)

    Args:
        signin_only: 仅执行签到翻牌，跳过活动和宠物乐园
    """
    result = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phone": PHONE[:3] + "****" + PHONE[-4:] if PHONE else "未设置",
        "login": False,
        "signin": {},
        "activities": [],
        "items": [],
    }

    if not PHONE or not PASSWORD:
        result["error"] = "账号或密码未配置"
        logger.error("账号或密码未配置，请在 .env 中设置 DX_ACCOUNT（格式: 手机号#密码）")
        _save_result(result)
        return result

    logger.info("=" * 60)
    logger.info("  中国电信话费自动化 v3.0 (API直调版)")
    logger.info(f"  号码: {result['phone']}")
    logger.info(f"  时间: {result['time']}")
    logger.info("=" * 60)

    client = TelecomClient()

    try:
        # 1. 登录
        if not client.login(PHONE, PASSWORD):
            result["error"] = "登录失败"
            result["items"].append({"type": "系统", "value": "登录失败"})
            _save_result(result)
            return result
        result["login"] = True

        # 2. 获取 ticket
        if not client.get_ticket():
            result["error"] = "获取 ticket 失败"
            result["items"].append({"type": "系统", "value": "ticket 获取失败"})
            _save_result(result)
            return result

        # 3. 获取瑞数 Cookie + Sign
        if not client._init_rs_cookies():
            logger.warning("瑞数 Cookie 初始化失败，部分功能可能不可用")
        if not client.get_sign():
            result["error"] = "获取 sign 失败"
            result["items"].append({"type": "系统", "value": "sign 获取失败"})
            _save_result(result)
            return result

        # 4. 查询金豆 (初始)
        _random_delay()
        client.user_coin_info()

        # 5. 签到
        if ENABLE_SIGNIN:
            _random_delay()
            signin_result = client.user_status_info()
            result["signin"] = signin_result
            if signin_result.get("ok"):
                coin = signin_result.get("coin", 0)
                msg = signin_result.get("msg", "完成")
                if signin_result.get("signed"):
                    result["items"].append({"type": "签到", "value": msg})
                else:
                    result["items"].append({"type": "签到", "value": msg})

            # 连签兑换
            if not signin_only:
                _random_delay()
                rs = client.continue_sign_records()
                for r in rs.get("records", []):
                    if r.get("ok"):
                        result["items"].append({"type": "连签兑换", "value": r.get("prize", r.get("msg", ""))})

        # 6. 首页任务
        if not signin_only and ENABLE_ACTIVITY:
            _random_delay()
            hp_result = client.homepage()
            result["activities"] = hp_result.get("completed", [])
            if hp_result.get("completed"):
                result["items"].append({
                    "type": "活动",
                    "value": f"完成 {len(hp_result['completed'])} 个任务",
                })

        # 7. 宠物乐园
        if not signin_only and ENABLE_ACTIVITY:
            _random_delay()
            paradise_result = client.get_paradise_info()
            if paradise_result.get("ok"):
                feed_count = sum(
                    1 for r in paradise_result.get("feed", []) if r.get("ok")
                )
                if feed_count > 0:
                    result["items"].append({
                        "type": "宠物",
                        "value": f"喂食 {feed_count} 次",
                    })

            # 兑换权益
            _random_delay()
            rights_result = client.get_level_rights()
            for r in rights_result.get("results", []):
                if r.get("ok"):
                    result["items"].append({
                        "type": "兑换",
                        "value": r.get("name", "权益"),
                    })

        # 8. 查询最终金豆
        _random_delay()
        client.user_coin_info(notify=True)

    except Exception as e:
        logger.error(f"运行异常: {e}")
        result["error"] = str(e)
        result["items"].append({"type": "系统", "value": f"异常: {e}"})

    finally:
        client.close()

    _save_result(result)

    logger.info("=" * 60)
    logger.info("  执行结果")
    logger.info(f"  登录: {'OK' if result['login'] else 'FAIL'}")
    logger.info(f"  签到: {result['signin'].get('msg', '-')}")
    logger.info(f"  活动: {len(result.get('activities', []))} 个")
    logger.info("=" * 60)

    return result


# ==================== 直接运行 ====================
if __name__ == "__main__":
    result = run_all()
    if result.get("error"):
        print(f"\n[FAIL] 执行失败: {result['error']}")
    else:
        print(f"\n[OK] 签到: {result.get('signin', {}).get('msg', '-')}")
        print(f"[OK] 活动: {len(result.get('activities', []))} 个")
        items = result.get("items", [])
        if items:
            items_str = " | ".join(f'{i["type"]}:{i["value"]}' for i in items)
            print(f"[OK] 产物: {items_str}")
