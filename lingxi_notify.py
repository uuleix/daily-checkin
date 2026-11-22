import sys
import urllib.parse
import urllib.request

from common import serverchan_token

token = serverchan_token()
text = sys.argv[1] if len(sys.argv) > 1 else ""
if not text:
    raise SystemExit(0)

# 第一行为标题，其余为正文
parts = text.split("\n", 1)
title = parts[0]
desp = parts[1] if len(parts) > 1 else ""

data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
url = f"https://sctapi.ftqq.com/{token}.send"
req = urllib.request.Request(url, data=data, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    body = resp.read().decode("utf-8", "replace")
print(body)
