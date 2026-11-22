"""灵犀每日签到（纯 Playwright 实现，可直接部署到 GitHub Actions）。"""

import json
import os
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from common import cookie_path

COOKIE_PATH = cookie_path()
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lingxi_checkin_log.txt")
RESULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lingxi_checkin_last.txt")
URL = "https://lingxi.kdocs.cn"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    if not os.path.exists(COOKIE_PATH):
        log("NEED_RELOGIN: cookie 文件不存在")
        return 2

    cookies = json.load(open(COOKIE_PATH, encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=UA)
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3500)
        except Exception as exc:
            log(f"FAIL: 打开灵犀失败 {exc}")
            browser.close()
            return 4

        # 未登录：页面仍是登录按钮
        body = page.locator("body").inner_text()
        login_btn = page.evaluate(
            """() => Array.from(document.querySelectorAll('button'))
                 .some(b => (b.innerText || '').trim() === '登录')"""
        )
        if login_btn and "新任务" not in body:
            log("NEED_RELOGIN: 登录态已失效")
            browser.close()
            return 3

        # 打开智点面板
        page.evaluate(
            """() => {
              const els = Array.from(document.querySelectorAll('button,[role=button]'));
              const t = els.find(el => ((el.getAttribute('aria-label') || '') + (el.innerText || ''))
                                        .includes('个人可用智点'));
              if (t) t.click();
              return !!t;
            }"""
        )
        page.wait_for_timeout(1500)

        # 任务中心可能已直接展开，否则点击入口
        body = page.locator("body").inner_text()
        if "每日签到与任务奖励" not in body and "距离下次签到" not in body \
                and "立即签到" not in body:
            page.evaluate(
                """() => {
                  const els = Array.from(document.querySelectorAll('button,a,[role=button],div,span,li'));
                  const t = els.find(el => (el.innerText || '').trim() === '任务中心');
                  if (t) (t.closest('button,a,[role=button],li,div') || t).click();
                  return !!t;
                }"""
            )
            page.wait_for_timeout(2500)

        body = page.locator("body").inner_text()
        if "每日签到与任务奖励" not in body and "距离下次签到" not in body \
                and "立即签到" not in body:
            log("FAIL: 任务中心内容未加载")
            browser.close()
            return 5

        # 判断今日是否已签：只认「立即签到」按钮。
        # 历史连签记录里也有「已签到」文本，用文本匹配会误判。
        has_pending = "立即签到" in body
        has_done = "距离下次签到" in body

        if has_done and not has_pending:
            log("OK: 今日已签到，跳过")
            browser.close()
            return 0

        if not has_pending:
            log("FAIL: 既未找到「立即签到」按钮，也未见「距离下次签到」，状态未知")
            browser.close()
            return 5

        clicked = page.evaluate(
            """() => {
              const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
              const t = els.find(el => {
                const s = (el.innerText || '').trim();
                return s === '立即签到' || (s.includes('立即签到') && s.length < 20);
              });
              if (!t) return false;
              (t.closest('button,[role=button]') || t).click();
              return true;
            }"""
        )
        if not clicked:
            log("FAIL: 未找到「立即签到」按钮")
            browser.close()
            return 6

        page.wait_for_timeout(3500)
        body2 = page.locator("body").inner_text()

        # 成功标志：「立即签到」消失 且 「距离下次签到」出现
        if "立即签到" not in body2 and "距离下次签到" in body2:
            log("OK: 签到成功")
            browser.close()
            return 0

        log(f"WARN: 已点击签到但未确认结果: {body2[:200]}")
        browser.close()
        return 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)
