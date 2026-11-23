import json
import os
import re
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

from common import cookie_path

COOKIE_PATH = cookie_path()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "wps_checkin_log.txt")
RESULT_PATH = os.path.join(BASE_DIR, "wps_checkin_last.txt")
# 任务中心稳定地址：依赖子路径 page_number，不依赖 mk_key 签名参数
URL = (
    "https://personal-act.wps.cn/rubik2/portal/"
    "HD2025031821201822/YM2025031821202008"
)


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        f.write(line + "\n")


def extract_days(body):
    m = re.search(r"已连续签到\s*(\d+)\s*天", body or "")
    return int(m.group(1)) if m else None


def main():
    if not os.path.exists(COOKIE_PATH):
        log("NEED_RELOGIN: cookie 文件不存在")
        return 2

    cookies = json.load(open(COOKIE_PATH, encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            timezone_id="Asia/Shanghai",
            locale="zh-CN",
        )
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        # 打开页面：用 domcontentloaded + 轮询等待，避免 networkidle 在美国 IP 下超时
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            log(f"WARN: 首次打开失败，重试: {exc}")
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc2:
                log(f"FAIL: 打开任务中心失败 {exc2}")
                browser.close()
                return 4
        # 轮询等待核心内容出现（给海外 IP 留足时间，最长 70 秒）
        loaded = False
        for _ in range(35):
            page.wait_for_timeout(2000)
            try:
                body = page.locator("body").inner_text()
            except Exception:
                body = ""
            if "已连续签到" in body or "退出" in body or "我的积分" in body or "点击签到" in body:
                loaded = True
                break
        if not loaded:
            log("FAIL: 页面加载超时(70s)，未见签到区域")
            try:
                page.screenshot(path=os.path.join(BASE_DIR, "wps_fail.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            return 4

        body = page.locator("body").inner_text()

        # 登录态判断：真正跳去登录页/有登录按钮才算失效；否则视为已登录
        login_form = page.evaluate(
            r"""() => {
              const btn = Array.from(document.querySelectorAll('button'))
                .find(b => (b.innerText || '').trim() === '登录' && b.offsetWidth > 0);
              const url = location.href;
              return { hasLoginBtn: !!btn, isLoginUrl: /login|passport|account/.test(url) };
            }"""
        )
        if login_form["isLoginUrl"] or (login_form["hasLoginBtn"] and "退出" not in body and "Hi，" not in body):
            log(f"NEED_RELOGIN: 跳转到登录页 (hasLoginBtn={login_form['hasLoginBtn']}, url={login_form['isLoginUrl']})")
            browser.close()
            return 3

        log(f"DEBUG: 页面已登录，含退出={('退出' in body)}, 含Hi={('Hi，' in body)}")

        # 只认「点击签到」按钮。
        # 页面永远显示「已连续签到N天」和「签到提醒」，用文本匹配会误判为已签。
        if "点击签到" not in body:
            days = ""
            for line in body.split("\n"):
                line = line.strip()
                if line.startswith("已连续签到"):
                    days = line
                    break
            log(f"OK: 今日已签到，跳过（{days or '状态正常'}）")
            browser.close()
            return 0

        days_before = extract_days(body)

        # 优先用 Playwright 真实鼠标事件点击（可信事件，比 JS el.click() 更可靠，
        # 后者可能被页面框架忽略，导致“点了没反应”）；失败再回退 JS 点击。
        clicked = False
        try:
            page.get_by_text("点击签到", exact=True).first.click(timeout=5000)
            clicked = True
        except Exception as exc:
            log(f"WARN: Playwright 点击未成功，回退 JS 点击: {exc}")
            clicked = page.evaluate(
                """
                () => {
                  const t = Array.from(document.querySelectorAll('div,button,span,a'))
                    .find(el => (el.innerText || '').trim() === '点击签到');
                  if (!t) return false;
                  t.click();
                  return true;
                }
                """
            )
        if not clicked:
            log("FAIL: 未找到可点击的「点击签到」按钮")
            try:
                page.screenshot(path=os.path.join(BASE_DIR, "wps_fail.png"), full_page=True)
            except Exception:
                pass
            browser.close()
            return 5

        # 确认结果：最长轮询约 15 秒。以前只等 4 秒，海外 runner 上页面响应慢会误报失败。
        # 三种成功判据任一命中即可：
        #   1) 「点击签到」按钮文本消失
        #   2) 「已连续签到N天」的 N 增加（可穿透按钮文本残留的误报）
        #   3) 页面出现签到成功/恭喜类文案
        body2 = body
        confirmed = False
        for _ in range(8):
            page.wait_for_timeout(2000)
            try:
                body2 = page.locator("body").inner_text()
            except Exception:
                continue
            days_after = extract_days(body2)
            if "点击签到" not in body2:
                confirmed = True
                break
            if days_before is not None and days_after is not None and days_after > days_before:
                confirmed = True
                break
            if "签到成功" in body2 or "恭喜" in body2:
                confirmed = True
                break

        if confirmed:
            days = ""
            for line in body2.split("\n"):
                line = line.strip()
                if line.startswith("已连续签到"):
                    days = line
                    break
            log(f"OK: 签到成功（{days or ''}）")
            browser.close()
            return 0

        # 未确认：截图存证，方便看页面到底是什么状态
        try:
            page.screenshot(path=os.path.join(BASE_DIR, "wps_warn.png"), full_page=True)
        except Exception:
            pass
        log(f"WARN: 已点击签到但未确认结果: {body2[:200]}")
        browser.close()
        return 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log(f"ERROR: {tb}")
        sys.exit(1)
