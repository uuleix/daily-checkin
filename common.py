"""共享配置：凭据优先取环境变量（GitHub Actions Secrets），否则回退本地文件。"""

import base64
import gzip
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE, "lingxi_cookies.json")
TOKEN_FILE = os.path.join(BASE, "serverchan.conf")


def cookie_path():
    """返回 Cookie 文件路径。

    环境变量 LINGXI_COOKIES_GZ_B64 存放 gzip+base64 编码的 Cookie JSON，
    适用于 GitHub Actions Secrets；未设置时回退本地文件。
    """
    b64 = os.environ.get("LINGXI_COOKIES_GZ_B64", "")
    # 消毒：从聊天/网页复制时极易混入零宽空格、BOM、不间断空格、换行等，
    # 这些会让 base64.b64decode 抛 "string argument should contain only ASCII characters"。
    # 只保留 base64 合法字符，彻底免疫粘贴污染。
    b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
    if not b64:
        return COOKIE_FILE

    raw = gzip.decompress(base64.b64decode(b64))
    out = os.path.join(BASE, ".cookies_from_secret.json")
    with open(out, "wb") as f:
        f.write(raw)
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return out


def serverchan_token():
    """返回 Server酱 SendKey，优先环境变量 SERVERCHAN_TOKEN。"""
    token = os.environ.get("SERVERCHAN_TOKEN", "").strip()
    if token:
        return token
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return f.read().strip()
