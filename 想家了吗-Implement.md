# 想家了吗 Implement

更新时间：2026-06-28

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

## 2. 当前运行方式

当前只需要启动一个服务：`edge-agent`。

启动命令：

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
GOHOME_AGENT_PORT=8711 GOHOME_DETECTOR_BACKEND=yolo ./run.sh
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
2. 接入 `connect.html` 添加摄像头、测试拉流、保存房间和选择主摄像头。
3. 接入 `rules.html` 规则配置。
4. 处理历史旧黑屏 / 本机摄像头离线事件。
5. 给 YOLO 人形结果补模型版本和规则命中原因。
6. 把检测结果拆成 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 的结构。
7. 配置一个手机通知通道。
8. 增加 Mac 开机自启、watchdog 和日志轮转。
9. 输出 Raspberry Pi 部署验证文档和脚本骨架。
10. 设计云端 `api/v1` 数据模型和设备上报接口草案。

每完成一项，都在本文件追加记录。

## 9. 2026-06-28 当前完成记录

- `edge-agent` 运行在 `8711`，当前本机服务地址为 `http://127.0.0.1:8711`，当前局域网服务地址为 `http://192.168.1.4:8711`。
- 已接入局域网摄像头 `192.168.1.11:554`，账号密码由摄像头配置保存，当前启用摄像头为 `id=3`，房间为“客厅”。
- 已禁用本机摄像头 `local:0`，避免 macOS 摄像头权限问题继续污染主流程。
- `snapshots` 表已新增 `width`、`height`、`analysis_json`，每次抓帧会保存 YOLO 检测结果、人数、人框、疑似跌倒候选、黑屏和运动信息。
- 管理台 `/admin/index.html` 已能展示真实截图、检测摘要、YOLO 人框叠加、规则开关和产品化检测项。
- 用户端 `/ui/monitor.html`、`/ui/events.html`、`/ui/index.html` 已接入本机 `edge-agent` 接口。
- 用户端事件列表和首页已过滤为当前启用摄像头事件，避免旧的本机摄像头测试告警影响产品状态。

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
