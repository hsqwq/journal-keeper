"""北邮教学云平台（ucloud.bupt.edu.cn）待办获取。

移植自独立脚本 bupt-ucloud-todo（ucloud_todo.py），只保留取数据的部分；只用标准库。
流程：CAS 统一认证 → service ticket → 平台 token → 学生待办接口；课程名通过逐门课的作业列表反查。
接口不是公开的，平台改版可能失效，失效时这里抛 UcloudError。
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

CAS_LOGIN = "https://auth.bupt.edu.cn/authserver/login?service=https://ucloud.bupt.edu.cn"
API = "https://apiucloud.bupt.edu.cn"
# 平台前端代码里写死的公开 OAuth 客户端标识（portal:portal_secret / sword:sword_secret），不是用户凭据
PORTAL_BASIC = "Basic cG9ydGFsOnBvcnRhbF9zZWNyZXQ="
SWORD_BASIC = "Basic c3dvcmQ6c3dvcmRfc2VjcmV0"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TIMEOUT = 15

# 与前端 tapUndone 的跳转逻辑对应
TYPE_NAMES = {1: "讨论", 2: "问卷", 3: "作业", 4: "测验", 5: "互评"}


class UcloudError(Exception):
    """可预期的失败（登录、接口、网络），消息给用户看。"""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def cas_login(username, password):
    """登录统一认证，返回 ucloud 的 service ticket。"""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect)
    opener.addheaders = [("User-Agent", UA)]

    page = opener.open(CAS_LOGIN, timeout=TIMEOUT).read().decode("utf-8", "replace")
    match = re.search(r'name="execution" value="([^"]+)"', page)
    if not match:
        raise UcloudError("统一认证页面结构变化：找不到 execution 字段")

    form = urllib.parse.urlencode({
        "username": username,
        "password": password,
        "submit": "LOGIN",
        "type": "username_password",
        "execution": match.group(1),
        "_eventId": "submit",
    }).encode()
    try:
        resp = opener.open(urllib.request.Request(CAS_LOGIN, data=form), timeout=TIMEOUT)
        status, location, body = resp.status, resp.headers.get("Location", ""), resp.read()
    except urllib.error.HTTPError as e:
        status, location, body = e.code, e.headers.get("Location", ""), e.read()

    ticket = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query).get("ticket", [""])[0]
    if status in (301, 302, 303) and ticket:
        return ticket.split("#", 1)[0]

    html = body.decode("utf-8", "replace")
    err = re.search(r'id="errorDiv"[^>]*>\s*<p>([^<]+)</p>', html)
    if 'id="captchaParent"' in html and 'name="captcha"' in html:
        raise UcloudError("统一认证要求验证码：请先在浏览器登录一次 auth.bupt.edu.cn 解除后重试")
    raise UcloudError(f"统一认证登录失败（HTTP {status}）：{err.group(1).strip() if err else '未知原因'}")


def api_request(path, headers, data=None):
    req = urllib.request.Request(API + path, data=data, headers={
        "User-Agent": UA,
        "Tenant-Id": "000000",
        **headers,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise UcloudError(f"接口 {path.split('?')[0]} 返回 HTTP {e.code}：{detail}") from None


def get_token(ticket):
    """用 ticket 换平台 token，返回 (access_token, user_id)。"""
    body = urllib.parse.urlencode({"ticket": ticket, "grant_type": "third"}).encode()
    data = api_request("/ykt-basics/oauth/token", {
        "Authorization": PORTAL_BASIC,
        "Content-Type": "application/x-www-form-urlencoded",
    }, body)
    if not data.get("access_token") or not data.get("user_id"):
        raise UcloudError(f"换取 token 失败：{data.get('error_description') or data.get('msg') or '响应缺少字段'}")
    return data["access_token"], data["user_id"]


def get_undone(token, user_id):
    query = urllib.parse.urlencode({"userId": user_id})
    data = api_request(f"/ykt-site/site/student/undone?{query}", {
        "Authorization": SWORD_BASIC,
        "Blade-Auth": token,
    })
    if not data.get("success", True) or not isinstance(data.get("data"), dict):
        raise UcloudError(f"获取待办失败：{data.get('msg') or '响应格式异常'}")
    return data["data"].get("undoneList") or []


def get_course_map(token, user_id):
    """返回 {作业ID: 课程名}。待办接口不带课程，只能逐门课查作业列表反查；失败不致命。"""
    headers = {"Authorization": SWORD_BASIC, "Blade-Auth": token}
    query = urllib.parse.urlencode({"size": 999999, "current": 1, "userId": user_id, "siteRoleCode": 2})

    def assignment_ids(site_id):
        body = json.dumps({"siteId": site_id, "userId": user_id, "current": 1, "size": 999}).encode()
        data = api_request("/ykt-site/work/student/list",
                           {**headers, "Content-Type": "application/json"}, body)
        return [str(r.get("id")) for r in data["data"]["records"]]

    try:
        sites = api_request(f"/ykt-site/site/list/student/current?{query}", headers)["data"]["records"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            id_lists = list(pool.map(assignment_ids, [s["id"] for s in sites]))
    except (UcloudError, KeyError, TypeError, urllib.error.URLError):
        return {}  # 课程名只是锦上添花，查不到就留空
    return {aid: site.get("siteName", "") for site, ids in zip(sites, id_lists) for aid in ids}


def normalize(item, courses):
    end = item.get("endTime")
    if isinstance(end, (int, float)):  # 毫秒时间戳
        end = datetime.fromtimestamp(end / 1000).strftime("%Y-%m-%d %H:%M")
    elif isinstance(end, str):
        end = end[:16]
    return {
        "type": TYPE_NAMES.get(item.get("type"), f"类型{item.get('type')}"),
        "title": (item.get("activityName") or item.get("undoneName") or "").strip(),
        "course": item.get("siteName") or courses.get(str(item.get("activityId")), ""),
        "end_time": end or "",
        "id": item.get("activityId") or item.get("undoneId"),
    }


def fetch_todos(username: str, password: str) -> list[dict]:
    """登录并取回全部待办：[{type, title, course, end_time, id}]，按截止时间排序。"""
    try:
        token, user_id = get_token(cas_login(username, password))
        undone = get_undone(token, user_id)
        courses = get_course_map(token, user_id) if undone else {}
    except urllib.error.URLError as e:
        raise UcloudError(f"连不上教学云平台：{e.reason}") from None
    except TimeoutError:
        raise UcloudError("连接教学云平台超时，请稍后再试") from None
    items = [normalize(i, courses) for i in undone]
    return sorted(items, key=lambda i: i["end_time"] or "9999")
