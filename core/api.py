"""
中国电信业务 API 模块
======================
封装所有 wappark 业务 API（签到、任务、宠物乐园等）。
依赖瑞数反爬模块和登录模块。

核心特性:
- 统一的 API 调用封装
- 自动重试机制
- 瑞数反爬优雅降级
- 与登录模块解耦

使用方式:
    from core.api import TelecomAPI
    api = TelecomAPI(http_client, phone, sign)
    result = api.user_status_info()
"""

import base64
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from Crypto.Cipher import AES, PKCS1_v1_5, DES3
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

from core.ruishu import RuishuClient

logger = logging.getLogger("DX.API")

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent.parent

# para 加密 RSA 公钥 (wappark API 请求体加密)
PARA_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+ugG5A8cZ3FqUKDwM57GM4io6"
    "JGcStivT8UdGt67PEOihLZTw3P7371+N47PrmsCpnTRzbTgcupKtUv8ImZalYk65"
    "dU8rjC/ridwhw9ffW2LBwvkEnDkkKKRi2liWIItDftJVBiWOh17o6gfbPoNrWORc"
    "Adcbpk2L+udld5kZNwIDAQAB"
)

# AES 密钥 (用于签到数据加密)
AES_KEY = b'34d7cb0bcdf07523'

# User-Agent
UA = (
    "Mozilla/5.0 (Linux; U; Android 12; zh-cn; ONEPLUS A9000 "
    "Build/QKQ1.190716.003) AppleWebKit/533.1 (KHTML, like Gecko) "
    "Version/5.0 Mobile Safari/533.1"
)

# API URL
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
CONVERSION_RIGHTS_API = "https://wappark.189.cn/jt-sign/paradise/conversionRights"


# ==================== 加密工具 ====================

def _rsa_encrypt_para(data: str) -> str:
    """RSA 加密 para 参数，返回 base64"""
    lines = [PARA_PUBLIC_KEY[i:i+64] for i in range(0, len(PARA_PUBLIC_KEY), 64)]
    pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(data.encode())
    return base64.b64encode(encrypted).decode()


def _encrypt_para(data: dict) -> str:
    """加密 wappark API 请求参数"""
    return _rsa_encrypt_para(json.dumps(data, separators=(",", ":")))


def _aes_encrypt(data: str) -> str:
    """AES-ECB-Pkcs7 加密，返回 hex"""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    ciphertext = cipher.encrypt(pad(data.encode(), AES.block_size))
    return ciphertext.hex()


def _random_delay(a: float = 0.5, b: float = 2.0):
    time.sleep(random.uniform(a, b))


# ==================== API 结果 ====================

class APIResult:
    """API 调用结果"""

    def __init__(self, ok: bool, data: dict = None, msg: str = "", code: int = -1):
        self.ok = ok
        self.data = data or {}
        self.msg = msg
        self.code = code

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        if self.ok:
            return f"APIResult(ok=True, code={self.code})"
        return f"APIResult(ok=False, code={self.code}, msg={self.msg})"


# ==================== 业务 API 客户端 ====================

class TelecomAPI:
    """电信业务 API 客户端

    负责所有 wappark 域下的业务 API 调用。
    依赖:
    - http_client: httpx.Client 实例
    - phone: 手机号
    - sign: SSO sign token（通过 ticket 换取）
    - ruishu: 瑞数反爬客户端（可选）
    """

    def __init__(self, http_client, phone: str, sign: str = ""):
        """
        Args:
            http_client: httpx.Client 实例
            phone: 手机号
            sign: sign token
        """
        self.http = http_client
        self.phone = phone
        self.sign = sign
        self._ruishu = RuishuClient(http_client)

    # ---------- 公共方法 ----------

    def set_sign(self, sign: str):
        """设置 sign token"""
        self.sign = sign

    def init_ruishu(self) -> bool:
        """初始化瑞数反爬

        Returns:
            是否成功（失败不影响使用，仅降级）
        """
        result = self._ruishu.init()
        return result.success

    @property
    def ruishu_available(self) -> bool:
        """瑞数是否可用"""
        return self._ruishu.available

    # ---------- 内部工具 ----------

    def _headers(self) -> dict:
        """构造请求头"""
        headers = {
            "User-Agent": UA,
            "Content-Type": "application/json",
        }
        # 添加瑞数 Cookie 和 sign
        rs_headers = self._ruishu.get_headers(sign=self.sign)
        headers.update(rs_headers)
        return headers

    def _post(self, url: str, json_data: dict) -> APIResult:
        """统一的 POST 请求封装

        Args:
            url: API URL
            json_data: 请求体

        Returns:
            APIResult
        """
        try:
            resp = self.http.post(url, json=json_data, headers=self._headers())

            if not resp.text:
                return APIResult(False, msg="响应为空")

            try:
                data = resp.json()
            except Exception:
                logger.debug(f"响应非JSON: {resp.text[:200]}")
                return APIResult(False, msg=f"响应非JSON: {resp.text[:100]}")

            # 统一解析 resoultCode
            result_code = data.get("resoultCode", -1)
            if result_code == 0:
                return APIResult(True, data, "成功", result_code)
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "") or f"错误码 {result_code}"
                return APIResult(False, data, msg, result_code)

        except Exception as e:
            logger.error(f"API 请求异常 [{url}]: {e}")
            return APIResult(False, msg=str(e))

    def _post_para(self, url: str, params: dict) -> APIResult:
        """使用 para 加密参数的 POST 请求

        Args:
            url: API URL
            params: 要加密的参数 dict

        Returns:
            APIResult
        """
        payload = {"para": _encrypt_para(params)}
        return self._post(url, payload)

    # ---------- SSO Sign ----------

    def get_sign_by_ticket(self, ticket: str) -> APIResult:
        """通过 ticket 获取 sign

        Args:
            ticket: 从登录系统获取的 ticket

        Returns:
            APIResult（data 中含 sign 字段）
        """
        logger.info("通过 ticket 获取 sign...")

        try:
            params = {"ticket": ticket}
            headers = self._headers()
            resp = self.http.get(SSO_SIGN_API, params=params, headers=headers)

            if not resp.text:
                return APIResult(False, msg="响应为空")

            data = resp.json()
            result_code = data.get("resoultCode", -1)

            if result_code == 0:
                sign = data.get("sign", "")
                self.sign = sign
                logger.info("获取 sign 成功")
                return APIResult(True, data, "成功", result_code)
            else:
                msg = data.get("msg", "") or data.get("resoultMsg", "") or f"错误码 {result_code}"
                logger.warning(f"获取 sign 失败 [{result_code}]: {msg}")
                return APIResult(False, data, msg, result_code)

        except Exception as e:
            logger.error(f"获取 sign 异常: {e}")
            return APIResult(False, msg=str(e))

    # ---------- 金豆查询 ----------

    def user_coin_info(self, notify: bool = False) -> APIResult:
        """查询金豆余额"""
        result = self._post_para(USER_COIN_API, {"phone": self.phone})

        if result.ok and notify:
            coin = result.data.get("totalCoin", 0)
            logger.info(f"金豆余额: {coin}")
            if result.data.get("amountEx"):
                expire_date = datetime.fromtimestamp(
                    result.data.get("expireDate", 0) / 1000
                ).strftime("%Y-%m-%d")
                logger.info(f"-- [{expire_date}将过期] {result.data['amountEx']}金豆")

        return result

    # ---------- 签到 ----------

    def user_status_info(self) -> APIResult:
        """查询签到状态，未签则签到"""
        logger.info("查询签到状态...")
        result = self._post_para(USER_STATUS_API, {"phone": self.phone})

        if result.ok:
            is_sign = result.data.get("data", {}).get("isSign", False)
            if is_sign:
                logger.info("今日已签到")
                result.data["signed"] = True
                result.msg = "今日已签到"
                return result

            # 未签到，执行签到
            return self.do_sign()

        return result

    def do_sign(self) -> APIResult:
        """执行签到"""
        logger.info("执行签到...")

        sign_data = {
            "phone": self.phone,
            "date": int(time.time() * 1000),
            "sysType": "20002",
        }
        encoded = _aes_encrypt(json.dumps(sign_data, separators=(",", ":")))

        payload = {"encode": encoded}
        result = self._post(SIGN_API, payload)

        if result.ok:
            inner_data = result.data.get("data", {})
            inner_code = inner_data.get("code", -1)
            if inner_code == 1:
                coin = inner_data.get("coin", 0)
                msg = f"签到成功，获得{coin}金豆"
                logger.info(msg)
                result.msg = msg
                result.data["signed"] = True
                result.data["coin"] = coin
            else:
                msg = inner_data.get("msg", "签到失败")
                logger.warning(f"签到失败 [{inner_code}]: {msg}")
                result.ok = False
                result.msg = msg

        return result

    # ---------- 连签记录 + 兑换 ----------

    def continue_sign_records(self) -> APIResult:
        """查询连签记录并兑换奖励"""
        logger.info("查询连签记录...")
        result = self._post_para(CONTINUE_RECORDS_API, {"phone": self.phone})

        if result.ok:
            records = []
            if result.data.get("continue15List", {}).get("length"):
                logger.info("兑换 15 天连签奖励")
                r = self.exchange_prize("15")
                records.append(r)
            if result.data.get("continue28List", {}).get("length"):
                logger.info("兑换 28 天连签奖励")
                r = self.exchange_prize("28")
                records.append(r)
            result.data["records"] = records

        return result

    def exchange_prize(self, prize_type: str = "7") -> APIResult:
        """兑换连签奖励"""
        logger.info(f"兑换 {prize_type} 天连签奖励...")

        result = self._post_para(EXCHANGE_PRIZE_API, {
            "phone": self.phone,
            "type": prize_type,
        })

        if result.ok:
            prize_detail = result.data.get("prizeDetail", {})
            inner_code = prize_detail.get("code", -1)
            if inner_code == 0:
                prize_title = (
                    prize_detail.get("biz", {}).get("winTitle", "未知")
                )
                msg = f"连签{prize_type}天抽奖: {prize_title}"
                logger.info(msg)
                result.msg = msg
                result.data["prize"] = prize_title
            else:
                err = prize_detail.get("err", "")
                msg = f"连签{prize_type}天抽奖失败 [{inner_code}]: {err}"
                logger.warning(msg)
                result.ok = False
                result.msg = msg

        return result

    # ---------- 首页任务 ----------

    def homepage(self, shop_type: str = "hg_dq_rzwj") -> APIResult:
        """获取首页任务列表并完成"""
        logger.info("获取首页任务...")
        completed = []

        result = self._post_para(HOMEPAGE_API, {
            "phone": self.phone,
            "shopId": "20001",
            "type": shop_type,
        })

        if not result.ok:
            return result

        data = result.data.get("data", {})
        head_code = data.get("head", {}).get("code", -1)
        if head_code != 0:
            err = data.get("head", {}).get("err", "")
            logger.warning(f"获取任务列表失败 [{head_code}]: {err}")
            result.ok = False
            result.msg = err
            return result

        ad_items = data.get("biz", {}).get("adItems", [])
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
                completed.append({"ok": True, "title": title, "type": "share"})
            elif content_one in ("10", "13"):  # 看直播
                logger.info(f"跳过任务 [{title}]: 看直播(需xtoken)")
                continue
            elif content_one == "18":  # 聚合任务
                logger.info(f"完成聚合任务 [{title}]")
                r = self._polymerize(item.get("taskId", ""), title)
                completed.append(r)

        result.data["completed"] = completed
        return result

    def _receive_reward(self, reward_id: str, title: str) -> dict:
        """领取奖励"""
        result = self._post_para(RECEIVE_REWARD_API, {
            "phone": self.phone,
            "rewardId": reward_id,
        })
        if result.ok:
            msg = result.data.get("resoultMsg", "")
            logger.info(f"领取任务 [{title}] 奖励成功: {msg}")
            return {"ok": True, "title": title, "msg": msg}
        else:
            logger.warning(f"领取任务 [{title}] 奖励失败: {result.msg}")
            return {"ok": False, "title": title, "msg": result.msg}

    def _open_msg(self, title: str) -> dict:
        """打开消息完成任务"""
        result = self._post_para(OPEN_MSG_API, {"phone": self.phone})
        if result.ok:
            msg = result.data.get("resoultMsg", "")
            logger.info(f"完成任务 [{title}]: {msg}")
            return {"ok": True, "title": title, "msg": msg}
        else:
            logger.warning(f"完成任务 [{title}] 失败: {result.msg}")
            return {"ok": False, "title": title, "msg": result.msg}

    def _polymerize(self, job_id: str, title: str) -> dict:
        """聚合任务"""
        result = self._post_para(POLYMERIZE_API, {
            "phone": self.phone,
            "jobId": job_id,
        })
        if result.ok:
            msg = result.data.get("resoultMsg", "")
            logger.info(f"完成聚合任务 [{title}]: {msg}")
            return {"ok": True, "title": title, "msg": msg}
        else:
            logger.warning(f"聚合任务 [{title}] 失败: {result.msg}")
            return {"ok": False, "title": title, "msg": result.msg}

    # ---------- 宠物乐园 ----------

    def get_paradise_info(self) -> APIResult:
        """查询宠物乐园信息并喂食"""
        logger.info("查询宠物乐园...")
        can_feed = True
        feed_results = []

        result = self._post_para(PARADISE_INFO_API, {"phone": self.phone})
        if not result.ok:
            return result

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
        resp2 = self._post_para(PARADISE_INFO_API, {"phone": self.phone})
        if resp2.ok:
            user_info = resp2.data.get("userInfo", {})
            level_info = user_info.get("levelInfoMap", {})
            level = level_info.get("level", 0)
            growth = level_info.get("growthValue", 0)
            full_growth = level_info.get("fullGrowthCoinValue", 0)
            logger.info(
                f"宠物等级 [Lv.{level}], 升级进度: {growth}/{full_growth}"
            )
            result.data["level"] = level
            result.data["growth"] = growth
            result.data["full_growth"] = full_growth

        result.data["feed"] = feed_results
        return result

    def _food(self, count: int) -> dict:
        """喂食"""
        result = self._post_para(FOOD_API, {"phone": self.phone})
        if result.ok:
            msg = result.data.get("resoultMsg", "成功")
            logger.info(f"第{count}次喂食: {msg}")
            level_up = result.data.get("levelUp", False)
            if level_up:
                reward = result.data.get("currLevelRightList", [{}])[0]
                level = reward.get("level", "?")
                name = reward.get("rightsName", "?")
                logger.info(f"宠物已升级到 [LV.{level}], 获得: {name}")
            return {"ok": True, "count": count, "can_continue": True, "msg": msg}
        else:
            msg = result.msg
            if "最大喂食次数" in msg:
                logger.info(f"第{count}次喂食: 已达最大次数")
                return {"ok": False, "count": count, "can_continue": False, "msg": msg}
            logger.warning(f"第{count}次喂食失败: {msg}")
            return {"ok": False, "count": count, "can_continue": True, "msg": msg}

    def get_level_rights(self) -> APIResult:
        """查询兑换权益并兑换话费"""
        logger.info("查询宠物兑换权益...")
        results = []

        result = self._post_para(GET_LEVEL_RIGHTS_API, {"phone": self.phone})
        if not result.ok:
            return result

        current_level = result.data.get("currentLevel", 6)
        level_key = f"V{current_level}"
        items = result.data.get(level_key, [])

        coin_info = self.user_coin_info()
        coin = coin_info.data.get("totalCoin", 0) if coin_info.ok else 0

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

        result.data["results"] = results
        return result

    def _conversion_rights(self, item: dict) -> dict:
        """兑换权益"""
        name = item.get("rightsName", "")
        result = self._post_para(CONVERSION_RIGHTS_API, {
            "phone": self.phone,
            "rightsId": item.get("id", ""),
        })
        if result.ok:
            logger.info(f"兑换权益 [{name}] 成功")
            return {"ok": True, "name": name}
        else:
            logger.warning(f"兑换权益 [{name}] 失败: {result.msg}")
            return {"ok": False, "name": name, "msg": result.msg}
