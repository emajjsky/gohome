# 回家本地 App API 服务器

这是 App/服务器闭环的第一版局域网服务器，用来先验证：

- 树莓派边缘盒子可以上传事件。
- 树莓派边缘盒子可以上传截图证据。
- H5/App 壳可以从服务器读取事件列表、事件详情和证据图。

它不是最终云端实现，但接口路径按正式 `api/v1` 方向设计。

## 启动

在 Mac 上：

```bash
cd /Users/tanyihua/trae比赛/gohome
GOHOME_APP_SERVER_PORT=8788 \
GOHOME_DEVICE_API_TOKEN=gohome-local-device-token \
GOHOME_APP_TOKEN=gohome-local-app-token \
npm run app-server
```

局域网里树莓派访问 Mac 时，要用 Mac 的局域网 IP，例如：

```text
http://192.168.1.x:8788
```

## 树莓派配置

在树莓派：

```bash
cd ~/gohome/edge-agent
source .venv/bin/activate

grep -q '^GOHOME_APP_SERVER_BASE_URL=' .env \
  && sed -i 's#^GOHOME_APP_SERVER_BASE_URL=.*#GOHOME_APP_SERVER_BASE_URL=http://192.168.1.x:8788#' .env \
  || echo 'GOHOME_APP_SERVER_BASE_URL=http://192.168.1.x:8788' >> .env

grep -q '^GOHOME_DEVICE_API_TOKEN=' .env \
  && sed -i 's/^GOHOME_DEVICE_API_TOKEN=.*/GOHOME_DEVICE_API_TOKEN=gohome-local-device-token/' .env \
  || echo 'GOHOME_DEVICE_API_TOKEN=gohome-local-device-token' >> .env

sudo systemctl restart gohome-edge-agent
```

把 `192.168.1.x` 换成 Mac 的真实局域网 IP。

## 验证

本机验证服务器协议：

```bash
npm run verify:app-server
```

树莓派验证上传状态：

```bash
curl -s http://127.0.0.1:8711/api/device | python -m json.tool | grep -A12 upload_agent
```

如果配置正确，`upload_agent.configured` 应为 `true`，上传队列会从 `pending` 逐步变成 `completed`。

## App/H5 打开方式

本地服务器会同时托管静态页面：

```text
http://127.0.0.1:8788/index.html?app=1
```

登录可用：

```text
账号：admin@gohome.local
密码：gohome
```

当前本地服务器的默认 App token 是 `gohome-local-app-token`。登录后浏览器会自动保存 token。
