# 想家了吗 Implement

更新时间：2026-06-30

## 1. 文档目的

这份文档记录 `想家了吗` 第二阶段的真实实施进度、当前运行方式、已完成能力、未完成事项和下一步开发记录。

PRD 负责定义产品边界，Plan 负责定义实施顺序，Implement 负责记录“现在到底做到哪里了”。

## 1.1 2026-06-27 文档升级记录

本次已把文档方向从“本机验证说明”升级为“可商业化落地的产品系统文档”。

关键调整：

- PRD 不再把当前 Mac 算力服务当成最终产品，而是定义为阶段 0 验证。
- PRD 已补充商业化产品形态、目标客户、收费模式、用户角色和产品边界。
- PRD 已补充用户端、云端后端、边缘硬件、视觉算法、API 管理、数据分层和硬件端职责。
- Plan 已从本机任务清单调整为商业化路线：本机验证、边缘端产品化、云端 API、用户端 App、视觉模型产品化、硬件试点、商业化运营。
- Plan 已补充工作线矩阵、关键依赖、里程碑产物和近期两周建议排期。
- 当前实现仍然只覆盖阶段 0 的一部分，不能代表最终商业化架构。

后续实现必须按新 PRD 和 Plan 推进，避免继续把逻辑堆在静态页面或单个本机服务里。

## 1.2 2026-06-28 路线确认

当前路线调整为：

- 先把当前 M4 / 24GB Mac 跑成第一版本地算力服务。
- 当前 Mac 负责 RTSP 拉流、YOLO 检测、规则判断、事件落库、Web 用户端和管理台。
- 树莓派或其他小盒子硬件可以开始采购，但暂时不作为主开发环境。
- 树莓派后续用于验证低功耗部署、开机自启、散热、断网恢复和 24 小时稳定性。
- 当前重点是本地产品闭环，不是硬件迁移。

后续所有实现都要按“未来边缘盒运行时”设计，避免只为当前 Mac 写死。

## 1.3 2026-06-28 新增执行约束

根据本轮补充要求，后续实现新增以下硬约束：

- 页面端和 App 端都必须通过核心链路，不能只做网页通过。
- 实时画面能力属于正式产品能力，不能只留在后台调试页。
- 视频服务后台必须和前端页面、App 打通，不能各做各的。
- 算法按“一算法一文件”组织，后台配置页必须能看到各算法模块。
- 姿态检测等高级算法不能只给一个框框，必须有更完整的解释结果。
- 数据层、算法层、规则层、视频层、展示层必须拆开，避免代码继续臃肿。

## 1.4 2026-06-28 App 与后端顺序校正

本轮确认：

- 正式 App 开发不能排在注册、登录、家庭空间、设备绑定等最小用户后端之前。
- 在最小用户后端完成前，可以继续推进 Web/H5 原型和本地闭环，但其定位是流程验证，不是正式 App 交付。
- 后续正式 App 的前提条件是：`identity-service`、登录鉴权、家庭关系、设备绑定、事件查询、实时画面鉴权已具备最小可用版本。

## 2. 当前运行方式

当前只需要启动一个服务：`edge-agent`。

启动命令：

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
cp .env.example .env
./run.sh
```

常用地址：

```text
产品首页：http://127.0.0.1:8711/ui/index.html
实时守护：http://127.0.0.1:8711/ui/monitor.html
告警列表：http://127.0.0.1:8711/ui/events.html
管理台：http://127.0.0.1:8711/admin/index.html
接口文档：http://127.0.0.1:8711/docs
健康检查：http://127.0.0.1:8711/health
```

测试当前局域网摄像头：

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/3/test
```

抓一帧：

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/3/capture
```

查看事件：

```bash
curl 'http://127.0.0.1:8711/api/events?limit=10'
```

## 3. 当前服务状态

截至本次记录：

- `edge-agent` 当前运行在本机 `8711`。
- 当前局域网访问地址为 `http://192.168.1.4:8711`。
- 当前默认本地验证端口为 `8711`。
- `8710` 不再作为当前默认服务端口。
- 摄像头优先使用局域网 RTSP 摄像头 `192.168.1.11:554`。
- 本机摄像头 `local:0` 因 macOS 权限问题已禁用，不作为当前主线路。
- YOLO 模式使用 `GOHOME_DETECTOR_BACKEND=yolo`。
- 当前运行设备是 M4 / 24GB Mac，作为第一阶段本地算力服务。

## 4. 已完成进度

### 4.1 工程结构

已新增独立目录：

```text
gohome/
  edge-agent/
    app/
    admin/
    data/
    logs/
    run.sh
    README.md
    requirements.txt
    requirements-yolo.txt
```

说明：

- `edge-agent` 与产品 Web 前端独立。
- `edge-agent` 同时提供 API、管理台、产品 Web 静态挂载和截图文件服务。
- 产品 Web 通过 `/ui` 访问。
- 管理台通过 `/admin` 访问。

### 4.2 API 服务

已完成：

- FastAPI 应用
- CORS
- `/health`
- `/api/device`
- `/docs`
- `/snapshots`
- `/admin`
- `/ui`

### 4.3 数据库

已完成 SQLite 表：

- `cameras`
- `snapshots`
- `events`
- `rules`

已支持：

- 摄像头创建和列表
- 截图记录
- 事件记录
- 事件处理状态
- 规则读取和保存
- 今日摘要

### 4.4 摄像头接入

已完成：

- 局域网 RTSP 摄像头 `192.168.1.11:554`
- 摄像头拉流测试
- 手动抓帧
- 自动抽帧
- 摄像头在线状态更新
- 摄像头失败时记录错误
- 管理台支持通过 IP、端口、账号、密码和路径配置局域网摄像头
- 保存后自动测试首帧

已修复：

- 本机摄像头刚打开时画面偏黑的问题：抓帧前增加预热。
- 低光截图显示偏暗的问题：预览保存时做了低光增强，检测指标仍保留原始帧。
- 旧本机摄像头记录已禁用，避免继续干扰主流程。

### 4.5 检测逻辑

已完成 `basic` 检测：

- 亮度
- 对比度
- 黑屏 / 遮挡
- 画面变化分数
- 长时间无画面变化候选

已完成 YOLO 可选检测：

- `person_count`
- `person_detected`
- `no_person_detected`
- YOLO 人框 `bbox`
- 置信度 `confidence`
- 长时间无人候选事件
- 疑似跌倒候选启发式
- 检测结果随截图保存到 `analysis_json`

限制：

- 疑似跌倒当前只是基于人框比例的候选判断，不是稳定跌倒模型。
- 当前样本未检测到人时不会显示人框；需要有人进入画面后再验证框选效果。

### 4.6 事件和通知

已完成：

- `camera_offline`
- `black_screen`
- `no_motion`
- `no_person`
- `fall_candidate`
- 事件节流，避免短时间重复刷屏
- `PATCH /api/events/{id}` 标记已处理或误报
- `DELETE /api/events?scope=acknowledged` 清理已处理事件
- `POST /api/notify/test` 测试通知接口

待完成：

- 选择并配置真实手机通知通道
- 验证真实异常推送到手机

### 4.7 管理台

已完成 `/admin/index.html`：

- 设备信息
- API 地址
- detector backend
- 通知通道状态
- 本机摄像头模式（仅开发调试，不作为当前主线路）
- 添加摄像头
- 摄像头列表
- 测试拉流
- 手动抓帧
- 自动刷新预览
- 截图亮度、运动分数、人形数量、标签
- 规则配置
- 事件列表
- 标记已处理
- 标记误报
- 清理已处理事件
- 测试通知
- 局域网摄像头配置向导：填写 IP、端口、账号、密码、路径后自动生成 RTSP 地址
- 保存摄像头后自动测试首帧
- 摄像头启用 / 禁用
- 摄像头删除
- 最新截图检测摘要
- YOLO 人框叠加
- 规则项按产品能力展示已实现 / 待实现状态

待完成：

- 摄像头编辑
- 清理全部开发事件
- 模型版本号展示
- 规则命中原因结构化展示

### 4.8 产品 Web 接入

已完成真实接口接入：

- `assets/scripts/edge-client.js`
- `assets/scripts/home-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/events-live.js`
- `assets/scripts/event-detail-live.js`

已接入页面：

- `index.html`
- `monitor.html`
- `events.html`
- `event_detail.html`

待接入页面：

- `connect.html`
- `rules.html`

## 5. 当前 API 速查

基础：

- `GET /health`
- `GET /api/device`

摄像头：

- `GET /api/cameras`
- `POST /api/cameras`
- `GET /api/cameras/{camera_id}`
- `PATCH /api/cameras/{camera_id}`
- `DELETE /api/cameras/{camera_id}`
- `POST /api/cameras/{camera_id}/test`
- `POST /api/cameras/{camera_id}/capture`
- `GET /api/cameras/{camera_id}/snapshot/latest`

事件：

- `GET /api/events`
- `GET /api/events/{event_id}`
- `PATCH /api/events/{event_id}`
- `DELETE /api/events?scope=acknowledged`

规则和摘要：

- `GET /api/summary/today`
- `GET /api/rules`
- `PUT /api/rules`

通知：

- `POST /api/notify/test`

## 6. 已知问题

- 历史数据库里可能还有之前 `basic` 模式生成的黑屏旧事件，会影响本地验证观感。
- 当前真实验证已切到局域网 RTSP 摄像头 `192.168.1.11`，本机摄像头因 macOS 权限问题暂时不作为主线路。
- YOLO 已能做人形数量，并已在 edge-agent 管理台展示检测摘要和检测框；当前样本未检测到人时不会显示框。
- 通知接口已存在，但还没有绑定真实 Bark / 飞书 / Telegram 配置。
- 当前还没有云端，所以手机 App 暂时不能远程访问老人家局域网设备。
- iOS 原生 App 暂不进入第一阶段开发。

## 6.1 与商业化目标的差距

当前阶段只完成了本机边缘验证的局部能力，距离商业化产品还有这些差距：

- 没有云端用户、家庭、设备和事件平台。
- 没有设备注册、设备密钥、设备绑定和心跳通道。
- 没有 App 推送、短信、电话等正式通知链路。
- 没有用户端 App，只是 Web 原型局部接入。
- 没有运营后台和售后诊断体系。
- 没有 API v1 版本规范、权限、审计、限流和幂等。
- 没有 `DetectionResult`、`RuleEvaluation`、`EventCandidate` 等产品级数据层。
- 还没有完整模型版本、模型灰度和误报反馈闭环。
- 没有边缘硬件的开机自启、watchdog、断网补传、日志轮转和远程升级。
- 没有 RTSP 摄像头兼容清单和安装 SOP。

## 6.2 当前验收判断

截至 `2026-06-28`，当前状态判断如下：

### 已经基本跑通

- 本机 `edge-agent` 可以启动并提供 API、管理台和用户端页面。
- 局域网 RTSP 摄像头已经接入，并可完成测试抓帧。
- YOLO 模式已经可以输出人数、人框和候选标签。
- 首页、守护页、事件页已经能读取本机真实数据。
- 管理台已经可以看到摄像头、截图、事件和规则的主要信息。

### 已经部分跑通，但还不能算完成

- `connect.html` 已经接入真实 API，但还缺少面向正式安装流程的完成定义与验收记录。
- `rules.html` 已经接入真实 API，但还缺少“规则命中原因”和“保存后可解释验证”的闭环。
- 通知接口已经存在，但真实手机通知链路还没有完成最终配置和送达验收。
- 检测结果已经写入 `analysis_json`，但还没有拆成 `DetectionResult / RuleEvaluation / EventCandidate / Event` 正式数据层。

### 还没有开始或还不算产品化完成

- 设备身份、设备密钥、设备绑定码。
- 云端 `api/v1`、心跳、事件上报、媒体上传。
- H5/App 家属端登录和家庭空间。
- Mac 开机自启、watchdog、日志轮转、状态诊断页。
- 树莓派或边缘盒 7 天稳定性试点。

结论：

- 当前项目仍处于“阶段 0 本机验证进行中”。
- 尚未达到“阶段 0 完成，可进入阶段 1”的状态。
- 接下来的工作必须围绕“把阶段 0 的剩余闭环补齐”推进。

## 7. App 后续怎么接入

阶段 0 本地验证时，Web 直接请求本机 `edge-agent`：

```text
Web 页面
-> http://127.0.0.1:8711/api/...
-> edge-agent
-> 局域网 RTSP 摄像头
```

后续 App 正式形态应改为：

```text
iOS / Android App
-> 云端 API
-> 云端设备通道
-> 老人家 edge-agent
-> 老人家局域网摄像头
```

原因：

- App 通常不在老人家局域网内，不能直接访问摄像头。
- 摄像头 RTSP 不应该暴露到公网。
- edge-agent 应主动连接云端，避免公网 IP 和端口映射问题。

第一版 App 只需要复用这些能力：

- 设备绑定
- 摄像头列表
- 看护规则
- 告警列表
- 告警详情
- 最新截图或短视频片段
- 推送通知

## 8. 下一步记录

按优先级继续做：

1. 固化 Mac 本地算力服务运行方式：配置文件、日志目录、数据目录、端口和启动命令。
2. 完成 `connect.html` 的正式验收：添加摄像头、测试拉流、保存房间、切换启用状态、异常提示。
3. 完成 `rules.html` 的正式验收：读取规则、保存规则、验证下一轮 worker 生效。
4. 处理历史旧黑屏 / 本机摄像头离线事件，清理对当前产品状态的干扰。
5. 给 YOLO 人形结果补模型版本、规则命中原因和可追踪字段。
6. 把检测结果拆成 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 的结构。
7. 配置一个真实手机通知通道并做送达验收。
8. 增加 Mac 开机自启、watchdog、日志轮转和状态诊断接口。
9. 输出 Raspberry Pi 部署验证文档和脚本骨架。
10. 设计云端 `api/v1` 数据模型、设备上报接口和设备身份草案。

每完成一项，都在本文件追加记录。

## 8.1 记录规范

从现在开始，本文件新增记录必须包含以下 5 项：

- 做了什么。
- 产物在哪个文件或接口。
- 如何复现和验证。
- 当前结果是“通过 / 部分通过 / 未通过”。
- 还剩什么风险或下一步。

## 8.2 当前进行中任务

当前正在执行：

- 比赛演示版功能收口

本次任务要完成：

- 继续按 `Plan` 顺序收口比赛真正会演示的主链功能，而不是继续扩张页面或新方向。
- 把 `登录 -> 家庭 -> 绑定设备 -> 接入摄像头 -> 守护 -> 实时画面 -> 检测 -> 事件 -> 事件详情` 串成稳定的 App 演示链。
- 把当前主链页面、App 壳、iOS 壳入口和 `app=1` 路由上下文统一起来，减少跳转后掉回网页版或状态错乱的问题。
- 优先修 `rules`、`events`、`event_detail`、`watch`、`detection`、`app-shell` 这条链上的功能阻塞，再做最后的比赛演示验收。
- 同步把文档中的“当前任务”从 `.env / iOS 壳补齐` 切到“比赛演示版功能收口”，避免文档与真实进度脱节。

本次任务验收口径：

- 比赛演示主链中的关键页面必须都能在 `app=1` 模式下稳定跳转，不掉回网页版。
- `watch / detection / events / event_detail / privacy / app-shell / index / monitor` 这些主链页面要统一手机壳结构，刘海和底部安全区不再挡住关键操作。
- 新账号进入 App 后，未绑设备、未接摄像头、未建家庭这些状态不能再被误判成登录失败或无权限错误。
- `Plan` 和 `Implement` 已同步切换为当前真实任务。
- 最近编辑文件诊断必须保持为 `0`。

本次任务完成后回写：

- 修改的代码文件。
- 静态验证方式和后续真机验证方式。
- 验收结果是“通过 / 部分通过 / 未通过”。
- 剩余问题和下一个任务。

## 9. 2026-06-28 当前完成记录

- `edge-agent` 运行在 `8711`，当前本机服务地址为 `http://127.0.0.1:8711`，当前局域网服务地址为 `http://192.168.1.4:8711`。
- 已接入局域网摄像头 `192.168.1.11:554`，账号密码由摄像头配置保存，当前启用摄像头为 `id=3`，房间为“客厅”。
- 已禁用本机摄像头 `local:0`，避免 macOS 摄像头权限问题继续污染主流程。
- `snapshots` 表已新增 `width`、`height`、`analysis_json`，每次抓帧会保存 YOLO 检测结果、人数、人框、疑似跌倒候选、黑屏和运动信息。
- 管理台 `/admin/index.html` 已能展示真实截图、检测摘要、YOLO 人框叠加、规则开关和产品化检测项。
- 用户端 `/ui/monitor.html`、`/ui/events.html`、`/ui/index.html` 已接入本机 `edge-agent` 接口。
- 用户端事件列表和首页已过滤为当前启用摄像头事件，避免旧的本机摄像头测试告警影响产品状态。

## 9.1 当前阶段出口前还缺什么

要让阶段 0 真正结束，还差以下出口项：

- `connect.html` 的接入和异常流程完成验收。
- `rules.html` 的读取、保存和生效完成验收。
- 至少一个真实手机通知通道送达成功。
- Mac 开机自启、watchdog、日志轮转和状态页可复现。
- `DetectionResult / RuleEvaluation / EventCandidate / Event` 数据链完成第一版结构化。

这些完成前，不进入云端和 App 主开发。

## 9.1.1 2026-06-29 `.env` 收口和最小 iOS 原生壳补齐记录

做了什么：

- 新增 `edge-agent/app/env_loader.py`，独立负责 `.env / .env.local` 解析，支持 `export KEY=value`、单双引号和行尾注释。
- 调整 `edge-agent/app/settings.py`，在配置对象初始化前加载 `.env / .env.local`，并把已加载文件记录到 `env_files`。
- 调整 `edge-agent/run.sh`，启动 `uvicorn` 前先复用 `env_loader.py` 的解析结果导入 shell 环境，避免只在 Python 层生效。
- 新增 `edge-agent/.env.example`，并在仓库内落了正式 `edge-agent/.env` 作为当前配置入口。
- 调整 `edge-agent/README.md` 和根目录 `.gitignore`，把运行口径从手动 `export` 切到 `.env`。
- 新增最小 `ios-shell/` 工程骨架，包含 `project.yml`、`Info.plist`、`entitlements`、`GoHomeShellApp.swift`、`GoHomeShellRuntime.swift`、`GoHomeShellWebView.swift`。
- 直接提交最小 `GoHomeShell.xcodeproj`、workspace 和 shared scheme，避免当前环境下必须依赖 `xcodegen` 才能打开工程。
- 在 `apns_relay_service.py` 和 `edge_bootstrap_service.py` 中补 `env_files` 状态暴露，便于后续在线验收判断服务是否吃到 `.env`。

产物位置：

- `edge-agent/app/env_loader.py`
- `edge-agent/app/settings.py`
- `edge-agent/run.sh`
- `edge-agent/.env.example`
- `edge-agent/.env`
- `edge-agent/README.md`
- `.gitignore`
- `edge-agent/app/apns_relay_service.py`
- `edge-agent/app/edge_bootstrap_service.py`
- `ios-shell/project.yml`
- `ios-shell/GoHomeShell.xcodeproj/project.pbxproj`
- `ios-shell/GoHomeShell.xcodeproj/project.xcworkspace/contents.xcworkspacedata`
- `ios-shell/GoHomeShell.xcodeproj/xcshareddata/xcschemes/GoHomeShell.xcscheme`
- `ios-shell/GoHomeShell/Config/Info.plist`
- `ios-shell/GoHomeShell/Config/GoHomeShell.entitlements`
- `ios-shell/GoHomeShell/Sources/GoHomeShellApp.swift`
- `ios-shell/GoHomeShell/Sources/GoHomeShellRuntime.swift`
- `ios-shell/GoHomeShell/Sources/GoHomeShellWebView.swift`
- `ios-shell/README.md`

如何复现和验证：

- `python3 -m py_compile app/env_loader.py app/settings.py app/apns_relay_service.py app/edge_bootstrap_service.py`
- `bash -n run.sh`
- `xcrun --sdk iphonesimulator swiftc -typecheck GoHomeShell/Sources/*.swift`
- `xcodebuild -list -project GoHomeShell.xcodeproj`
- 额外跑一组 `.env` 解析断言，确认 `export KEY=value`、单双引号、空格值和行尾注释都能被正确解析。
- 服务启动后，通过本地浏览器会话临时注册验收账号、创建家庭并绑定当前设备，再调用 `GET /api/v1/runtime/app-push-relay` 和 `GET /api/v1/runtime/edge-service` 做在线验收。
- 真机阶段下一步使用 `xcodegen generate` 生成工程，配置签名后在 iPhone 上触发 `registerForRemoteNotifications()`，拿到真实 `APNs device token` 并上报 `/api/v1/app/push-tokens`。

当前结果：

- `部分通过`

说明：

- `.env` 收口、运行脚本接入、状态字段补齐和最小 iOS 原生壳代码均已落地，相关 Python / Bash / Swift 静态检查已通过。
- 当前仓库内已经有正式 `.env` 文件入口，后续不再依赖手工 `export` 作为主路径。
- 在线 `8711` 验收已通过：`/api/v1/runtime/app-push-relay` 和 `/api/v1/runtime/edge-service` 都返回了 `env_files=["/Users/tanyihua/trae比赛/gohome/edge-agent/.env"]`，说明在线进程已吃到正式 `.env`。
- 在线 `app-push-relay` 状态同时确认当前 `provider="apns"`、`configured=false`、`topic="com.gohome.family"`、`default_environment="sandbox"`，这与当前 `.env` 未填 APNs 凭证的状态一致。
- 已提交 `GoHomeShell.xcodeproj`，并通过 `xcodebuild -list -project GoHomeShell.xcodeproj` 确认工程能被本机 Xcode 工具链识别。
- 当前仍未完成真实 iPhone 的 APNs token 获取和系统通知送达，所以整轮结果保持 `部分通过`。
- 下一步直接进入 `xcodegen generate`、签名和真机运行，拿到真实 `APNs device token` 后再打通 `/api/v1/app/push-tokens` 和 `POST /api/v1/app/push-test`。

## 9.1.2 2026-06-29 比赛演示版功能收口记录

做了什么：

- 把比赛演示需要的主链页面继续压成一套统一的手机壳，重点收口了 `index.html`、`app-shell.html`、`monitor.html`、`watch.html`、`detection.html`、`events.html`、`event_detail.html`、`privacy.html`。
- 在 `ios-shell/GoHomeShell/Sources/GoHomeShellWebView.swift` 中把 `WKWebView` 的加载策略切到忽略本地缓存，并给关键页面的 `app.css` 加版本戳，避免 iPhone 持续吃旧页面。
- 修复了新账号进入 App 壳后，因“当前设备未绑定”被误判为登录失败或无权限的路径；当前未绑设备、未建家庭、未接摄像头时，页面会保留登录态并显示正确的下一步动作。
- 把 `events -> event_detail`、`monitor -> watch -> detection`、`index -> app-shell` 这些关键跳转统一补上 `app=1`，避免从 App 模式掉回网页版。
- 顺手补了 `rules.html`、`companionship.html` 以及纪念模式几个页面的 `app=1` 链接，减少比赛演示时误点后掉链子的风险。

本轮涉及的关键文件：

- `index.html`
- `app-shell.html`
- `monitor.html`
- `watch.html`
- `detection.html`
- `events.html`
- `event_detail.html`
- `privacy.html`
- `assets/styles/app.css`
- `assets/scripts/events-live.js`
- `assets/scripts/edge-client.js`
- `assets/scripts/app-shell-live.js`
- `ios-shell/GoHomeShell/Sources/GoHomeShellWebView.swift`

怎么验证：

- 对最近收口的主链页面和相关文档运行编辑器诊断，确保没有新增 HTML / JS / Swift 语法错误。
- 用本地浏览器和 App 壳路径重复检查主链页面的 `app=1` 跳转，重点确认 `watch / detection / events / event_detail / privacy` 不再轻易掉回网页版。
- 在真实 iPhone 上完成 App 壳安装、局域网地址接入和首轮画面打开，确认 `WKWebView` 已能承载比赛演示主链。

当前结果：

- `部分通过`

说明：

- 主链页面的 App 模式跳转、缓存策略、统一手机壳和比赛演示入口已经继续收口，页面侧最容易翻车的几条链已经压稳。
- 当前 iPhone 已经能安装 App 壳并打开局域网页面，手机侧白屏问题已通过把入口地址改成局域网地址和禁用缓存的方式解决。
- 当前仍然没有完成完整的比赛口径冒烟验收，因为用户这轮暂时无法继续在手机上逐页查看，所以这轮结果保持 `部分通过`。
- 接下来先按用户要求回到 `Plan` 的功能线：先收 `rules`、`events` 和演示路径相关功能闭环，再做完整比赛演示彩排。

## 9.1.3 2026-06-30 `rules` 保存后立即生效闭环记录

做了什么：

- 在 `edge-agent/app/worker.py` 里把 worker 的等待机制改成可被主动唤醒的 `_wake` 事件，不再只能傻等下一个 `capture_interval_seconds` 周期。
- 在 `edge-agent/app/main.py` 里新增 `persist_rules_update()`，把真正写规则的入口统一收口到一个地方，避免后续再出现“写库了但没通知 worker”的分叉逻辑。
- 把 `PUT /api/rules` 接上 `worker.request_rules_reload()`，让 `rules.html` 保存后会立即唤醒 worker 去读新规则。
- 把设备同步链路里真正落库规则的分支也接到同一套 `persist_rules_update()`，保证本机保存和远端同步两条规则写入路径行为一致。
- 清掉 `worker.py` 里已经失去调用方的旧 `mark_rules_reloaded()` 方法，避免继续堆无效状态更新。

产物位置：

- `edge-agent/app/worker.py`
- `edge-agent/app/main.py`

怎么验证：

- 对 `edge-agent/app/main.py` 和 `edge-agent/app/worker.py` 运行编辑器诊断，结果保持为 `0`。
- 运行 `python -m py_compile app/main.py app/worker.py`，确认这轮后端修改没有引入语法问题。
- 用最小假对象脚本直接启动 `EdgeWorker`，在 `updated_at` 从 `v1` 改到 `v2` 后调用 `request_rules_reload()`，确认 worker 会在等待周期内被提前唤醒并读到新规则，而不是继续等完整的 5 秒间隔。

当前结果：

- `通过`

说明：

- 代码层面的“规则写入后主动唤醒 worker”闭环已经补齐，最关键的延迟来源已经从“必须等下一个抓帧周期”收敛成“当前轮处理结束后立即进入下一轮”。
- 本轮静态检查已通过，后端两处真实规则写入入口现在都走同一条唤醒链，不会再出现一个入口生效、另一个入口不生效的分叉。
- 已在真实 `8711` 在线环境下做保存验收：对 `/api/rules` 执行一次同值 `PUT` 后，新 `updated_at` 为 `2026-06-30T07:13:33.709040+00:00`，`/api/rules/runtime` 在约 `508ms` 内把 `last_rules_loaded_at` 跟到了同一时间戳，说明即时唤醒链在线已生效。
- 当前这条闭环已经通过，后续只需要在继续推进规则功能时保持这条在线验收口径。

## 9.1.4 2026-06-30 `event_detail` 处理状态即时回流记录

做了什么：

- 调整 `assets/scripts/event-detail-live.js`，让“已确认安全 / 标记误报”按钮在成功调用 `appUpdateEvent()` 后立即用后端返回的最新事件数据重刷详情页状态，而不是只改一行提示文案。
- 在详情页里增加一个极小的 `sessionStorage` 同步层，把刚处理过的事件状态按 `event.id` 临时存起来，解决从详情页回到列表页时可能命中浏览器缓存、列表还显示旧状态的问题。
- 调整 `assets/scripts/events-live.js`，在拉取事件列表后先清掉已经被后端确认吸收的临时状态，再把尚未吸收到服务端返回里的本地状态补到列表渲染结果中。
- 给 `events-live.js` 增加 `pageshow` 和页面重新可见时的重刷，避免 iPhone / `WKWebView` 从详情页返回列表时继续拿到旧 DOM。

产物位置：

- `assets/scripts/event-detail-live.js`
- `assets/scripts/events-live.js`

怎么验证：

- 对 `assets/scripts/event-detail-live.js` 和 `assets/scripts/events-live.js` 运行编辑器诊断，结果保持为 `0`。
- 手工检查详情页按钮逻辑：点击“已确认安全”或“标记误报”后，详情页状态文案会立即变成最终状态，两个按钮也会同步锁定，避免重复提交。
- 手工检查列表页回流逻辑：从 `events.html` 进入 `event_detail.html` 完成处理后返回列表页，不需要再等 12 秒轮询，也能立刻看到卡片状态从“待确认”变成“已处理”。

当前结果：

- `通过`

说明：

- 这一轮已经把“详情页处理动作能立即反馈到详情页自己”和“返回列表页后不再看到明显旧状态”两个最容易影响演示观感的问题补上了。
- 已在真实 `8711` 在线环境下跑通了一条完整链：新注册账号 -> 创建家庭 -> 绑定当前设备 -> 拉取 `/api/app/events` -> 对事件 `id=794` 执行 `PATCH /api/app/events/{id}` -> 回读详情确认 `acknowledged=true`、`resolution=handled`。
- 随后通过真实页面验收确认：`event_detail.html?eventId=794&app=1` 点击“已确认安全”后，详情页状态立即变成“已确认安全”，两个操作按钮同步锁定；再返回 `events.html?app=1` 后，对应卡片已经直接显示“已处理”，不需要再等 12 秒轮询。
- 当前这条事件处理回流闭环已经通过，下一步继续沿着 `Plan` 主线看还有没有需要补的事件筛选态、归档态或演示路径断点。

## 9.1.5 2026-06-30 `family -> device_binding -> connect` 上下文收口记录

做了什么：

- 调整 `assets/scripts/family-live.js`，给家庭页上的几个“绑定设备”入口统一补上当前首个家庭的 `family_id`，避免用户从家庭页继续往下走时丢掉当前家庭上下文。
- 调整 `assets/scripts/device-binding-live.js`，让绑定成功后跳转 `connect.html` 时把当前选中的 `family_id` 一起带过去，而不是只保留 `app=1`。
- 调整 `connect.html` 和 `assets/scripts/connect-live.js`，让接入页顶部返回键能够把 `family_id` 原样带回 `device_binding.html`，避免回退后掉回默认家庭或空选状态。
- 给 `family.html`、`device_binding.html`、`connect.html` 上这轮改动涉及的脚本入口补版本戳，避免浏览器继续吃旧缓存导致新逻辑看起来没生效。

产物位置：

- `family.html`
- `device_binding.html`
- `connect.html`
- `assets/scripts/family-live.js`
- `assets/scripts/device-binding-live.js`
- `assets/scripts/connect-live.js`

怎么验证：

- 对上述 6 个文件运行编辑器诊断，结果保持为 `0`。
- 用真实页面跑新账号主链：注册新账号 -> `family.html?app=1` 创建家庭 -> 自动进入 `device_binding.html?family_id=...&app=1` -> 绑定当前设备 -> 自动进入 `connect.html?family_id=...&app=1`。
- 在接入页读取顶部返回链接，确认它现在回到 `device_binding.html?family_id=...&app=1`，而不是丢掉当前家庭上下文。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：新创建家庭后，页面会进入 `device_binding.html?family_id=37&app=1`；绑定当前设备后，会进入 `connect.html?family_id=37&app=1`；接入页顶部返回链接也已经变成 `device_binding.html?family_id=37&app=1`。
- 这条修复不扩张业务逻辑，只是把比赛演示主链里的家庭上下文保住，避免多家庭或回退重走时页面状态突然错位。
- 下一步继续沿着主链往下看 `connect -> monitor/watch` 还有没有需要补的演示断点。

## 9.1.6 2026-06-30 `connect -> monitor/watch` 下一步出口收口记录

做了什么：

- 在 `connect.html` 的预览区后面补了一个极小的“下一步”区块，只保留两个动作：`守护` 和 `实时`。
- 调整 `assets/scripts/connect-live.js`，让这个区块只在已经存在可用网络摄像头时显示；没有摄像头时保持隐藏，不制造假动作。
- 在 `connect-live.js` 里给这两个入口统一走 `GoHomeEdge.pageHref()`，保证继续留在 `app=1` 模式，不会从 App 壳掉回普通网页。
- 把 `connect-live.js` 的版本戳抬到 `20260630-flow2`，避免手机继续吃旧缓存导致看不到新的下一步出口。

产物位置：

- `connect.html`
- `assets/scripts/connect-live.js`

怎么验证：

- 对 `connect.html` 和 `assets/scripts/connect-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `connect.html?app=1`，当页面已有 1 路可用摄像头时，确认“下一步”区块显示为 `可继续`，并给出 `monitor.html?app=1` 和 `watch.html?app=1` 两个入口。
- 真实点击 `守护` 按钮，确认页面会进入 `monitor.html?app=1`，并继续显示真实守护摘要而不是空白或错误页。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`connect.html?app=1` 现在会显示“下一步”区块，状态为 `可继续`，并给出 `monitor.html?app=1`、`watch.html?app=1` 两个入口。
- 真实点击 `守护` 后，页面已成功进入 `monitor.html?app=1`，并显示“当前画面暂未检测到人，持续观察中”这类真实守护结论，不再停留在“接入成功但下一步不明确”的断点。
- 这条修复只补比赛演示主链的出口，不改摄像头测试、保存、启停和删除原有逻辑。

## 9.1.7 2026-06-30 `watch -> detection -> event_detail -> watch` 摄像头上下文保活记录

做了什么：

- 在 `watch.html`、`detection.html`、`event_detail.html` 补了用于动态改写跳转地址的 DOM 锚点，避免把 `camera_id` 写死在静态链接里。
- 调整 `assets/scripts/watch-live.js`，支持从 query 读取当前 `camera_id`，并在用户切换摄像头后用 `history.replaceState()` 持续同步地址栏。
- 调整 `assets/scripts/detection-live.js`，让检测页也能读取并保留当前 `camera_id`，返回实时页时继续回到同一路摄像头。
- 调整 `assets/scripts/event-detail-live.js`，让详情页右上角“实时”入口优先回到当前事件所属的 `camera_id`，避免多路演示时跳错画面。
- 把 `watch-live.js`、`detection-live.js`、`event-detail-live.js` 的版本戳统一抬到 `20260630-flow3`，避免手机继续命中旧缓存。

产物位置：

- `watch.html`
- `detection.html`
- `event_detail.html`
- `assets/scripts/watch-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/event-detail-live.js`

怎么验证：

- 对上述 6 个文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `watch.html?app=1`，切到指定摄像头后确认地址栏会自动保留 `camera_id=...`，且“检测细节”入口会带同一个 `camera_id`。
- 真实点击进入 `detection.html?camera_id=...&app=1`，确认顶部返回链接会回到 `watch.html?camera_id=...&app=1`，不会退回默认摄像头。
- 在真实 `event_detail.html?eventId=...&app=1` 页面检查右上角“实时”入口，确认它会跳到 `watch.html?camera_id=事件所属摄像头&app=1`。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`watch.html?app=1&cb=flow5` 会自动保留 `camera_id=9`，顶部“检测细节”入口已变成 `detection.html?camera_id=9&app=1`。
- 真实进入 `detection.html?camera_id=9&app=1` 后，顶部返回链接已变成 `watch.html?camera_id=9&app=1`，说明 `watch -> detection -> watch` 这段上下文不再丢失。
- 真实打开 `event_detail.html?eventId=794&app=1&cb=flow5` 后，右上角“实时”入口已变成 `watch.html?camera_id=9&app=1`，说明从事件详情回实时也能回到对应摄像头。
- 这条修复只补比赛演示主链里的摄像头上下文，不改实时流、检测摘要和事件处理逻辑本身。

## 9.1.8 2026-06-30 `watch/detection -> events -> event_detail -> events/watch` 摄像头上下文续接记录

做了什么：

- 在 `events.html` 补了动态链接锚点，让时间线页里的“先看实时画面”和顶部返回入口可以由脚本按当前 `camera_id` 改写。
- 调整 `assets/scripts/events-live.js`，让事件页支持读取并保留 `camera_id`，并把详情页入口统一改成 `event_detail.html?eventId=...&camera_id=...`。
- 调整 `assets/scripts/watch-live.js` 和 `assets/scripts/detection-live.js`，让它们跳去 `events.html` 时也继续带上当前摄像头的 `camera_id`。
- 调整 `assets/scripts/event-detail-live.js`，让详情页返回 `events.html` 时优先保留来源页的 `camera_id`，而“去实时”继续回到对应事件摄像头。
- 把 `events-live.js`、`watch-live.js`、`detection-live.js`、`event-detail-live.js` 对应页面的版本戳统一抬到 `20260630-flow4`，避免手机继续吃旧缓存。

产物位置：

- `events.html`
- `watch.html`
- `detection.html`
- `event_detail.html`
- `assets/scripts/events-live.js`
- `assets/scripts/watch-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/event-detail-live.js`

怎么验证：

- 对上述 8 个文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `watch.html?app=1`，确认“事件”入口变成 `events.html?camera_id=...&app=1`。
- 真实进入 `events.html?camera_id=...&app=1`，确认“先看实时画面”入口会回到 `watch.html?camera_id=...&app=1`，且列表中的事件详情链接会带同一个 `camera_id`。
- 真实进入 `event_detail.html?eventId=...&camera_id=...&app=1`，确认顶部返回链接回到 `events.html?camera_id=...&app=1`，右上角“实时”入口回到 `watch.html?camera_id=事件所属摄像头&app=1`。
- 真实进入 `detection.html?camera_id=...&app=1`，确认主按钮、次按钮和底部导航里的“事件”入口都会带相同的 `camera_id`。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`watch.html?app=1&cb=flow7` 当前会自动保留 `camera_id=9`，并把“事件”入口改成 `events.html?camera_id=9&app=1`。
- 真实进入 `events.html?camera_id=9&app=1` 后，“先看实时画面”入口已变成 `watch.html?camera_id=9&app=1`，首条详情链接已变成 `event_detail.html?eventId=805&camera_id=9&app=1`。
- 真实进入 `event_detail.html?eventId=805&camera_id=9&app=1` 后，顶部返回链接已变成 `events.html?camera_id=9&app=1`，右上角“实时”入口已变成 `watch.html?camera_id=9&app=1`。
- 真实进入 `detection.html?camera_id=9&app=1&cb=flow7` 后，主按钮、次按钮和底部导航里的“事件”入口都已变成 `events.html?camera_id=9&app=1`。
- 这条修复只补比赛演示主链里的 `events` 上下文续接，不新增事件筛选、归档或多条件浏览逻辑。

## 9.1.9 2026-06-30 比赛演示固定冒烟顺序记录

做了什么：

- 按 `Plan` 要求，基于当前真实 `8711` 在线链路，把“已登录、已绑设备、已有摄像头”的比赛演示主路径整理成一条固定顺序，不再临场随机点页面。
- 用真实页面从 `app-shell.html?app=1` 开始重新串跑 `watch -> detection -> events -> event_detail -> watch` 主展示链，确认页面状态、标题文案和关键跳转都稳定。
- 顺手补查 `monitor.html?app=1`，确认“守护概览”仍可作为演示中的说明页插入，不会掉出 App 模式，也不会跳到空白页。
- 把这条顺序沉淀为当前推荐口径：`App 壳入口 -> 实时观看 -> 检测细节 -> 事件时间线 -> 事件详情 -> 回到实时观看`；`守护概览` 作为可选插入页，用于讲“结论层”。

产物位置：

- `想家了吗-Plan.md`
- `想家了吗-Implement.md`
- `app-shell.html`
- `watch.html`
- `detection.html`
- `events.html`
- `event_detail.html`
- `monitor.html`

怎么验证：

- 在真实 `8711` 在线页面环境下打开 `app-shell.html?app=1`，确认主按钮为“进入实时观看”，并能直接进入 `watch.html?app=1`。
- 从 `watch.html?camera_id=...&app=1` 点击顶部“检测细节”，确认进入 `detection.html?camera_id=...&app=1`。
- 从 `detection.html?camera_id=...&app=1` 点击“去看事件”，确认进入 `events.html?camera_id=...&app=1`，首条详情链接为 `event_detail.html?eventId=...&camera_id=...&app=1`。
- 从 `event_detail.html?eventId=...&camera_id=...&app=1` 点击右上角“实时”，确认回到 `watch.html?camera_id=...&app=1`。
- 从 `watch.html?camera_id=...&app=1` 点击“守护概览”，确认能正常进入 `monitor.html?app=1`，展示真实守护摘要。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`app-shell.html?app=1&cb=smoke2` 当前主按钮是“进入实时观看”，会直接进入 `watch.html?app=1&camera_id=9`。
- 真实进入 `watch.html?app=1&camera_id=9` 后，顶部“检测细节”和“事件”入口分别为 `detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`，适合作为比赛主讲入口。
- 真实进入 `detection.html?camera_id=9&app=1` 后，主按钮“去看事件”为 `events.html?camera_id=9&app=1`；再进入 `events.html?camera_id=9&app=1` 后，首条详情链接为 `event_detail.html?eventId=807&camera_id=9&app=1`。
- 真实进入 `event_detail.html?eventId=807&camera_id=9&app=1` 后，顶部返回链接和右上角“实时”入口都能保住 `camera_id=9`，最终回到 `watch.html?camera_id=9&app=1`。
- 真实进入 `monitor.html?app=1` 后，页面会显示“当前画面暂未检测到人，持续观察中”这类真实守护结论，因此它适合在演示中作为“先讲结论”的可选插页，但当前最稳主顺序仍建议从 `watch` 开始。

## 9.1.10 2026-06-30 `event_detail` 规则解释直出记录

做了什么：

- 不再只在详情页展示泛化文案，而是直接消费事件接口里已经返回的 `payload.rule.reason`、`payload.rule.observed`、`payload.rule.threshold` 和 `payload.evaluation.state`。
- 调整 `assets/scripts/event-detail-live.js`，让详情页的“持续时间”“提示标签”“事实”“事实补充”改为展示真实规则解释，而不是只显示一段固定说明。
- 把秒级观测值转成人能直接读懂的时长文案，并把 `still / not_visible / offline` 这类评估状态翻成中文，减少演示时还要靠口头解释。
- 把 `event-detail-live.js` 版本戳抬到 `20260630-flow5`，避免手机继续命中旧缓存。

产物位置：

- `event_detail.html`
- `assets/scripts/event-detail-live.js`

怎么验证：

- 对 `event_detail.html` 和 `assets/scripts/event-detail-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `event_detail.html?eventId=...&camera_id=...&app=1`，确认详情页会直接显示规则原因、当前观测值、规则阈值和评估状态。
- 重点确认“长时间无人”这类事件不再只显示固定说明，而是能读到类似“当前观测：连续无人 16 小时；规则阈值：连续无人 5 分”的解释。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`event_detail.html?eventId=807&camera_id=9&app=1&cb=flow9` 当前会显示规则原因“连续未检测到人形的时长超过配置阈值。”。
- 页面同时会显示真实解释链：`当前观测：连续无人 16 小时。规则阈值：连续无人 5 分。评估状态：画面状态 静止，人物状态 未检测到人，静止时长 16 小时，连续无人 16 小时。`
- 这条修复不改事件列表和检测页逻辑，只把接口里已经存在的可解释字段真正接到用户端详情页，便于比赛时直接讲“为什么会触发这条提醒”。

## 9.1.11 2026-06-30 `events` 列表轻量解释记录

做了什么：

- 不再让事件列表卡片只显示“适合现在看一眼”这类泛提示，而是直接消费事件接口里已有的 `payload.rule.observed` 和 `payload.rule.threshold`。
- 调整 `assets/scripts/events-live.js`，把事件卡片底部说明改成轻量解释文案，优先展示“当前观测 + 规则阈值”，保留列表页轻量、详情页重解释的层次。
- 把秒级观测值转成人能直接读懂的时长文案，保证列表页一眼就能看出“为什么这条会进时间线”。
- 把 `events-live.js` 版本戳抬到 `20260630-flow5`，避免手机继续命中旧缓存。

产物位置：

- `events.html`
- `assets/scripts/events-live.js`

怎么验证：

- 对 `events.html` 和 `assets/scripts/events-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `events.html?camera_id=...&app=1`，确认首条事件卡片底部不再是泛提示，而是类似“连续无人 15 分，阈值 连续无人 5 分。”的轻量解释。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`events.html?camera_id=9&app=1&cb=flow11` 首条事件卡片当前显示 `连续无人 15 分，阈值 连续无人 5 分。`
- 这样列表页负责“快速解释”，详情页负责“完整解释”，当前用户端事件链已经能从列表到详情连续讲清楚为什么会触发提醒。

## 9.1.12 2026-06-30 `detection` 规则解释对齐记录

做了什么：

- 不再让检测页的“规则判断”只显示候选事件摘要，而是直接消费评估接口里已有的 `matched_rules / explanation / observed / threshold`。
- 调整 `assets/scripts/detection-live.js`，让 `detectionRuleSummary` 优先展示“规则原因 + 当前观测 + 规则阈值”，和列表页、详情页的解释口径保持一致。
- 继续沿用轻量时长格式，把 `no_person_seconds / no_motion_seconds` 这类秒值在检测页也转成人能直接读懂的分钟/小时文案。
- 把 `detection-live.js` 版本戳抬到 `20260630-flow5`，避免手机继续命中旧缓存。

产物位置：

- `detection.html`
- `assets/scripts/detection-live.js`

怎么验证：

- 对 `detection.html` 和 `assets/scripts/detection-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `detection.html?camera_id=...&app=1`，确认“规则判断”区域不再只显示事件摘要，而是类似“连续未检测到人形的时长超过配置阈值。当前观测：连续无人 20 分。规则阈值：连续无人 5 分。”。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 在线页面环境下验通：`detection.html?camera_id=9&app=1&cb=flow13` 当前会显示 `连续未检测到人形的时长超过配置阈值。 当前观测：连续无人 20分 规则阈值：连续无人 5分`。
- 当前检测页、事件列表页、事件详情页已经形成一致口径：检测页讲“规则为什么命中”，列表页讲“快速解释”，详情页讲“完整解释链”。

## 9.1.13 2026-06-30 `monitor` 摄像头上下文续接记录

做了什么：

- 调整 `monitor.html`，给进入 `watch`、`detection`、`events` 的关键入口补上动态锚点，避免首页守护页固定写死到无上下文链接。
- 调整 `assets/scripts/monitor-live.js`，让守护页像 `watch / detection` 一样优先读取 URL 里的 `camera_id`，并把当前选中的摄像头继续写回地址栏。
- 让守护页所有跳转都显式续上当前 `camera_id` 和 `app=1`，保证 `monitor -> watch / detection / events` 不再掉链。
- 将守护页实时画面切到 `createManagedVideoStream()`，和 `watch` 页使用同一套视频流重连与刷新策略，减少守护页与实时页的接入分叉。
- 把 `monitor-live.js` 版本戳抬到 `20260630-flow6`，避免手机继续命中旧缓存。

产物位置：

- `monitor.html`
- `assets/scripts/monitor-live.js`

怎么验证：

- 对 `monitor.html` 和 `assets/scripts/monitor-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `monitor.html?app=1&camera_id=9`，确认守护页自身会保留 `camera_id=9`。
- 检查守护页进入 `watch / detection / events` 的链接，均应分别变成 `watch.html?camera_id=9&app=1`、`detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`monitor.html?app=1&camera_id=9&cb=monitorflow6` 当前可正常显示 `客厅` 与最新更新时间，说明守护页已吃到指定摄像头上下文。
- 同页在线读取到的关键跳转已全部续上摄像头参数：顶部去实时、画面卡片去实时、去检测、去事件分别为 `watch.html?camera_id=9&app=1`、`watch.html?camera_id=9&app=1`、`detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`。
- 这样当前用户端实时主链已经从 `monitor -> watch -> detection -> events -> event_detail` 统一保持 `camera_id`，演示时不再出现“守护页进去后跳到别的摄像头”的断点。

## 9.1.14 2026-06-30 `detection` 实时流入口对齐记录

做了什么：

- 移除 `assets/scripts/detection-live.js` 里单独手写的 `v1VideoStreamPlaybackUrl()` 挂流逻辑，改为复用 `GoHomeEdge.createManagedVideoStream()`。
- 让检测页实时画面和 `watch / monitor` 使用同一套播放票据刷新、失败重连、页面可见性恢复策略，避免三页各自维护一套流入口。
- 保留原有检测截图、规则解释、检测框叠加逻辑不变，只收实时流接入这一层。
- 为检测页补上 `beforeunload -> dispose()`，避免离页后继续保留旧的流定时器。
- 把 `detection-live.js` 和 `detection.html` 版本戳抬到 `20260630-flow6`，避免手机继续命中旧缓存。

产物位置：

- `detection.html`
- `assets/scripts/detection-live.js`

怎么验证：

- 对 `detection.html` 和 `assets/scripts/detection-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `detection.html?app=1&camera_id=9`，确认 `detectionSnapshotImage` 当前直接加载 `/api/v1/video/cameras/9/stream.mjpg?profile=detail...`。
- 页面应继续显示实时画面、规则判断和检测时间，且空态层保持隐藏，不因流入口切换而退回灰图。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`detection.html?app=1&camera_id=9&cb=flow14` 当前会正常显示 `客厅`、`19:41 更新`、规则解释文案以及 `profile=detail` 的实时流地址。
- 在线读取到的 `detectionSnapshotImage.src` 已变成 `/api/v1/video/cameras/9/stream.mjpg?profile=detail&playback_ticket=...`，说明检测页已切到与 `watch / monitor` 同一套视频流入口，而不是继续走旧的单页直挂逻辑。
- 这样当前 `watch / monitor / detection` 三页实时画面入口已经统一到同一个流管理器，后续如果再调刷新周期或重连策略，只需要继续收敛 `edge-client.js` 这一处。

## 9.1.15 2026-06-30 视频流共享预设收口记录

做了什么：

- 在 `assets/scripts/edge-client.js` 增加共享视频流预设，让 `createManagedVideoStream()` 可以按 `scene` 自动推导 `profile / refreshMs / retryMs`。
- 约定当前三种场景：`watch` 默认走 `mobile/monitor` 自适应，`monitor` 固定走 `monitor`，`detection` 固定走 `detail`。
- 调整 `watch-live.js`、`monitor-live.js`、`detection-live.js`，三页不再各自手写实时流默认策略，而是统一改成传 `scene` 给共享层。
- 同步抬高 `watch.html`、`monitor.html`、`detection.html` 的 `edge-client.js` 版本戳到 `20260630-video1`，并把对应页面脚本版本戳抬到 `flow7`，避免继续命中旧缓存。

产物位置：

- `assets/scripts/edge-client.js`
- `assets/scripts/watch-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/detection-live.js`
- `watch.html`
- `monitor.html`
- `detection.html`

怎么验证：

- 对上述文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `watch.html?app=1&camera_id=9`、`monitor.html?app=1&camera_id=9`、`detection.html?app=1&camera_id=9`。
- 在线读取三页当前图像地址，确认分别命中 `profile=mobile`、`profile=monitor`、`profile=detail`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`watch` 当前加载 `/api/v1/video/cameras/9/stream.mjpg?profile=mobile...`，`monitor` 当前加载 `/api/v1/video/cameras/9/stream.mjpg?profile=monitor...`，`detection` 当前加载 `/api/v1/video/cameras/9/stream.mjpg?profile=detail...`。
- 这样当前实时观看、守护概览、检测细节三页已经共享同一套流策略入口，后续如果还要调刷新周期、重连策略或新增页面场景，只需要继续收口 `edge-client.js` 这一层，不必再逐页分散修改。

## 9.1.16 2026-06-30 `edge-client` 缓存一致性收口记录

做了什么：

- 把主链和关键入口页里仍然引用旧版 `edge-client.js` 的版本戳统一抬到 `20260630-video1`。
- 本轮覆盖页面包括：`login`、`index`、`app-shell`、`family`、`device_binding`、`connect`、`rules`、`events`、`event_detail`，再加上前面已经更新过的 `watch / monitor / detection`。
- 不改业务逻辑，只解决“共享层已经更新，但部分页面仍命中旧缓存”的一致性问题，避免演示时出现页面之间共享能力口径不一致。

产物位置：

- `login.html`
- `index.html`
- `app-shell.html`
- `family.html`
- `device_binding.html`
- `connect.html`
- `rules.html`
- `events.html`
- `event_detail.html`

怎么验证：

- 全局检查产品页 HTML 中的 `edge-client.js?v=`，应统一为 `20260630-video1`。
- 对本轮改动的 HTML 文件运行编辑器诊断，结果保持为 `0`。

当前结果：

- `通过`

说明：

- 当前产品端 12 个入口/主链页面已统一引用 `assets/scripts/edge-client.js?v=20260630-video1`，不会再出现实时流共享层已经更新，但部分页面继续使用旧版脚本的缓存分叉。
- 这样后续若继续在 `edge-client.js` 增加共享能力，只需抬同一条版本戳即可覆盖整条用户端主链，不必再按页面分别追缓存问题。

## 9.1.17 2026-06-30 `connect` 预览媒体入口对齐记录

做了什么：

- 调整 `assets/scripts/connect-live.js`，测试摄像头成功后不再手写 `GoHomeEdge.edgeUrl(snapshot.image_url)` 直出图片地址。
- 统一改成走 `GoHomeEdge.appMediaPlaybackUrl(snapshot.image_url)`，让接入页测试预览也复用用户端共享媒体鉴权入口。
- 把 `connect-live.js` 版本戳抬到 `20260630-flow3`，避免手机继续命中旧缓存。

产物位置：

- `connect.html`
- `assets/scripts/connect-live.js`

怎么验证：

- 对 `connect.html` 和 `assets/scripts/connect-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `connect.html?app=1`，点击已接入摄像头卡片里的“测试”按钮。
- 测试通过后，`connectionPreviewImage.src` 应变成 `/api/app/media/snapshots/...?...playback_ticket=...`，而不是裸 `snapshots` 或手写 `edgeUrl(...)` 地址。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`connect.html?app=1&cb=connectflow3` 点击现有 RTSP 摄像头“测试”后，预览图当前加载 `http://127.0.0.1:8711/api/app/media/snapshots/camera_9/...jpg?playback_ticket=...`。
- 这样接入页的测试预览也和事件详情、检测截图一样，统一走共享媒体播放入口；后续如果媒体鉴权或回放票据策略变化，不再需要单独回头修 `connect` 页。

## 9.1.18 2026-06-30 `app-shell` 原生唤起上下文保活记录

做了什么：

- 调整 `assets/scripts/app-shell-live.js` 里的原生唤起目标解析逻辑。
- 修正摄像头唤起时错误使用 `cameraId` 的问题，统一改成主链约定的 `camera_id`。
- 补齐事件详情原生唤起时的摄像头上下文，让 `event_detail.html?eventId=...` 同时带上 `camera_id`，避免从原生推送进来后在 `detail -> watch/events` 回链时丢上下文。
- 把 `app-shell-live.js` 版本戳抬到 `20260630-flow2`，确保真实页面吃到新逻辑。

产物位置：

- `assets/scripts/app-shell-live.js`
- `app-shell.html`

怎么验证：

- 对 `assets/scripts/app-shell-live.js` 和 `app-shell.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `app-shell.html?app=1`，确认当前实际加载脚本为 `assets/scripts/app-shell-live.js?v=20260630-flow2`。
- 在线读取该脚本文本，确认已包含 `watch.html?camera_id=` 与事件详情追加 `&camera_id=` 的新逻辑。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`app-shell.html?app=1&cb=appshell2` 当前实际加载 `http://127.0.0.1:8711/ui/assets/scripts/app-shell-live.js?v=20260630-flow2`，并且线上脚本内容已经包含 `watch.html?camera_id=` 和事件详情附带 `camera_id` 的逻辑。
- 这样原生壳从推送或启动参数直达 `watch / event_detail` 时，也能继续承接用户端已经统一好的 `camera_id` 上下文链，不会再因为参数名不一致而掉回默认视图。

## 9.1.19 2026-06-30 首页入口摄像头上下文续接记录

做了什么：

- 在 `index.html` 给首页“演示主链”三张入口卡片补上动态锚点：`edgeHomeMonitorLink`、`edgeHomeWatchLink`、`edgeHomeEventsLink`。
- 调整 `assets/scripts/home-live.js`，让首页在算出当前优选摄像头后，统一把主按钮和三张入口卡片改成带 `camera_id` 的目标地址。
- 同时把 `setAction()` 收到共享导航口径，统一通过 `GoHomeEdge.pageHref()` 生成页面跳转地址，避免首页按钮继续手写静态链接。
- 把 `home-live.js` 版本戳抬到 `20260630-flow2`，确保真实页面命中新逻辑。

产物位置：

- `index.html`
- `assets/scripts/home-live.js`

怎么验证：

- 对 `index.html` 和 `assets/scripts/home-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `index.html?app=1`，确认首页当前主按钮和“演示主链”三张卡片都带同一个优选 `camera_id`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index.html?app=1&cb=homeflow2` 当前 `edgeHomePrimaryAction` 为 `watch.html?camera_id=9&app=1`，三张演示卡分别为 `monitor.html?camera_id=9&app=1`、`watch.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`。
- 这样首页作为比赛演示和用户日常入口时，不会再从第一跳就丢掉当前优选摄像头，上下文可以直接承接到 `monitor / watch / events` 主链。

## 9.1.20 2026-06-30 陪伴入口 `app` 参数一致性记录

做了什么：

- 修正 `companionship.html` 底部导航里当前页自己的链接，补上缺失的 `?app=1`。
- 修正 `rules.html` 底部导航跳去陪伴页的链接，同样补上 `?app=1`。
- 本轮不动业务逻辑，只补齐用户端主导航里漏掉的 App 壳参数，避免从规则页或陪伴页切换时掉出 App 模式。

产物位置：

- `companionship.html`
- `rules.html`

怎么验证：

- 对 `companionship.html` 和 `rules.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `companionship.html?app=1` 和 `rules.html?app=1`。
- 在线读取底部导航里的“陪伴”链接，确认都为 `companionship.html?app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`companionship.html?app=1&cb=companion2` 当前底部导航“陪伴”为 `companionship.html?app=1`；`rules.html?app=1&cb=companion2` 当前底部导航“陪伴”同样为 `companionship.html?app=1`。
- 这样从规则页进入陪伴页、以及停留在陪伴页继续切换底部导航时，都不会再因为漏掉 `app=1` 而脱离 App 壳链路。

## 9.1.21 2026-06-30 `privacy` 动态底部导航共享接入记录

做了什么：

- 在 `privacy.html` 接入 `assets/scripts/edge-client.js?v=20260630-video1`。
- 调整“我的”页内联的 `renderBottomNav()`，不再手写普通模式和纪念模式的跳转地址，而是统一通过 `GoHomeEdge.pageHref()` 生成。
- 普通模式下的 `index / monitor / events / companionship / privacy`，以及纪念模式下的 `memorial_home / digital_human / memory_gallery / voice_archive / privacy`，现在都会自动附带当前 App 壳参数。

产物位置：

- `privacy.html`

怎么验证：

- 对 `privacy.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `privacy.html?app=1`，读取普通模式底部导航，确认链接为 `...?app=1`。
- 再把纪念模式开关切为开启，确认纪念模式底部导航生成 `...?memorial=on&app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`privacy.html?app=1&cb=privacy2` 普通模式底部导航当前为 `index.html?app=1`、`monitor.html?app=1`、`events.html?app=1`、`companionship.html?app=1`、`privacy.html?app=1`。
- 同页把纪念模式切为开启后，底部导航当前变为 `memorial_home.html?memorial=on&app=1`、`digital_human.html?memorial=on&app=1`、`memory_gallery.html?memorial=on&app=1`、`voice_archive.html?memorial=on&app=1`、`privacy.html?memorial=on&app=1`。
- 这样“我的”页无论处于普通模式还是纪念模式，底部导航都已经收进共享导航口径，不再各自维护静态跳转地址。

## 9.1.22 2026-06-30 纪念模式页内互跳参数收口记录

做了什么：

- 修正 `memorial_home.html`、`digital_human.html`、`memory_gallery.html`、`voice_archive.html` 内部互跳链接。
- 统一把纪念模式四页底部导航里的 `memorial_home / digital_human / memory_gallery / voice_archive` 改成显式携带 `?app=1&memorial=on`。
- 顺手补齐页内 CTA 的纪念模式参数，例如 `voice_archive` 去平行世界、`memorial_home` 去记忆馆/声音页等入口，也统一带上 `?app=1&memorial=on`。

产物位置：

- `memorial_home.html`
- `digital_human.html`
- `memory_gallery.html`
- `voice_archive.html`

怎么验证：

- 对上述 4 个 HTML 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `memorial_home.html?app=1&memorial=on` 和 `voice_archive.html?app=1&memorial=on`。
- 读取底部导航和页内 CTA，确认都已显式携带 `?app=1&memorial=on`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`memorial_home.html?app=1&memorial=on&cb=memorial2` 当前底部导航为 `memorial_home.html?app=1&memorial=on`、`digital_human.html?app=1&memorial=on`、`memory_gallery.html?app=1&memorial=on`、`voice_archive.html?app=1&memorial=on`、`privacy.html?app=1&memorial=on`，相关 CTA 也已带齐纪念模式参数。
- `voice_archive.html?app=1&memorial=on&cb=memorial2` 当前页内“去平行世界”已变成 `digital_human.html?app=1&memorial=on`，底部导航同样整组保持 `?app=1&memorial=on`。
- 这样纪念模式四页之间的互跳不会再因为漏掉 `app / memorial` 参数而掉回普通模式或脱离 App 壳。

## 9.1.23 2026-06-30 `connect` 下一步摄像头上下文续接记录

做了什么：

- 调整 `assets/scripts/connect-live.js` 的 `syncNextStepLinks()`，让“下一步”的 `守护 / 实时` 链接不再只跳固定页面。
- 当前页面如果已经选中或识别出优选摄像头，会把该 `camera_id` 一起续传到 `monitor.html` 和 `watch.html`。
- 保留原先“没有摄像头时隐藏下一步”的逻辑，不扩散修改整页其他静态导航，只收这一处最直接的接入闭环。

产物位置：

- `assets/scripts/connect-live.js`

怎么验证：

- 对 `assets/scripts/connect-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `connect.html?app=1`，确认当页面已有优选摄像头时，“下一步”区域显示为 `可继续`。
- 在线读取 `connectMonitorLink` 和 `connectWatchLink`，确认都显式携带同一个 `camera_id`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`connect.html?app=1&cb=connectcamera1` 当前显示优选房间为 `客厅`，`connectNextStepBadge` 为 `可继续`，并且 `connectMonitorLink = monitor.html?camera_id=9&app=1`、`connectWatchLink = watch.html?camera_id=9&app=1`。
- 这样从摄像头接入页走“下一步”进入守护或实时观看时，不会再掉回默认摄像头，而是直接承接当前已接入、已优选的那一路画面。

## 9.1.24 2026-06-30 `app-shell` 优选摄像头入口续接记录

做了什么：

- 调整 `assets/scripts/app-shell-live.js`，让 `app-shell` 在拿到摄像头列表后先计算当前优选摄像头。
- 把主按钮“进入实时观看”改成带优选 `camera_id` 的 `watch.html`。
- 把“一句话导航”里的 `实时 / 事件` 入口、以及配置卡片里的“实时观看”入口，一并改成承接同一个优选 `camera_id`。
- 在 `app-shell.html` 给“一句话导航”三张卡片补上动态锚点，并把脚本版本戳抬到 `20260630-flow3`。

产物位置：

- `assets/scripts/app-shell-live.js`
- `app-shell.html`

怎么验证：

- 对 `assets/scripts/app-shell-live.js` 和 `app-shell.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `app-shell.html?app=1`。
- 在线读取主按钮、“一句话导航”的 `实时 / 事件`、以及配置卡片里的“实时观看”，确认都带同一个优选 `camera_id`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`app-shell.html?app=1&cb=appshell3` 当前 `appShellPrimaryAction = watch.html?camera_id=9&app=1`，`appShellWatchLink = watch.html?camera_id=9&app=1`，`appShellEventsLink = events.html?camera_id=9&app=1`，配置卡片里的“实时观看”同样为 `watch.html?camera_id=9&app=1`。
- 这样 App 壳作为比赛演示开场入口时，不只是原生唤起能带住 `camera_id`，连页面内的主按钮和快捷卡片也已经直接承接到当前优选摄像头，不会再从第一跳掉回默认视角。

## 9.1.25 2026-06-30 `device_binding` 家庭上下文保活记录

做了什么：

- 在 `device_binding.html` 给返回入口、空状态入口、底部导航里的“家庭 / 设备”补上动态锚点。
- 调整 `assets/scripts/device-binding-live.js`，当页面确定当前家庭后，会把 `family_id` 写回当前 URL。
- 同时让本页底部导航里的“设备”链接也显式带上当前 `family_id`，避免刷新或二次进入时掉回默认家庭。
- 保持“去家庭页”的链接仍走 `family.html?app=1`，不额外扩展 `family.html` 的参数口径。

产物位置：

- `device_binding.html`
- `assets/scripts/device-binding-live.js`

怎么验证：

- 对 `device_binding.html` 和 `assets/scripts/device-binding-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `device_binding.html?app=1`。
- 在线读取当前 URL 和底部导航“设备”链接，确认都已经显式携带当前 `family_id`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`device_binding.html?app=1&cb=binding2` 打开后，页面当前 URL 已同步成 `device_binding.html?app=1&cb=binding2&family_id=37`，下拉当前家庭值为 `37`，并且底部导航“设备”当前为 `device_binding.html?family_id=37&app=1`。
- 当前环境下只有一个家庭可选，但这已经证明 `device_binding` 会把已选家庭持续写回 URL 和当前页链接；后续多家庭场景下切换时，也能沿用这套保活方式，不必重新补链。

## 9.1.26 2026-06-30 `family` 当前家庭上下文显式化记录

做了什么：

- 在 `family.html` 给返回入口、首页底部导航、当前页底部导航补上动态锚点。
- 调整 `assets/scripts/family-live.js`，让 `family` 页优先读取 URL 里的 `family_id` 作为当前家庭。
- 当页面拿到当前家庭后，会把该 `family_id` 写回当前 URL，并把主按钮、列表入口、底部导航“设备”统一指向同一个家庭的 `device_binding.html?family_id=...`。
- 同时让当前页底部导航“家庭”自身链接也显式带上该 `family_id`，避免刷新后又回到隐式默认状态。

产物位置：

- `family.html`
- `assets/scripts/family-live.js`

怎么验证：

- 对 `family.html` 和 `assets/scripts/family-live.js` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `family.html?app=1`。
- 在线读取当前 URL、主按钮、列表“绑定设备”、当前页底部导航，确认它们都显式携带同一个 `family_id`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`family.html?app=1&cb=family2` 当前 URL 已同步成 `family.html?app=1&cb=family2&family_id=37`，并且 `familyPrimaryBindingLink = device_binding.html?family_id=37&app=1`、`familyListBindingLink = device_binding.html?family_id=37&app=1`、`familyNavSelfLink = family.html?family_id=37&app=1`。
- 这样 `family -> device_binding` 这一步不再只是“页面里隐式用了第一家庭”，而是把当前家庭显式写进 URL 和所有关键入口；后续从设备页再回流家庭页时，也能保持同一个家庭上下文。

补充收口：

- 同步调整了 `assets/scripts/device-binding-live.js` 的回链逻辑，让 `device_binding -> family` 也会继续携带当前 `family_id`。
- 本轮已在真实 `8711` 在线页面环境下验通：`device_binding.html?app=1&cb=binding3` 当前 URL 为 `device_binding.html?app=1&cb=binding3&family_id=37`，并且 `bindingBackLink = family.html?family_id=37&app=1`、`bindingNavFamilyLink = family.html?family_id=37&app=1`、`bindingEmptyFamilyLink = family.html?family_id=37&app=1`。
- 这样 `family <-> device_binding` 这条前链已经双向保活同一个家庭上下文，不再只是一边写入、一边丢失。

## 9.1.27 2026-06-30 零散守护入口摄像头上下文收口记录

做了什么：

- 给 `connect.html` 顶部去守护、底部去事件入口补上动态锚点，并在 `assets/scripts/connect-live.js` 里复用当前已接入摄像头，统一把 `monitor / watch / events` 续成同一个 `camera_id`。
- 调整 `assets/scripts/watch-live.js`，让 `watch` 顶部返回守护和“守护概览”按钮都继续携带当前摄像头，不再回退成裸 `monitor.html`。
- 调整 `assets/scripts/events-live.js`，让事件页顶部返回、主操作“回守护页”、底部“守护”都继续携带当前 `camera_id`。
- 调整 `assets/scripts/monitor-live.js` 与 `assets/scripts/detection-live.js`，让底部 `events / monitor` 导航与当前摄像头保持一致；同时抬高对应页面脚本版本戳，避免 WebView 继续命中旧缓存。

产物位置：

- `connect.html`
- `watch.html`
- `detection.html`
- `events.html`
- `monitor.html`
- `assets/scripts/connect-live.js`
- `assets/scripts/watch-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/events-live.js`
- `assets/scripts/monitor-live.js`

怎么验证：

- 对上述改动文件运行编辑器诊断，确认没有新增报错。
- 在真实 `8711` 在线页面分别打开 `connect.html?app=1`、`watch.html?app=1&camera_id=9`、`events.html?app=1&camera_id=9`、`monitor.html?app=1&camera_id=9`、`detection.html?app=1&camera_id=9`。
- 在线读取顶部入口、主操作按钮和底部导航的 `href`，确认它们都显式带上同一个 `camera_id=9`，并继续保留 `app=1`。

当前结果：

- `通过`

说明：

- 本轮收口的是最后一类“页面已经拿到当前摄像头，但跳去 `monitor / events / watch` 时仍退回裸链接”的零散入口，不涉及新的业务逻辑。
- 这样从 `connect -> monitor/events`、`watch -> monitor`、`events -> monitor`、`monitor -> events`、`detection -> monitor` 再切页时，会继续停留在同一个摄像头视角，不会因为命中静态入口而退回默认摄像头。

## 9.1.28 2026-06-30 首页底部导航摄像头上下文收口记录

做了什么：

- 给 `index.html` 底部导航里的“守护 / 事件”补上动态锚点。
- 调整 `assets/scripts/home-live.js` 的 `syncCameraEntryLinks()`，让首页在拿到优选摄像头后，不只更新主按钮和“演示主链”三张卡片，也同步更新底部导航的 `monitor / events` 入口。
- 抬高 `home-live.js` 版本戳，避免 WebView 继续读取旧缓存。

产物位置：

- `index.html`
- `assets/scripts/home-live.js`

怎么验证：

- 对 `index.html` 和 `assets/scripts/home-live.js` 运行编辑器诊断，确认没有新增报错。
- 在真实 `8711` 在线页面环境下打开 `index.html?app=1`。
- 在线读取 `edgeHomeMonitorLink`、`edgeHomeEventsLink`、`edgeHomeNavMonitorLink`、`edgeHomeNavEventsLink` 的 `href`，确认它们都显式带上同一个优选 `camera_id`，并继续保留 `app=1`。

当前结果：

- `通过`

说明：

- 首页本来已经能根据摄像头状态算出优选摄像头，但底部导航仍是裸 `monitor.html / events.html`；这一轮收口后，首页所有进入守护主链的入口口径已经一致。

## 9.1.29 2026-06-30 `connect` 真实 RTSP 验收与下一步状态修正记录

做了什么：

- 在真实 `8711` 页面环境下，使用现有 RTSP 摄像头对 `connect.html` 完成一轮完整验收：`填入表单 -> 测试 -> 保存 -> 刷新页面 -> 再次测试 -> 停用 -> 恢复启用`。
- 在线验收时发现：当唯一一路摄像头被停用后，`connect` 页“下一步”仍显示 `可继续`，会误导用户继续进入守护主链。
- 调整 `assets/scripts/connect-live.js`，让“下一步”区块是否可继续改为取决于“当前是否存在已启用的网络摄像头”，不再只看是否存在已接入记录。
- 抬高 `connect-live.js` 版本戳，避免 WebView 继续命中旧缓存。

产物位置：

- `connect.html`
- `assets/scripts/connect-live.js`

怎么验证：

- 对 `connect.html` 和 `assets/scripts/connect-live.js` 运行编辑器诊断，确认没有新增报错。
- 在真实 `8711` 在线页面环境下打开 `connect.html?app=1`，对现有 RTSP 摄像头依次执行：
  - `填入表单`
  - `测试`
  - `保存启用`
  - 刷新页面后再次 `测试`
  - `停用`
  - `设为当前`
- 在线读取结果标题、预览图、最近成功取帧时间，以及“下一步”状态，确认：
  - 测试和保存链路都能跑通；
  - 停用后不再误报“可继续”；
  - 恢复启用后重新回到可继续状态。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 页面环境下验通：现有摄像头 `rtsp://192.168.1.11:554/1/2` 能完成“测试 -> 保存 -> 刷新后再次测试”，页面显示 `画面已接入 / 640x360 / yolo / 人数 0`，预览图也能正常展示。
- 同时已验证启停切换往返：停用后页面显示 `已停用`、卡片状态变为 `已禁用`；恢复后页面显示 `已设为当前`、卡片状态回到 `在线`。
- 因为已补上“唯一一路被停用时，下一步不应继续显示可继续”的状态判断，这一轮 `connect` 的真实 RTSP 接入闭环已经不再停留在 `部分通过`。

## 9.1.30 2026-06-30 首页无启用摄像头时的入口状态收口记录

做了什么：

- 在线复验时发现：首页虽然已经能根据摄像头状态生成主链入口，但当唯一一路摄像头被停用后，首页仍会继续把主按钮和守护入口指向 `camera_id=9`，文案与入口状态不一致。
- 调整 `assets/scripts/home-live.js`，让首页的优选摄像头只从“已启用摄像头”里挑选，不再把已禁用摄像头当作可进入的主链目标。
- 当“有摄像头记录，但当前没有启用中的摄像头”时，首页会回到明确的空状态提示，并把主按钮改成 `去接入页`。
- 抬高 `home-live.js` 版本戳，避免 WebView 继续命中旧缓存。

产物位置：

- `index.html`
- `assets/scripts/home-live.js`

怎么验证：

- 对 `index.html` 和 `assets/scripts/home-live.js` 运行编辑器诊断，确认没有新增报错。
- 在真实 `8711` 页面环境下，先把唯一一路摄像头停用，再打开 `index.html?app=1`。
- 在线读取首页标题、主按钮和底部导航，确认：
  - 首页显示“当前没有启用中的摄像头”；
  - 主按钮指向 `connect.html?app=1`；
  - 守护 / 事件入口不再继续带失效的 `camera_id`。
- 最后把摄像头重新设为当前，确认现场状态恢复。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 页面环境下验通：唯一一路摄像头停用后，首页显示 `当前没有启用中的摄像头`，主按钮已切到 `connect.html?app=1`，同时守护入口回退为不带 `camera_id` 的安全入口。
- 随后已把摄像头重新恢复为当前启用状态，当前现场配置不受影响。

## 9.2 2026-06-28 `connect.html` 闭环改造记录

做了什么：

- 新增“测试但不保存”的接口 `POST /api/cameras/test-connection`，避免用户点击“测试画面”时先把错误配置写入数据库。
- 调整 `connect.html` 对应脚本，使“测试画面”和“保存启用”真正分离。
- 补充已接入摄像头的“设为当前 / 停用 / 删除 / 填入表单 / 测试”操作。
- 补充更可理解的失败提示，不再只显示原始报错。
- 修复 RTSP 路径带查询参数时重新载入表单会丢失查询串的问题。

产物位置：

- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/connect-live.js`

如何复现和验证：

- 页面端进入 `connect.html`。
- 在表单里填写局域网 RTSP 摄像头信息后点击“测试画面”，应只测试，不新增数据库记录。
- 点击“保存启用”后，摄像头应进入已接入列表。
- 在已接入列表里可以继续测试、设为当前、停用或删除。
- 当 IP、路径或账号密码错误时，页面应给出更可理解的中文提示。

当前结果：

- `部分通过`

说明：

- 代码结构和接口已补齐，静态诊断无错误。
- 使用项目虚拟环境直接调用 `test_camera_connection`，对无效 RTSP 地址返回 `HTTP 400: Cannot open network stream`，说明新测试接口已生效。
- 还没有完成“至少一台真实 RTSP 摄像头”上的最终人工验收，因此当前不能记为完全通过。

剩余问题和下一步：

- 用真实 RTSP 摄像头完成一次“测试 -> 保存 -> 再次打开页面 -> 重新测试 -> 切换启用状态”的完整验收。
- 验收通过后，再进入 `rules.html` 闭环。

## 9.3 2026-06-28 `rules.html` 闭环改造记录

做了什么：

- 新增规则运行态接口 `GET /api/rules/runtime`，用于返回 `worker` 是否运行、最近一次开始循环的时间、最近一次加载规则的时间和当前运行中的规则快照。
- 在 `worker` 内部记录最近一次读取规则的时间戳和规则快照，避免页面只能看到“保存成功”，看不到“是否已生效”。
- 调整 `rules.html` 对应脚本，保存后会主动轮询运行态接口，区分“已保存”“等待下一轮生效”“worker 未运行”三种状态。
- 为规则数值输入增加范围收敛，减少无效输入导致的保存异常。

产物位置：

- `edge-agent/app/worker.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/rules-live.js`

如何复现和验证：

- 页面端进入 `rules.html`，应先读取当前规则和检测后端。
- 修改任意规则后点击保存，页面应显示“保存中 -> 等待生效 / 已生效”。
- 如果 `worker` 正在运行，下一轮抽帧后页面应显示最近一次读取规则的时间。
- 如果 `worker` 未运行，页面应明确提示规则已写入但后台循环未运行。

当前结果：

- `通过`

说明：

- 早期已在新启动的 `8712` 实例上完成真实接口验证：`/api/rules` 可读写，`/api/rules/runtime` 可返回运行态，说明“保存 -> worker 读取 -> 生效”的链路成立。
- 本轮已在真实 `8711` 在线页面环境下完成页面端人工点击验收：打开 `rules.html?app=1&cb=rules1` 后，页面初始即显示“规则已同步 / 已生效 / YOLO 已启用”。
- 真实把“抽帧间隔”修改后点击保存，页面会回到“规则已同步”，并继续显示 `worker 最近一次读取规则时间`，随后我已把该值恢复回 `5` 并再次保存确认状态仍为“已生效”。
- 说明当前 `rules.html` 的读取、保存和页面端生效反馈在真实 `8711` 环境下已经跑通，不再只停留在接口层验证。

剩余问题和下一步：

- 继续进入 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 数据链拆分和事件可解释性收口。

## 9.4 2026-06-28 数据链拆分第一版记录

做了什么：

- 在本地 SQLite 中新增 `detection_results`、`rule_evaluations`、`event_candidates` 三张正式表。
- 为 `events` 增加 `detection_result_id`、`rule_evaluation_id`、`candidate_id` 关联字段，保留现有事件接口兼容。
- 调整 `worker`，让每次处理按 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 顺序写入。
- 调整 `event_agent`，让候选事件在被真正提升为用户事件后回写为 `promoted`，被节流抑制时回写为 `suppressed`。
- 调整 `GET /api/cameras/{camera_id}/evaluation/latest` 优先从数据库返回最新规则评估，而不是只依赖内存态。
- 调整手动抓图接口 `POST /api/cameras/{camera_id}/capture`，接入同一条数据链。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/worker.py`
- `edge-agent/app/event_agent.py`
- `edge-agent/app/main.py`

如何复现和验证：

- 启动新代码实例后，数据库中应存在 `detection_results`、`rule_evaluations`、`event_candidates` 三张表。
- 真实摄像头正常抓帧后，应写入新的检测结果和规则评估记录。
- 使用离线摄像头场景验证时，应写入 `camera_offline` 候选事件，并在需要时提升为用户事件。
- `GET /api/events/{id}` 返回的用户事件中，应能看到 `candidate_id` 和 `rule_evaluation_id`。
- `GET /api/cameras/{camera_id}/evaluation/latest` 应能返回数据库中的最新规则评估。

当前结果：

- `通过`

说明：

- 早期已用 `8712` 新实例验证：真实摄像头链路会新增 `detection_results` 和 `rule_evaluations` 记录；离线错误流会新增 `event_candidates` 并在需要时提升为用户事件。
- 本轮已在真实 `8711` 在线页面环境下补完人工验收：对 `camera_id=9` 直接执行一次 `POST /api/cameras/9/capture`，实际返回耗时约 `2687ms`，响应中直接带回了 `snapshotId=24130`、`detectionResultId=19219`、`evaluationId=19465`。
- 随后继续回读 `/api/app/cameras/9/evaluation/latest`，确认最新评估同样返回 `id=19465`、`detection_result_id=19219`、`matched_rule=no_person`，说明 `Capture -> DetectionResult -> RuleEvaluation` 在真实 `8711` 上已经对齐。
- 同时回读 `/api/app/events?limit=5`，看到最新用户事件仍停在更早一条 `event.id=811 / ruleEvaluationId=19454 / candidateId=27718`，这与当前 `EventAgent.emit()` 的 5 分钟重复事件节流逻辑一致，说明“抓图生成新评估”与“用户事件是否提升”已被正确拆开，不会因为每次抓图都刷出一条重复提醒。

剩余问题和下一步：

- `event_candidates` 的管理台可见性已在 `9.4.1` 收口完成。
- 在不打断当前页面的前提下，继续进入页面端实时画面能力建设。

## 9.4.1 2026-06-30 候选事件可观测性收口记录

做了什么：

- 在 `edge-agent/app/storage.py` 新增 `list_event_candidates()`，从 `event_candidates` 联表摄像头与已提升事件，返回候选状态、解释信息、观测值、阈值和已提升事件编号。
- 在 `edge-agent/app/main.py` 新增 `GET /api/event-candidates`，用于给管理台读取最近候选，支持 `limit` 和 `status`。
- 在 `edge-agent/admin/index.html` 首页事件区块下增加“最近候选”列表，不新开页面，直接复用首页现有信息密度。
- 在 `edge-agent/admin/console.js` 新增候选加载与状态文案渲染，让 `promoted / suppressed / new` 都能被直接看见。
- 补了一层前端兜底：当候选接口不可用时，`candidateList` 不再静默留空，而是明确显示“候选接口暂不可用”，避免误判为暂无数据。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/main.py`
- `edge-agent/admin/index.html`
- `edge-agent/admin/console.js`

如何复现和验证：

- 打开 `http://127.0.0.1:8711/admin/index.html`，首页事件区块下应直接看到“最近候选”列表。
- 访问 `GET /api/event-candidates?limit=5`，应返回真实候选记录，而不是 `404`。
- 候选列表中应同时能区分 `已提升` 与 `已抑制`，并展示规则原因、观测时长、规则阈值和已提升事件编号。
- 当服务尚未重启到最新代码时，管理台候选区块应显示“候选接口暂不可用”，而不是静默空白。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下完成验收：`GET /api/event-candidates?limit=5` 返回 `200`，最新候选里已同时出现 `status=promoted` 与多条 `status=suppressed` 的 `no_person` 记录。
- 同一时刻首页 `#candidateList` 已成功渲染 12 条候选，首条为 `已提升`，并继续展示多条 `已抑制`，说明“节流抑制后的候选”不再只存在数据库里。
- 当前列表文案已经带上 `连续未检测到人形的时长超过配置阈值。`、`观测 35 分 18 秒`、`阈值 5 分钟`、`事件 #814` 等解释链字段，管理台已能直接讲清楚候选为什么被提升或被抑制。
- 前一轮验收中曾暴露旧进程未重启导致 `/api/event-candidates` 返回 `404`；现在页面已经补上显式兜底提示，后续即便服务没重启，也不会再出现“候选区块空白但看不出原因”的状态。

剩余问题和下一步：

- 在不打断当前页面的前提下，继续进入页面端实时画面能力建设。

## 9.5 2026-06-28 视频接入层稳态化记录

做了什么：

- 调整 `camera_agent` 的网络摄像头抓图策略，单次抓图不再直接在主进程里长时间阻塞，而是改成“子进程限时抓一帧”。
- 为错误流增加硬超时控制，避免 RTSP 错流继续卡到 20-30 秒。
- 为网络 MJPEG 预览改成“多次限时抓图拼流”的策略，不再长期持有一条不稳定的 RTSP 连接。
- 保留本机摄像头原有的直接读取方式，避免影响本机调试。

产物位置：

- `edge-agent/app/camera_agent.py`

如何复现和验证：

- 使用错误 RTSP 地址验证时，应在约 `10s` 内返回超时错误，而不是继续拖到 `30s`。
- 使用当前真实 RTSP 摄像头验证时，应能在约 `10s` 内拿到首帧。
- 直接调用 `mjpeg_frames()` 时，应能返回第一段 JPEG chunk。

当前结果：

- `部分通过`

说明：

- 已验证错误流 `rtsp://192.0.2.10:554/bad` 会在约 `10.07s` 返回：`network stream timed out after 10.0s`。
- 已验证当前真实摄像头 `id=3` 在当前代码下可以在约 `6.87s` 返回单帧，分辨率为 `2880x1620`。
- 已验证 `mjpeg_frames()` 第一段预览数据可在约 `8.28s` 返回，说明预览链路已能吃到新策略。
- 日志中仍然存在 `HEVC` 参考帧警告，说明这台摄像头当前流本身仍偏重或偏不稳定；代码已经把超时收敛，但最佳方案仍是把摄像头改成 `H.264 + 子码流 + 更低分辨率`。
- 当前页面若要真正使用这套新逻辑，需要将 `edge-agent` 重启到最新代码。

剩余问题和下一步：

- 重启 `edge-agent` 后，用页面实际走一轮 `connect.html` 和实时预览验收。
- 开始进入页面端实时画面能力建设，并为后续 App 实时画面保留同一条视频接入策略。

## 9.6 2026-06-28 Web 端实时流统一记录

做了什么：

- 将检测页从“优先等最新截图”调整成“优先显示实时流，截图用于检测证据图和规则解释”。
- 开始把用户端实时流参数往统一入口收敛，避免不同页面各自手写 `fps / quality / drop`。
- 以低延迟为优先目标，对检测页实时流参数做过一轮人工体验校正，使其更接近 `admin` 的实时感。

产物位置：

- `assets/scripts/edge-client.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/monitor-live.js`

如何复现和验证：

- 打开 `monitor.html` 和 `detection.html`，确认两页都能直接看到实时画面。
- 对比 `admin` 管理台实时流，确认检测页和守护页不再出现“慢好几秒”的明显体感差异。
- 当 `snapshot/latest` 暂时还没生成时，检测页仍然应继续显示实时画面，而不是回退到旧灰图。

当前结果：

- `进行中`

说明：

- 已确认检测页在改成 `fps=5 / quality=60 / drop=4` 后，实际延迟明显收敛。
- 下一步需要继续把守护页和后续页面收敛到同一套实时流入口与参数策略，减少用户端体验分叉。
- 已开始处理 `snapshot/latest 404` 的终端噪音：当证据截图暂未生成时，前后端改为“允许缺图但继续实时流”，不再把正常降级路径当作错误刷屏。

## 9.7 2026-06-28 最小用户后端第一版记录

做了什么：

- 在 `storage.py` 中新增 `users`、`auth_sessions`、`families`、`family_members`、`device_bindings` 五组表结构，作为最小用户后端第一版落地。
- 使用 Bearer Token 会话补齐第一版身份链路，新增注册、登录、当前用户接口。
- 新增家庭空间接口：创建家庭、查看我的家庭；创建家庭后自动把创建者写入 `family_members`，角色为 `owner`。
- 新增设备绑定接口：允许家庭成员把当前运行中的 edge-agent 设备绑定到家庭，并把本机 `device_id / device_name / lan_ip / api_port` 作为第一版绑定元数据保存。
- 为 `/api/device` 补充稳定的 `device_id` 字段，给后续绑定码、设备 token 和心跳机制预留边界。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/main.py`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动 `edge-agent` 后，查看 `/docs`，应新增：
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `GET /api/users/me`
  - `POST /api/families`
  - `GET /api/families/mine`
  - `POST /api/device-bindings`
  - `GET /api/device-bindings`
- 先调用注册接口获取 Bearer Token，再使用同一个 Token 访问当前用户、创建家庭、查看我的家庭和绑定设备接口。
- 访问 `/api/device`，应能看到新增的 `device_id` 字段。
- 使用非家庭成员访问设备绑定或绑定列表接口时，应返回权限错误，而不是静默成功。

当前结果：

- `通过`

说明：

- 已完成代码落地，最近编辑文件的 IDE 诊断均为 0，未发现语法或静态诊断错误。
- 已在当前真实运行中的 `8711` 实例上完成一轮接口验收，`/docs` 已可见全部新增接口。
- 已实测通过一轮真实链路：`注册 -> 当前用户 -> 创建家庭 -> 绑定设备 -> 查看我的家庭`，返回状态均为 `200`。
- 已实测 `device-bindings` 权限控制：未登录访问返回 `401`，非家庭成员带 Token 访问返回 `403`，符合预期。
- 已实测 `/api/device` 返回的 `device_id` 与绑定结果中的 `device_id` 一致，说明当前设备身份字段已可用于后续绑定码、设备 token 和心跳机制。

剩余问题和下一步：

- 下一步进入事件上报、媒体访问和实时视频鉴权前，需要先把前端 H5 的登录态接入方式定下来。
- 当前最适合继续推进的是：在 `edge-client.js` 中补 Bearer Token 和用户态封装，为后续 H5 登录页与登录后流程接入做共享底座。

## 9.8 2026-06-28 App / H5 登录态共享层第一版记录

做了什么：

- 在 `edge-client.js` 中新增 Bearer Token 的读取、保存、清理和统一请求头注入，避免后续页面各自手写 `Authorization`。
- 新增共享层接口封装：`register / login / currentUser / createFamily / myFamilies / bindDevice / deviceBindings`。
- 保持旧有摄像头、规则、事件、实时流接口不变，确保当前页面继续兼容。
- 让登录后页面后续只需要调用 `GoHomeEdge`，不需要再关心 token 存储细节。

产物位置：

- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 打开任一已挂载 `edge-client.js` 的页面，例如 `index.html`。
- 在页面控制台或同源脚本环境中调用：
  - `GoHomeEdge.register(...)`
  - `GoHomeEdge.currentUser()`
  - `GoHomeEdge.createFamily(...)`
  - `GoHomeEdge.bindDevice(...)`
  - `GoHomeEdge.myFamilies()`
- 调用成功后，`localStorage` 中应出现 `gohome.authToken`，且后续受保护接口无需手写请求头即可访问。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `http://127.0.0.1:8711/ui/index.html` 页面环境里完成一轮共享层验收。
- 实测结果显示：`GoHomeEdge.register -> currentUser -> createFamily -> bindDevice -> myFamilies` 全链路正常，`tokenSaved=true`，家庭数量 `1`，设备数量 `1`。
- 最近编辑文件诊断为 0，未引入新的静态错误。

剩余问题和下一步：

- 共享层已可用，下一步应该开始接入真正的登录页和登录后首页流转，而不是继续把登录逻辑藏在控制台调用里。
- 在正式做登录后页面前，需要决定是先做独立 `login.html`，还是先把现有首页接成“未登录态 / 已登录态”双态页面。

## 9.9 2026-06-28 独立登录页第一版记录

做了什么：

- 新增独立页面 `login.html`，提供第一版登录 / 注册入口。
- 新增 `assets/scripts/login-live.js`，负责服务连接、登录 / 注册切换、会话检查、退出账号和成功跳转首页。
- 登录页复用现有 `edge-client.js` 共享 SDK，不在页面里重复实现鉴权逻辑。
- 已登录用户再次进入登录页时，会识别当前会话并直接提供“进入首页 / 退出当前账号”操作。

产物位置：

- `login.html`
- `assets/scripts/login-live.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 打开 `http://127.0.0.1:8711/ui/login.html`。
- 页面应先显示守护服务连接状态。
- 切到“注册”，填写称呼、邮箱和密码后提交。
- 注册成功后应自动进入 `index.html`。
- 再次访问登录页时，应识别当前已登录状态，并显示“进入首页 / 退出当前账号”。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成注册验收。
- 实测过程为：退出当前账号 -> 切到注册 -> 提交新账号 -> 自动跳转到 `http://127.0.0.1:8711/ui/index.html`。
- 跳转完成后，页面存在首页核心节点，且 `localStorage` 中 Bearer Token 保持存在，说明“登录页 -> 登录态 -> 首页”链路已成立。
- 最近编辑文件诊断为 0，未引入新的静态错误。

剩余问题和下一步：

- 下一步应开始让首页识别“未登录 / 已登录”状态，而不是只依赖手动访问 `login.html`。
- 登录后还缺真正的家庭空间页和设备绑定页入口，后续应按顺序接上。

## 9.10 2026-06-28 登录后首页、家庭和设备绑定流程接入第一版记录

做了什么：

- 改造 `index.html` 和 `home-live.js`，让首页识别三种状态：未登录、已登录但未创建家庭、已登录且未绑定当前设备。
- 首页新增最小流程入口，不再把用户直接丢进旧的纯内容态首页。
- 新增 `family.html` 和 `assets/scripts/family-live.js`，承接创建家庭、查看我的家庭和退出当前账号。
- 新增 `device_binding.html` 和 `assets/scripts/device-binding-live.js`，承接当前设备绑定到所选家庭，并展示已绑定设备列表。
- 保持现有守护、检测、事件、连接和规则页面不受影响。

产物位置：

- `index.html`
- `assets/scripts/home-live.js`
- `family.html`
- `assets/scripts/family-live.js`
- `device_binding.html`
- `assets/scripts/device-binding-live.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 打开 `http://127.0.0.1:8711/ui/login.html`，完成注册或登录。
- 首次进入首页时，若当前账号还没有家庭，首页应显示“先建家庭”。
- 打开 `http://127.0.0.1:8711/ui/family.html`，创建一个家庭后，列表应立即刷新。
- 打开 `http://127.0.0.1:8711/ui/device_binding.html`，选择家庭并绑定当前设备。
- 绑定成功后再次进入首页，应回到正常的守护首页状态，而不是继续停留在设置提示态。

当前结果：

- `通过`

说明：

- 最近编辑文件 `index.html`、`home-live.js`、`family.html`、`family-live.js`、`device_binding.html`、`device-binding-live.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。
- 已在真实运行中的 `8711` 页面环境完成一轮前端验收。
- 实测链路为：`登录页注册 -> 首页显示先建家庭 -> 家庭页创建家庭 -> 设备页绑定当前设备 -> 首页恢复正常守护态`。
- 页面验收中，`family.html` 创建后家庭数从 `0` 变为 `1`，`device_binding.html` 绑定后状态从“待绑定”变为“已绑定”，且列表显示当前设备。

剩余问题和下一步：

- 首页当前只接了最小登录后入口，家庭成员邀请、切换家庭、解绑设备还没开始做。
- 下一步按顺序进入事件上报、媒体访问和实时画面鉴权，不再继续扩大家庭页本轮范围。

## 9.11 2026-06-29 事件、媒体和实时画面鉴权第一版记录

做了什么：

- 在 `edge-agent/app/main.py` 中新增一组受保护的用户侧接口：
  - `GET /api/app/device`
  - `GET /api/app/cameras`
  - `GET /api/app/cameras/{id}/snapshot/latest`
  - `GET /api/app/cameras/{id}/evaluation/latest`
  - `GET /api/app/cameras/{id}/stream.mjpg`
  - `GET /api/app/events`
  - `GET /api/app/events/{id}`
  - `PATCH /api/app/events/{id}`
  - `GET /api/app/summary/today`
  - `GET /api/app/media/snapshots/{path}`
- 基于当前设备 `device_id` 与 `device_bindings` 新增“当前用户是否有这台设备访问权”的判断，不把权限判断散落到每个页面里。
- 保留旧的 `/api/events`、`/api/cameras/{id}/stream.mjpg`、`/snapshots/...` 供管理台和接入页继续调试，本轮不硬切它们。
- 在 `edge-client.js` 中新增 `appDevice / appCameras / appLatestSnapshot / appLatestEvaluation / appEvents / appEvent / appUpdateEvent / appSummary / appStreamUrl / appMediaUrl`。
- 用户侧页面 `home-live.js`、`monitor-live.js`、`detection-live.js`、`events-live.js`、`event-detail-live.js` 已切到受保护接口。
- 为了解决 `img.src` 和 MJPEG `<img>` 不能自动带 Bearer Header 的问题，第一版在媒体与流 URL 上补了 `access_token` 查询参数，仅这两类资源接受 query token。

产物位置：

- `edge-agent/app/main.py`
- `edge-agent/app/storage.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/home-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/events-live.js`
- `assets/scripts/event-detail-live.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 先用登录页登录，并确保当前账号已创建家庭且已把当前设备绑定到家庭。
- 未登录时访问 `GET /api/app/device`，应返回 `401`。
- 使用不属于当前设备绑定家庭的账号访问 `GET /api/app/device`，应返回 `403`。
- 使用有访问权的账号访问 `GET /api/app/events` 和 `GET /api/app/events/{id}`，应返回真实事件数据。
- 打开 `events.html` 和 `event_detail.html`，页面应能显示真实事件和受保护截图。
- 访问 `GET /api/app/cameras/{id}/stream.mjpg`，应返回 `multipart/x-mixed-replace` 的受保护 MJPEG 流。

当前结果：

- `通过`

说明：

- 最近编辑文件 `main.py`、`storage.py`、`edge-client.js`、`home-live.js`、`monitor-live.js`、`detection-live.js`、`events-live.js`、`event-detail-live.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。
- 已使用临时新实例 `8712` 完成一轮真实验收，避免直接打断当前用户正在使用的 `8711`。
- 实测结果：
  - 未登录访问受保护设备接口返回 `401`
  - 已登录但无设备访问权的账号访问受保护设备接口返回 `403`
  - 已绑定家庭成员可成功读取受保护事件列表和详情
  - 受保护截图实际加载成功，详情页图片 `naturalWidth=640`
  - 受保护实时流接口返回 `200`，`content-type=multipart/x-mixed-replace; boundary=frame`
- 用户页默认仍按原逻辑优先连 `8711`，因此本轮页面验收通过 `?edge=http://127.0.0.1:8712` 指向新实例完成。

剩余问题和下一步：

- 当前媒体和实时流的第一版访问令牌仍直接复用登录 token 查询参数，后续应在设备 token、会话票据和播放鉴权收口时换成更短时效的专用票据。
- 下一步进入设备 token、心跳和绑定码机制补齐，再把实时画面会话与播放鉴权正式收口。

## 9.12 2026-06-29 设备 token、心跳和绑定码机制第一版记录

做了什么：

- 在 `storage.py` 中新增 `device_binding_codes`、`device_tokens` 两组数据结构，并补齐绑定码生成、消费、设备 token 签发和心跳写入逻辑。
- 在 `main.py` 中新增设备侧最小接口：
  - `POST /api/device/binding-codes`
  - `GET /api/device/binding-codes`
  - `POST /api/device/token/exchange`
  - `POST /api/device/heartbeat`
  - `POST /api/device/heartbeat/self`
  - `GET /api/device/auth-status`
- 为当前 edge-agent 增加本地设备 token 持久化，设备通过绑定码激活成功后会把 token 写入 `device_token.txt`。
- 在 `edge-client.js` 中新增 `createDeviceBindingCode / deviceBindingCodes / exchangeDeviceToken / deviceHeartbeatSelf / deviceAuthStatus` 共享封装。
- 在 `device_binding.html` 和 `device-binding-live.js` 中补齐最小入口：生成绑定码、激活当前设备、发送一次心跳、查看当前设备身份状态。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `device_binding.html`
- `assets/scripts/device-binding-live.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 实例后，确认以下接口存在且不再返回 `404`：
  - `POST /api/device/binding-codes`
  - `POST /api/device/token/exchange`
  - `GET /api/device/auth-status`
  - `POST /api/device/heartbeat/self`
- 在 `http://127.0.0.1:8711/ui/login.html` 页面环境中，使用真实共享层 `GoHomeEdge` 跑一轮完整链路：
  - 注册新账号
  - 创建家庭
  - 绑定当前设备到家庭
  - 生成绑定码
  - 使用绑定码激活当前设备
  - 发送一次心跳
  - 再次读取设备身份状态
- 验收关键结果应满足：
  - 绑定码列表数量大于 `0`
  - `local_token_saved=true`
  - `authHasToken=true`
  - `heartbeatOk=true`
  - `lastHeartbeatAt` 和 `lastSeenAt` 有真实时间

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 实例完成一轮真实验收，不再依赖临时 `8712`。
- 实测结果为：`注册 -> 创建家庭 -> 绑定当前设备 -> 生成绑定码 -> 激活当前设备 -> 发送心跳 -> 读取设备身份状态` 全链路通过。
- 本轮真实验收结果中，生成的绑定码为 `FQ4SNX`，`bindingCodeListCount=1`，激活后 `localTokenSaved=true`、`authHasToken=true`、`heartbeatOk=true`。
- 激活与心跳后的设备身份状态显示：`deviceId=edge-22251ebf4d874e4d`，`accessibleFamilyIds=[7]`，`lastHeartbeatAt` 和 `lastSeenAt` 已成功写入时间戳。
- 最近编辑文件 `main.py`、`storage.py`、`device-binding-live.js`、`edge-client.js` 的诊断均为 `0`。

剩余问题和下一步：

- 当前设备 token 第一版仍是本地 edge-agent 内部签发与消费，后续进入正式云端 `api/v1` 时需要拆成云端设备身份体系。
- 当前媒体和实时流仍在第一版里复用登录 token 查询参数，下一步应继续做实时画面会话和播放鉴权的正式收口。

## 9.13 2026-06-29 实时画面会话和播放鉴权正式收口记录

做了什么：

- 在 `main.py` 中新增最小播放会话接口 `POST /api/app/playback-sessions`，由已登录且有当前设备访问权的用户换取短时播放票据。
- 为受保护媒体和 MJPEG 流增加 `playback_ticket` 校验，允许媒体与实时流在不暴露登录 token 的情况下被 `<img>` 和 `fetch` 访问。
- 保留原有 `Authorization` / `access_token` 兼容入口，避免当前已跑通的页面和验收链路被一次性打断。
- 在 `edge-client.js` 中新增 `createPlaybackSession / appStreamPlaybackUrl / appMediaPlaybackUrl`，让页面统一走短时播放票据，不再直接把 Bearer Token 拼到 URL 上。
- 更新首页、守护页、检测页和事件详情页的媒体/实时流访问方式，并给相关 HTML 脚本引用增加版本号，避免浏览器继续吃旧缓存。

产物位置：

- `edge-agent/app/main.py`
- `edge-agent/app/schemas.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/home-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/event-detail-live.js`
- `login.html`
- `index.html`
- `monitor.html`
- `detection.html`
- `event_detail.html`
- `family.html`
- `device_binding.html`
- `events.html`
- `connect.html`
- `rules.html`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 实例后，确认 `POST /api/app/playback-sessions` 不再返回 `404`，未登录访问返回 `401`。
- 访问 `http://127.0.0.1:8711/ui/login.html`，确认页面实际加载的是带版本号的脚本引用，而不是旧缓存脚本。
- 在真实页面环境中跑一轮完整验收：
  - 注册新账号
  - 创建家庭
  - 绑定当前设备
  - 读取当前可用摄像头
  - 生成实时流播放 URL
  - 生成截图播放 URL
  - 验证 URL 包含 `playback_ticket` 且不包含 `access_token`
  - 验证媒体和实时流可以正常访问
  - 验证一个 `30s` 短时播放票据在过期前可用、过期后返回 `401`

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收，不再依赖手工注入或临时实例。
- 实测结果：
  - `streamUrlHasPlaybackTicket=true`
  - `streamUrlHasAccessToken=false`
  - `streamStatus=200`
  - `streamContentType=multipart/x-mixed-replace; boundary=frame`
  - `snapshotUrlHasPlaybackTicket=true`
  - `snapshotUrlHasAccessToken=false`
  - `snapshotStatus=200`
  - `snapshotContentType=image/jpeg`
  - `shortTicketBeforeExpire=200`
  - `shortTicketAfterExpire=401`
  - `shortTicketAfterExpireBody={\"detail\":\"Playback ticket expired\"}`
- 最近编辑文件 `main.py`、`schemas.py`、`edge-client.js`、`home-live.js`、`monitor-live.js`、`detection-live.js`、`event-detail-live.js` 的诊断均为 `0`。

剩余问题和下一步：

- 当前播放票据仍由本地 edge-agent 自签、自验，后续进入正式云端 `video-service` 时需要拆成云端会话与播放授权服务。
- 下一步按文档顺序进入正式云端 `api/v1` 与事件上云链路补齐，不继续在本轮扩张更多页面能力。

## 9.14 2026-06-29 正式云端 `api/v1` 与事件上云链路补齐记录

做了什么：

- 在 `main.py` 中补一版正式 `/api/v1` 命名空间，先把当前单机服务里的用户、家庭、设备和事件能力挂到未来云端可复用的路径上。
- 新增 `/api/v1/identity/register`、`/api/v1/identity/login`、`/api/v1/identity/me`，让用户身份接口不再只停留在本地旧命名。
- 新增 `/api/v1/households`、`/api/v1/households/mine`、`/api/v1/devices/current`、`/api/v1/events`、`/api/v1/events/{id}`、`/api/v1/summary/today`，补齐用户侧最小查询闭环。
- 新增 `/api/v1/device/heartbeat` 和 `/api/v1/device/events`，让设备 token 可直接走正式命名空间完成心跳和事件上报。
- 在 `storage.py` 中新增 `event_ingests` 幂等表，并补 `get_event_ingest` / `bind_event_ingest`，确保同一设备用相同 `idempotency_key` 重试时不会生成重复事件。
- 在 `storage.py` 中补 `get_snapshot_by_path`，并让 `create_event` 支持传入外部 `occurred_at`，为后续真正设备上云保留原始事件时间。
- 在 `schemas.py` 中新增 `V1DeviceEventIngest` 契约，在 `edge-client.js` 中补齐最小 `/api/v1` SDK 封装，便于后续页面和 App 逐步迁移。

产物位置：

- `edge-agent/app/main.py`
- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，先确认未登录访问：
  - `GET /api/v1/identity/me` 返回 `401`
  - `POST /api/v1/device/heartbeat` 返回 `401`
  - `GET /api/v1/events` 返回 `401`
- 在真实页面环境里跑一轮完整闭环：
  - `POST /api/v1/identity/register`
  - `POST /api/v1/households`
  - `POST /api/device/binding-codes`
  - `POST /api/device/token/exchange`
  - `POST /api/v1/device/heartbeat`
  - `POST /api/v1/device/events`
  - 同一 `idempotency_key` 再次 `POST /api/v1/device/events`
  - `GET /api/v1/devices/current`
  - `GET /api/v1/events`
  - `GET /api/v1/events/{id}`
  - `PATCH /api/v1/events/{id}`
  - `GET /api/v1/summary/today`

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 路由加载确认：
  - `GET /health = 200`
  - `GET /api/v1/identity/me = 401`
  - `POST /api/v1/device/heartbeat = 401`
  - `GET /api/v1/events = 401`
- 完整闭环实测结果：
  - `registerStatus=200`
  - `meStatus=200`
  - `householdStatus=200`
  - `bindingCodeStatus=200`
  - `exchangeStatus=200`
  - `v1HeartbeatStatus=200`
  - `v1HeartbeatOk=true`
  - `ingestFirstStatus=200`
  - `ingestSecondStatus=200`
  - `ingestSecondDeduplicated=true`
  - `ingestEventIdSame=true`
  - `ingestEventId=300`
  - `currentDeviceStatus=200`
  - `currentDeviceAccessibleFamilyIds=[12]`
  - `eventsStatus=200`
  - `eventsCount=10`
  - `firstEventType=fall_candidate`
  - `eventDetailStatus=200`
  - `eventDetailSummary=疑似跌倒`
  - `eventUpdateStatus=200`
  - `eventAcknowledged=true`
  - `summaryStatus=200`
- 最近编辑文件 `main.py`、`storage.py`、`schemas.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 这一轮仍然是“在现有 edge-agent 里先落正式 `/api/v1` 契约”，还没有拆成独立部署的真实云端服务。
- 事件上云目前只完成最小 JSON ingest，还没有正式媒体上传、对象存储、预签名 URL 和通知链路。
- 下一步按文档顺序进入“设备与云端的远程配置、版本和状态同步补齐”。

## 9.15 2026-06-29 设备与云端的远程配置、版本和状态同步补齐记录

做了什么：

- 在 `storage.py` 中新增 `device_sync_states` 表，用于保存每台设备的目标 App 版本、目标模型版本、目标规则配置、目标通用配置、最近上报状态、最近同步时间和最近应用时间。
- 在 `storage.py` 中补 `ensure_device_sync_state`、`update_device_sync_target`、`report_device_sync`、`mark_device_sync_rules_applied` 等同步状态读写方法，形成最小同步数据层。
- 在 `schemas.py` 中新增 `V1DeviceSyncTargetUpdate` 和 `V1DeviceSyncReport` 契约，分别承接用户侧目标配置下发和设备侧同步上报。
- 在 `main.py` 中新增：
  - `GET /api/v1/devices/current/sync-state`
  - `PATCH /api/v1/devices/current/sync-target`
  - `POST /api/v1/device/sync`
- 让用户侧可查看当前设备同步状态并下发目标 App 版本、目标模型版本和目标规则配置。
- 让设备侧在同步时上报当前版本和运行状态，同时拉取目标配置；当发现目标规则版本变更时，直接应用到当前规则并更新同步状态。
- 在 `worker.py` 中补 `mark_rules_reloaded()`，确保设备同步应用规则后，运行时快照立即刷新，不会出现“规则已应用但 runtime 仍显示旧值”的错位。
- 在 `edge-client.js` 中补最小同步 SDK：`v1CurrentDeviceSyncState`、`v1UpdateDeviceSyncTarget`、`v1DeviceSync`。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/main.py`
- `edge-agent/app/worker.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，确认未登录访问：
  - `GET /api/v1/devices/current/sync-state` 返回 `401`
  - `PATCH /api/v1/devices/current/sync-target` 返回 `401`
  - `POST /api/v1/device/sync` 返回 `401`
- 在真实页面环境里跑一轮完整闭环：
  - 注册新账号
  - 创建家庭
  - 生成绑定码
  - 换取设备 token
  - 用户侧读取初始同步状态
  - 用户侧下发目标 App 版本、目标模型版本、目标规则和目标配置
  - 设备侧调用 `/api/v1/device/sync` 上报当前状态并执行同步
  - 用户侧再次读取同步状态，确认目标值、已上报值、已应用规则版本和运行时规则快照都正确更新

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 路由加载确认：
  - `GET /health = 200`
  - `GET /api/v1/devices/current/sync-state = 401`
  - `PATCH /api/v1/devices/current/sync-target = 401`
  - `POST /api/v1/device/sync = 401`
- 完整闭环实测结果：
  - `registerStatus=200`
  - `householdStatus=200`
  - `bindingCodeStatus=200`
  - `exchangeStatus=200`
  - `beforeStateStatus=200`
  - `targetStatus=200`
  - `targetAppVersion=0.2.1`
  - `targetModelVersion=yolov8n-sync-test.pt`
  - `targetRuleVersion=2026-06-29T01:19:01.043271+00:00`
  - `targetNotificationEnabled=true`
  - `targetPersonDetectionEnabled=true`
  - `targetYoloConfidence=0.44`
  - `targetReleaseChannel=beta`
  - `deviceSyncStatus=200`
  - `deviceRulesApplied=true`
  - `syncReportedAppVersion=0.1.0`
  - `syncReportedModelVersion=yolov8n.pt`
  - `syncReportedWorkerRunning=true`
  - `syncReportedLanIp=127.0.0.1`
  - `syncReportedRuntimeSource=puppeteer-sync`
  - `afterStateStatus=200`
  - `afterTargetAppVersion=0.2.1`
  - `afterTargetModelVersion=yolov8n-sync-test.pt`
  - `afterReportedAppVersion=0.1.0`
  - `afterReportedModelVersion=yolov8n.pt`
  - `afterAppliedRuleVersion=2026-06-29T01:19:01.048119+00:00`
  - `afterRuleVersion=2026-06-29T01:19:01.048119+00:00`
  - `afterNotificationEnabled=true`
  - `afterPersonDetectionEnabled=true`
  - `afterYoloConfidence=0.44`
  - `afterLastSeenAt`、`afterLastSyncAt`、`afterLastAppliedAt` 都成功写入时间戳
  - `afterReleaseChannel=beta`
  - `afterWorkerRunning=true`
  - `afterLanIp=127.0.0.1`
  - `afterRuntimeSource=puppeteer-sync`
- 最近编辑文件 `storage.py`、`schemas.py`、`main.py`、`worker.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 当前同步仍然是单设备、单实例、拉模式的最小闭环，还没有做批量设备管理、灰度、回滚和真正的独立云控服务。
- 目标模型版本目前只完成了状态同步，还没有落到真实模型下载、切换和回滚链路。
- 下一步按文档顺序进入“云端 `video-service` 和正式播放会话服务拆分”。

## 9.16 2026-06-29 云端 `video-service` 和正式播放会话服务拆分记录

做了什么：

- 在 `main.py` 中把播放会话底层逻辑收成 `create_playback_session()`，让旧 `/api/app/playback-sessions` 和新 `/api/v1/video/sessions` 复用同一套校验和票据签发逻辑。
- 在 `main.py` 中新增正式视频命名空间：
  - `POST /api/v1/video/sessions`
  - `GET /api/v1/video/cameras/{id}/stream.mjpg`
  - `GET /api/v1/video/media/snapshots/{path}`
- 在 `main.py` 中补 `v1_video_snapshot_url()` 和 `event_for_v1()`，让正式 `/api/v1` 事件数据里的截图地址对齐到新视频命名空间。
- 在 `edge-client.js` 中补正式视频 SDK：
  - `createV1VideoSession`
  - `v1VideoStreamUrl`
  - `v1VideoStreamPlaybackUrl`
  - `v1VideoMediaPlaybackUrl`
- 把首页、守护页、检测页、事件详情页切到新的 `/api/v1/video/*` 播放入口，但保留旧 `/api/app/*` 兼容入口，不硬切断现有链路。
- 把各页面脚本版本号提升到 `20260629-video1`，避免浏览器继续吃旧缓存。

产物位置：

- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/home-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/event-detail-live.js`
- `login.html`
- `index.html`
- `monitor.html`
- `detection.html`
- `event_detail.html`
- `events.html`
- `family.html`
- `device_binding.html`
- `connect.html`
- `rules.html`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，先确认未登录访问：
  - `POST /api/v1/video/sessions` 返回 `401`
- 在真实页面环境里跑一轮完整闭环：
  - 注册新账号
  - 创建家庭
  - 生成绑定码
  - 换取设备 token
  - 读取当前设备摄像头和最近截图
  - 调 `POST /api/v1/video/sessions` 分别换取流和截图的播放会话
  - 通过 `GoHomeEdge.v1VideoStreamPlaybackUrl()` 和 `GoHomeEdge.v1VideoMediaPlaybackUrl()` 生成新视频 URL
  - 验证 URL 带 `playback_ticket`、不带 `access_token`，且走 `/api/v1/video/*`
  - 验证实时流和截图可访问
  - 验证短时票据过期前返回 `200`，过期后返回 `401`

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 路由加载确认：
  - `GET /health = 200`
  - `POST /api/v1/video/sessions = 401`
- 完整闭环实测结果：
  - `registerStatus=200`
  - `householdStatus=200`
  - `bindingCodeStatus=200`
  - `exchangeStatus=200`
  - `camerasStatus=200`
  - `snapshotMetaStatus=200`
  - `snapshotAvailable=true`
  - `streamSessionStatus=200`
  - `streamSessionHasUrl=true`
  - `snapshotSessionStatus=200`
  - `snapshotSessionHasUrl=true`
  - `streamUrlHasPlaybackTicket=true`
  - `streamUrlHasAccessToken=false`
  - `streamUrlUsesV1=true`
  - `snapshotUrlHasPlaybackTicket=true`
  - `snapshotUrlHasAccessToken=false`
  - `snapshotUrlUsesV1=true`
  - `streamStatus=200`
  - `streamContentType=multipart/x-mixed-replace; boundary=frame`
  - `snapshotStatus=200`
  - `snapshotContentType=image/jpeg`
  - `shortTicketBeforeExpire=200`
  - `shortTicketAfterExpire=401`
  - `shortTicketAfterExpireBody={\"detail\":\"Playback ticket expired\"}`
- 本轮中间修复了两个真实运行时问题：
  - `/api/v1/video/sessions` 首次验收时因 `create_playback_ticket()` 被截断导致 `500`
  - 修复后再次在真实 `8711` 上复验通过
- 最近编辑文件 `main.py`、`edge-client.js`、`home-live.js`、`monitor-live.js`、`detection-live.js`、`event-detail-live.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 这一轮只是把正式视频契约和播放会话从 `/api/app` 中拆出来，还没有拆成独立部署的真实 `video-service` 进程。
- 目前视频访问仍直接读取本地快照目录和本地 MJPEG 代理，还没有接对象存储、媒体上传和公网分发。
- 下一步按文档顺序进入“媒体上传、对象存储和正式通知链路补齐”。

## 9.17 2026-06-29 媒体上传、对象存储和正式通知链路补齐记录

做了什么：

- 在 `settings.py` 中新增本地 `object_storage` 目录，把“对象存储”第一版先落在本机文件系统，保持后续替换 S3 / OSS 的接口形状。
- 在 `storage.py` 中新增两张正式表：
  - `media_assets`
  - `notification_deliveries`
- 在 `storage.py` 中补齐媒体资产和通知投递的持久化方法，让截图提升、通知落库和查询都不再走临时内存。
- 在 `main.py` 中新增媒体资产相关辅助逻辑：
  - `asset_file_path()`
  - `checksum_sha256()`
  - `promote_snapshot_media_asset()`
- 在 `main.py` 中新增通知持久化辅助逻辑：
  - `notification_delivery_status()`
  - `notification_recipient()`
  - `dispatch_notification()`
- 在 `main.py` 中补正式接口：
  - `POST /api/v1/device/media-assets`
  - `GET /api/v1/notifications/deliveries`
  - `POST /api/v1/notifications/test`
  - `GET /api/v1/video/assets/{asset_id}`
- 在 `main.py` 中扩展 `POST /api/v1/device/events`，让设备事件上云时自动把已有截图提升为正式媒体资产，并在通知开关开启时写入正式投递记录。
- 在 `schemas.py` 中补 `V1MediaAssetCreate`，并把播放会话扩到 `asset` 资源类型。
- 在 `edge-client.js` 中补共享层封装：
  - `v1CreateDeviceMediaAsset`
  - `v1NotificationDeliveries`
  - `v1NotificationTest`
  - `v1VideoAssetPlaybackUrl`

产物位置：

- `edge-agent/app/settings.py`
- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，在真实页面环境里使用现有登录态和真实数据做验收。
- 先取当前家庭和最近事件，拿一张已有快照作为媒体提升输入。
- 调 `POST /api/v1/notifications/test`，验证正式通知投递记录是否落库。
- 调 `POST /api/device/binding-codes` 生成绑定码，再调 `POST /api/device/token/exchange` 换取一枚新的设备 token。
- 用新设备 token 调 `POST /api/v1/device/media-assets`，把已有快照提升成正式媒体资产。
- 再用新设备 token 调 `POST /api/v1/device/events`，验证事件上云响应里能直接带回 `media_asset` 和 `notification_delivery`。
- 调 `POST /api/v1/video/sessions` 为 `asset` 资源换取播放票据，再访问 `GET /api/v1/video/assets/{asset_id}`，验证正式媒体地址可读。
- 额外伪造一张已过期的 `asset` 播放票据，验证媒体接口返回 `401`。
- 最后确认本地 `object_storage` 目录下已生成对应文件。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 正式通知接口实测通过：
  - `GET /api/v1/notifications/deliveries?limit=5 = 200`
  - 首次读取时返回空数组，说明新路由已在线且可查询
  - `POST /api/v1/notifications/test = 200`
  - 测试通知写入 `notification_deliveries`
- 设备 token 和媒体资产链路实测通过：
  - `POST /api/device/binding-codes = 200`
  - `POST /api/device/token/exchange = 200`
  - `POST /api/v1/device/media-assets = 200`
  - 本轮把快照 `camera_9/20260629_112421_342587.jpg` 提升为正式资产 `asset_id=1`
- 事件上云自动补媒体和通知实测通过：
  - `POST /api/v1/device/events = 200`
  - 返回 `accepted=true`
  - 返回事件 `event_id=351`
  - 返回 `media_asset.id=1`
  - 返回 `notification_delivery.id=2`
  - 当前通知通道配置为 `off`，所以投递记录状态为 `skipped`，但正式落库链路已成立
- 正式媒体播放链路实测通过：
  - `POST /api/v1/video/sessions(resource_type=asset) = 200`
  - `GET /api/v1/video/assets/1?playback_ticket=... = 200`
  - `content-type=image/jpeg`
  - `byteLength=6635`
- 过期票据校验实测通过：
  - 伪造已过期 `asset` 票据后访问 `GET /api/v1/video/assets/1 = 401`
  - 返回 `{\"detail\":\"Playback ticket expired\"}`
- 本地对象存储落盘已确认：
  - 文件已生成在 `edge-agent/data/object_storage/family_19/snapshots/10746_20260629_112421_342587.jpg`
  - 与返回的 `object_key=family_19/snapshots/10746_20260629_112421_342587.jpg` 一致
  - 资产 `checksum_sha256=cbb753f84827946b7b1bf0ff0033f2378ca99760139da11445bdafe04678e102`
- 最近编辑文件 `settings.py`、`storage.py`、`schemas.py`、`main.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 这一轮对象存储仍是本地 mock 目录，还没有接真实公网对象存储和预签名上传。
- 通知投递当前只补到正式落库和可查询，还没有做复杂重试、模板和多通道路由。
- 下一步按文档顺序进入“设备批量管控、灰度和回滚能力补齐”。

## 9.18 2026-06-29 设备批量管控、灰度和回滚能力补齐记录

做了什么：

- 在 `storage.py` 中新增 `device_rollouts` 表，正式记录发布批次、灰度范围、已下发设备、已回滚设备和回滚前目标快照。
- 在 `storage.py` 中补 `set_device_sync_target()`，让批次回滚时可以把设备目标直接恢复到发布前快照，而不是只能继续走增量 patch。
- 在 `storage.py` 中补发布批次读写能力：
  - `create_device_rollout()`
  - `get_device_rollout()`
  - `list_device_rollouts()`
  - `update_device_rollout_state()`
- 在 `schemas.py` 中补第一版批量管控契约：
  - `V1DeviceRolloutCreate`
  - `V1DeviceRolloutPromote`
  - `V1DeviceRolloutRollback`
- 在 `main.py` 中补家庭设备视图和发布编排辅助逻辑：
  - `build_family_device_view()`
  - `list_family_devices_view()`
  - `apply_rollout_to_devices()`
  - `rollback_rollout_devices()`
  - `device_rollout_for_api()`
- 在 `main.py` 中新增正式接口：
  - `GET /api/v1/devices?family_id=...`
  - `GET /api/v1/device-rollouts?family_id=...`
  - `POST /api/v1/device-rollouts`
  - `GET /api/v1/device-rollouts/{id}`
  - `POST /api/v1/device-rollouts/{id}/promote`
  - `POST /api/v1/device-rollouts/{id}/rollback`
- 在 `edge-client.js` 中补共享层封装：
  - `v1Devices`
  - `v1DeviceRollouts`
  - `v1CreateDeviceRollout`
  - `v1DeviceRollout`
  - `v1PromoteDeviceRollout`
  - `v1RollbackDeviceRollout`

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，使用现有登录态进入真实页面环境。
- 先为当前家庭生成两台新的验收设备：
  - 调 `POST /api/device/binding-codes`
  - 调 `POST /api/device/token/exchange`
- 调 `GET /api/v1/devices?family_id=19`，确认家庭设备列表和同步状态可读。
- 调 `POST /api/v1/device-rollouts` 创建第一版 canary 批次，只先下发给其中一台设备。
- 调 `GET /api/v1/device-rollouts/{id}` 和 `GET /api/v1/devices?family_id=19`，确认只有 canary 设备目标被更新。
- 调 `POST /api/v1/device-rollouts/{id}/promote`，把剩余设备推进到同一目标。
- 再调 `GET /api/v1/device-rollouts/{id}` 和 `GET /api/v1/devices?family_id=19`，确认两台设备都收到目标。
- 最后调 `POST /api/v1/device-rollouts/{id}/rollback`，验证两台设备都恢复到发布前目标。
- 再调 `GET /api/v1/device-rollouts?family_id=19&limit=5`，确认批次列表和状态可查询。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 真实验收中新增了两台测试设备：
  - `rollout-a-1782711018830`
  - `rollout-b-1782711018838`
- 家庭设备列表接口实测通过：
  - `GET /api/v1/devices?family_id=19 = 200`
  - 可返回家庭内设备及各自 `sync.target / sync.reported` 状态
- 发布批次创建实测通过：
  - `POST /api/v1/device-rollouts = 200`
  - 新建批次 `rollout_id=1`
  - `status=canary`
  - `scope_count=2`
  - `applied_count=1`
  - `remaining_count=1`
- 灰度阶段实测通过：
  - 初次创建后只有 canary 设备 `rollout-b-1782711018838` 被下发
  - 该设备目标变为：
    - `app_version=0.3.0-canary`
    - `model_version=yolov8n-rollout.pt`
    - `config.release_channel=canary`
  - 同批剩余设备 `rollout-a-1782711018830` 仍保持空目标，未被误下发
- 灰度推进实测通过：
  - `POST /api/v1/device-rollouts/1/promote = 200`
  - 批次状态变为 `completed`
  - `applied_count=2`
  - 两台设备目标都更新为同一版本和配置
- 回滚实测通过：
  - `POST /api/v1/device-rollouts/1/rollback = 200`
  - 批次状态变为 `rolled_back`
  - `rolled_back_count=2`
  - 两台验收设备都恢复到发布前空目标：
    - `app_version=''`
    - `model_version=''`
    - `config={}`
- 批次查询实测通过：
  - `GET /api/v1/device-rollouts/1 = 200`
  - `GET /api/v1/device-rollouts?family_id=19&limit=5 = 200`
  - 列表中可看到 `id=1`、`status=rolled_back`、`title=rollout verify batch`
- 最近编辑文件 `storage.py`、`schemas.py`、`main.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 这一轮灰度和回滚还是“目标配置层”的最小闭环，还没有接真实应用包下载、模型包下载、执行器和健康门禁。
- 当前批次推进仍是手动接口触发，还没有做复杂百分比灰度、自动暂停、失败阈值和审批流。
- 下一步按文档顺序进入“独立部署的 `video-service`、转码和分发能力补齐”。

## 9.19 2026-06-29 独立部署的 `video-service`、转码和分发能力补齐记录

做了什么：

- 新增 `video_profiles.py`，把视频档位定义抽成纯数据模块，不再把 `fps / width / height / quality / drop` 硬编码散落在前端和主入口里。
- 新增 `video_service.py`，把以下视频服务逻辑从 `main.py` 中拆出，集中收进独立服务层：
  - 播放票据签发与校验
  - 快照路径和资产路径解析
  - 正式媒体资产提升
  - 视频流分发响应
  - `/api/v1/video/*` 路由
- 新增 `video_app.py`，作为第一版独立 `video-service` 应用入口，具备独立 `FastAPI app`、独立 `/health` 和独立视频路由挂载能力。
- 在 `main.py` 中保留业务主入口，只负责：
  - 挂载 `video_service` 路由
  - 调用 `video_service` 的媒体提升和播放票据能力
  - 兼容旧 `/api/app/*` 入口
- 在 `edge-client.js` 中去掉实时流档位的硬编码参数表，只保留 `profile` 名称和可选覆盖参数。
- 在 `edge-client.js` 中新增 `v1VideoProfiles()`，让前端可以读正式视频档位，而不是自己内置一份静态表。

产物位置：

- `edge-agent/app/video_profiles.py`
- `edge-agent/app/video_service.py`
- `edge-agent/app/video_app.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，在真实页面环境中使用现有登录态做正式验收。
- 先调 `GET /api/v1/video/profiles`，确认视频档位接口已在线。
- 再调：
  - `POST /api/v1/video/sessions`
  - `GET /api/v1/video/cameras/{id}/stream.mjpg?profile=mobile`
  - `GET /api/v1/video/media/snapshots/{path}`
  - `GET /api/v1/video/assets/{id}`
- 同时保留旧兼容入口，调：
  - `POST /api/app/playback-sessions`
  - `GET /api/app/cameras/{id}/stream.mjpg?profile=monitor`
- 确认实时流响应头中能返回：
  - `X-GoHome-Video-Profile`
  - `X-GoHome-Video-Distribution`
- 额外对 `video_app.py` 做应用级自检：
  - `GET /health = 200`
  - 未登录访问 `GET /api/v1/video/profiles = 401`

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 视频档位接口实测通过：
  - `GET /api/v1/video/profiles = 200`
  - 返回正式档位：
    - `default`
    - `detail`
    - `monitor`
    - `mobile`
- 正式视频会话与分发链路实测通过：
  - `POST /api/v1/video/sessions(stream) = 200`
  - `POST /api/v1/video/sessions(snapshot) = 200`
  - `POST /api/v1/video/sessions(asset) = 200`
  - `GET /api/v1/video/cameras/9/stream.mjpg?profile=mobile&playback_ticket=... = 200`
  - 实时流响应头：
    - `content-type=multipart/x-mixed-replace; boundary=frame`
    - `x-gohome-video-profile=mobile`
    - `x-gohome-video-distribution=mjpeg`
  - `GET /api/v1/video/media/snapshots/camera_9/20260629_133946_985694.jpg?playback_ticket=... = 200`
  - `snapshot content-type=image/jpeg`
  - `snapshot byteLength=7178`
  - `GET /api/v1/video/assets/1?playback_ticket=... = 200`
  - `asset content-type=image/jpeg`
  - `asset byteLength=6635`
- 兼容旧 `/api/app/*` 入口实测通过：
  - `POST /api/app/playback-sessions = 200`
  - `GET /api/app/cameras/9/stream.mjpg?profile=monitor&playback_ticket=... = 200`
  - 响应头：
    - `x-gohome-video-profile=monitor`
    - `x-gohome-video-distribution=mjpeg`
- 独立 `video_app.py` 应用级自检通过：
  - `TestClient(GET /health) = 200`
  - `TestClient(GET /api/v1/video/profiles) = 401`
- 这一轮关键拆分已经成立：
  - 档位数据在 `video_profiles.py`
  - 视频服务逻辑在 `video_service.py`
  - 独立服务入口在 `video_app.py`
  - 主业务入口 `main.py` 只做挂载与业务调用，不再承载整套视频细节
- 最近编辑文件 `video_profiles.py`、`video_service.py`、`video_app.py`、`main.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 当前“独立部署”已经完成代码与应用入口拆分，但还没有做常驻进程、独立端口、守护脚本和生产部署编排。
- 当前分发仍是 MJPEG 第一版，还没有扩展到 HLS、WebRTC、RTMP 或公网 CDN。
- 下一步按文档顺序进入“真正对象存储、公网媒体分发和预签名上传能力补齐”。

## 9.20 2026-06-29 真正对象存储、公网媒体分发和预签名上传能力补齐记录

做了什么：

- 在 `storage.py` 中新增 `media_upload_sessions` 表，把“上传会话态”和“正式媒体资产态”拆开，避免把上传过程直接混进 `media_assets`。
- 在 `storage.py` 中新增上传会话读写能力：
  - `create_media_upload_session()`
  - `get_media_upload_session()`
  - `get_media_upload_session_by_token_hash()`
  - `mark_media_upload_session_uploaded()`
  - `complete_media_upload_session()`
- 在 `storage.py` 中补 `get_media_asset_by_object_key()`，让对象路径和媒体资产能正式关联。
- 在 `schemas.py` 中新增第一版对象存储契约：
  - `V1MediaUploadSessionCreate`
  - `V1MediaUploadSessionComplete`
  - `V1MediaPublicLinkCreate`
- 在 `settings.py` 中补对象存储提供方和 bucket 配置：
  - `GOHOME_OBJECT_STORAGE_PROVIDER`
  - `GOHOME_OBJECT_STORAGE_BUCKET`
- 新增 `object_storage_service.py`，把对象存储相关逻辑单独收口，负责：
  - object key 生成
  - 上传 / 下载令牌签名与校验
  - 上传内容落盘
  - 上传完成后正式入库 `media_asset`
  - 公网下载链接生成
- 在 `video_service.py` 中把对象文件路径和资产 API 组装复用到 `object_storage_service.py`，保持视频服务只消费“已经存在的资产”。
- 在 `main.py` 中新增正式接口：
  - `POST /api/v1/media/upload-sessions`
  - `PUT /api/v1/media/upload-sessions/{id}/content`
  - `POST /api/v1/media/upload-sessions/{id}/complete`
  - `POST /api/v1/media/assets/{id}/public-links`
  - `GET /api/public/media/assets/{id}`
- 在 `edge-client.js` 中补共享层封装：
  - `v1CreateMediaUploadSession`
  - `v1UploadMediaContent`
  - `v1CompleteMediaUploadSession`
  - `v1CreateMediaPublicLink`
- 修复了一处真实运行时回归：
  - `video_service.py` 在拆模块时遗漏了 `hashlib` 导入，导致新上传资产走 `POST /api/v1/video/sessions(asset)` 时 `500`
  - 已补回导入并重新完成真实验收

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/settings.py`
- `edge-agent/app/object_storage_service.py`
- `edge-agent/app/video_service.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，使用真实登录态进入页面环境。
- 调 `POST /api/v1/media/upload-sessions` 创建上传会话，拿到：
  - `upload_url`
  - `complete_url`
  - `object_key`
- 调 `PUT /api/v1/media/upload-sessions/{id}/content?upload_token=...` 直接上传内容。
- 调 `POST /api/v1/media/upload-sessions/{id}/complete?upload_token=...` 完成资产入库。
- 调 `POST /api/v1/media/assets/{id}/public-links` 生成带时效的公网下载链接。
- 调 `GET /api/public/media/assets/{id}?download_token=...` 验证公网下载可用。
- 再调 `POST /api/v1/video/sessions(resource_type=asset)` 和 `GET /api/v1/video/assets/{id}?playback_ticket=...`，确认新上传资产仍能走受保护播放链路。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 本轮真实验收使用家庭 `family_id=1`，真实创建了一条新的上传链路：
  - `upload_session_id=2`
  - `asset_id=3`
  - `provider=signed-localfs`
  - `bucket=public-media`
  - `object_key=family_1/uploads/20260629/061451_01c3ab57_verify-public-2.jpg`
- 预签名上传会话实测通过：
  - `POST /api/v1/media/upload-sessions = 200`
  - 返回：
    - `upload_url`
    - `complete_url`
    - `object_key`
    - `provider=signed-localfs`
    - `bucket=public-media`
- 上传内容实测通过：
  - `PUT /api/v1/media/upload-sessions/2/content?... = 200`
  - 上传会话状态变为 `uploaded`
  - `byte_size=10`
- 完成资产入库实测通过：
  - `POST /api/v1/media/upload-sessions/2/complete?... = 200`
  - 上传会话状态变为 `completed`
  - 新资产：
    - `asset_id=3`
    - `public_asset_path=/api/public/media/assets/3`
    - `storage_url=/api/v1/video/assets/3`
- 公网分发实测通过：
  - `POST /api/v1/media/assets/3/public-links = 200`
  - 生成带时效的 `public_url`
  - `GET /api/public/media/assets/3?download_token=... = 200`
  - 响应头：
    - `content-type=image/jpeg`
    - `cache-control=public, max-age=60`
  - 返回字节长度 `10`
  - 正文内容 `test-bytes`
- 受保护资产播放链路实测通过：
  - `POST /api/v1/video/sessions(resource_type=asset, asset_id=3) = 200`
  - `GET /api/v1/video/assets/3?playback_ticket=... = 200`
  - 响应头 `content-type=image/jpeg`
  - 返回字节长度 `10`
  - 正文内容 `test-bytes`
- 这一轮拆分已经成立：
  - 上传态在 `media_upload_sessions`
  - 完成态在 `media_assets`
  - 对象存储逻辑在 `object_storage_service.py`
  - 视频服务继续只消费已存在资产，不再管理上传过程
- 最近编辑文件 `storage.py`、`schemas.py`、`settings.py`、`object_storage_service.py`、`video_service.py`、`main.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 当前“真正对象存储”还是本地签名存储适配层第一版，尚未接入真实云厂商 S3 / OSS / COS。
- 当前上传仍是单请求直传，还没有做分片上传、断点续传、去重和生命周期管理。
- 下一步按文档顺序进入“真实应用包、模型包下载与升级执行能力补齐”。

## 9.21 2026-06-29 真实应用包、模型包下载与升级执行能力补齐记录

做了什么：

- 在 `settings.py` 中新增正式发布目录：
  - `releases_dir`
  - `app_releases_dir`
  - `model_releases_dir`
- 在 `storage.py` 中新增 `package_releases` 表，正式记录包发布元数据，把“目标版本”和“真实包资产”对应起来。
- 在 `storage.py` 中新增 `package_executions` 表，正式记录设备升级执行结果，把下载/安装状态从同步状态里拆出来。
- 在 `storage.py` 中新增包发布与执行读写能力：
  - `create_package_release()`
  - `get_package_release()`
  - `get_package_release_by_version()`
  - `list_package_releases()`
  - `create_package_execution()`
  - `update_package_execution()`
  - `get_package_execution()`
  - `list_package_executions()`
  - `get_latest_package_execution()`
- 新增 `package_service.py`，把包发布和升级执行逻辑从 `main.py` 中拆出，统一负责：
  - 包发布登记
  - 发布下载链接生成
  - 当前已安装版本清单
  - 本地发布目录落盘
  - 第一版包执行结果回写
- 在 `schemas.py` 中新增第一版包发布 / 升级执行契约：
  - `V1PackageReleaseCreate`
  - `V1PackageDownloadLinkCreate`
  - `V1DeviceUpgradeRun`
- 在 `main.py` 中新增正式接口：
  - `GET /api/v1/package-releases`
  - `POST /api/v1/package-releases`
  - `GET /api/v1/package-releases/{id}`
  - `POST /api/v1/package-releases/{id}/download-links`
  - `GET /api/v1/package-executions`
  - `POST /api/v1/devices/current/upgrade-run`
  - `POST /api/v1/device/upgrade-run`
- 在 `main.py` 中补 `record_local_package_execution()`，让升级执行后同步状态能真实反映最新安装结果。
- 在 `main.py` 中补 `device_sync` 视图扩展：
  - `current.packages`
  - `reported.package_executions`
  - 当前 `app_version / model_version` 由 `package_service` 的当前版本清单驱动，而不是继续写死。
- 在 `edge-client.js` 中补共享层封装：
  - `v1PackageReleases`
  - `v1CreatePackageRelease`
  - `v1PackageRelease`
  - `v1CreatePackageDownloadLink`
  - `v1PackageExecutions`
  - `v1RunCurrentDeviceUpgrade`
  - `v1RunDeviceUpgrade`

产物位置：

- `edge-agent/app/settings.py`
- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/package_service.py`
- `edge-agent/app/main.py`
- `assets/scripts/edge-client.js`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 启动真实 `8711` 后，在真实页面环境中使用现有登录态完成验证。
- 先走现有预签名上传链路各上传一个最小 `app` 包和最小 `model` 包。
- 调 `POST /api/v1/package-releases` 把两个资产分别注册成：
  - `app@0.3.0`
  - `model@yolov8n-rollout.pt`
- 调 `POST /api/v1/package-releases/{id}/download-links` 验证包下载链接可生成。
- 调 `PATCH /api/v1/devices/current/sync-target` 把当前设备目标版本切到：
  - `app_version=0.3.0`
  - `model_version=yolov8n-rollout.pt`
- 调 `POST /api/v1/devices/current/upgrade-run` 执行当前设备升级。
- 调 `GET /api/v1/devices/current/sync-state` 和 `GET /api/v1/package-executions` 确认：
  - 当前安装版本已更新
  - 执行结果已入库
  - 落盘路径已生成
- 最后调 `POST /api/v1/device/upgrade-run`，验证设备 token 侧执行入口也可用。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 本轮真实上传并注册了两份包资产：
  - `app` 资产：
    - `upload_session_id=3`
    - `asset_id=4`
    - `object_key=family_1/uploads/20260629/062841_b970289e_gohome-app-0.3.0.pkg`
  - `model` 资产：
    - `upload_session_id=4`
    - `asset_id=5`
    - `object_key=family_1/uploads/20260629/062841_1cd5ed32_gohome-model-yolov8n-rollout.pt`
- 包发布登记实测通过：
  - `POST /api/v1/package-releases(app@0.3.0) = 200`
  - `POST /api/v1/package-releases(model@yolov8n-rollout.pt) = 200`
  - 真实发布结果：
    - `app release_id=1`
    - `model release_id=2`
- 包下载链接实测通过：
  - `POST /api/v1/package-releases/1/download-links = 200`
  - `POST /api/v1/package-releases/2/download-links = 200`
- 当前设备目标版本下发实测通过：
  - `PATCH /api/v1/devices/current/sync-target = 200`
  - 目标切为：
    - `app_version=0.3.0`
    - `model_version=yolov8n-rollout.pt`
    - `config.rollout_channel=stable-upgrade`
- 当前设备升级执行实测通过：
  - `POST /api/v1/devices/current/upgrade-run = 200`
  - 真实执行了两条成功记录：
    - `package_execution_id=1` for `app@0.3.0`
    - `package_execution_id=2` for `model@yolov8n-rollout.pt`
  - 执行状态都为 `succeeded`
- 落盘结果实测通过：
  - app 落盘：
    - `/Users/tanyihua/trae比赛/gohome/edge-agent/data/releases/app/0.3.0/gohome-app-0.3.0.pkg`
  - model 落盘：
    - `/Users/tanyihua/trae比赛/gohome/edge-agent/data/releases/model/yolov8n-rollout.pt/gohome-model-yolov8n-rollout.pt`
- `device_sync` 视图实测通过：
  - `GET /api/v1/devices/current/sync-state = 200`
  - `current.app_version=0.3.0`
  - `current.model_version=yolov8n-rollout.pt`
  - `current.packages.app.version=0.3.0`
  - `current.packages.model.version=yolov8n-rollout.pt`
  - `reported.app_version=0.3.0`
  - `reported.model_version=yolov8n-rollout.pt`
  - `reported.package_executions.app.status=succeeded`
  - `reported.package_executions.model.status=succeeded`
- 包执行记录列表实测通过：
  - `GET /api/v1/package-executions?family_id=1&device_id=edge-22251ebf4d874e4d&limit=10 = 200`
  - 可返回最近两条执行记录及其落盘路径
- 设备 token 侧执行入口实测通过：
  - `POST /api/v1/device/upgrade-run = 200`
  - 因当前设备已与目标版本一致，所以本次返回 `executionCount=0`
  - 但设备侧入口可正常鉴权并执行“已最新版本”的空操作闭环
- 这一轮拆分已经成立：
  - `package_releases` 只管包发布数据
  - `package_executions` 只管设备执行状态
  - `package_service.py` 只管发布、下载、安装和当前版本清单
  - `main.py` 只保留薄接口和同步视图接线
- 最近编辑文件 `settings.py`、`storage.py`、`schemas.py`、`package_service.py`、`main.py`、`edge-client.js`、`想家了吗-Plan.md`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 当前升级执行还是“文件落盘 + 当前版本清单更新”的第一版，还没有做真正进程热替换、自更新守护器和失败自动回滚。
- 当前应用包也还没有做解压、校验脚本和启动切换编排，只补到真实包资产下载和执行状态闭环。
- 下一步按文档顺序进入“移动端 / App 视频观看链路和播放体验补齐”。

## 9.22 2026-06-29 移动端 / App 视频观看链路和播放体验补齐记录

做了什么：

- 在 `assets/scripts/edge-client.js` 中补 `preferredVideoProfile()` 和 `createManagedVideoStream()`，把移动观看页的档位选择、票据刷新、失败重连和可见性恢复沉到共享层。
- 新增 `watch.html` 和 `assets/scripts/watch-live.js`，作为独立的移动端 / App 专用实时观看页，页面只保留实时画面、摄像头列表、档位切换、最新提醒和到守护/检测页的最小跳转。
- 调整入口联动：
  - `assets/scripts/home-live.js` 首页主按钮改跳 `watch.html`
  - `monitor.html` 实时画面入口改跳 `watch.html`
  - `detection.html` 返回入口改回 `watch.html`
  - `index.html`、`monitor.html`、`detection.html` 同步更新静态脚本版本号
- 在真实验收中发现 `watch-live.js` 对 `GET /api/v1/video/profiles` 的返回结构假设错误，实际线上返回是 `{ distribution, profiles }`，因此补了 `normalizeProfiles()` 兼容层，避免页面直接报 `profiles.filter is not a function`。
- 为了让浏览器立即加载修复后的脚本，把 `watch.html` 的脚本版本号从 `20260629-watch1` 升到 `20260629-watch2`。

产物位置：

- `assets/scripts/edge-client.js`
- `assets/scripts/watch-live.js`
- `assets/scripts/home-live.js`
- `watch.html`
- `index.html`
- `monitor.html`
- `detection.html`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 使用真实运行中的 `8711` 页面环境，先补一枚当前设备所属 owner 用户的新登录 token，确保浏览器进入真实登录态。
- 打开 `http://127.0.0.1:8711/ui/index.html`，确认首页主按钮：
  - `href=watch.html`
  - 文案为 `实时观看`
- 在真实首页点击主按钮，确认可进入 `http://127.0.0.1:8711/ui/watch.html`。
- 在 `watch.html` 中确认首屏接流成功：
  - `watchStatusBadge=直播中`
  - `watchRoomBadge=客厅`
  - `watchDetectorBadge=YOLO`
  - 画面地址为 `/api/v1/video/cameras/9/stream.mjpg?...profile=mobile...`
- 在 `watch.html` 中点击档位按钮，确认 `detail` 和 `monitor` 都能真实切流：
  - 点击 `detail` 后画面地址切到 `profile=detail`
  - 点击 `monitor` 后画面地址切到 `profile=monitor`
  - 切换过程中状态保持 `直播中`
- 在 `watch.html` 点击“检测细节”进入 `http://127.0.0.1:8711/ui/detection.html`，确认页面返回按钮 `href=watch.html`，再点击返回后能回到 `watch.html` 且继续直播。
- 重新检查最近编辑文件，`watch-live.js` 和 `watch.html` 诊断均为 `0`。

当前结果：

- `通过`

说明：

- 已在真实运行中的 `8711` 页面环境完成一轮真验收。
- 首页入口真验收通过：
  - `GET /ui/index.html` 渲染后主按钮真实指向 `watch.html`
  - 点击后成功进入新的移动观看页
- 新观看页真验收通过：
  - `GET /ui/watch.html?reload=watch2` 后页面恢复正常
  - 真实状态为 `直播中`
  - 当前接入房间为 `客厅`
  - 当前检测后端为 `YOLO`
  - 当前事件摘要正常显示最近提醒
- 档位切换真验收通过：
  - `mobile -> detail -> monitor` 三档都能改写真实流地址
  - 每次切换都走新的受保护 `playback_ticket`
- 检测页往返真验收通过：
  - `watch.html -> detection.html -> watch.html` 已跑通
- 本轮修复确认成立：
  - `watch-live.js` 不再把视频档位返回值写死为数组
  - `watch.html` 已通过脚本版本号切换到最新页面逻辑
- 当前验收环境只有 `1` 路启用中的摄像头，因此本轮真实验证到“摄像头列表正常渲染、默认选择正常、单路观看正常”；多路摄像头之间的真实切换，还需要在接入第二路启用摄像头后再补一轮验收。
- 最近编辑文件 `watch-live.js`、`watch.html`、`想家了吗-Implement.md` 的诊断均为 `0`。

剩余问题和下一步：

- 当前移动观看仍是 MJPEG + 短时票据保活第一版，还没有做更长时段的观看稳定性观察、弱网处理和播放统计。
- 当前移动页已经具备档位切换和入口闭环，但多路摄像头真实切换还需等第二路启用摄像头后补验。
- 下一步按 `Plan` 顺序进入“多实例视频服务和公网分发优化能力补齐”。

## 9.23 2026-06-29 多实例视频服务和公网分发优化能力补齐记录

做了什么：

- 在 `edge-agent/app/settings.py` 中新增分发相关配置数据：
  - `GOHOME_PUBLIC_BASE_URL`
  - `GOHOME_VIDEO_SERVICE_PUBLIC_BASE_URL`
  - `GOHOME_MEDIA_PUBLIC_BASE_URL`
  - `GOHOME_VIDEO_SERVICE_NODE_ID`
  - `GOHOME_VIDEO_SERVICE_REGION`
  - `GOHOME_VIDEO_SERVICE_ROLE`
  - `GOHOME_VIDEO_DISTRIBUTION_NAME`
- 新增 `edge-agent/app/video_distribution_service.py`，把视频分发节点信息、绝对 URL 组装和公网基址选择从视频/存储逻辑里独立出去。
- 在 `edge-agent/app/video_service.py` 中接入分发服务：
  - `POST /api/v1/video/sessions` 现在会返回当前视频节点 `service`
  - `stream_url / media_url / asset_url` 现在返回绝对分发地址
  - 同时保留 `stream_path / media_path / asset_path` 作为相对路径边界
  - 新增 `GET /api/v1/video/service-info`
  - 视频流响应头新增 `X-GoHome-Video-Node`
- 在 `edge-agent/app/object_storage_service.py` 中接入分发服务：
  - `media_asset_for_api()` 现在返回 `storage_path / storage_url / public_asset_path / public_asset_url`
  - `POST /api/v1/media/assets/{id}/public-links` 现在返回 `public_path / public_url` 和服务节点信息
  - 公开下载响应头新增 `X-GoHome-Media-Node`
- 在 `edge-agent/app/main.py` 和 `edge-agent/app/video_app.py` 中只做接线，把分发逻辑保持在独立服务层，不回流到主入口。

产物位置：

- `edge-agent/app/settings.py`
- `edge-agent/app/video_distribution_service.py`
- `edge-agent/app/object_storage_service.py`
- `edge-agent/app/video_service.py`
- `edge-agent/app/main.py`
- `edge-agent/app/video_app.py`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 重启真实 `8711` 实例，使新分发服务代码生效。
- 在真实浏览器登录态下打开 `http://127.0.0.1:8711/ui/watch.html?reload=multi-video-verify`。
- 使用当前 owner 用户登录态直接调接口验证：
  - `GET /api/v1/video/profiles`
  - `GET /api/v1/video/service-info`
  - `POST /api/v1/video/sessions`
  - `POST /api/v1/media/assets/1/public-links`
- 额外用本机直连方式校验响应头：
  - 视频流地址实际返回 `X-GoHome-Video-Node`
  - 公开媒体下载实际返回 `X-GoHome-Media-Node`
- 检查最近编辑文件诊断和 `py_compile`：
  - `video_distribution_service.py`
  - `object_storage_service.py`
  - `video_service.py`
  - `main.py`
  - `video_app.py`
  - `settings.py`

当前结果：

- `通过`

说明：

- 已在真实 `8711` 环境完成一轮真验收。
- 视频分发节点信息真验收通过：
  - `GET /api/v1/video/profiles = 200`
  - 返回 `service.node_id=edge-22251ebf4d874e4d`
  - 返回 `service.role=origin`
  - 返回 `service.distribution=single-origin`
  - 返回 `service.service_url=http://192.168.1.4:8711`
  - 返回 `service.media_url=http://192.168.1.4:8711`
- 独立视频服务信息接口真验收通过：
  - `GET /api/v1/video/service-info = 200`
  - 返回当前节点和分发基址信息
- 视频会话绝对地址真验收通过：
  - `POST /api/v1/video/sessions = 200`
  - 返回 `stream_path=/api/v1/video/cameras/9/stream.mjpg`
  - 返回 `stream_url=http://192.168.1.4:8711/api/v1/video/cameras/9/stream.mjpg`
  - 返回 `service.node_id=edge-22251ebf4d874e4d`
- 公网媒体绝对地址真验收通过：
  - `POST /api/v1/media/assets/1/public-links = 200`
  - 返回 `public_path=/api/public/media/assets/1?...`
  - 返回 `public_url=http://192.168.1.4:8711/api/public/media/assets/1?...`
  - 返回 `distribution=single-origin`
- 响应头真验收通过：
  - 实际视频流响应头返回：
    - `X-GoHome-Video-Node=edge-22251ebf4d874e4d`
    - `X-GoHome-Video-Distribution=mjpeg`
    - `X-GoHome-Video-Profile=mobile`
  - 实际公开媒体下载响应头返回：
    - `X-GoHome-Media-Node=edge-22251ebf4d874e4d`
    - `Cache-Control=public, max-age=60`
- 设备信息视图同步通过：
  - `GET /api/device = 200`
  - 返回 `video_distribution.service.node_id=edge-22251ebf4d874e4d`
- 最近编辑文件诊断均为 `0`，并且 `python3 -m py_compile` 已通过：
  - `settings.py`
  - `video_distribution_service.py`
  - `object_storage_service.py`
  - `video_service.py`
  - `main.py`
  - `video_app.py`

剩余问题和下一步：

- 当前仍是“单节点可声明分发信息”第一版，还没有做真正的视频节点注册中心、健康探测和自动切流。
- 当前公网地址仍默认回落到局域网 `http://192.168.1.4:8711`，还没有接真实公网域名、CDN 或云厂商对象存储域名。
- 下一步按 `Plan` 顺序进入“真正进程级升级器、失败回滚和守护能力补齐”。

## 9.24 2026-06-29 真正进程级升级器、失败回滚和守护能力补齐记录

做了什么：

- 在 `edge-agent/app/settings.py` 中新增运行时守护目录和守护配置：
  - `runtime_dir`
  - `app_runtime_dir`
  - `runtime_logs_dir`
  - `GOHOME_APP_RUNTIME_WATCHDOG_INTERVAL_SECONDS`
  - `GOHOME_APP_RUNTIME_STARTUP_GRACE_SECONDS`
- 新增 `edge-agent/app/app_runtime_guard_service.py`，把受管 app 进程的启动、停止、状态文件、watchdog 和重启逻辑独立成服务层，不把进程守护逻辑塞回 `main.py`。
- 在 `edge-agent/app/package_service.py` 中把 app 包升级从“只写 `current.json`”补成“真正尝试拉起受管进程”的闭环：
  - 成功启动时把运行结果写进 `package_executions.output.runtime`
  - 启动失败时自动回滚到上一版 manifest
  - 回滚成功时将执行状态记为 `rolled_back`
  - 回滚后若稳定版没有真正跑起来，会自动补一次 `restart_current()`
- 在 `edge-agent/app/main.py` 中接入运行时守护服务，并新增最小运行态接口：
  - `GET /api/v1/runtime/app-status`
  - `POST /api/v1/runtime/app/restart`
  - `POST /api/v1/runtime/app/stop`
- 在 `/health` 和 `/api/device` 中增加 `app_runtime` 状态输出，方便后续诊断。

产物位置：

- `edge-agent/app/settings.py`
- `edge-agent/app/app_runtime_guard_service.py`
- `edge-agent/app/package_service.py`
- `edge-agent/app/main.py`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 重启真实 `8711`，让运行时守护代码生效。
- 验证 `GET /api/v1/runtime/app-status` 已在线。
- 使用真实登录态执行受管 app 验收：
  - 先把目标版本切到 `0.3.1-runtime-watchdog`
  - 触发 `POST /api/v1/devices/current/upgrade-run`
  - 观察 `GET /api/v1/runtime/app-status.restart_count >= 1`
- 再把目标版本切到 `0.3.1-runtime-stable`
  - 触发 `POST /api/v1/devices/current/upgrade-run`
  - 或使用 `POST /api/v1/runtime/app/restart`
  - 确认运行态恢复为 stable 版本
- 再把目标版本切到 `0.3.2-runtime-bad`
  - 触发 `POST /api/v1/devices/current/upgrade-run`
  - 查看 `GET /api/v1/package-executions` 顶部执行状态为 `rolled_back`
  - 确认运行态重新回到 `0.3.1-runtime-stable`
- 最后把设备目标版本恢复为 stable，避免把验收环境留在坏版本目标。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 环境完成一轮真验收。
- 运行时守护接口真验收通过：
  - `GET /api/v1/runtime/app-status = 200`
  - `POST /api/v1/runtime/app/restart = 200`
  - `POST /api/v1/runtime/app/stop = 200`
- watchdog 自动拉起真验收通过：
  - 受管版本 `0.3.1-runtime-watchdog` 启动后会自动退出
  - 再次检查运行态时 `restart_count=3`
  - 说明 watchdog 已经实际自动拉起过该进程
- 稳定版受管进程拉起真验收通过：
  - `0.3.1-runtime-stable` 的执行记录状态为 `succeeded`
  - `package_executions.output.runtime.ok = true`
  - `POST /api/v1/runtime/app/restart` 后当前运行态恢复为：
    - `running=true`
    - `version=0.3.1-runtime-stable`
    - `pid=70892`（验收时实时值）
- 坏版本升级自动回滚真验收通过：
  - 顶部执行记录 `id=10`
  - `status=rolled_back`
  - `target_version=0.3.2-runtime-bad`
  - `output.runtime.rolled_back = true`
  - `output.runtime.active_version = 0.3.1-runtime-stable`
  - `output.runtime_restart_after_rollback.ok = true`
  - 回滚后运行态重新回到：
    - `running=true`
    - `version=0.3.1-runtime-stable`
- 设备同步视图已恢复到稳定版本验收状态：
  - 当前 `current.app_version = 0.3.1-runtime-stable`
  - 当前 `target.app_version = 0.3.1-runtime-stable`
- 本轮验收用到的测试版本如下：
  - `0.3.1-runtime-watchdog`
  - `0.3.1-runtime-stable`
  - `0.3.2-runtime-bad`
- 最近编辑文件诊断均为 `0`。

剩余问题和下一步：

- 当前完成的是“受管 app 进程”级别的升级、回滚和守护，还没有做到 `edge-agent` 自身的自更新与自替换。
- 当前仍未接入 `launchd` 或系统服务级常驻拉起，进程守护仍运行在当前 `edge-agent` 主进程内部。
- 下一步按 `Plan` 顺序进入“原生 App 壳、登录态承接和上架准备补齐”。

## 9.25 2026-06-29 原生 App 壳、登录态承接和上架准备补齐记录

做了什么：

- 新增 `app-shell.html`，作为第一版 App 容器首页，只承接入口和登录态，不重写现有业务页。
- 在 `assets/scripts/edge-client.js` 中新增 App 壳公共能力：
  - `bootstrapLaunchState()`
  - `pageHref()`
  - `loginHref()`
  - `redirectTarget()`
  - `currentPagePath()`
  - `isAppShellMode()`
- 让共享层可以从 URL 承接：
  - `edge`
  - `auth_token`
  - `app`
  - `next`
- 新增 `assets/data/app-shell-config.json`，把壳的应用名、bundle id、scheme 和 tab 数据从页面逻辑中拆开，保持“数据和代码逻辑分离”。
- 新增 `assets/scripts/app-shell-live.js`，只负责读取配置、渲染 App 壳状态和复用现有页面入口。
- 新增 `app.webmanifest`，补齐第一版最小上架准备入口。
- 更新 `login.html` 和 `assets/scripts/login-live.js`，让登录成功后按 `next` 回跳，而不是固定回 `index.html`。
- 更新以下现有业务页的未登录跳转，统一保留当前页 `next`：
  - `assets/scripts/watch-live.js`
  - `assets/scripts/family-live.js`
  - `assets/scripts/device-binding-live.js`
  - `assets/scripts/detection-live.js`
  - `assets/scripts/monitor-live.js`
  - `assets/scripts/events-live.js`
  - `assets/scripts/event-detail-live.js`

产物位置：

- `app-shell.html`
- `app.webmanifest`
- `assets/data/app-shell-config.json`
- `assets/scripts/app-shell-live.js`
- `assets/scripts/edge-client.js`
- `assets/scripts/login-live.js`
- `login.html`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 打开 `http://127.0.0.1:8711/ui/app-shell.html?app=1`。
- 未登录时，App 壳应显示：
  - `待登录`
  - 主按钮跳转 `login.html?app=1&next=app-shell.html`
- 使用 `auth_token` 直进：
  - `http://127.0.0.1:8711/ui/app-shell.html?app=1&auth_token=...`
  - 页面应自动吃掉 token，并清理地址栏里的 `auth_token`
- 登录态进入 App 壳后，页面应展示：
  - `实时观看`
  - `家庭空间`
  - `设备绑定`
- 打开 `watch.html?app=1` 且无登录态时，应自动跳到：
  - `login.html?app=1&next=watch.html%3Fapp%3D1`
- 登录态下分别打开：
  - `family.html?app=1`
  - `device_binding.html?app=1`
  - 页面应正常加载原业务内容，不需要重新登录。

当前结果：

- `通过`

说明：

- 已在真实 `8711` 浏览器环境完成最小 App 壳真验收。
- `app-shell.html?app=1` 登录态真验收通过：
  - `statusBadge = 已接入`
  - 主入口为 `watch.html?app=1`
  - 三个入口为：
    - `watch.html?app=1`
    - `family.html?app=1`
    - `device_binding.html?app=1`
- 未登录进入 App 壳真验收通过：
  - `statusBadge = 待登录`
  - 主按钮为 `login.html?app=1&next=app-shell.html`
- `auth_token` 直进 App 壳真验收通过：
  - 页面地址已清理为 `/ui/app-shell.html?app=1`
  - 本地 token 已写入成功
- 业务页保留 `next` 真验收通过：
  - 未登录打开 `watch.html?app=1`
  - 自动跳到 `/ui/login.html?app=1&next=watch.html%3Fapp%3D1`
- 业务页复用真验收通过：
  - `family.html?app=1` 已正常展示当前家庭数据
  - `device_binding.html?app=1` 已正常展示当前设备数据
- 最近编辑文件诊断均为 `0`。

剩余问题和下一步：

- 当前完成的是“轻量混合壳 + H5 复用”第一版，还没有创建完整 iOS / Android 原生工程。
- 当前 `app.webmanifest` 仅用于最小打包准备，尚未补齐应用图标矩阵、启动图、权限说明文案和商店素材。
- 下一步按 `Plan` 顺序进入“多节点视频调度、真实公网域名和跨地域分发能力补齐”。

## 9.26 2026-06-29 多节点视频调度、真实公网域名和跨地域分发能力补齐记录

做了什么：

- 在 `edge-agent/app/storage.py` 新增 `video_service_nodes` 数据表，以及节点 upsert / 查询 / 列表数据层方法。
- 在 `edge-agent/app/schemas.py` 新增 `V1VideoServiceNodeUpsert`，并扩展 `PlaybackSessionCreate`、`V1MediaPublicLinkCreate`，把 `family_id`、`preferred_region`、`require_public` 等调度参数正式收口到契约层。
- 在 `edge-agent/app/video_distribution_service.py` 新增节点标准化、当前节点 fallback、节点注册、节点列表、活性判断、最小调度选择与绝对 URL 组装能力。
- 在 `edge-agent/app/video_service.py` 补齐：
  - `GET /api/v1/video/service-nodes`
  - `POST /api/v1/video/service-nodes`
  - `GET /api/v1/video/service-info`
  - `POST /api/v1/video/sessions`
  让视频会话返回调度后的 `service`、`selection`、`stream_url / asset_url`。
- 在 `edge-agent/app/object_storage_service.py` 让媒体资产和公网链接消费调度结果，返回调度后的 `public_url`、`service`、`selection`。
- 在 `edge-agent/app/main.py` 与 `edge-agent/app/video_app.py` 保持主入口薄接线，只把 `storage` 与设备身份解析器注入 `VideoDistributionService`，不把分发逻辑塞进入口。

产物位置：

- `edge-agent/app/storage.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/video_distribution_service.py`
- `edge-agent/app/video_service.py`
- `edge-agent/app/object_storage_service.py`
- `edge-agent/app/main.py`
- `edge-agent/app/video_app.py`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 重启 `8711` 上的 `edge-agent`，确保新路由已在线。
- 在真实浏览器环境注册新账号并创建新家庭。
- 将当前设备绑定到该家庭，确保通过 `require_device_access()`。
- 调用 `POST /api/v1/video/service-nodes` 依次登记：
  - 一个局域网 `origin` 节点：`http://10.0.0.8:9101`
  - 一个公网 `sg` `relay` 节点：`https://sg-video.example.com` / `https://sg-media.example.com`
- 调用 `GET /api/v1/video/service-nodes?family_id=22`，应返回 2 个节点。
- 调用 `GET /api/v1/video/service-info?family_id=22&preferred_region=sg&require_public=true`，应返回：
  - `selection.selected_node_id = sg-1782723861692`
  - `service.service_url = https://sg-video.example.com`
  - `service.media_url = https://sg-media.example.com`
- 调用 `POST /api/v1/video/sessions` 创建 `stream` 会话，实测返回：
  - `selection.selected_node_id = sg-1782723861692`
  - `stream_url = https://sg-video.example.com/api/v1/video/cameras/9/stream.mjpg`
- 调用 `POST /api/v1/media/upload-sessions` -> `PUT content` -> `POST complete` 创建测试资产，再调用 `POST /api/v1/video/sessions` 创建 `asset` 会话，实测返回：
  - `selection.selected_node_id = sg-1782723861692`
  - `asset_url = https://sg-media.example.com/api/v1/video/assets/12`
- 调用 `POST /api/v1/media/assets/12/public-links`，实测返回：
  - `selection.selected_node_id = sg-1782723861692`
  - `public_url = https://sg-media.example.com/api/public/media/assets/12?...`

当前结果：

- `通过`

说明：

- 已在真实 `8711` 浏览器环境完成本轮多节点调度真验收。
- 路由在线状态确认通过：
  - `GET /api/v1/video/service-nodes?family_id=1`
  - `GET /api/v1/video/service-info`
  - `GET /api/v1/runtime/app-status`
  都已不再返回 `404`，而是进入正式鉴权流程。
- 节点注册真验收通过：
  - 局域网节点 `local-1782723861692` 注册成功。
  - 公网节点 `sg-1782723861692` 注册成功。
- 节点查询真验收通过：
  - `GET /api/v1/video/service-nodes?family_id=22` 返回节点数 `2`
  - 节点顺序为：
    - `sg-1782723861692`
    - `local-1782723861692`
- 节点调度真验收通过：
  - `preferred_region = sg`
  - `require_public = true`
  - 命中节点 `sg-1782723861692`
  - 命中角色 `relay`
  - 命中区域 `sg`
- 视频会话真验收通过：
  - `stream` 资源返回公网 `sg` 视频地址。
  - `asset` 资源返回公网 `sg` 媒体地址。
- 公网媒体链接真验收通过：
  - `public_url` 已按选中媒体节点输出到 `https://sg-media.example.com/...`
- 最近编辑文件诊断均为 `0`。

剩余问题和下一步：

- 当前完成的是“多节点登记 + 最小调度 + 绝对 URL 分发”第一版，还没有实现真正跨机中继、边缘缓存、切片转封装和 QoS 主动探测。
- 当前 `service_url / media_url` 仍由节点登记时显式提供，尚未接入自动注册、DNS 管理或云厂商负载均衡控制台。
- 下一步按 `Plan` 顺序进入“盒子级自更新、自举守护和系统服务编排补齐”。

## 9.27 2026-06-29 盒子级自更新、自举守护和系统服务编排补齐记录

做了什么：

- 新增 `edge-agent/app/edge_bootstrap_service.py`，把盒子级 bootstrap 配置、启动脚本生成、`launchd plist` 生成和 `launchctl` 编排从入口层独立成服务层。
- 在 `edge-agent/app/settings.py` 新增：
  - `edge_bootstrap_dir`
  - `edge_bootstrap_logs_dir`
  - `edge_launch_agent_label`
  让 bootstrap 运行目录、日志目录和 `LaunchAgent label` 从配置层统一收口。
- 在 `edge-agent/app/main.py` 只做最小接线，新增正式接口：
  - `GET /api/v1/runtime/edge-service`
  - `POST /api/v1/runtime/edge-service/install`
  - `POST /api/v1/runtime/edge-service/reload`
  - `POST /api/v1/runtime/edge-service/uninstall`
- 让系统服务固定通过 bootstrap 脚本拉起当前 `edge-agent`，而不是把 `launchd` 逻辑散写到 `run.sh` 或路由里。
- 保持 `run.sh` 继续只做本地直启入口，不承担系统服务安装与编排逻辑。

产物位置：

- `edge-agent/app/edge_bootstrap_service.py`
- `edge-agent/app/settings.py`
- `edge-agent/app/main.py`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

运行时产物位置：

- `edge-agent/data/runtime/edge-bootstrap/config.json`
- `edge-agent/data/runtime/edge-bootstrap/bootstrap.py`
- `edge-agent/data/runtime/edge-bootstrap/com.gohome.edge-agent.plist`
- `~/Library/LaunchAgents/com.gohome.edge-agent.plist`
- `edge-agent/data/runtime/edge-bootstrap/logs/edge-bootstrap.log`
- `edge-agent/data/runtime/edge-bootstrap/logs/edge-bootstrap.error.log`

如何复现和验证：

- 重启 `8711` 上的 `edge-agent`，确保新路由已在线。
- 在真实浏览器环境注册新账号并创建新家庭。
- 将当前设备绑定到该家庭，确保通过 `require_device_access()`。
- 调用 `GET /api/v1/runtime/edge-service`，应返回：
  - `installed = false`
  - `loaded = false`
  - bootstrap 脚本、生成 plist、安装 plist 和日志路径
- 调用 `POST /api/v1/runtime/edge-service/install`，应完成：
  - 生成 bootstrap 产物
  - 将 plist 安装到 `~/Library/LaunchAgents`
  - 执行 `launchctl bootstrap`
  - 执行 `launchctl kickstart`
- 调用 `GET /api/v1/runtime/edge-service` 再次确认：
  - `installed = true`
  - `loaded = true`
  - `launchctl_status_code = 0`
- 调用 `POST /api/v1/runtime/edge-service/reload`，应完成重载并继续返回：
  - `installed = true`
  - `loaded = true`
- 调用 `POST /api/v1/runtime/edge-service/uninstall`，应完成：
  - `launchctl bootout`
  - 删除 `~/Library/LaunchAgents/com.gohome.edge-agent.plist`
- 调用 `GET /api/v1/runtime/edge-service` 最终确认：
  - `installed = false`
  - `loaded = false`

当前结果：

- `通过`

说明：

- 已在真实 `8711` 浏览器环境完成本轮盒子级 bootstrap 和系统服务编排真验收。
- 路由在线状态确认通过：
  - `GET /api/v1/runtime/edge-service`
  - `GET /api/v1/runtime/app-status`
  都已进入正式鉴权流程，不再返回 `404`。
- 状态接口真验收通过：
  - 安装前返回：
    - `installed = false`
    - `loaded = false`
    - `label = com.gohome.edge-agent`
    - `target_path = /Users/tanyihua/trae比赛/gohome/edge-agent/run.sh`
- 安装真验收通过：
  - `POST /api/v1/runtime/edge-service/install` 返回：
    - `installed = true`
    - `loaded = true`
    - `launchctl_status_code = 0`
  - `launchctl print` 片段里可见：
    - `type = LaunchAgent`
    - `state = running`
    - `arguments = ... bootstrap.py`
- 重载真验收通过：
  - `POST /api/v1/runtime/edge-service/reload` 返回：
    - `installed = true`
    - `loaded = true`
    - `launchctl_status_code = 0`
- 卸载真验收通过：
  - `POST /api/v1/runtime/edge-service/uninstall` 返回：
    - `installed = false`
    - `loaded = false`
  - 最终状态查询再次确认：
    - `installed = false`
    - `loaded = false`
- bootstrap 入口真验收通过：
  - `bootstrap_script_path = /Users/tanyihua/trae比赛/gohome/edge-agent/data/runtime/edge-bootstrap/bootstrap.py`
  - `generated_plist_path = /Users/tanyihua/trae比赛/gohome/edge-agent/data/runtime/edge-bootstrap/com.gohome.edge-agent.plist`
  - `installed_plist_path = /Users/tanyihua/Library/LaunchAgents/com.gohome.edge-agent.plist`
- 最近编辑文件诊断均为 `0`。

剩余问题和下一步：

- 当前完成的是“当前用户级 macOS LaunchAgent + 统一 bootstrap 入口”第一版，还没有做到 edge-agent 自身包的真正自替换、自举升级和版本迁移。
- 当前系统服务能力只覆盖 macOS `launchd`，尚未补齐 `systemd`、Windows Service 或 Docker 编排。
- 下一步按 `Plan` 顺序进入“试点安装 SOP、硬件清单和小规模商业化验证补齐”。

## 9.28 2026-06-29 试点安装 SOP、硬件清单和小规模商业化验证补齐记录

做了什么：

- 在 `edge-agent/README.md` 中新增一套当前可执行的试点安装 SOP，覆盖：
  - 材料准备
  - 安装前检查
  - 主机环境安装
  - 账号与家庭初始化
  - 摄像头接入与实时画面验证
  - `edge-service` 系统服务安装 / 重载 / 卸载
  - 首日验收口径
- 在 `edge-agent/README.md` 中补齐当前阶段硬件清单，明确：
  - 当前必备
  - 试点推荐
  - 本轮暂不推荐
- 在 `edge-agent/README.md` 中补齐 1-5 个家庭的小规模商业化验证矩阵，明确：
  - 试点目标项
  - 通过信号
  - 角色分工
  - 本轮退出条件
- 在 `想家了吗-Plan.md` 与 `想家了吗-Implement.md` 顶部把当前任务切到“试点安装 SOP、硬件清单和小规模商业化验证补齐”，让后续试点材料和实现顺序保持一致。

产物位置：

- `edge-agent/README.md`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 打开 `edge-agent/README.md`，确认新增以下正式章节：
  - `Pilot install SOP`
  - `Hardware checklist`
  - `Small-batch validation`
- 核对 SOP 中引用的当前真实入口和接口是否都已存在并在前两轮真验中通过：
  - `http://127.0.0.1:8711/health`
  - `http://127.0.0.1:8711/docs`
  - `http://127.0.0.1:8711/ui/login.html`
  - `http://127.0.0.1:8711/admin/cameras.html`
  - `GET /api/v1/runtime/edge-service`
  - `POST /api/v1/runtime/edge-service/install`
  - `POST /api/v1/runtime/edge-service/reload`
  - `POST /api/v1/runtime/edge-service/uninstall`
- 核对硬件清单和试点矩阵是否只基于当前已确认边界：
  - 主开发与主验证设备仍是当前 `M4 Mac / 24GB`
  - 试点候选仍以 `Mac mini / N100` 为近端部署优先
  - `Raspberry Pi` 仍只作为后续低功耗与长期运行验证，不反客为主
- 检查最近编辑文件诊断是否保持为 `0`。

当前结果：

- `通过`

说明：

- 当前试点材料已不再停留在高层描述，而是补成了可直接执行的 README 安装流。
- SOP 已与现有系统服务能力对齐：
  - 先启动 `edge-agent`
  - 再创建账号、家庭和设备绑定
  - 再添加摄像头和验证实时画面
  - 最后安装 `LaunchAgent`
- 硬件清单已与当前开发真实边界对齐，没有提前扩张到未验证的平台组合。
- 小规模商业化验证矩阵已明确 1-5 个家庭试点的目标、通过信号和退出条件，可直接用于下一阶段试点准备。
- 最近编辑文件诊断均为 `0`。

剩余问题和下一步：

- 当前完成的是“第一版试点交付材料”，还没有输出更细的现场网络排障树、摄像头兼容品牌清单和售后复装流程。
- 当前商业化验证仍停留在小规模试点口径，还没有扩张到正式报价单、合同、售后工单和大规模渠道交付。
- 下一步按 `Plan` 顺序进入“小规模公网试点和告警接收体验补齐”。

## 9.29 2026-06-29 小规模公网试点和告警接收体验补齐记录

做了什么：

- 新增 `edge-agent/app/public_pilot_service.py`，把公网试点状态、页面公网链接和通知打开链接的生成逻辑独立收口成服务层。
- 在 `edge-agent/app/main.py` 新增：
  - `GET /api/v1/public-pilot/status`
  - 并让 `dispatch_notification()`、`POST /api/v1/notifications/test` 统一走公网链接增强逻辑。
- 扩展 `edge-agent/app/schemas.py` 中的 `NotificationTest`，支持：
  - `event_id`
  - `camera_id`
  - `preferred_region`
  - `include_public_links`
- 扩展 `edge-agent/app/notifier.py`，让：
  - `feishu`
  - `bark`
  - `telegram`
  能在已有通道能力范围内附带打开链接。
- 保持主入口只接线，不把公网 base url 判断、事件页链接拼装和通知链接拼装散回路由层。

产物位置：

- `edge-agent/app/public_pilot_service.py`
- `edge-agent/app/main.py`
- `edge-agent/app/notifier.py`
- `edge-agent/app/schemas.py`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 重启 `8711` 上的 `edge-agent`，确保新路由已在线。
- 注册临时账号并创建家庭。
- 绑定当前设备，确保通过 `require_device_access()`。
- 调用 `GET /api/v1/public-pilot/status`：
  - 在默认本地环境下，应明确返回 `public_web / public_video / public_media / notification_channel` 各自是否就绪，而不是报错。
- 调用 `POST /api/v1/notifications/test`：
  - 即使通知通道当前为 `off`，也应在 `delivery.response.links` 中保留本次生成的页面链接结构。
- 给家庭注册一个公网视频节点后，再调 `GET /api/v1/public-pilot/status?preferred_region=sg`：
  - 应命中该公网节点
  - 并返回 `public_web_ready = true`
  - `public_video = true`
  - `public_media = true`
- 再调 `POST /api/v1/notifications/test`：
  - 应返回带公网 `app_shell_url / watch_url / events_url / event_url / open_url`
- 检查 `GET /api/v1/notifications/deliveries`：
  - 应能看到落库后的 `response.links` 和 `response.open_url`

当前结果：

- `部分通过`

说明：

- 路由在线真验收通过：
  - `GET /api/v1/public-pilot/status` 已在线，并进入正式鉴权流程，不再返回 `404`。
- 本地默认环境真验收通过：
  - 在未配置 `GOHOME_PUBLIC_BASE_URL`、未登记公网节点、通知通道为 `off` 的情况下，
  - 状态接口会明确返回：
    - `public_web = false`
    - `public_video = false`
    - `public_media = false`
    - `notification_channel = false`
  - 说明状态判断链路成立，没有再把“环境未就绪”和“代码错误”混在一起。
- 公网节点模拟真验收通过：
  - 已为临时家庭注册 `sg` 公网节点：
    - `service_url = https://sg-video.example.com`
    - `media_url = https://sg-media.example.com`
  - `GET /api/v1/public-pilot/status?preferred_region=sg` 返回：
    - `public_web_base_url = https://sg-video.example.com`
    - `public_web_ready = true`
    - `selected_node_id = sg-public-...`
    - `public_video = true`
    - `public_media = true`
- 通知链接生成真验收通过：
  - `POST /api/v1/notifications/test` 返回里的 `delivery.response` 已包含：
    - `app_shell_url`
    - `watch_url`
    - `events_url`
    - `event_url`
    - `open_url`
  - 其中 `open_url` 已正确指向：
    - `https://sg-video.example.com/ui/app-shell.html?app=1&next=event_detail.html%3FeventId%3D1`
- 通知落库真验收通过：
  - `GET /api/v1/notifications/deliveries` 中可看到最新记录的：
    - `response.links`
    - `response.open_url`
- 当前未完成项是“真实手机送达”：
  - 当前运行环境 `notify_channel = off`
  - 所以测试通知和事件通知状态均为 `skipped`
  - 这说明“链接生成和通知落库”已成立，但“真实手机接收体验”还差最后一步环境配置。
- 最近编辑文件诊断均为 `0`，`python3 -m py_compile` 已通过。

剩余问题和下一步：

- 当前还缺一个真实通知通道配置，例如 `bark / feishu / telegram / webhook` 之一，否则这轮无法收口为“完全通过”。
- 当前还没有真实公网域名和真实公网节点接入，只用模拟公网节点完成了代码能力验收。
- 下一步仍然是继续把本任务收口为“完全通过”：配置一个真实通知通道，并在真实公网节点或真实公网域名下完成最终手机送达验收。

## 9.30 2026-06-29 App 原生通知第一版补齐记录

做了什么：

- 新增 `edge-agent/app/app_push_service.py`，把 App 安装实例的 push token 注册、深链目标生成和 `app_push` 投递逻辑从旧的临时通知通道中拆开。
- 在 `edge-agent/app/storage.py` 新增 `app_push_tokens` 表，单独存储：
  - `user_id`
  - `family_id`
  - `app_install_id`
  - `platform`
  - `provider`
  - `push_token`
  - `environment`
  - `metadata`
- 在 `edge-agent/app/main.py` 新增正式接口：
  - `GET /api/v1/app/push-tokens`
  - `POST /api/v1/app/push-tokens`
  - `DELETE /api/v1/app/push-tokens/{app_install_id}`
  - `POST /api/v1/app/push-test`
- 在真实事件入口 `POST /api/v1/device/events` 中补齐 `app_push_delivery`，让事件触发后不再只走旧的临时通知通道。
- 在 `edge-agent/app/settings.py` 新增：
  - `GOHOME_APP_PUSH_PROVIDER`
  - `GOHOME_APP_PUSH_RELAY_URL`
  - `GOHOME_APP_PUSH_RELAY_SECRET`
  - `GOHOME_APP_DEEP_LINK_SCHEME`
- 在 `assets/scripts/edge-client.js` 中新增原生桥接 helper：
  - `nativeBridgeAvailable()`
  - `requestNativePushRegistration()`
  - `consumeNativeLaunchPayload()`
  - `resolveNativeBridgeResult()`
- 在 `assets/scripts/app-shell-live.js` 中补齐：
  - 原生壳存在时自动尝试读取 push token
  - 已登录后自动上报 token
  - 原生通知点击启动时承接 `next / event_id / camera_id`
- 保持 `app-shell.html` 只承接入口和登录态，不新开冗余页面，也不把原生推送逻辑散写到各业务页。

产物位置：

- `edge-agent/app/app_push_service.py`
- `edge-agent/app/storage.py`
- `edge-agent/app/main.py`
- `edge-agent/app/schemas.py`
- `edge-agent/app/settings.py`
- `assets/scripts/edge-client.js`
- `assets/scripts/app-shell-live.js`
- `app-shell.html`
- `想家了吗-Plan.md`
- `想家了吗-Implement.md`

如何复现和验证：

- 重启 `8711` 上的 `edge-agent`，确保新路由在线。
- 注册临时账号并创建家庭。
- 调 `POST /api/v1/app/push-tokens` 注册一个 `ios / apns / sandbox` token。
- 调 `GET /api/v1/app/push-tokens?family_id=...`，确认当前用户能看到刚注册的安装实例。
- 调 `POST /api/v1/app/push-test`，确认会创建一条 `channel = app_push` 的投递记录，并带出 `open_deep_link`。
- 再走一次 `POST /api/v1/device/events`，确认响应里会带回 `app_push_delivery`。
- 检查 `GET /api/v1/notifications/deliveries?limit=10`，确认落库里能看到 `channel = app_push` 的记录和深链目标。
- 打开 `http://127.0.0.1:8711/ui/app-shell.html?app=1`，模拟原生壳注入：
  - `registerForPush()`
  - `consumeLaunchPayload()`
  确认共享层能读到 token 和启动载荷。

当前结果：

- `通过`

说明：

- 路由在线验收通过：
  - `GET /api/v1/app/push-tokens` 未登录返回 `401`
  - `POST /api/v1/app/push-test` 未登录返回 `401`
  - 说明新路由已进入正式鉴权，不再是旧版本或 `404`
- App push token 注册验收通过：
  - 已成功注册 1 个 `ios / apns / sandbox` 安装实例
  - `POST /api/v1/app/push-tokens = 200`
  - `GET /api/v1/app/push-tokens?family_id=27 = 200`
  - 返回记录中已包含：
    - `app_install_id`
    - `platform = ios`
    - `provider = apns`
    - `environment = sandbox`
- App push 测试投递验收通过：
  - `POST /api/v1/app/push-test = 200`
  - 返回 `delivery.channel = app_push`
  - 返回 `delivery.status = skipped`
  - 原因是当前 `GOHOME_APP_PUSH_PROVIDER = off`
  - 但 `response.targets` 已正确生成：
    - `app_shell_deep_link = gohome://open?app=1`
    - `watch_deep_link = gohome://open?app=1&next=watch.html%3FcameraId%3D9`
    - `open_deep_link = gohome://open?app=1&next=watch.html%3FcameraId%3D9`
- 真实事件触发验收通过：
  - `POST /api/v1/device/events = 200`
  - 返回中已带回 `app_push_delivery`
  - `app_push_delivery.channel = app_push`
  - `app_push_delivery.event_id = 593`
  - `app_push_delivery.response.targets.event_deep_link` 已正确生成：
    - `gohome://open?app=1&next=event_detail.html%3FeventId%3D593`
- 投递落库验收通过：
  - `GET /api/v1/notifications/deliveries?limit=10 = 200`
  - 最新记录中可看到：
    - `channel = app_push`
    - `status = skipped`
    - `response.targets.open_deep_link`
- 原生桥接 helper 验收通过：
  - `http://127.0.0.1:8711/ui/app-shell.html?app=1` 页面中：
    - `window.GoHomeEdge.nativeBridgeAvailable` 存在
    - `window.GoHomeEdge.requestNativePushRegistration` 存在
    - `window.GoHomeEdge.consumeNativeLaunchPayload` 存在
  - 用模拟原生桥注入后，已成功拿到：
    - `app_install_id = bridge-install-1`
    - `push_token = bridge-token-1234567890`
    - `next = event_detail.html?eventId=321`
  - 共享层生成的 App 内目标链接为：
    - `event_detail.html?eventId=321&app=1`
- 最近编辑文件诊断均为 `0`
- `python3 -m py_compile app/storage.py app/app_push_service.py app/main.py app/schemas.py app/settings.py` 已通过

剩余问题和下一步：

- 当前只完成了 App 原生通知第一版的数据层、接口层、桥接层和深链承接。
- 当前还没有接入真实的 APNs / FCM relay，因此 `delivery.status` 仍是 `skipped`，没有做到真机系统通知送达。
- 下一步应该继续做：
  - 配置 `GOHOME_APP_PUSH_PROVIDER=relay`
  - 接一个最小 APNs / FCM relay
  - 用真实 iPhone / Android 真机做系统通知送达和点击回跳验收。

## 10. 立即开工清单

### 10.1 本地 Mac 算力服务固化

目标：让当前 Mac 像第一版“小盒子”一样长期运行。

要做：

- 新增本地配置文件，避免摄像头、端口、数据路径散落在环境变量和数据库里。
- 新增日志目录和日志轮转策略。
- 新增服务状态页或接口，展示进程、摄像头、模型、磁盘和最近错误。
- 新增 macOS 开机自启方案。
- 新增 watchdog 或自恢复脚本。

验收：

- 重启 Mac 后服务能自动恢复。
- 服务崩溃后能自动重启。
- 管理台能看到最近错误和运行状态。

### 10.2 用户端连接管理

目标：让人能按产品流程接入摄像头，而不是靠 curl 或技术配置。

要做：

- `connect.html` 读取当前摄像头列表。
- 支持添加局域网摄像头：IP、端口、账号、密码、RTSP 路径。
- 保存后调用 `/api/cameras`。
- 测试时调用 `/api/cameras/{id}/test`。
- 成功后显示真实截图。
- 允许选择房间和启用状态。

验收：

- 非技术用户可以按页面完成摄像头添加和测试。
- 用户端不暴露复杂调试字段；管理台保留高级配置。

### 10.3 规则配置产品化

目标：让用户端能配置看护能力，管理台能解释规则和算法。

要做：

- `rules.html` 接入 `/api/rules`。
- 已实现项：离线提醒、黑屏/遮挡、长时间无变化、人形检测、长时间无人、疑似跌倒候选。
- 待实现项：夜间异常活动、区域停留、生活节奏观察、陌生人提醒。
- 保存后立即同步到 `edge-agent`。

验收：

- 用户端规则状态和管理台规则状态一致。
- 规则保存后下一轮 worker 生效。

### 10.4 树莓派验证准备

目标：板子到手后能快速验证，不打断当前 Mac 主线。

要做：

- 新增 `docs/raspberry-pi-deploy.md`。
- 记录系统依赖、Python 环境、OpenCV / FFmpeg、服务启动方式。
- 记录性能策略：低分辨率子码流、低频抽帧、模型降采样。
- 记录硬件验证项：电源、散热、网线、存储、开机自启、断网恢复。

验收：

- 板子到手后按文档能部署 `edge-agent`。
- 树莓派只做硬件稳定性验证，不影响当前 Mac 本地产品闭环。

## 10.5 当前推荐执行顺序

为了减少返工，当前开发只按下面顺序推进：

1. 先做 `10.2 用户端连接管理` 的剩余闭环。
2. 再做 `10.3 规则配置产品化` 的剩余闭环。
3. 再做 `10.1 本地 Mac 算力服务固化`。
4. 然后做 `DetectionResult / RuleEvaluation / EventCandidate / Event` 数据层。
5. 然后接真实手机通知。
6. 最后再进入云端、App 和硬件试点。

## 11. 后续协作方式

从现在开始，后续开发按以下方式推进：

- 每次只做一个闭环任务，不并行发散。
- 每做完一个功能，就回写本文件的“完成记录”和“验收结果”。
- 只有当前任务明确通过，才进入下一个任务。
- 如需调整方向，先改 `PRD` 和 `Plan`，再改代码和 `Implement`。
