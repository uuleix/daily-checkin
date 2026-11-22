# GitHub Actions 每日签到配置说明

本仓库通过 GitHub Actions 在云端定时执行灵犀 + WPS 会员签到，
不依赖本地电脑，也不依赖任何对话会话。

## 需要上传的文件

```
.github/workflows/daily-checkin.yml   # 定时工作流
.gitignore                            # 防止密钥被提交
common.py                             # 凭据读取
daily_checkin.py                      # 统一入口
lingxi_checkin.py                     # 灵犀签到
wps_checkin.py                        # WPS 会员签到
lingxi_notify.py                      # Server酱 推送
GITHUB_SETUP.md                       # 本说明
```

以下文件已被 `.gitignore` 排除，严禁提交：

- `lingxi_cookies.json`（登录态）
- `serverchan.conf`（Server酱 Token）
- `lingxi_login_once.py`（依赖本机环境，CI 用不到）

## 配置 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret

### 1. SERVERCHAN_TOKEN

你的 Server酱 SendKey：

```
SCT478078TvrOaKZErsaKQPPsasStQtNb6
```

### 2. LINGXI_COOKIES_GZ_B64

把 Cookie 压缩并转成 base64。

Linux：

```bash
gzip -c lingxi_cookies.json | base64 -w0
```

macOS：

```bash
gzip -c lingxi_cookies.json | base64 | tr -d '\n'
```

把输出的整串粘贴进 secret 值。

## 验证

Actions → 每日签到 → Run workflow（手动触发）。

执行成功后：

- 日志出现「全部成功」
- 微信不会收到消息（成功不推送，节省每日 5 条额度）
- 失败时会推微信，并附带 Actions 日志链接

## 已知限制

1. Cookie 会过期（实测约 8 天）。过期后报 `NEED_RELOGIN` 并推微信，
   需重新扫码导出 Cookie、更新 Secret。
2. 定时可能延迟几分钟，GitHub 在仓库繁忙时会延后执行。
3. 仓库 60 天无活动会暂停定时任务，需偶尔 push 或访问。
4. cron 按 UTC 计算，改时间记得换算（北京时间 = UTC + 8）。
5. 首次部署建议观察 2-3 天，确认 GitHub 服务器 IP 访问国内站点正常。

## 时间对照（UTC → 北京）

| UTC | 北京 |
|---|---|
| `30 1 * * *` | 每天 09:30 |
| `0 13 * * *` | 每天 21:00 |
