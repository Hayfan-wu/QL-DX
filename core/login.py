"""
中国电信登录模块
=================
独立的登录模块，不依赖瑞数反爬。
提供服务密码登录、短信验证码登录等功能。
"""

import base64
import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

logger = logging.getLogger("DX.Login")

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent.parent

# 登录 RSA 公钥
LOGIN_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDBkLT15ThVgz6/NOl6s8GNPofd"
    "WzWbCkWnkaAm7O2LjkM1H7dMvzkiqdxU02jamGRHLX/ZNMCXHnPcW/sDhiFCBN18"
    "qFvy8g6VYb9QtroI09e176s+ZCtiv7hbin2cCTj99iUpnEloZm19lwHyo69u5UMi"
    "PMpq0/XKBO8lYhN/gwIDAQAB"
)

# API URL
LOGIN_API = "https://appgologin.189.cn:9031/login/client/userLoginNormal"
TICKET_API = "https://appgologin.189.cn:9031/map/clientXML"

# User-Agent
UA = (
    "Mozilla/5.0 (Linux; U; Android 12; zh-cn; ONEPLUS A9000 "
    "Build/QKQ1.190716.003) AppleWebKit/533.1 (KHTML, like Gecko) "
    "Version/5.0 Mobile Safari/533.1"
)

# 缓存文件
CACHE_FILE = PROJECT_DIR / "chinaTelecom_cache.json"

# ==================== 加密工具 ====================

def _rsa_encrypt(data: str, public_key_b64: str) -> str:
    """RSA PKCS1 加密，返回 base64 字符串"""
    lines = [public_key_b64[i:i+64] for i in range(0, len(public_key_b64), 64)]
    pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(data.encode())
    return base64.b64encode(encrypted).decode()


def _encode_phone(phone: str) -> str:
    """手机号编码：每个字符 ASCII +2"""
    return "".join(chr(ord(c) + 2) for c in phone)


def _encode_password(password: str) -> str:
    """密码编码：每个字符 ASCII +2"""
    return "".join(chr(ord(c) + 2) for c in password)


def _generate_uuid() -> list:
    """生成 UUID v4 格式数组
    返回: [8位, 4位, '4xxx', 4位, 12位]
    """
    hex_chars = "abcdef0123456789"
    def _rand(pattern: str) -> str:
        return "".join(
            c if c != "x" else random.choice(hex_chars)
            for c in pattern
        )
    return [
        _rand("xxxxxxxx"),
        _rand("xxxx"),
        _rand("4xxx"),
        _rand("xxxx"),
        _rand("xxxxxxxxxxxx"),
    ]


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


# ==================== 登录结果 ====================

class LoginResult:
    """登录结果"""

    def __init__(self, success: bool, code: str = "", msg: str = "",
                 token: str = "", user_id: str = "",
                 verify_code_token: str = ""):
        self.success = success
        self.code = code
        self.msg = msg
        self.token = token
        self.user_id = user_id
        self.verify_code_token = verify_code_token

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"LoginResult(success=True, code={self.code})"
        return f"LoginResult(success=False, code={self.code}, msg={self.msg})"


# ==================== 登录客户端 ====================

class LoginClient:
    """电信登录客户端（独立模块，不依赖瑞数反爬）"""

    def __init__(self, timeout: int = 30):
        self.client = httpx.Client(
            timeout=timeout,
            verify=False,
            follow_redirects=False,
            headers={
                "User-Agent": UA,
                "Connection": "keep-alive",
            },
        )
        self.token: str = ""
        self.user_id: str = ""
        self.phone: str = ""

    def close(self):
        self.client.close()

    def login(self, phone: str, password: str,
              use_cache: bool = True) -> LoginResult:
        """服务密码登录

        Args:
            phone: 手机号
            password: 服务密码
            use_cache: 是否使用缓存的 token

        Returns:
            LoginResult
        """
        self.phone = phone

        # 检查缓存
        if use_cache:
            cache = _load_cache()
            if phone in cache:
                entry = cache[phone]
                if entry.get("token") and entry.get("userId"):
                    age = (time.time() * 1000 - entry.get("t", 0)) / 1000
                    if age < 86400:  # 24小时内有效
                        self.token = entry["token"]
                        self.user_id = entry["userId"]
                        logger.info(f"从缓存恢复登录状态: {phone[:3]}****{phone[-4:]}")
                        return LoginResult(
                            success=True, code="0000", msg="缓存登录成功",
                            token=self.token, user_id=self.user_id,
                        )

        uuid_arr = _generate_uuid()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
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
                    "deviceUid": "".join(uuid_arr[:3]),
                    "phoneNum": _encode_phone(phone),
                    "isChinatelecom": "0",
                    "systemVersion": "15.4.0",
                    "authentication": _encode_password(password),
                },
            },
        }

        try:
            resp = self.client.post(
                LOGIN_API, json=payload, headers={"User-Agent": UA}
            )
            logger.debug(f"登录响应状态: {resp.status_code}")

            if not resp.text:
                return LoginResult(success=False, code="-1", msg="登录响应为空")

            data = resp.json()
            resp_data = data.get("responseData") or {}
            result_code = (
                resp_data.get("resultCode", -1)
                if isinstance(resp_data, dict)
                else str(resp_data)
            )

            logger.info(f"登录响应码: {result_code}")

            if result_code == "0000":
                # 登录成功
                login_result = (
                    (resp_data.get("data") or {}).get("loginSuccessResult") or {}
                )
                self.user_id = login_result.get("userId", "")
                self.token = login_result.get("token", "")

                if self.token:
                    logger.info(f"登录成功 [{result_code}]")
                    # 缓存
                    cache = _load_cache()
                    cache[phone] = {
                        "token": self.token,
                        "userId": self.user_id,
                        "t": int(time.time() * 1000),
                    }
                    _save_cache(cache)
                    return LoginResult(
                        success=True, code=result_code, msg="登录成功",
                        token=self.token, user_id=self.user_id,
                    )
                else:
                    return LoginResult(
                        success=False, code=result_code,
                        msg="登录返回成功但无 token",
                    )

            elif result_code == "3006":
                # 需要短信验证码
                result_desc = (
                    resp_data.get("resultDesc", "")
                    if isinstance(resp_data, dict) else ""
                )
                verify_code_token = (
                    ((resp_data.get("data") or {}).get("loginFailResult") or {})
                    .get("verifyCode", "")
                )
                logger.warning(f"登录需要二次验证 [{result_code}]: {result_desc or '需要短信验证码'}")
                if verify_code_token:
                    logger.info(f"verifyCode token: {verify_code_token}")

                # 保存验证状态
                verify_state = {
                    "phone": phone,
                    "password": password,
                    "verifyCodeToken": verify_code_token,
                    "timestamp": int(time.time() * 1000),
                    "status": "pending",
                    "resultCode": result_code,
                    "resultDesc": result_desc,
                }
                (PROJECT_DIR / "chinaTelecom_verify_state.json").write_text(
                    json.dumps(verify_state, ensure_ascii=False, indent=2)
                )

                return LoginResult(
                    success=False, code=result_code,
                    msg=result_desc or "需要短信验证码",
                    verify_code_token=verify_code_token,
                )

            else:
                # 其他错误
                msg = (
                    data.get("msg", "")
                    or (resp_data.get("resultDesc", "") if isinstance(resp_data, dict) else "")
                    or (data.get("headerInfos") or {}).get("reason", "")
                )
                logger.error(f"登录失败 [{result_code}]: {msg}")
                return LoginResult(
                    success=False, code=result_code, msg=msg,
                )

        except Exception as e:
            logger.error(f"登录异常: {e}")
            return LoginResult(success=False, code="EXCEPTION", msg=str(e))

    def login_with_sms(self, phone: str, password: str,
                       sms_code: str, verify_code_token: str = "") -> LoginResult:
        """使用短信验证码完成登录

        Args:
            phone: 手机号
            password: 服务密码
            sms_code: 短信验证码
            verify_code_token: 从 3006 响应中获取的 verifyCode token

        Returns:
            LoginResult
        """
        self.phone = phone
        logger.info(f"使用短信验证码登录: {phone[:3]}****{phone[-4:]}")

        uuid_arr = _generate_uuid()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        uuid_prefix = "".join(uuid_arr[:2])

        login_str = (
            f"iPhone 14 15.4.{uuid_prefix}{phone}{timestamp}{password}0$$$0."
        )
        encrypted = _rsa_encrypt(login_str, LOGIN_PUBLIC_KEY)

        field_data = {
            "loginType": "4",
            "accountType": "",
            "loginAuthCipherAsymmertric": encrypted,
            "deviceUid": "".join(uuid_arr[:3]),
            "phoneNum": _encode_phone(phone),
            "isChinatelecom": "0",
            "systemVersion": "15.4.0",
            "authentication": _encode_password(password),
            "verifyCodeInput": sms_code,
        }
        if verify_code_token:
            field_data["verifyCode"] = verify_code_token

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
                "fieldData": field_data,
            },
        }

        try:
            resp = self.client.post(
                LOGIN_API, json=payload, headers={"User-Agent": UA}
            )

            if not resp.text:
                return LoginResult(success=False, code="-1", msg="登录响应为空")

            data = resp.json()
            resp_data = data.get("responseData") or {}
            result_code = (
                resp_data.get("resultCode", -1)
                if isinstance(resp_data, dict)
                else str(resp_data)
            )

            logger.info(f"验证码登录响应码: {result_code}")

            if result_code == "0000":
                login_result = (
                    (resp_data.get("data") or {}).get("loginSuccessResult") or {}
                )
                self.user_id = login_result.get("userId", "")
                self.token = login_result.get("token", "")

                if self.token:
                    logger.info(f"验证码登录成功 [{result_code}]")
                    cache = _load_cache()
                    cache[phone] = {
                        "token": self.token,
                        "userId": self.user_id,
                        "t": int(time.time() * 1000),
                    }
                    _save_cache(cache)
                    return LoginResult(
                        success=True, code=result_code, msg="登录成功",
                        token=self.token, user_id=self.user_id,
                    )
                else:
                    return LoginResult(
                        success=False, code=result_code,
                        msg="登录返回成功但无 token",
                    )
            else:
                msg = (
                    data.get("msg", "")
                    or (resp_data.get("resultDesc", "") if isinstance(resp_data, dict) else "")
                    or (data.get("headerInfos") or {}).get("reason", "")
                )
                logger.error(f"验证码登录失败 [{result_code}]: {msg}")
                return LoginResult(
                    success=False, code=result_code, msg=msg,
                )

        except Exception as e:
            logger.error(f"验证码登录异常: {e}")
            return LoginResult(success=False, code="EXCEPTION", msg=str(e))

    def get_ticket(self) -> str:
        """获取 ticket（登录成功后调用）

        Returns:
            ticket 字符串，失败返回空字符串
        """
        if not self.token or not self.user_id:
            logger.error("未登录，无法获取 ticket")
            return ""

        from Crypto.Cipher import DES3
        from Crypto.Util.Padding import pad

        logger.info("获取 ticket...")

        DES3_KEY = b'1234567`90koiuyhgtfrdews'
        DES3_IV = b'\0\0\0\0\0\0\0\0'

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        cipher = DES3.new(DES3_KEY, DES3.MODE_CBC, DES3_IV)
        encrypted_user_id = cipher.encrypt(pad(self.user_id.encode(), DES3.block_size)).hex()

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
                    "Content-Type": "application/xml",
                },
            )
            import re
            match = re.search(r"<Ticket>([^<]+)</Ticket>", resp.text)
            if match:
                ticket = match.group(1)
                logger.info("ticket 获取成功")
                return ticket
            else:
                logger.error(f"ticket 解析失败: {resp.text[:200]}")
                return ""
        except Exception as e:
            logger.error(f"ticket 获取异常: {e}")
            return ""
