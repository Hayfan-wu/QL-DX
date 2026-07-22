"""
中国电信话费自动化 (林老师风格改写版)
=========================================
基于林老师的脚本结构，适配青龙面板和 QQ 机器人插件。

环境变量:
  dxlin=手机号#密码#AndroidID
  多账号换行分隔

  兼容旧变量: chinaTelecomAccount=手机号#密码 (需额外设置 DX_ANDROID_ID)

AndroidID 获取: https://commissions-yields-exception-personally.trycloudflare.com/

青龙定时任务:
  命令: task dx_auto.py
  定时: 0 8,12,18 * * *

依赖安装:
  pip install requests pycryptodome certifi --break-system-packages
"""

import base64
import json
import logging
import os
import random
import string
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Union

import certifi
import requests
from Crypto.Cipher import AES, DES3, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# ==================== 环境变量加载 ====================
_PROJECT_DIR = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_DIR / ".env"
if _ENV_FILE.exists():
    with open(str(_ENV_FILE), "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                if _key.strip() not in os.environ:
                    os.environ.setdefault(_key.strip(), _val.strip().strip("\"'"))

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent
RESULT_FILE = PROJECT_DIR / "result.json"
LOG_FILE = PROJECT_DIR / "dx_telecom.log"

# 功能开关
ENABLE_SIGNIN = os.environ.get("DX_ENABLE_SIGNIN", "true").lower() in ("true", "1", "yes", "on")
ENABLE_ACTIVITY = os.environ.get("DX_ENABLE_ACTIVITY", "true").lower() in ("true", "1", "yes", "on")
ENABLE_LOTTERY = os.environ.get("DX_ENABLE_LOTTERY", "true").lower() in ("true", "1", "yes", "on")
ENABLE_EXCHANGE = os.environ.get("DX_ENABLE_EXCHANGE", "true").lower() in ("true", "1", "yes", "on")
ENABLE_FLASH_SALE = os.environ.get("DX_ENABLE_FLASH_SALE", "false").lower() in ("true", "1", "yes", "on")
FLASH_SALE_TIME = os.environ.get("DX_FLASH_SALE_TIME", "10:00:00")

# 密钥
KEYS = {
    'login_rsa': """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDBkLT15ThVgz6/NOl6s8GNPofdWzWbCkWnkaAm7O2LjkM1H7dMvzkiqdxU02jamGRHLX/ZNMCXHnPcW/sDhiFCBN18qFvy8g6VYb9QtroI09e176s+ZCtiv7hbin2cCTj99iUpnEloZm19lwHyo69u5UMiPMpq0/XKBO8lYhN/gwIDAQAB
-----END PUBLIC KEY-----""",
    'data_rsa': """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+ugG5A8cZ3FqUKDwM57GM4io6JGcStivT8UdGt67PEOihLZTw3P7371+N47PrmsCpnTRzbTgcupKtUv8ImZalYk65dU8rjC/ridwhw9ffW2LBwvkEnDkkKKRi2liWIItDftJVBiWOh17o6gfbPoNrWORcAdcbpk2L+udld5kZNwIDAQAB
-----END PUBLIC KEY-----""",
    'des3': b'1234567`90koiuyhgtfrdews',
    'aes_def': b'34d7cb0bcdf07523',
    'aes_login': 'telecom_wap_2018',
}

# ==================== 日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DX-Telecom")

# ==================== 工具函数 ====================

_global_logs = []

def log(msg: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"
    _global_logs.append(full_msg)
    logger.info(msg)


def mask(s: str) -> str:
    if not s or len(s) < 7:
        return s
    return f"{s[:3]}****{s[-4:]}"


def ts() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S')


def rd_str(length: int) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def encode(s: str) -> str:
    return ''.join(chr(ord(c) + 2) for c in s)


# ==================== SSL 与 HTTP 会话 ====================

class CustomSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1:!aNULL:!eNULL:!MD5')
        ctx.check_hostname = False
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.verify = certifi.where()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; U; Android 12; zh-cn) AppleWebKit/533.1 (KHTML, like Gecko) Version/5.0 Mobile Safari/533.1'
})
_session.mount('https://', CustomSSLAdapter())


# ==================== 加密逻辑 ====================

def encrypt_des3(data, mode='enc'):
    cipher = DES3.new(KEYS['des3'], DES3.MODE_CBC, 8 * b'\0')
    if mode == 'enc':
        return cipher.encrypt(pad(data.encode(), 8)).hex()
    return unpad(cipher.decrypt(bytes.fromhex(data)), 8).decode()


def encrypt_aes(data, key=KEYS['aes_def'], b64=False):
    data = json.dumps(data, separators=(',', ':')) if isinstance(data, (dict, list)) else data
    cipher = AES.new(key if isinstance(key, bytes) else key.encode(), AES.MODE_ECB)
    enc = cipher.encrypt(pad(data.encode(), 16))
    return base64.b64encode(enc).decode() if b64 else enc.hex()


def encrypt_rsa(data, key_type='data', out='hex'):
    cipher = PKCS1_v1_5.new(RSA.import_key(KEYS[f'{key_type}_rsa']))
    data = json.dumps(data, separators=(',', ':')) if isinstance(data, (dict, list)) else data
    if out == 'hex':
        return ''.join(cipher.encrypt(data[i:i+32].encode()).hex() for i in range(0, len(data), 32))
    return base64.b64encode(cipher.encrypt(data.encode())).decode()


# ==================== 请求函数 ====================

def api_req(url: str, method: str = 'POST', raw: bool = False, **kwargs) -> Union[Dict[str, Any], str]:
    try:
        r = _session.request(method, url, timeout=15, **kwargs)
        if raw:
            return r.text
        return r.json()
    except Exception as e:
        log(f"[网络异常] {str(e)}")
        return '' if raw else {}


# ==================== 登录 ====================

def login_v2(phone: str, password: str, android_id: str):
    """登录

    Args:
        phone: 手机号
        password: 服务密码
        android_id: AndroidID（从指定网站获取）

    Returns:
        dict: 用户信息（含token, userId, uid, Authorization等）或 None
    """
    m_phone = mask(phone)
    log(f"[登录] {m_phone} 开始登录")

    body = {
        "headerInfos": {
            "code": "userLoginNormal",
            "timestamp": ts(),
            "broadAccount": "",
            "broadToken": "",
            "clientType": "#11.0.0#channel8#Xiaomi 20#",
            "shopId": "20002",
            "source": "110003",
            "sourcePassword": "Sid98s",
            "token": "",
            "userLoginName": encode(phone)
        },
        "content": {
            "attach": "test",
            "fieldData": {
                "loginType": "4",
                "accountType": "",
                "loginAuthCipherAsymmertric": encrypt_rsa(
                    f"Xiaomi 20 8.0.0.{android_id[:12]}{phone}{ts()}{password}0$$$0.",
                    'login', 'b64'
                ),
                "deviceUid": "",
                "phoneNum": encode(phone),
                "isChinatelecom": "",
                "systemVersion": "8.0.0",
                "androidId": encode(android_id),
                "loginAuthCipher": "",
                "authentication": encode(password)
            }
        }
    }
    res = api_req(
        'https://appgologin.189.cn:9031/login/client/userLoginNormal',
        json=body
    )
    if not isinstance(res, dict):
        log(f"[登录失败] {m_phone} 响应非JSON")
        return None

    # 调试：打印完整登录响应
    resp_data = res.get('responseData') or {}
    result_code = resp_data.get('resultCode', '') if isinstance(resp_data, dict) else ''
    result_desc = resp_data.get('resultDesc', '') if isinstance(resp_data, dict) else ''
    log(f"[登录响应] {m_phone} resultCode={result_code}, resultDesc={result_desc}")
    log(f"[登录响应] {m_phone} 完整数据: {json.dumps(res, ensure_ascii=False)[:500]}")

    login_data = resp_data.get('data', {}).get('loginSuccessResult') if isinstance(resp_data, dict) else None
    if not login_data:
        err_msg = (resp_data.get('data', {}).get('resultMsg', '') if isinstance(resp_data, dict) else '') or '接口返回无登录数据'
        log(f"[登录失败] {m_phone}: {err_msg}")
        return None

    # 获取Ticket
    xml = f'''<Request>
        <HeaderInfos>
            <Code>getSingle</Code>
            <Timestamp>{ts()}</Timestamp>
            <BroadAccount></BroadAccount>
            <BroadToken></BroadToken>
            <ClientType>#9.6.1#channel50#iPhone 14 Pro Max#</ClientType>
            <ShopId>20002</ShopId>
            <Source>110003</Source>
            <SourcePassword>Sid98s</SourcePassword>
            <Token>{login_data["token"]}</Token>
            <UserLoginName>{phone}</UserLoginName>
        </HeaderInfos>
        <Content>
            <Attach>test</Attach>
            <FieldData>
                <TargetId>{encrypt_des3(login_data["userId"])}</TargetId>
                <Url>4a6862274835b451</Url>
            </FieldData>
        </Content>
    </Request>'''
    xml_res = api_req(
        'https://appgologin.189.cn:9031/map/clientXML',
        data=xml,
        headers={'Content-Type': 'application/xml'},
        raw=True
    )
    if not isinstance(xml_res, str):
        log(f"[获取Ticket失败] {m_phone} 返回非字符串")
        return None
    if '过期' in xml_res or '校验错误' in xml_res:
        log(f"[获取Ticket失败] {m_phone} 票据校验异常")
        return None
    if '<Ticket>' not in xml_res:
        log(f"[Ticket异常] {m_phone} 响应缺失Ticket")
        return None

    try:
        ticket = xml_res.split('<Ticket>')[1].split('</Ticket>')[0]
        uid = encrypt_des3(ticket, 'dec')
    except Exception as e:
        log(f"[解析Ticket失败] {m_phone}: {str(e)}")
        return None

    # 统一登录获取Bearer
    auth_body = encrypt_aes(
        {"ticket": uid, "backUrl": "https%3A%2F%2Fwapact.189.cn%3A9001", "platformCode": "P201010301", "loginType": 2},
        KEYS['aes_login'],
        True
    )
    auth_res = api_req(
        'https://wapact.189.cn:9001/unified/user/login',
        data=auth_body,
        headers={'Content-Type': 'application/json'}
    )
    user_info = {
        **login_data,
        'uid': uid,
        'phoneNbr': phone
    }
    if isinstance(auth_res, dict) and auth_res.get('code') == 0:
        user_info['Authorization'] = f"Bearer {auth_res['biz']['token']}"
    else:
        log(f"[统一登录警告] {m_phone} 未获取Bearer，抽奖功能不可用")

    return user_info


# ==================== 话费券秒杀 ====================

def do_flash_sale(user: dict, sign_header: dict) -> dict:
    """话费券秒杀

    在指定时间抢话费券。会等待到目标时间点精确执行。

    Args:
        user: 用户信息
        sign_header: 带 sign 的请求头

    Returns:
        dict: {"type": "秒杀", "value": "..."} 或 None
    """
    m = mask(user['phoneNbr'])
    phone = user['phoneNbr']

    # 解析目标秒杀时间
    try:
        parts = FLASH_SALE_TIME.split(':')
        target_h, target_m, target_s = int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        log(f"[秒杀] {m} 秒杀时间格式错误: {FLASH_SALE_TIME}，应为 HH:MM:SS")
        return None

    now = datetime.now()
    target = now.replace(hour=target_h, minute=target_m, second=target_s, microsecond=0)

    # 如果目标时间已过（超过60秒），跳过
    if (target - now).total_seconds() < -60:
        log(f"[秒杀] {m} 今日秒杀时间 {FLASH_SALE_TIME} 已过，跳过")
        return None

    # 等待到秒杀时间（提前2秒开始准备）
    if target > now:
        wait_secs = (target - now).total_seconds() - 2
        if wait_secs > 0:
            log(f"[秒杀] {m} 等待到 {FLASH_SALE_TIME}，还需 {int(wait_secs)} 秒")
            # 每秒检查，避免长时间阻塞
            while wait_secs > 0:
                time.sleep(min(1, wait_secs))
                wait_secs -= 1

    # 精确等待到整秒
    while datetime.now().second % 1 != 0:
        time.sleep(0.05)

    log(f"[秒杀] {m} 开始抢购！")

    # 1. 查询秒杀活动列表
    sale_list = api_req(
        'https://wappark.189.cn/jt-sign/seckill/list',
        json={"para": encrypt_rsa({"phone": phone})},
        headers=sign_header
    )
    if not isinstance(sale_list, dict):
        log(f"[秒杀] {m} 查询秒杀列表失败")
        return None

    sale_items = sale_list.get('data', {}).get('biz', {}).get('seckillGoods', [])
    if not sale_items:
        log(f"[秒杀] {m} 当前无秒杀活动")
        return None

    log(f"[秒杀] {m} 发现 {len(sale_items)} 个秒杀商品")

    grabbed = []
    for item in sale_items:
        goods_id = item.get('goodsId', '')
        goods_name = item.get('goodsName', '未知')
        sale_price = item.get('salePrice', 0)
        stock = item.get('stock', 0)

        log(f"[秒杀] {m} 商品: {goods_name} (价格:{sale_price} 库存:{stock})")

        if stock <= 0:
            continue

        # 疯狂点击抢购（3次重试）
        for attempt in range(3):
            buy_res = api_req(
                'https://wappark.189.cn/jt-sign/seckill/buy',
                json={"para": encrypt_rsa({"phone": phone, "goodsId": goods_id})},
                headers=sign_header
            )
            if isinstance(buy_res, dict):
                buy_code = buy_res.get('resoultCode', -1)
                buy_msg = buy_res.get('resoultMsg', '')
                if buy_code == 0:
                    log(f"[秒杀成功] {m} 抢到: {goods_name}")
                    grabbed.append(goods_name)
                    break
                elif '已抢' in buy_msg or '已购' in buy_msg or '库存不足' in buy_msg:
                    log(f"[秒杀] {m} {buy_msg}")
                    break
                else:
                    log(f"[秒杀] {m} 第{attempt+1}次抢购: {buy_msg}")
            time.sleep(0.5)

        time.sleep(0.3)

    if grabbed:
        msg = f"抢到 {len(grabbed)} 个: {'、'.join(grabbed)}"
        log(f"[秒杀] {m} {msg}")
        return {"type": "秒杀", "value": msg}
    else:
        log(f"[秒杀] {m} 未抢到任何商品")
        return None


# ==================== 任务执行 ====================

def sign_tasks(user: dict):
    """执行签到及所有任务

    Args:
        user: login_v2 返回的用户信息 dict
    """
    m = mask(user['phoneNbr'])
    log(f"[任务开始] {m}")

    result = {
        "phone": m,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "items": [],
        "login": True,
        "signin": {},
        "activities": [],
        "signDay": 0,        # 连续签到天数
        "totalCoin": 0,      # 金豆总数
        "todayCoin": 0,      # 今日获得豆子
        "nonCoinRewards": [], # 非豆子奖励
    }

    sso_url = f"https://wappark.189.cn/jt-sign/ssoHomLogin?ticket={user['uid']}"
    sso = api_req(sso_url, method='GET')
    if not isinstance(sso, dict) or not sso or 'sign' not in sso:
        log(f"[获取sign失败] {m} 中断所有签到任务")
        result["error"] = "获取 sign 失败"
        _save_result(result)
        return result
    sign_header = {'sign': sso['sign']}

    # 先查询签到状态（获取连续签到天数和金豆余额）
    status_res = api_req(
        'https://wappark.189.cn/jt-sign/api/home/userStatusInfo',
        json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
        headers=sign_header
    )
    if isinstance(status_res, dict):
        status_data = status_res.get('data', {})
        result["signDay"] = status_data.get('signDay', 0)
        log(f"[状态] {m} 连续签到 {result['signDay']} 天")

    # 查询金豆余额
    coin_res = api_req(
        'https://wappark.189.cn/jt-sign/api/home/userCoinInfo',
        json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
        headers=sign_header
    )
    if isinstance(coin_res, dict):
        result["totalCoin"] = coin_res.get('totalCoin', 0)
        log(f"[金豆] {m} 当前余额: {result['totalCoin']}")

    # 签到
    if ENABLE_SIGNIN:
        log(f"[签到] {m} 执行每日签到")
        sign_res = api_req(
            'https://wappark.189.cn/jt-sign/webSign/sign',
            json={"encode": encrypt_aes({"phone": user['phoneNbr'], "date": int(time.time()*1000)})},
            headers=sign_header
        )
        if isinstance(sign_res, dict):
            inner = sign_res.get('data', {})
            if inner.get('code') == 1:
                coin = inner.get('coin', 0)
                result["todayCoin"] += coin
                msg = f"签到成功，获得{coin}金豆"
                log(f"[签到成功] {m} {msg}")
                result["items"].append({"type": "签到", "value": msg})
                result["signin"] = {"ok": True, "msg": msg, "coin": coin}
            else:
                msg = inner.get('msg', '签到失败')
                log(f"[签到] {m} {msg}")
                result["signin"] = {"ok": False, "msg": msg}
        else:
            result["signin"] = {"ok": False, "msg": "签到响应异常"}

    # 连签 + 累签
    def check_and_award(path, key, days_list, label):
        res = api_req(
            f'https://wappark.189.cn/jt-sign/{path}',
            json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
            headers=sign_header
        )
        if not isinstance(res, dict):
            return
        days = str(res.get('data', {}).get(key) if 'data' in res else res.get(key, 0))
        log(f"[{label}] {m}: {days}天")
        if days in days_list:
            log(f"[{label}领奖] {m} 达标{days}天，领取奖励")
            award_res = api_req(
                'https://wappark.189.cn/jt-sign/webSign/exchangePrize',
                json={"para": encrypt_rsa({"phone": user['phoneNbr'], "type": days})},
                headers=sign_header
            )
            if isinstance(award_res, dict):
                prize = award_res.get('prizeDetail', {}).get('biz', {}).get('winTitle', '未知')
                result["items"].append({"type": f"{label}兑换", "value": prize})
                # 判断是否为非豆子奖励
                if '金豆' not in prize:
                    result["nonCoinRewards"].append(prize)

    check_and_award('api/home/userStatusInfo', 'signDay', ['7'], '连签')
    check_and_award('webSign/continueSignDays', 'continueSignDays', ['15', '28'], '累签')

    # 金豆转盘抽奖
    if ENABLE_LOTTERY and 'Authorization' in user:
        log(f"[抽奖] {m} 查询转盘活动")
        tab = api_req(
            f"https://wapact.189.cn:9001/gateway/golden/api/queryTurnTable?userType=1&_={int(time.time()*1000)}",
            method='GET',
            headers={'Authorization': user['Authorization']}
        )
        if isinstance(tab, dict) and tab.get('code') == 0:
            act_id = tab['biz']['wzTurntable']['code']
            chk = api_req(
                f"https://wapact.189.cn:9001/gateway/standQuery/detail/check?activityId={act_id}",
                method='GET',
                headers={'Authorization': user['Authorization']}
            )
            if isinstance(chk, dict) and chk.get('code') == 0:
                info = chk.get('biz', {}).get('resultInfo', {})
                remain = info.get('userMaximum', 0) - info.get('userCount', 0)
                log(f"[抽奖] {m} 剩余可抽奖次数：{remain}次")
                for idx in range(remain):
                    log(f"[抽奖] {m} 进行第{idx+1}次抽奖")
                    api_req(
                        'https://wapact.189.cn:9001/gateway/golden/api/lottery',
                        json={"activityId": act_id},
                        headers={'Authorization': user['Authorization']}
                    )
                    time.sleep(2)
                if remain > 0:
                    result["items"].append({"type": "抽奖", "value": f"转盘 {remain} 次"})
            else:
                log(f"[抽奖] {m} 查询剩余次数接口异常")
        else:
            log(f"[抽奖] {m} 无可用转盘活动")
    elif ENABLE_LOTTERY:
        log(f"[抽奖] {m} 缺少Bearer凭证，跳过抽奖")

    # 任务列表
    if ENABLE_ACTIVITY:
        tasks_res = api_req(
            'https://wappark.189.cn/jt-sign/webSign/homepage',
            json={"para": encrypt_rsa({"phone": user['phoneNbr'], "shopId": "20001", "type": "hg_qd_zrwzjd"})},
            headers=sign_header
        )
        if isinstance(tasks_res, dict):
            tasks = tasks_res.get('data', {}).get('biz', {}).get('adItems', [])
            log(f"[任务列表] {m} 待完成任务总数：{len(tasks)}个")
            completed_count = 0
            for t in tasks:
                if t.get('taskState') in ['0', '1'] and t.get('contentOne') == '18':
                    log(f"[任务执行] {m} 执行任务：{t.get('title', '未知任务')}")
                    api_req(
                        'https://wappark.189.cn/jt-sign/webSign/polymerize',
                        json={"para": encrypt_rsa({"phone": user['phoneNbr'], "jobId": t['taskId']})},
                        headers=sign_header
                    )
                    completed_count += 1
                    time.sleep(2)
            if completed_count > 0:
                result["items"].append({"type": "活动", "value": f"完成 {completed_count} 个任务"})

    # 喂食
    log(f"[喂食] {m} 开始宠物喂食")
    feed_count = 0
    for i in range(10):
        res = api_req(
            'https://wappark.189.cn/jt-sign/paradise/food',
            json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
            headers=sign_header
        )
        msg = res.get('resoultMsg', '') if isinstance(res, dict) else ''
        if "最大" in msg or "已达" in msg or not msg:
            if msg:
                log(f"[喂食结束] {m} {msg}")
            break
        feed_count += 1
        time.sleep(1)
    if feed_count > 0:
        result["items"].append({"type": "宠物", "value": f"喂食 {feed_count} 次"})

    # 宠物乐园等级权益兑换话费券
    if ENABLE_EXCHANGE:
        log(f"[权益兑换] {m} 查询宠物等级权益")
        rights_res = api_req(
            'https://wappark.189.cn/jt-sign/paradise/getLevelRightsList',
            json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
            headers=sign_header
        )
        if isinstance(rights_res, dict):
            current_level = rights_res.get('currentLevel', 6)
            level_key = f"V{current_level}"
            items = rights_res.get(level_key, [])

            # 使用已查询的金豆余额
            coin = result["totalCoin"]

            exchanged = 0
            for item in items:
                rights_name = item.get('rightsName', '')
                cost_coin = item.get('costCoin', 0)
                # 只兑换话费券和专享金豆
                import re
                is_phone_coupon = re.search(r'\d+元话费', rights_name)
                is_special_coin = re.search(r'专享\d+金豆', rights_name)
                if (is_phone_coupon or is_special_coin) and coin >= cost_coin:
                    log(f"[权益兑换] {m} 兑换: {rights_name} (需{cost_coin}金豆，余额{coin})")
                    exc_res = api_req(
                        'https://wappark.189.cn/jt-sign/paradise/conversionRights',
                        json={"para": encrypt_rsa({"phone": user['phoneNbr'], "rightsId": item.get('id', '')})},
                        headers=sign_header
                    )
                    exc_msg = exc_res.get('resoultMsg', '') if isinstance(exc_res, dict) else ''
                    log(f"[权益兑换] {m} 结果: {exc_msg or '成功'}")
                    result["items"].append({"type": "兑换", "value": rights_name})
                    if '金豆' not in rights_name:
                        result["nonCoinRewards"].append(rights_name)
                    exchanged += 1
                    coin -= cost_coin
                    time.sleep(1)
            if exchanged == 0:
                log(f"[权益兑换] {m} 无可兑换的话费券权益或金豆不足")
        else:
            log(f"[权益兑换] {m} 查询等级权益失败")

    # 话费券秒杀
    if ENABLE_FLASH_SALE:
        log(f"[秒杀] {m} 开始话费券秒杀")
        flash_result = do_flash_sale(user, sign_header)
        if flash_result:
            result["items"].append(flash_result)

    log(f"[任务全部完成] {m}")
    _save_result(result)
    return result


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
    records["history"].append(run_result)
    for item in run_result.get("items", []):
        key = item.get("type", "其他")
        val = item.get("value", "")
        if key not in records["total"]:
            records["total"][key] = []
        records["total"][key].append({"time": run_result["time"], "value": val})
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))


def format_wxpusher_summary(result: dict) -> str:
    """格式化 Wxpusher 风格摘要（供 bot 插件和 notify 调用）

    输出格式:
      电信签到 成功/失败
      连续签到 X 天
      今日豆子 +X
      豆子总数 X
      其他奖励: X元话费券、XXX
    """
    phone = result.get("phone", "未知")
    time_str = result.get("time", "")
    signin = result.get("signin", {})
    sign_day = result.get("signDay", 0)
    total_coin = result.get("totalCoin", 0)
    today_coin = result.get("todayCoin", 0)
    non_coin = result.get("nonCoinRewards", [])

    lines = [
        f"📱 电信签到 {'✅成功' if signin.get('ok') else '❌失败'}",
        f"📅 连续签到 {sign_day} 天",
        f"🟡 今日豆子 +{today_coin}",
        f"💰 豆子总数 {total_coin}",
    ]

    if non_coin:
        lines.append(f"🎁 其他奖励: {'、'.join(non_coin)}")

    if result.get("error"):
        lines.append(f"⚠️ 异常: {result['error']}")

    return "\n".join(lines)


def query_results() -> str:
    """查询最近一次执行结果（Wxpusher 风格简化输出）"""
    records = _load_results()
    history = records.get("history", [])
    if not history:
        return "暂无任务执行记录，请先执行 电信执行"
    last = history[-1]
    return format_wxpusher_summary(last)


# ==================== 主入口 ====================

def run_all(signin_only: bool = False) -> dict:
    """执行全部任务（青龙面板入口）

    Args:
        signin_only: 如果为 True，仅执行签到和连签/累签
    """
    global _global_logs
    _global_logs = []

    # 读取环境变量
    raw = os.environ.get('dxlin', '')

    # 兼容旧格式: chinaTelecomAccount=手机号#密码 + DX_ANDROID_ID=xxx
    if not raw:
        old_acc = os.environ.get('chinaTelecomAccount') or os.environ.get('DX_ACCOUNT', '')
        old_aid = os.environ.get('DX_ANDROID_ID', '')
        if old_acc and '#' in old_acc and old_aid:
            raw = f"{old_acc}#{old_aid}"

    if not raw:
        log("未找到环境变量 dxlin，请按格式设置：手机号#密码#AndroidID")
        log("AndroidID 获取: https://commissions-yields-exception-personally.trycloudflare.com/")
        log("多账号换行分隔，兼容旧变量: chinaTelecomAccount=手机号#密码 + DX_ANDROID_ID=xxx")
        return {"error": "账号未配置", "login": False}

    accs = [line.strip().split('#') for line in raw.strip().split('\n') if line.strip() and '#' in line]
    if not accs:
        log("未解析到有效账号，请检查格式（手机号#密码#AndroidID）")
        return {"error": "账号格式错误", "login": False}

    all_results = []
    for idx, parts in enumerate(accs, 1):
        phone = parts[0].strip()
        pwd = parts[1].strip() if len(parts) > 1 else ''
        android_id = parts[2].strip() if len(parts) > 2 else ''

        if not android_id:
            log(f"[账号{idx}] 错误：缺少 AndroidID，格式应为 手机号#密码#AndroidID")
            continue

        log(f"\n{'='*10} 账号[{idx}] {mask(phone)} {'='*10}")
        user = login_v2(phone, pwd, android_id)

        if user:
            if signin_only:
                # 仅签到：简化为只执行签到和连签/累签
                m = mask(user['phoneNbr'])
                log(f"[签到模式] {m}")
                sso_url = f"https://wappark.189.cn/jt-sign/ssoHomLogin?ticket={user['uid']}"
                sso = api_req(sso_url, method='GET')
                if isinstance(sso, dict) and 'sign' in sso:
                    sign_header = {'sign': sso['sign']}
                    sign_res = api_req(
                        'https://wappark.189.cn/jt-sign/webSign/sign',
                        json={"encode": encrypt_aes({"phone": user['phoneNbr'], "date": int(time.time()*1000)})},
                        headers=sign_header
                    )
                    if isinstance(sign_res, dict):
                        inner = sign_res.get('data', {})
                        if inner.get('code') == 1:
                            coin = inner.get('coin', 0)
                            log(f"[签到成功] {m} 获得{coin}金豆")
                        else:
                            log(f"[签到] {m} {inner.get('msg', '签到失败')}")
                    api_req(
                        'https://wappark.189.cn/jt-sign/api/home/userStatusInfo',
                        json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
                        headers=sign_header
                    )
                    api_req(
                        'https://wappark.189.cn/jt-sign/webSign/continueSignDays',
                        json={"para": encrypt_rsa({"phone": user['phoneNbr']})},
                        headers=sign_header
                    )
                time.sleep(2)
            else:
                result = sign_tasks(user)
                all_results.append(result)
        else:
            log(f"[账号跳过] {mask(phone)} 登录失败，不执行任务")

        time.sleep(2)

    # 推送简化摘要（如果存在 notify 模块）
    try:
        import notify
        if all_results:
            for r in all_results:
                summary = format_wxpusher_summary(r)
                notify.send('电信签到推送', summary)
            log("通知推送成功")
    except ImportError:
        pass

    return all_results[0] if all_results else {"error": "无执行结果", "login": False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="中国电信话费自动化")
    parser.add_argument("--signin-only", action="store_true", help="仅执行签到")
    args = parser.parse_args()

    result = run_all(signin_only=args.signin_only)
    if result.get("error"):
        print(f"\n[FAIL] {result['error']}")
        sys.exit(1)
    else:
        print(f"\n[OK] 执行完成")
        sys.exit(0)
