# 回家 Implement

更新时间：2026-07-21

## 1. 文档目的

这份文档记录 `回家` 第二阶段的真实实施进度、当前运行方式、已完成能力、未完成事项和下一步开发记录。

PRD 负责定义产品边界，Plan 负责定义实施顺序，Implement 负责记录“现在到底做到哪里了”。

### 1.0 记录约束

为了避免“原型看起来像完成了、实际产品却没对齐”的问题，`Implement` 固定遵守下面规则：

- 不把阶段 0 原型能力写成正式产品能力已完成。
- 不把局域网直连能力写成云端远程能力已完成。
- 不把页面原型文案写成正式消息平台已完成。
- 不把本地 token、绑定码、心跳第一版写成正式云端设备体系已完成。

任何一项实现回写前，都必须同时检查：

1. 这项能力是否已经在 `PRD` 里被定义。
2. 这项能力是否已经在 `Plan` 里进入当前阶段。
3. 当前记录的是“已完成”“部分通过”还是“尚未完成”。

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

## 1.1.1 2026-07-21 原生 iOS 支线决策（待实施）

本节是当前用户端最高优先级实现口径。后文关于 H5、陪伴页和 SwiftUI + WKWebView 壳的内容属于已完成历史验证，不代表正式 iOS 交付仍采用网页套壳。

已确认但尚未实现：

- 正式比赛交付切换为最低 iOS 16 的原生 SwiftUI App。
- 家属端五个主导航调整为首页、守护、事件、精选和我的；原“陪伴”页退出主导航。
- 回家提醒改为持久化消息和推送，消息详情生成真实上下文话题与可编辑发送参考，通过系统分享面板承接微信等目标，并记录已联系、稍后提醒或已回家。
- 精选页只推荐有真实来源和外链的非医疗类适老生活用品，不建立购物车、支付、订单、库存或物流。
- 云端 API、数据库、盒子同步、事件与视频继续复用；盒子视觉算法在原主线继续验收，本支线不修改。
- 现有家属端 Web 仅在迁移期用于对照。原生五个页面验收后停止公开入口，最终保留盒子管理、云端运维、隐私协议和帮助网页。

当前代码状态：

- `ios-shell` 仍是 SwiftUI + WKWebView 过渡壳，不能表述为原生主页面已经完成。
- 手机验证码仍含演示替身，APNs 尚未完成正式投递。
- PostgreSQL 已运行，但当前 Node 数据层仍以内存对象和整表替换方式保存，必须先改成实体级事务仓储。
- 原生设计规格已写入 `docs/superpowers/specs/2026-07-21-native-ios-app-redesign.md`；详细实施计划待规格评审后生成。

## 1.2 2026-06-28 路线确认（历史记录，已被 1.8 覆盖）

本节记录的是 2026-06-28 的阶段判断。2026-07-01 树莓派已到位且可 SSH 连接后，当前执行口径已切到 `1.8`：先做树莓派盒子侧能力，再做最小服务器，最后调整 App。

当时路线记录为：

- 先把当前 M4 / 24GB Mac 跑成第一版本地算力服务。
- 当前 Mac 负责 RTSP 拉流、YOLO 检测、规则判断、事件落库、Web 用户端和管理台。
- 树莓派或其他小盒子硬件可以开始采购，但暂时不作为主开发环境。
- 当时把树莓派定位为低功耗部署、开机自启、散热、断网恢复和 24 小时稳定性的后续验证设备。
- 当前重点是本地产品闭环，不是硬件迁移。

后续所有实现仍要按“未来边缘盒运行时”设计，避免只为当前 Mac 写死；但当前主验证对象已从 Mac 切换到树莓派盒子。

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

## 1.5 2026-06-30 盒子形态与正式产品链路对齐

本轮再次确认了产品目标：

- 树莓派或边缘盒负责本地视觉服务、局域网摄像头接入、事件生成和本地运行时。
- 正式 App 运行在云端产品体系之上，不直接访问盒子局域网地址。
- 用户完成盒子配网后，手机退出配网页，后续通过 App 登录云端继续使用。
- 用户在任意网络环境下都应能看到设备状态、告警、截图、短视频和被授权的实时画面。

对应当前项目状态判断如下：

### 已符合

- 当前 `edge-agent` 已能承担第一版本地守护盒原型。
- 已跑通局域网 RTSP 摄像头接入、测试、抓帧、检测、规则和事件链路。
- 已跑通 `登录 -> 家庭 -> 绑定设备 -> connect -> watch -> monitor -> events -> event_detail` 这条产品演示链。
- 已补齐树莓派部署文档、`.env` 运行口径、`systemd` 安装脚本和 24 小时验收准备。

### 仍未符合

- 当前手机端或 Web 仍主要直连本地 `edge-agent`，还不是正式云端远程产品。
- 当前还没有完整云端 `api/v1`、设备通道、设备密钥、设备注册和正式媒体服务。
- 当前还没有完成“用户在任意网络下通过 App 使用”的真实闭环。
- 当前设备 token 第一版仍以内置本地签发与消费为主，后续必须拆到正式云端设备身份体系。

### 本轮结论

- 当前项目符合“本地盒子原型”。
- 当前项目不等于“正式家庭版远程产品”。
- 后续文档、排期和实现都必须围绕“盒子本地处理 + 云端承接远程使用”这条正式链路推进，不能再把局域网页面直连能力表述成最终形态。

## 1.6 2026-06-30 执行顺序决策记录

本轮明确决定：

- 不直接重投入完整云端。
- 先把本地盒子闭环做成硬结果。
- 本地闭环通过后，再上最小云。

当前推荐执行顺序如下：

### 第一步：先树莓派盒子跑通

目标是先证明“盒子本地视觉服务可独立成立”，具体包括：

1. 在树莓派上部署并启动 `edge-agent`。
2. 盒子完成联网并具备稳定运行环境。
3. 接入一路真实 RTSP 摄像头并完成 720p 实时画面测试。
4. 跑通 `/setup` 手机配网入口和本地 `/admin` 管理台。
5. 跑通 `/admin/algorithms.html` 统一实时感知和 `/admin/logs` 日志诊断。
6. 跑通跌倒、火灾候选等高优先级测试报警。
7. 跑通至少一个真实通知通道。
8. 完成重启恢复、自启和 24 小时观察。

这一阶段的完成信号是：

- 盒子不依赖 IDE 手工盯着运行。
- 摄像头、检测、事件、截图、预览、日志和通知能持续工作。
- 重启后可以自动恢复。

### 第二步：再上最小云

本地盒子闭环稳定后，再进入最小云，不上复杂全量平台。

最小云只做三件事：

1. 设备身份：
   - 注册
   - 绑定
   - 心跳
2. 事件链路：
   - 事件上报
   - 事件列表
   - 事件详情
   - 处理状态同步
3. 媒体和播放：
   - 截图或短视频上传
   - 授权访问
   - 播放会话和播放鉴权

这一阶段的完成信号是：

- App/H5 不再依赖局域网 IP。
- 设备在线状态、事件和媒体都能通过云端读取。
- 用户离开老人家局域网后仍能继续使用。

### 第三步：最后切正式用户端

在最小云稳定后，再把正式 App/H5 切到云端。

当前明确不建议的顺序是：

- 盒子稳定性还没验证完，就先做完整云端。
- 设备、云端、App 三条线同时大规模展开。

### 明天树莓派的实际验收单

明天树莓派到手后，按下面顺序实操并记录结果：

1. 硬件准备
   - 电源、散热、系统、网络确认
   - 安装 `python3`、`ffmpeg`、`git`、`curl`
2. 环境准备
   - 克隆仓库
   - 创建 `.venv`
   - 复制 `.env.example` 为 `.env`
3. 前台启动
   - 运行 `./run.sh`
   - 检查 `/health`
   - 检查 `admin/index.html` 和 `ui/index.html`
4. 摄像头接入
   - 添加一路 RTSP 摄像头
   - 执行测试
   - 保存并启用
   - 抓取一帧验证
5. 主链验证
   - `connect -> watch -> monitor -> events -> event_detail`
   - 确认截图、状态和解释字段
6. 通知验证
   - 配置一个真实通知通道
   - 发送测试通知
   - 触发一次真实事件
7. 自启验证
   - 安装 `systemd`
   - 重启服务
   - 重启机器
8. 24 小时验证
   - 观察 crash loop
   - 观察温度、磁盘、内存
   - 观察摄像头是否持续在线

如果以上任一关键项未通过，先停留在本地闭环修复，不进入最小云开发。

### 最小云第一批接口范围

本地闭环通过后，第一批只进入下面这些接口，不扩张：

1. 设备身份
   - 注册
   - 激活 / 绑定
   - 心跳
   - 设备状态查询
2. 事件链路
   - 事件上报
   - 事件列表
   - 事件详情
   - 事件状态回写
3. 媒体与播放
   - 截图 / 短视频上传
   - 媒体元数据查询
   - 播放会话
   - 实时流播放鉴权

本轮判断标准：

- 如果树莓派还没稳定，不写云端全量服务。
- 如果本地事件和截图还不能稳定产生，不写远程事件平台。
- 如果本地实时流还不稳，不推进正式远程实时画面。

### Pi 到手当天命令清单

为了避免明天临场再组织命令，本轮先固定命令顺序如下：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git curl jq rsync
sudo apt install -y htop iotop
```

```bash
cd /home/pi
git clone <your-repo-url> gohome
cd /home/pi/gohome/edge-agent
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

如果当天同时验证 YOLO：

```bash
cd /home/pi/gohome/edge-agent
./.venv/bin/pip install -r requirements-yolo.txt
```

配置并启动：

```bash
cd /home/pi/gohome/edge-agent
cp .env.example .env
./run.sh
```

启动后验证：

```bash
curl http://127.0.0.1:8711/health
curl -I http://127.0.0.1:8711/ui/index.html
curl -I http://127.0.0.1:8711/admin/index.html
```

摄像头和事件验证：

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/1/test
curl -X POST http://127.0.0.1:8711/api/cameras/1/capture
curl 'http://127.0.0.1:8711/api/events?limit=10'
```

通知与自启：

```bash
cd /home/pi/gohome/edge-agent
bash scripts/send-test-notification.sh
bash scripts/install-systemd-service.sh
sudo systemctl status gohome-edge-agent --no-pager
```

观察命令：

```bash
journalctl -u gohome-edge-agent -n 200 --no-pager
journalctl -u gohome-edge-agent -f
free -h
df -h
uptime
vcgencmd measure_temp
```

### 设备状态机口径

后续实现统一按下面状态理解设备，不再各写各的：

- `factory_new`
- `wifi_config_pending`
- `registered`
- `activation_pending`
- `bound`
- `online`
- `offline`

关键规则：

- 未注册前，不上报正式事件。
- 未绑定前，不出现在家属可见设备列表。
- 离线只表示心跳超时，不等于解绑。
- 解绑只能由显式用户动作触发。

### 最小云第一批字段口径

第一批接口先按下面字段范围收口：

1. `devices/register`
   - `device_name`
   - `hardware_model`
   - `software_version`
   - `lan_ip`
   - 返回 `device_id`、`device_secret`、`status`
2. `devices/activate`
   - `device_id`
   - `binding_code`
   - 返回 `family_id`、`status`
3. `devices/heartbeat`
   - `device_id`
   - `status`
   - `lan_ip`
   - `software_version`
   - `camera_count`
   - `detector_backend`
4. `devices/{device_id}/events`
   - `camera_id`
   - `event_type`
   - `occurred_at`
   - `room`
   - `severity`
   - `reason`
   - `snapshot_id`
5. `devices/{device_id}/media`
   - `media_type`
   - `file_name`
   - `content_type`
   - 返回 `media_id`、`upload_url`

当前这批字段的目标不是做全，而是先把：

- 设备能注册
- 设备能绑定
- 设备能稳定心跳
- 事件和截图能上云
- App/H5 能读到最小远程数据

### 最小云第一批 schema 口径

为了避免接口开发时各自命名，先统一四个核心对象：

1. `Device`
   - `device_id`
   - `family_id`
   - `device_name`
   - `hardware_model`
   - `software_version`
   - `status`
   - `lan_ip`
   - `camera_count`
   - `last_heartbeat_at`
2. `Event`
   - `event_id`
   - `device_id`
   - `camera_id`
   - `event_type`
   - `room`
   - `severity`
   - `status`
   - `reason`
   - `occurred_at`
   - `snapshot_id`
3. `MediaAsset`
   - `media_id`
   - `device_id`
   - `camera_id`
   - `media_type`
   - `content_type`
   - `file_name`
   - `storage_key`
4. `PlaybackSession`
   - `session_id`
   - `device_id`
   - `camera_id`
   - `viewer_user_id`
   - `playback_ticket`
   - `expires_at`

本轮要求：

- `snapshot_id` 只引用媒体对象，不直接塞本地文件路径。
- 时间字段统一 ISO8601 UTC。
- 状态字段统一枚举，不允许页面自由拼接。

### 第一批开发任务顺序

后续进入最小云开发时，严格按下面顺序做：

1. 先做 `T1 设备身份`
   - 注册
   - 激活 / 绑定
   - 心跳
   - 设备状态查询
2. 再做 `T2 事件对象`
   - 事件上报
   - 事件列表
   - 事件详情
   - 事件状态回写
3. 再做 `T3 媒体对象`
   - 截图上传
   - 媒体元数据查询
   - 事件和媒体关联
4. 再做 `T4 播放会话`
   - 播放票据
   - 实时流鉴权
5. 最后做 `T5 edge-agent 接入改造`
   - 设备注册客户端
   - 心跳客户端
   - 事件上报客户端
   - 媒体上传客户端

为什么这样排：

- 没有设备身份，就没有远程设备语义。
- 没有事件对象，就没有远程产品价值。
- 没有媒体对象，事件详情就不完整。
- 没有播放会话，不适合急着做远程实时流。
- `edge-agent` 改造必须跟着云端对象走，不能反过来先写死。

## 1.7 2026-06-30 云端多模态、日志与回家消息缺口补记

本轮重新检查后，确认前面的文档虽然已经补齐了最小云主链，但还缺三条产品级链路的单独落位：

1. 云端多模态识别编排
2. 日志与诊断链路
3. 回家消息生成与推送链路

### 当前状态

- 当前项目已经具备边缘端视觉检测、规则判断、事件和通知接口的阶段 0 基线。
- 当前项目还没有正式云端多模态编排层，不能把事件进一步变成更稳定的产品消息层。
- 当前项目还没有云端日志接入、推送回执与审计日志的完整链路。
- 当前项目还没有“回家消息 / 陪伴消息”的正式生成服务，当前页面里的陪伴型文案更多还是原型展示，不是正式消息平台。
- 当前项目还没有统一的 `DeviceLog`、`NotificationReceipt`、`AuditLog` 云端对象口径。

### 本轮补充后的口径

- 云端多模态层的定位不是直接拉家庭视频，而是组合边缘端结构化结果、证据媒体、规则上下文和历史节奏。
- 日志链路的定位不是做一个大日志平台，而是先支撑安装、售后、推送失败和审计追踪。
- 回家消息链路的定位不是替代异常报警，而是在低危或陪伴场景下补一层“值得联系 / 值得回家 / 值得看一眼”的消息产品能力。
- `MessageCandidate`、`DeviceLog`、`NotificationReceipt`、`AuditLog` 已在文档层统一语义，后续接口和表结构必须复用这套命名。
- 场景化图文消息卡片不是独立主对象，而是 `MessageCandidate` 的渲染形态。
- 老人资料、家庭日历、天气信号、联系记录、回家记录已被确认为 `message-service` 的第二批输入域。

### 仍未完成

- 正式云端 `message-service` 还未实现。
- `log-service` 还未实现。
- `MessageCandidate`、推送回执、审计日志对象还未正式落库。
- `DeviceLog`、`NotificationReceipt`、`AuditLog` 还没有接口和表结构实现。
- 云端多模态编排层还没有进入代码实现阶段。
- `ContactRecord`、`VisitRecord` 还没有进入主文档已排期的正式接口和表结构实现。

### 后续顺序

- 先保证设备、事件、媒体和播放主链稳定。
- 再补日志与诊断链路。
- 最后补回家消息和陪伴消息生成，不抢前面的主链优先级。

### 本轮新增的对齐结果

这轮把四个对象正式压成统一口径：

1. `MessageCandidate`
   - 面向家属端的解释/陪伴/回家消息层
   - 必须引用来源事件或来源媒体
2. `DeviceLog`
   - 面向设备诊断的结构化日志对象
   - 只接收脱敏后的运行摘要和错误上下文
3. `NotificationReceipt`
   - 面向通知结果追踪的回执对象
   - 用于记录 accepted / delivered / clicked / failed
4. `AuditLog`
   - 面向责任追踪的审计对象
   - 用于记录查看、播放、确认、忽略、修改规则等关键动作

后续如果代码实现出现与这四个对象不一致的命名、字段或阶段顺序，应优先回到文档修正，不直接在代码里另起一套。

### 本轮继续补齐的契约层

这轮继续把“对象”压到了“可落库、可定义接口”的层，但仍然没有进入代码实现：

1. 已补第一批数据库表结构草案
   - `devices`
   - `events`
   - `media_assets`
   - `message_candidates`
   - `message_candidate_sources`
   - `notifications`
   - `notification_receipts`
   - `device_logs`
   - `audit_logs`
2. 已补统一业务错误码规范
   - 设备链路
   - 事件与媒体
   - 消息与通知
   - 日志与审计
3. 已补 `/api/v1` 的 OpenAPI 契约口径
   - schema 命名
   - tag 分组
   - 统一响应包裹
   - 错误响应格式

### 当前仍未完成

- 这些表结构还没有真正建 migration。
- 这些错误码还没有落实到接口返回。
- OpenAPI 还没有生成正式文档文件。
- `edge-agent` 端和未来云端服务端都还没有基于这套契约进入实现。

### 这一步的意义

到这里为止，文档已经不只是“方向正确”，而是已经具备：

- 产品对象
- 阶段边界
- 执行顺序
- 状态机
- schema 草案
- 表结构草案
- 错误码口径
- OpenAPI 契约口径

后面真正开始写云端代码时，应该先把这套文档当成唯一基线，而不是边写边想。

### 本轮与场景化图文消息补充需求的对齐结果

已确认并写回主文档的对齐结论：

1. 补充需求里的“图文消息卡片”属于 `MessageCandidate` 的展示层，不另起主对象。
2. 补充需求里的老人资料、日历、天气、联系记录、回家记录，已进入主文档的 `message-service` 第二批输入域。
3. 这批输入域的实现顺序必须晚于：
   - 设备身份
   - 事件主链
   - 媒体主链
   - 播放会话
   - 最小消息主链 `/api/v1/app/messages`
4. `阶段 0` 可以继续用 mock 数据或手动录入展示这些卡片，但不能宣称云端消息体系已完成。

### 本轮已开始的阶段 0 消息闭环实现

这一轮已经开始进入代码实现，但范围只限于 `阶段 0` 的本地最小闭环：

1. 已在 `edge-agent` 本地 SQLite 中新增：
   - `elder_profiles`
   - `calendar_events`
   - `message_candidates`
2. 已补本地消息相关 schema：
   - `ElderProfileUpsert`
   - `CalendarEventCreate`
   - `MessageGenerateRequest`
   - `MessageStatusUpdate`
3. 已补第一批接口：
   - `GET/PUT /api/v1/families/{family_id}/elders/{elder_id}/profile`
   - `GET/POST /api/v1/families/{family_id}/calendar-events`
   - `GET /api/v1/families/{family_id}/weather-signals`
   - `POST /api/v1/internal/messages/generate`
   - `GET /api/v1/app/messages`
   - `GET /api/v1/app/messages/{message_id}`
   - `PATCH /api/v1/app/messages/{message_id}`
4. 当前已接入的消息输入域只有：
   - `ElderProfile`
   - `CalendarEvent`
   - `WeatherSignal`（mock）
   - 边缘端现有 `Event`
5. 当前可生成的消息类型以演示为主：
   - 生日 / 回家建议
   - 天气关怀
   - 基于现有事件的一条解释型提醒
6. 当前 App/H5 已经接入一处最小承接位：
   - `index.html` 首页新增 `今日牵挂` 卡片区
   - `assets/scripts/home-live.js` 会优先读取 `/api/v1/app/messages`
   - 当家庭下还没有消息时，会再调用 `POST /api/v1/internal/messages/generate` 现场生成
   - 如果消息接口失败，首页会自动隐藏该区块，旧首页逻辑继续兜底
7. 2026-07-01 在线验收结果：
   - 运行中的 `8711` 服务重启后，`/openapi.json` 已能看到 `/api/v1/internal/messages/generate` 与 `/api/v1/app/messages`
   - 在真实页面 `http://127.0.0.1:8711/ui/index.html?app=1` 中，`今日牵挂` 卡片已真实显示
   - 当前登录家庭 `family_id=37`，在线读取到 2 条 `MessageCandidate`
   - 同一会话下再次调用生成接口，也能成功返回 2 条新消息
   - 当前首页实际展示的是基于真实边缘事件生成的 `alert` 型消息，说明首页已经能消费正式口径主对象 `MessageCandidate`
8. 已补第二处现有页面承接位，但仍不新开消息大页：
   - `companionship.html` 新增 `陪伴消息` 列表区，最多承接 3 条打开中的 `MessageCandidate`
   - 新增 `assets/scripts/companionship-live.js`，通过共享层 `GoHomeEdge` 读取 `/api/v1/app/messages`
   - 当当前家庭下还没有消息时，会调用 `POST /api/v1/internal/messages/generate` 补一批最小消息
   - 如果消息接口失败或当前用户未登录 / 无家庭，该区块会继续保持隐藏，不影响原有静态陪伴页
9. 2026-07-01 陪伴页在线验收结果：
   - 在真实页面 `http://127.0.0.1:8711/ui/companionship.html?app=1` 中，`陪伴消息` 区块已真实显示
   - 当前登录家庭 `family_id=37`，页面与接口都读取到 3 条打开中的消息
   - 首条消息为真实边缘事件生成的 `alert` 型消息
   - 卡片操作入口已保持 `app=1` 口径，当前验收到的首条卡片按钮为 `events.html?app=1` 和 `watch.html?app=1`
10. 已补消息轻量详情态，但仍不新开详情页：
   - `companionship-live.js` 现在支持卡片内 `查看详情 / 收起详情`
   - 展开后可直接看到 `message_id`、`status`、`generated_by`、来源引用和正文
   - 同一卡片内已补 `标记已读` 操作，直接调用 `PATCH /api/v1/app/messages/{message_id}`
11. 2026-07-01 轻量详情在线验收结果：
   - 在真实页面中点开首条消息后，详情区已展示 `MessageCandidate` 的扩展字段
   - 点首条 `标记已读` 后，列表已刷新到下一条打开中的消息，说明页面已能承接最小状态更新闭环
12. 已补消息状态反馈，不新增页面：
   - `companionship.html` 消息区头部新增即时反馈文案位
   - `companionship-live.js` 现在会把计数明确写成 `X 条打开中`
   - 点 `标记已读` 成功后，头部文案会即时变成“已将一条消息标记为已读，列表已刷新。”
   - 约 2.5 秒后会自动恢复成默认说明，不会一直停留在动作态
13. 2026-07-01 状态反馈在线验收结果：
   - 已捕获到动作刚执行后的头部文案为“上下文家庭2 · 已将一条消息标记为已读，列表已刷新。”
   - 稍后再次读取时，头部文案已自动恢复为“上下文家庭2 · 当前展示打开中的消息”

### 本轮仍未进入

- 还没有把这套消息接成独立的完整消息列表页和详情页。
- 还没有接 `ContactRecord`、`VisitRecord`。
- 还没有真实天气 API。
- 还没有图文卡片主图生成和模板回退。
- 还没有把 `message_candidates` 迁移成正式云端存储和多服务调用链。

## 1.8 2026-07-01 树莓派盒子能力纠偏记录

本轮根据树莓派已经到位、可 SSH 连接，以及产品安装场景重新确认当前实现方向。

核心结论：

- 接下来不先扩完整云端，也不先大改正式 App。
- 先把树莓派盒子侧做成可安装、可配网、可接摄像头、可看算法预览、可报警、可诊断、可自启的本地视觉盒子。
- 服务器和 App 必须排在盒子侧稳定之后。

### 本轮新增的产品要求

1. 盒子配网
   - 开发阶段可以继续用 Pi Imager 预填 Wi-Fi。
   - 产品化不能依赖 Pi Imager，必须支持首次通电后的安装模式。
   - 第一版优先做 Wi-Fi 热点配网：盒子发出 `GoHome-XXXX` 热点，手机连接后进入 `/setup`。
   - BLE 配网可以预留，但不阻塞第一轮树莓派验证。
2. 手机优先配网入口
   - 新增 `/setup` 作为手机优先页面。
   - 最新纠偏后，`/setup` 只覆盖：连接盒子热点、选择家庭 Wi-Fi、填写密码、连接中、成功提示、回到 `回家` App 或进入管理端。
   - `/setup` 不再承载绑定家庭、添加摄像头、测试画面、选择守护场景、测试报警和日志诊断。
3. 本地盒子管理台
   - `/admin` 定位为安装人员、研发、售后和高级管理员使用，形态接近路由器后台。
   - 盒子入网后通过 `gohome.local/admin` 或配网页显示的局域网 IP 进入。
   - 普通 App 不展示 RTSP 密码、模型原始输出、阈值和大段日志。
   - 本地管理台需要拆成：首页、摄像头配置、算法配置、算法预览、报警配置、日志诊断。
4. 算法预览
   - 新增 `/admin/preview`。
   - 选择一个摄像头，在同一真实画面查看全部视觉结果。
   - 实时画面上叠加检测框、区域或状态。
   - 页面显示当前输出、置信度、阈值、规则解释和最近日志。
   - 支持触发测试事件或测试报警，方便现场演示。
5. 第一批算法预览范围
   - 图像质量：亮度、对比度、清晰度、黑屏、遮挡。
   - 人形检测：人数、人框、置信度。
   - 长时间无人：当前无人时长、阈值和候选状态。
   - 长时间静止 / 久坐：基于运动变化、人体位置和时间窗。
   - 疑似跌倒：基于人框比例、位置、姿态或后续姿态模型。
   - 用餐行为候选：饭点时间、厨房/餐桌区域、人形存在和低移动组合判断。
   - 夜间异常活动：夜间时间窗、活动检测和作息基线。
   - 火灾候选：烟雾、明火、异常亮度变化或火焰颜色区域的视觉候选。
   - 摄像头异常：离线、黑屏、花屏、拉流延迟和最后成功取帧时间。
6. 应急报警
   - 疑似跌倒和火灾候选不能只进入普通事件列表。
   - 事件详情必须提供应急动作：查看证据、实时查看、打电话、通知家属、联系邻居/物业、拨打急救或火警电话、标记误报。
   - 报警渠道需要支持 App 推送、短信/电话/机器人或其它可验证通道中的至少一种。
   - 超时未处理时需要有升级通知策略。
7. 日志诊断
   - 新增 `/admin/logs` 或等价入口。
   - 需要能看到服务状态、摄像头拉流错误、检测错误、最近报警、磁盘/温度/内存等诊断信息。

### 当前已经具备的基础

- `edge-agent` 当前可以在 Mac 上运行，`8711` 在线链路已验证过摄像头、实时画面、检测、规则、事件和页面展示。
- 树莓派部署文档和 `systemd` 安装脚本已经存在。
- 管理台已经收口为首页、摄像头配置、算法配置三页。
- 当前检测链路已有图像质量、人形检测、长时间无人和疑似跌倒候选的基础。
- 本地消息卡片第一版已经开始接入 `MessageCandidate`。

### 当前尚未完成

- 树莓派真实设备上还没有完成完整部署验收。
- 还没有 Wi-Fi 热点配网。
- 还没有 BLE 配网。
- 还没有完成 `/setup` 纯配网页的最终收口验收。
- 还没有完成 `/admin` 登录保护、管理地址展示和开发管理模式验收。
- 还没有 `/admin` 算法预览能力的最终验收。
- 还没有 `/admin` 日志诊断能力的最终验收。
- 还没有火灾候选算法。
- 还没有用餐候选、夜间活动、久坐/静止的完整算法预览。
- 跌倒和火灾还没有完整报警渠道、升级策略和应急动作闭环。
- 当前事件归并和频控还不足，同类事件可能刷屏。
- 正式服务器设备绑定、配置下发、事件和媒体上云还没有完成。
- 正式 App 仍应等待盒子侧和最小服务器稳定后再系统调整。

### 最新执行顺序

1. 树莓派同步当前代码并前台启动 `edge-agent`。
2. 安装 `systemd` 并验证重启恢复。
3. 接入一路 H.264 / 720p RTSP 子码流。
4. 验证实时画面、抓帧、规则评估和事件详情。
5. 收口 `/setup` 纯配网页，并验证切换 Wi-Fi 导致页面断连时提示合理。
6. 收口 `/admin` 开发管理模式，补登录、IP 展示、网络状态和服务状态。
7. 在 `/admin` 完成摄像头接入、720p 子码流、实时画面、抓帧和断流恢复测试。
8. 在 `/admin` 补第一批算法预览和报警测试。
9. 在 `/admin` 补日志诊断和上传队列观察。
10. 做事件归并、频控和误报反馈。
11. 跑通至少一个真实通知或报警通道。
12. 再进入最小服务器。
13. 最后调整 App 安装模式和日常使用页面。

## 1.9 2026-07-02 盒子完整测试优先记录

本轮确认：当前不是继续做正式 App，也不是先扩服务器，而是先把硬件盒子的全部测试闭环跑完。

最新边界：

- 普通用户入口：`/setup`，只做 Wi-Fi 配网。
- 开发 / 管理入口：`/admin`，盒子联网后通过 `gohome.local/admin` 或局域网 IP 登录。
- App 名称统一为 `回家`。
- 摄像头接入、算法开关、算法预览、日志诊断、报警测试全部放在 `/admin` 或后续 App / 服务端，不放在 `/setup`。
- 盒子测试前必须先完成本地初始化；初始化不是联网成功后才做，而是首次启动时先生成设备身份、管理员凭证、hostname / mDNS 名称和运行目录。
- 开发阶段盒子管理端默认账号统一为 `admin / 123456`。

本轮要优先验证的盒子能力：

1. 初始化测试：设备 ID、本地密钥、管理员账号 `admin / 123456`、hostname / mDNS、数据目录、日志目录、初始化标记。
2. 配网测试：热点、选网、密码、切换网络断连提示、成功后的管理地址。
3. 管理端测试：登录、初始账号、改密、IP 获取、服务状态、网络状态、重启入口。
4. 摄像头测试：局域网扫描、RTSP 默认路径、用户名密码、端口、H.264 / 720p 子码流、首帧、延迟和花屏。
5. 视觉测试：一次只预览一个算法，至少覆盖图像质量、人形检测、久坐/静止、疑似跌倒、火灾候选和摄像头异常。
6. 报警测试：疑似跌倒和火灾候选必须能触发可验证报警或测试报警。
7. 事件测试：命中截帧、定时截帧、本地缓存、事件归并、频控和误报反馈。
8. 日志测试：服务日志、拉流错误、检测错误、报警投递、上传队列、CPU、温度、内存、磁盘。
9. 稳定性测试：重启恢复、服务自启、断网恢复、摄像头断流恢复和至少 24 小时运行记录。

初始化设计结论：

- 树莓派本体按钮只适合作为电源 / 重启级操作，不能直接当作产品级初始化按钮。
- 开发阶段先通过 SSH 或 `/admin` 触发初始化 / 恢复出厂。
- 产品化阶段需要在外壳增加独立长按按钮，接 GPIO，长按 8 到 10 秒后写入恢复标记并重启。
- 恢复出厂应清除 Wi-Fi、管理员密码、摄像头配置、算法配置和本地缓存，但保留硬件序列号。
- 如果用户现在的 Pi 已经通过 Pi Imager 连上 Wi-Fi，可以直接走“已联网初始化”路径：先生成本地身份和 `admin / 123456` 管理员凭证，再进入 `/admin` 测摄像头和算法。

盒子完整测试没有通过前，不再把“服务器已完整可用”或“App 已完整可用”作为当前阶段结论。

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
- 当前 iPhone / WebView 已能打开局域网页面做演示，但这仍属于阶段 0 验证，不代表正式远程使用能力已完成。

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

补充说明：

- 当前“设备绑定码、激活、心跳”第一版已经在本地 `edge-agent` 内跑通，但它的定位仍是阶段 0 到阶段 1 之间的本地验证接口。
- 这套本地设备身份流程后续必须迁移到正式云端设备体系，不能把当前本地实现当成最终设备平台。

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
- 树莓派 `systemd` 自启、watchdog、日志轮转、状态诊断页。
- 树莓派盒子 24 小时稳定性试点。

结论：

- 当前项目仍处于“阶段 0 树莓派盒子本地闭环进行中”。
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

1. 同步当前代码到树莓派，前台启动 `edge-agent`，确认 `/health`、`/admin` 和 `/ui`。
2. 安装 `systemd`，验证服务重启恢复、watchdog、日志目录和数据目录。
3. 接入一路真实 RTSP 摄像头，优先 H.264 / 720p 子码流，验证实时画面、截图和事件列表。
4. 新增或补齐 `/setup` 手机配网页。
5. 新增或补齐 `/admin` 开发管理模式和统一实时感知。
6. 新增或补齐 `/admin` 日志诊断。
7. 给 YOLO 和后续模型结果补模型版本、检测框、置信度、规则命中原因和可追踪字段。
8. 把检测结果拆成 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 的结构，并补事件归并和频控。
9. 配置一个真实手机通知或报警通道并做送达验收。
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

- 树莓派盒子侧能力闭环

本次任务要完成：

- 把当前代码同步到树莓派并前台启动 `edge-agent`。
- 安装并验证 `systemd` 自启，确认重启后服务自动恢复。
- 接入一路真实 RTSP 摄像头，优先使用 H.264 / 720p 子码流，降低延迟和花屏。
- 跑通实时画面、抓帧、规则评估、事件列表和事件详情。
- 新增或补齐 `/setup` 手机优先配网页，只做家庭 Wi-Fi 配网和成功提示。
- 新增或补齐 `/admin` 开发管理模式和统一实时感知能力，选择摄像头后同时展示全部检测结果。
- 新增或补齐 `/admin` 日志诊断能力，覆盖服务、拉流、检测、报警和系统状态。
- 补齐跌倒候选、火灾候选、用餐候选、久坐/静止、夜间活动、摄像头异常等演示级算法预览。
- 补事件归并、频控和高优先级报警测试，先解决 `no_person` 等重复事件刷屏。
- 跑通至少一个真实通知或可验证报警通道。

本次任务验收口径：

- 树莓派能在前台启动 `edge-agent`，`/health`、`/admin` 和 `/ui` 可打开。
- `systemd` 安装后，重启树莓派服务可自动恢复。
- 720p 实时画面延迟和花屏明显低于当前高码流状态。
- 真实 RTSP 摄像头能连续抓帧、检测、生成截图和事件。
- `/setup` 只承担 Wi-Fi 配网，不混入摄像头、算法、事件、日志和普通用户日常功能。
- `/admin` 能展示单算法实时效果、检测框、阈值、置信度、规则解释和最近日志。
- `/admin` 能定位拉流失败、检测异常、报警投递失败和系统状态。
- 跌倒和火灾候选能触发测试报警，并展示应急动作。
- 同类事件完成基础归并和频控，不能继续刷屏污染事件列表。
- 这轮仍不把正式云端和 App 主开发作为验收目标。

本次任务完成后回写：

- 树莓派部署路径、启动命令、服务状态和端口。
- 摄像头 RTSP 配置、码流档位、帧率、延迟和稳定性结果。
- 新增或修改的 `/setup`、`/admin` 算法预览、`/admin` 日志诊断文件和接口。
- 报警通道、应急动作和事件频控的验证方式。
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

- 树莓派真实设备完成前台启动、`systemd` 自启和重启恢复验收。
- 树莓派接入一路真实 RTSP 摄像头，优先 H.264 / 720p 子码流，完成连续拉流、抓帧和实时画面验收。
- `/setup` 手机配网页完成第一版验收。
- `/admin` 统一实时感知完成第一版验收。
- `/admin` 日志诊断完成第一版验收。
- 至少一个真实手机通知通道送达成功。
- 跌倒候选和火灾候选至少完成测试报警与应急动作展示。
- 事件归并和频控完成第一版，避免 `no_person` 等低价值事件刷屏。
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

## 9.1.22.1 2026-07-01 `privacy` 普通态 / 纪念态壳层同步记录

做了什么：

- 继续只做展示层，不碰设置逻辑和开关行为。
- 给 `privacy.html` 的顶部返回、页头标题、副标题、模式徽标和两处区块标题补上动态节点。
- 当纪念模式开启时，“我的”页会同步切到 `回忆设置 / 回忆模式设置 / 回忆陪伴 / 资料保护` 这一套文案口径；普通模式下则保持原来的 `我的 / 比赛演示版设置 / 关系提醒 / 守护方式`。
- 同时把“开启回忆模式”展开面板的底色和内部三张统计卡层次拉开，避免原来一整块灰蓝色堆在一起，信息不够分层。
- 把 `privacy.html` 中 `edge-client.js` 的版本戳抬到 `20260701-privacy1`，避免真实页面继续吃旧缓存。

产物位置：

- `privacy.html`

怎么验证：

- 对 `privacy.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `privacy.html?app=1&memorial=on`，读取页头与区块标题，确认已切到纪念模式文案，同时返回入口指向 `memorial_home.html?memorial=on&app=1`。
- 再打开 `privacy.html?app=1&memorial=off`，确认页头和区块标题回到普通模式文案，返回入口恢复为 `index.html?app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`privacy.html?app=1&memorial=on&cb=privacy-mem1` 当前标题为 `回忆模式设置`，区块标题为 `回忆陪伴` 和 `资料保护`，返回链接为 `memorial_home.html?memorial=on&app=1`。
- 同一页面切回普通模式后，页头回到 `我的 / 比赛演示版设置`，区块标题恢复为 `关系提醒 / 守护方式`，返回链接恢复为 `index.html?app=1`。
- 这样“我的”页在纪念模式下不再只换底部导航而保留普通模式语义，普通态和纪念态的展示口径已经对齐。

## 9.1.22.2 2026-07-01 `memorial_home` / `digital_human` 首屏进入感统一记录

做了什么：

- 继续只做展示层，不碰纪念模式页的跳转、聊天、底部导航和输入逻辑。
- 在 `memorial_home.html` 主视觉上方补了一条轻量模式说明条，先把“今天适合怎么进入回忆”说清楚，再进入主视觉卡片。
- 在 `digital_human.html` 聊天记录上方补了一条轻量页头，让页面不再像直接掉进聊天记录，而是先给出“今天适合慢慢说”的进入语气。
- 这两页都只补了一层轻提示，不新加业务交互，也不改原有 CTA 和输入区行为。

产物位置：

- `memorial_home.html`
- `digital_human.html`

怎么验证：

- 对 `memorial_home.html` 和 `digital_human.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `memorial_home.html?app=1&memorial=on` 和 `digital_human.html?app=1&memorial=on`。
- 观察首屏截图，确认 `memorial_home` 已出现模式说明条，`digital_human` 已出现轻量页头，同时聊天输入区和底部导航仍正常显示。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`memorial_home.html?app=1&memorial=on&cb=memorial-head2` 首屏新增 `MEMORY MODE` 说明条，`digital_human.html?app=1&memorial=on&cb=memorial-head2` 首屏新增 `PARALLEL WORLD` 说明条。
- `digital_human` 当前输入区 `chat-composer` 和底部导航 `bottom-nav` 仍正常存在，说明这次首屏补层没有把原有交互区挤坏。
- 这样纪念模式首页和聊天页的首屏语气已经更连贯：前者先引导“怎么进入回忆”，后者先引导“怎么开始说话”。

## 9.1.22.3 2026-07-01 `voice_archive` / `memory_gallery` 首屏进入层统一记录

做了什么：

- 继续只做展示层，不碰纪念模式声音页和记忆馆的按钮、素材卡、跳转与底部导航逻辑。
- 在 `voice_archive.html` 的主视觉前补了一条轻量进入说明，先把“今天适合先听哪一句”这件事说清楚，再进入声音主卡和推荐内容。
- 在 `memory_gallery.html` 的首屏主卡前补了一条轻量进入说明，让页面先给出“今天适合先看哪一组画面”的进入语气，再进入回看内容。
- 两页都沿用同一套安静、低打扰的说明层做法，只补一层首屏提示，不新增业务交互。

产物位置：

- `voice_archive.html`
- `memory_gallery.html`

怎么验证：

- 对 `voice_archive.html` 和 `memory_gallery.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `voice_archive.html?app=1&memorial=on&cb=memorial-media2` 和 `memory_gallery.html?app=1&memorial=on&cb=memorial-media2`。
- 观察首屏截图，确认两页都已出现新的进入说明层，同时原 hero、主卡和底部导航仍正常显示，没有被首屏补层挤坏。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`voice_archive.html?app=1&memorial=on&cb=memorial-media2` 首屏新增 `VOICE ARCHIVE` 说明条，`memory_gallery.html?app=1&memorial=on&cb=memorial-media2` 首屏新增 `MEMORY GALLERY` 说明条。
- `voice_archive` 当前“去平行世界”入口、声音主卡和底部导航仍正常存在；`memory_gallery` 当前主视觉大图、双按钮和底部导航也仍正常存在。
- 这样纪念模式里的“首页 -> 对话 -> 声音 -> 记忆馆”四个入口页，首屏都已有统一的进入语气，不再只有后两页直接落入内容主体。

补充收口：

- 把 `companionship.html`、`privacy.html`、`memorial_home.html`、`digital_human.html`、`voice_archive.html`、`memory_gallery.html` 的 `app.css` 版本戳统一抬到 `20260630-style10`，避免这些最近连续改动的页面在真实设备和 `WKWebView` 中继续命中旧样式缓存。
- 在真实 `8711` 在线页面环境下再次核验：`memorial_home.html?app=1&memorial=on&cb=style10-memorial`、`voice_archive.html?app=1&memorial=on&cb=style10-voice`、`privacy.html?app=1&memorial=on&cb=style10-privacy` 当前都已经加载 `assets/styles/app.css?v=20260630-style10`，且首屏说明、返回入口和底部导航仍正常存在。
- 这样最近一轮收过的陪伴页、我的页和纪念模式入口页，在真实运行态里都切回同一版样式缓存口径，减少“代码已改但设备仍显示旧样式”的假断层。

## 9.1.22.4 2026-07-01 `watch` / `monitor` / `detection` 样式缓存收口记录

做了什么：

- 继续只做展示层缓存收口，不碰实时画面、检测结果、摄像头切换和任何脚本逻辑。
- 把 `watch.html`、`monitor.html`、`detection.html` 的 `app.css` 版本戳统一从 `20260630-style1` 抬到 `20260630-style10`。
- 这一步只为解决实时链主页面在真实设备和 `WKWebView` 中可能继续命中旧样式缓存的问题，不改页面结构和业务行为。

产物位置：

- `watch.html`
- `monitor.html`
- `detection.html`

怎么验证：

- 对 `watch.html`、`monitor.html`、`detection.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `watch.html?app=1&cb=watch-style10`、`monitor.html?app=1&cb=watch-style10`、`detection.html?app=1&cb=watch-style10`。
- 在线读取样式链接与关键导航，确认三页都已加载 `assets/styles/app.css?v=20260630-style10`，同时 `camera_id` 和 `app=1` 续接仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`watch`、`monitor`、`detection` 三页当前都已加载 `assets/styles/app.css?v=20260630-style10`。
- `watch` 当前仍正常续传到 `monitor.html?camera_id=9&app=1` 和 `detection.html?camera_id=9&app=1`；`monitor` 和 `detection` 返回 `watch` 的入口也仍保留 `camera_id=9&app=1`。
- 这样实时守护主链里最常来回切换的三页，已经和最近一轮展示层页面统一到同一版样式缓存口径，减少真机验收时出现“局部页面还是旧视觉”的断层。

## 9.1.22.5 2026-07-01 `index` / `app-shell` / `family` / `device_binding` 样式缓存收口记录

做了什么：

- 继续只做展示层缓存收口，不碰登录态、家庭选择、设备绑定和入口跳转逻辑。
- 把 `index.html`、`app-shell.html`、`family.html`、`device_binding.html` 的 `app.css` 版本戳统一从 `20260630-style1` 抬到 `20260630-style10`。
- 这一步只为解决入口链页面在真实设备和 `WKWebView` 中继续命中旧样式缓存的问题，不改 DOM 结构和脚本行为。

产物位置：

- `index.html`
- `app-shell.html`
- `family.html`
- `device_binding.html`

怎么验证：

- 对 `index.html`、`app-shell.html`、`family.html`、`device_binding.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `index.html?cb=entry-style10`、`app-shell.html?app=1&cb=entry-style10`、`family.html?app=1&cb=entry-style10`、`device_binding.html?app=1&family_id=37&cb=entry-style10`。
- 在线读取样式链接与关键入口，确认四页都已加载 `assets/styles/app.css?v=20260630-style10`，同时 `app=1` 和 `family_id` 续接仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index`、`app-shell`、`family`、`device_binding` 四页当前都已加载 `assets/styles/app.css?v=20260630-style10`。
- `index` 当前仍正常进入 `app-shell.html?app=1`；`app-shell` 当前入口仍保留 `watch.html?camera_id=9&app=1`、`family.html?app=1` 等主链链接；`device_binding` 返回入口仍保留 `family.html?family_id=37&app=1`。
- 这样“首页 -> App 壳 -> 家庭 -> 绑定设备”这条入口链，已经和实时守护链、纪念模式页、陪伴页统一到同一版样式缓存口径，减少真机验收时前半程还是旧视觉的断层。

## 9.1.22.6 2026-07-01 `login` / `rules` 样式缓存收口记录

做了什么：

- 继续只做展示层缓存收口，不碰登录表单、规则读取保存和页内交互逻辑。
- 把 `login.html`、`rules.html` 的 `app.css` 版本戳统一从 `20260630-style7` 抬到 `20260630-style10`。
- 这一步只为解决登录页和规则页在真实设备与 `WKWebView` 中继续命中旧样式缓存的问题，不改结构和脚本行为。

产物位置：

- `login.html`
- `rules.html`

怎么验证：

- 对 `login.html` 和 `rules.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下分别打开 `login.html?cb=style10-login`、`rules.html?app=1&cb=style10-rules`。
- 在线读取样式链接与关键节点，确认两页都已加载 `assets/styles/app.css?v=20260630-style10`，同时登录输入框、规则页返回入口和保存按钮仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`login`、`rules` 两页当前都已加载 `assets/styles/app.css?v=20260630-style10`。
- `login` 当前仍保留 3 个输入框；`rules` 当前返回入口仍为 `monitor.html?app=1`，保存按钮 `saveRulesButton` 也仍正常存在。
- 这样首页、入口链、实时链、陪伴页、我的页、纪念模式页、登录页和规则页都已经统一到同一版样式缓存口径，当前最明显的“页面还是旧视觉缓存”断层已基本清完。

## 9.1.22.7 2026-07-01 语义色与局部运行时样式统一记录

做了什么：

- 继续只做展示层，不碰首页、守护页、纪念模式页和事件详情页的业务逻辑。
- 在 `assets/styles/app.css` 补了 `app-tone-info / app-tone-warn / app-tone-good` 三个轻量语义文本类，让“事实 / 感觉 / 行动 / 下一步”这类辅助标签不再手写零散色值。
- 把 `index.html`、`memorial_home.html`、`voice_archive.html` 的三组语义图标统一改成 `app-story-icon info / warn / good`，并把 `index.html`、`memory_gallery.html`、`event_detail.html` 的辅助标签改成统一语义文本类。
- 另外收掉了一处真实运行时断点：`assets/scripts/monitor-live.js` 之前会在渲染后把 `edgeStatusIcon` 重新写回硬编码的橙绿类名；本轮改成统一写 `app-story-icon warn / good`，并把 `monitor.html` 的脚本版本戳抬到 `20260701-tone1`。
- 因为 `app.css` 新增了语义文本类，这一轮涉及的 `index / monitor / memorial_home / voice_archive / memory_gallery / event_detail` 同步把样式版本戳从 `style10` 抬到 `style11`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `index.html`
- `monitor.html`
- `assets/scripts/monitor-live.js`
- `memorial_home.html`
- `voice_archive.html`
- `memory_gallery.html`
- `event_detail.html`

怎么验证：

- 对上述 CSS / HTML / JS 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `index.html?cb=tone-unify2`、`memory_gallery.html?app=1&memorial=on&cb=tone-unify2`、`monitor.html?app=1&cb=tone-monitor3`。
- 在线读取样式链接、语义类名和计算后的颜色值，确认 `warn / good` 文本色已经分别生效为橙色和绿色，同时 `monitor` 的状态图标类不再被运行时脚本写回硬编码色值。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index` 和 `memory_gallery` 当前都已加载 `assets/styles/app.css?v=20260630-style11`，其中 `感觉 / 情绪` 的计算颜色为 `rgb(200, 123, 42)`，`下一步 / 行动` 的计算颜色为 `rgb(45, 125, 92)`。
- `monitor` 当前也已加载 `assets/styles/app.css?v=20260630-style11`，并且 `edgeStatusIcon` 的运行时类名已经变成 `app-story-icon good shrink-0`，不再被旧脚本写回硬编码色值。
- 这样这组页面里的语义图标和语义文本终于回到同一套视觉口径，不再出现“模板改了但运行时又被写回旧色值”的假统一状态。

## 9.1.22.8 2026-07-01 `companionship` / `privacy` / `index` 细碎语义色收口记录

做了什么：

- 继续只做展示层，不碰首页、陪伴页和我的页的逻辑与交互。
- 在 `assets/styles/app.css` 新增 `app-bg-good`，把首页头部状态点从手写绿色背景收口到统一类。
- 把 `index.html` 里剩余的绿色提示文本和“建议动作”标签改成 `app-tone-good`，把状态点改成 `app-bg-good`。
- 把 `companionship.html` 里“周六回家”和“看了一眼就挂了”这两处残留橙色文本改成 `app-tone-warn`。
- 把 `privacy.html` 里“纪念日与回忆”区块的 `cake` 图标改成 `app-tone-warn`。
- 因为 `app.css` 新增了 `app-bg-good`，本轮涉及的 `index / companionship / privacy` 同步把样式版本戳抬到 `style12`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `index.html`
- `companionship.html`
- `privacy.html`

怎么验证：

- 对上述 CSS / HTML 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `index.html?cb=style12-index`、`companionship.html?app=1&cb=style12-companionship`、`privacy.html?app=1&cb=style12-privacy`。
- 在线读取样式链接和计算后的颜色值，确认三页都已加载 `assets/styles/app.css?v=20260630-style12`，并且对应的绿色/橙色语义色已经真实生效。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index` 当前已加载 `assets/styles/app.css?v=20260630-style12`，头部状态点、设备文案和“建议动作”文案的计算颜色都已统一到绿色语义口径。
- `companionship` 当前也已加载 `assets/styles/app.css?v=20260630-style12`，其中“周六回家”和“看了一眼就挂了”的计算颜色都为 `rgb(200, 123, 42)`。
- `privacy` 当前同样已加载 `assets/styles/app.css?v=20260630-style12`，`cake` 图标的计算颜色为 `rgb(200, 123, 42)`。
- 这样首页、陪伴页和我的页里剩下最散的硬编码语义色也被收进统一类，细节层级更干净。

## 9.1.22.9 2026-07-01 入口链表单控件层次统一记录

做了什么：

- 继续只做展示层，不碰 `family`、`device_binding`、`connect` 的表单提交和跳转逻辑。
- 在 `assets/styles/app.css` 新增 `app-form-field`，把入口链里散写的输入框和下拉框收口成一套统一表单样式。
- 把 `family.html` 里的家庭名称输入框改成 `app-form-field`。
- 把 `device_binding.html` 里的家庭下拉框和备注输入框改成 `app-form-field`。
- 把 `connect.html` 里的名称、房间、IP、端口、账号、密码、路径这 7 个输入框全部改成 `app-form-field`。
- 因为 `app.css` 新增了 `app-form-field`，本轮涉及的 `family / device_binding / connect` 同步把样式版本戳抬到 `style13`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `family.html`
- `device_binding.html`
- `connect.html`

怎么验证：

- 对上述 CSS / HTML 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `family.html?app=1&cb=style13-family`、`device_binding.html?app=1&family_id=37&cb=style13-binding`、`connect.html?app=1&cb=style13-connect`。
- 在线读取样式链接和表单控件计算样式，确认三页都已加载 `assets/styles/app.css?v=20260630-style13`，并且输入框/下拉框高度、圆角和背景层次已经统一。
- 同时检查入口参数，确认 `device_binding` 返回入口仍保留 `family_id=37&app=1`，`connect` 下一步入口仍保留 `monitor.html?camera_id=9&app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`family` 当前输入框类名已变成 `app-form-field`，计算高度为 `44px`、圆角为 `18px`、背景为 `rgba(250, 245, 240, 0.96)`。
- `device_binding` 当前家庭下拉框和备注输入框都已切成 `app-form-field`，并且返回入口仍为 `family.html?family_id=37&app=1`。
- `connect` 当前 7 个输入框都已切成 `app-form-field`，同时“下一步”入口仍为 `monitor.html?camera_id=9&app=1`。
- 这样入口链这组最常用的表单控件，视觉层次终于统一到同一套边框、背景和圆角口径里。

## 9.1.22.10 2026-07-01 首页与检测页按钮交互态收口记录

做了什么：

- 继续只做展示层，不碰 `index`、`detection` 的按钮跳转和业务逻辑。
- 在 `assets/styles/app.css` 的 `app-btn-primary / app-btn-secondary` 中补上统一的 `transform / box-shadow / background-color / opacity` 过渡。
- 同时给 `app-btn-primary / app-btn-secondary` 补上统一的 `:active` 缩放态，给 `app-btn-secondary` 补上统一的 `:hover` 背景态。
- 把 `index.html` 里 4 个主次按钮上的 `transition-all / hover:bg-primary/5 / active:scale-[0.98]` 重复类移除，改为完全由公共按钮样式接管。
- 把 `detection.html` 里“抓取一帧”和“去看事件”按钮上的 `active:scale-[0.98]` 移除，改为完全由公共按钮样式接管。
- 因为 `app.css` 的按钮基线有新增，本轮涉及的 `index / detection` 同步把样式版本戳抬到 `style14`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `index.html`
- `detection.html`

怎么验证：

- 对上述 CSS / HTML 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `index.html?cb=style14-index`、`detection.html?app=1&cb=style14-detection`。
- 在线读取样式链接、按钮类名和计算后的过渡属性，确认两页都已加载 `assets/styles/app.css?v=20260630-style14`，并且按钮过渡已由公共样式接管。
- 同时检查按钮链接，确认首页“家庭空间”仍为 `family.html?app=1`，检测页“去看事件”仍保留 `events.html?camera_id=9&app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index` 当前 4 个主次按钮类名里已不再包含 `transition-all / hover:bg-primary/5 / active:scale-[0.98]`，按钮计算过渡属性为 `transform, box-shadow, background-color, opacity`。
- `detection` 当前两个主次按钮类名里也已不再包含 `active:scale-[0.98]`，按钮计算过渡属性同样为 `transform, box-shadow, background-color, opacity`。
- `index` 的“家庭空间”入口仍为 `family.html?app=1`，`detection` 的“去看事件”入口仍为 `events.html?camera_id=9&app=1`。
- 这样首页和检测页里原先散写在标签上的按钮交互态，已经回到公共按钮基线里，后续继续收按钮态时就不用再逐页补同一串类。

## 9.1.22.11 2026-07-01 `monitor` 卡片按压态收口记录

做了什么：

- 继续只做展示层，不碰 `monitor` 的数据读取、状态渲染和页面跳转逻辑。
- 在 `assets/styles/app.css` 新增 `app-pressable`，把卡片型入口的按压态和过渡统一成一套公共样式。
- 把 `monitor.html` 里“去看细节”“接入画面”“刚刚发生”这 3 个入口上的 `active:scale-[0.99] / transition-transform` 移除，改为统一挂 `app-pressable`。
- 因为 `app.css` 新增了 `app-pressable`，本轮涉及的 `monitor` 同步把样式版本戳抬到 `style15`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `monitor.html`

怎么验证：

- 对上述 CSS / HTML 文件运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `monitor.html?app=1&cb=style15-monitor`。
- 在线读取样式链接、卡片类名和计算后的过渡属性，确认页面已加载 `assets/styles/app.css?v=20260630-style15`，并且这 3 个入口都已由 `app-pressable` 接管按压态。
- 同时检查入口链接，确认“去看细节”仍为 `detection.html?camera_id=9&app=1`，“接入画面”仍为 `connect.html?app=1`，“刚刚发生”仍为 `events.html?camera_id=9&app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`monitor` 当前已加载 `assets/styles/app.css?v=20260630-style15`。
- “去看细节”“接入画面”“刚刚发生”这 3 个入口当前类名都已切到 `app-pressable`，计算过渡属性为 `transform, box-shadow, background-color, opacity`。
- 对应入口链接仍保持 `detection.html?camera_id=9&app=1`、`connect.html?app=1`、`events.html?camera_id=9&app=1`，没有影响主链导航。
- 这样 `monitor` 里残留的卡片按压态也回到公共基线，主链页面的交互层级更一致了。

## 9.1.22.12 2026-07-01 底部导航 hover 样式收口记录

做了什么：

- 继续只做展示层，不碰底部导航的结构、链接生成和业务逻辑。
- 在 `assets/styles/app.css` 给 `app-bottom-nav` 下的 `app-nav-pill` 补上统一 hover 规则，让非激活态导航盒子的 hover 背景和文字色由公共样式接管。
- 把 `index.html`、`monitor.html`、`detection.html`、`events.html`、`companionship.html`、`privacy.html`、`family.html`、`device_binding.html`、`connect.html`、`rules.html` 里散写的 `group-hover:bg-primary/5` 从底部导航盒子上移除。
- 同时把 `privacy.html` 里动态底部导航的 `box.className` 也从 `app-nav-pill group-hover:bg-primary/5` 改成 `app-nav-pill`。
- 因为 `app.css` 的导航基线有新增，本轮涉及的上述 10 个页面统一把样式版本戳抬到 `style16`，避免真实浏览器继续吃旧 CSS。

产物位置：

- `assets/styles/app.css`
- `index.html`
- `monitor.html`
- `detection.html`
- `events.html`
- `companionship.html`
- `privacy.html`
- `family.html`
- `device_binding.html`
- `connect.html`
- `rules.html`

怎么验证：

- 对 `app.css`、`index.html`、`monitor.html`、`privacy.html` 运行编辑器诊断，结果保持为 `0`。
- 搜索上述页面和脚本，确认已不存在 `group-hover:bg-primary/5` 与旧的 `box.className = 'app-nav-pill group-hover:bg-primary/5';`。
- 在真实 `8711` 在线页面环境下打开 `index.html?cb=style16-index`、`monitor.html?app=1&cb=style16-monitor-nav`、`privacy.html?app=1&cb=style16-privacy-nav`。
- 在线读取样式链接、底部导航盒子类名和底部导航链接，确认 3 页都已加载 `assets/styles/app.css?v=20260630-style16`，且底部导航盒子类名已只剩 `app-nav-pill` 或 `app-nav-pill active`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`index`、`monitor`、`privacy` 当前都已加载 `assets/styles/app.css?v=20260630-style16`。
- 这 3 页底部导航盒子当前类名都已经只剩 `app-nav-pill` 或 `app-nav-pill active`，不再散写 `group-hover:bg-primary/5`。
- 对应底部导航入口仍保持正常：例如 `index` 当前仍为 `index.html?app=1 / monitor.html?camera_id=9&app=1 / events.html?camera_id=9&app=1 / privacy.html?app=1`；`monitor` 当前仍为 `index.html?app=1 / monitor.html?app=1 / events.html?camera_id=9&app=1 / companionship.html?app=1 / privacy.html?app=1`；`privacy` 在纪念模式下仍正确生成 `memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这组 `?memorial=on&app=1` 链接。
- 这样底部导航的 hover 表现也回到公共导航基线里，导航层的视觉口径基本统一了。

## 9.1.22.13 2026-07-01 `digital_human` 首屏开场过渡补层记录

做了什么：

- 继续只做展示层，不碰聊天消息、输入区、视频通话浮层和底部导航逻辑。
- 在 `digital_human.html` 的首屏说明条和聊天正文之间补了一张轻量开场提示卡，让页面先落到“先从一句熟悉的话开始”，再进入第一条对话。
- 同时把 `digital_human.html` 的 `app.css` 版本戳抬到 `20260630-style16`，与当前全站展示基线保持一致。

产物位置：

- `digital_human.html`

怎么验证：

- 对 `digital_human.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `digital_human.html?app=1&memorial=on&cb=hero-audit4`。
- 在线读取首屏新增提示、输入区、底部导航和样式链接，确认新增提示存在，`chat-composer` 与 `bottom-nav` 仍正常存在，并已加载 `assets/styles/app.css?v=20260630-style16`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`digital_human` 首屏当前新增 `先从一句熟悉的话开始` 的轻量提示，正文会从“我在呢”这一句自然接上，不再由说明条直接掉进聊天记录。
- 当前输入区 `chat-composer` 和底部导航 `bottom-nav` 仍正常存在，没有被新增首屏层挤坏。
- 这样 `digital_human` 的首屏进入节奏比上一轮更顺一层：先说明今天适合慢慢说，再给一句开场提示，最后进入真实对话。

## 9.1.22.14 2026-07-01 `memorial_home` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `memorial_home` 的主视觉、推荐顺序、CTA 和底部导航逻辑。
- 把 `memorial_home.html` 的 `app.css` 版本戳从 `20260630-style11` 抬到 `20260630-style16`，让它和最近已收过的纪念模式页保持同一版样式缓存口径。

产物位置：

- `memorial_home.html`

怎么验证：

- 对 `memorial_home.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `memorial_home.html?app=1&memorial=on&cb=hero-audit6`。
- 在线读取样式链接、页内 CTA 和底部导航，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且 `先听她说话 / 去平行世界 / 记忆馆 / 声音 / 我的` 这些入口仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`memorial_home` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 页内 CTA 仍保持 `voice_archive.html?app=1&memorial=on`、`digital_human.html?app=1&memorial=on`，底部导航仍保持 `memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这一组 `?app=1&memorial=on` 链接。
- 这样纪念模式首页不再停留在旧样式缓存口径，和刚收过的 `digital_human` 以及其他纪念模式入口页回到同一版展示基线。

## 9.1.22.15 2026-07-01 `watch` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `watch` 的实时流、画面切换、档位切换和事件入口逻辑。
- 把 `watch.html` 的 `app.css` 版本戳从 `20260630-style10` 抬到 `20260630-style16`，让实时观看页和最近已收过的首页、守护页、纪念模式页保持同一版样式缓存口径。

产物位置：

- `watch.html`

怎么验证：

- 对 `watch.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `watch.html?app=1&cb=watch-style16`。
- 在线读取样式链接和 5 个关键入口，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，并且 `watchMonitorTopLink`、`watchDetectionTopLink`、`watchEventsLink`、`watchMonitorLink`、`watchDetectionLink` 仍都显式带上同一个 `camera_id` 与 `app=1`。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`watch` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 关键入口当前仍保持 `monitor.html?camera_id=9&app=1`、`detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1` 这一组上下文续接，没有被样式口径调整影响。
- 这样实时观看页不再停留在旧样式缓存口径，和已经收过的主链页面重新回到同一版展示基线。

## 9.1.22.16 2026-07-01 `app-shell` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `app-shell` 的壳层状态、登录承接、主按钮和演示链入口逻辑。
- 把 `app-shell.html` 的 `app.css` 版本戳从 `20260630-style10` 抬到 `20260630-style16`，让 App 壳入口页和最近已收过的首页、实时页、守护页保持同一版样式缓存口径。

产物位置：

- `app-shell.html`

怎么验证：

- 对 `app-shell.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `app-shell.html?app=1&cb=appshell-style16`。
- 在线读取样式链接以及 `appShellPrimaryAction`、`appShellSecondaryAction`、`appShellHomeLink`、`appShellWatchLink`、`appShellEventsLink`，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且主链入口仍保持原有链接口径。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`app-shell` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 关键入口当前仍保持 `watch.html?camera_id=9&app=1`、`family.html?app=1`、`index.html?app=1`、`events.html?camera_id=9&app=1` 这一组入口，没有被样式口径调整影响。
- 这样 App 壳入口页不再停留在旧样式缓存口径，和已经收过的主链页面重新回到同一版展示基线。

## 9.1.22.17 2026-07-01 `login` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `login` 的登录、注册、已登录态切换和脚本逻辑。
- 把 `login.html` 的 `app.css` 版本戳从 `20260630-style10` 抬到 `20260630-style16`，让登录入口页和最近已收过的主链页面保持同一版样式缓存口径。

产物位置：

- `login.html`

怎么验证：

- 对 `login.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `login.html?cb=login-style16`。
- 在线读取样式链接、输入框数量、提交按钮文案和已登录态主按钮，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且 `3` 个输入框、`立即登录` 按钮和 `进入首页` 按钮仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`login` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 当前登录页仍保留 `3` 个输入框、提交按钮 `立即登录`，已登录态卡片主按钮 `进入首页` 也仍正常存在，没有被样式口径调整影响。
- 这样登录入口页不再停留在旧样式缓存口径，和已经收过的主链页面重新回到同一版展示基线。

## 9.1.22.18 2026-07-01 `voice_archive` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `voice_archive` 的声音主卡、推荐顺序、页内 CTA 和纪念模式底部导航逻辑。
- 把 `voice_archive.html` 的 `app.css` 版本戳从 `20260630-style11` 抬到 `20260630-style16`，让声音页和最近已收过的纪念模式入口页保持同一版样式缓存口径。

产物位置：

- `voice_archive.html`

怎么验证：

- 对 `voice_archive.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `voice_archive.html?app=1&memorial=on&cb=voice-style16`。
- 在线读取样式链接、页内 CTA 和纪念模式底部导航，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且 `去平行世界`、`memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这一组入口仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`voice_archive` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 页内 CTA 当前仍保持 `digital_human.html?app=1&memorial=on`，底部导航仍保持 `memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这一组 `?app=1&memorial=on` 链接，没有被样式口径调整影响。
- 这样声音页不再停留在旧样式缓存口径，和已经收过的纪念模式入口页重新回到同一版展示基线。

## 9.1.22.19 2026-07-01 `memory_gallery` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `memory_gallery` 的首屏主卡、事实区、推荐卡和纪念模式底部导航逻辑。
- 把 `memory_gallery.html` 的 `app.css` 版本戳从 `20260630-style11` 抬到 `20260630-style16`，让记忆馆页和最近已收过的纪念模式入口页保持同一版样式缓存口径。

产物位置：

- `memory_gallery.html`

怎么验证：

- 对 `memory_gallery.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `memory_gallery.html?app=1&memorial=on&cb=gallery-style16`。
- 在线读取样式链接和纪念模式底部导航，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且 `memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这一组入口仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`memory_gallery` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 底部导航当前仍保持 `memorial_home / digital_human / memory_gallery / voice_archive / privacy` 这一组 `?app=1&memorial=on` 链接，没有被样式口径调整影响。
- 这样记忆馆页不再停留在旧样式缓存口径，和已经收过的纪念模式入口页重新回到同一版展示基线。

## 9.1.22.20 2026-07-01 `event_detail` 样式缓存口径补齐记录

做了什么：

- 继续只做展示层，不碰 `event_detail` 的详情解释、状态按钮、返回入口和实时入口逻辑。
- 把 `event_detail.html` 的 `app.css` 版本戳从 `20260630-style11` 抬到 `20260630-style16`，让详情页和最近已收过的主链页面保持同一版样式缓存口径。

产物位置：

- `event_detail.html`

怎么验证：

- 对 `event_detail.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `event_detail.html?eventId=807&camera_id=9&app=1&cb=eventdetail-style16`。
- 在线读取样式链接、返回入口、实时入口和底部状态按钮，确认当前已加载 `assets/styles/app.css?v=20260630-style16`，且 `edgeDetailBackLink`、`edgeDetailWatchLink`、`edgeMarkFalsePositive`、`edgeMarkHandled` 仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`event_detail` 当前已经加载 `assets/styles/app.css?v=20260630-style16`。
- 关键入口当前仍保持 `events.html?camera_id=9&app=1`、`watch.html?camera_id=9&app=1`，底部按钮 `标记误报` 和 `已确认安全` 也仍正常存在，没有被样式口径调整影响。
- 这样详情页不再停留在旧样式缓存口径，和已经收过的主链页面重新回到同一版展示基线。

## 9.1.22.21 2026-07-01 `watch` 单路摄像头卡片铺满记录

做了什么：

- 继续只做展示层，不碰 `watch` 的实时流、摄像头切换、档位切换和事件跳转逻辑。
- 调整 `assets/scripts/watch-live.js` 的 `renderCameraList()`，当页面只有 `1` 路摄像头时，不再让卡片以悬浮小块的方式停在左侧，而是让它自动铺满整张“切换画面”卡片的可用宽度。
- 同时把 `watch.html` 的 `watch-live.js` 版本戳抬到 `20260701-watchui1`，避免真实页面继续命中旧脚本缓存。

产物位置：

- `assets/scripts/watch-live.js`
- `watch.html`

怎么验证：

- 对 `assets/scripts/watch-live.js` 和 `watch.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `watch.html?app=1&cb=watch-visual-audit3`。
- 在线读取脚本链接、`watchCameraList` 的类名、首个摄像头卡片宽度以及 `watchMonitorLink / watchDetectionLink / watchEventsLink`，确认已加载 `assets/scripts/watch-live.js?v=20260701-watchui1`，单路摄像头卡片宽度已从窄悬浮块变成铺满卡宽，同时主链入口仍正常存在。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`watch` 当前单路摄像头态下，`watchCameraList` 已切成无横向滚动的紧凑布局，首个摄像头卡片宽度约为 `314px`，不再只剩一小块悬在左侧。
- `watchMonitorLink`、`watchDetectionLink`、`watchEventsLink` 当前仍保持 `monitor.html?camera_id=9&app=1`、`detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`，说明这次只收了展示层，没有影响主链上下文。
- 这样 `watch` 在只有一路摄像头时，首屏层次会更稳，卡片密度也和其它页面更一致。

## 9.1.22.22 2026-07-01 `watch` 实时画面容器高度修正记录

做了什么：

- 继续只做展示层，不碰 `watch` 的实时流管理、摄像头切换、档位切换和事件跳转逻辑。
- 调整 `watch.html` 里的 `watchStage` 容器，不再依赖当前运行态下未稳定生效的比例类，而是显式补上 `aspect-ratio: 16 / 9;`，让实时画面卡在真页里稳定撑开。
- 保留原有的黑底、渐变遮罩、房间标签和说明文案，只修正容器高度本身。

产物位置：

- `watch.html`

怎么验证：

- 对 `watch.html` 运行编辑器诊断，结果保持为 `0`。
- 在真实 `8711` 在线页面环境下打开 `watch.html?app=1&cb=watch-visual-audit5`。
- 在线读取 `watchStage` 与其外层 section 的尺寸、样式和主链入口，确认当前画面卡高度已稳定存在，`aspectRatio = 16 / 9`，同时 `watchMonitorLink / watchDetectionLink / watchEventsLink` 仍保持原有链接。

当前结果：

- `通过`

说明：

- 本轮已在真实 `8711` 在线页面环境下验通：`watchStage` 当前尺寸约为 `354 x 199`，外层画面卡高度约为 `201px`，实时画面卡已重新回到首屏层次里。
- `watchMonitorLink`、`watchDetectionLink`、`watchEventsLink` 当前仍保持 `monitor.html?camera_id=9&app=1`、`detection.html?camera_id=9&app=1`、`events.html?camera_id=9&app=1`，说明这次只修了展示容器，没有影响主链上下文。
- 这样 `watch` 的主画面不再在真页里塌掉，实时观看页终于回到“先看画面，再看切换与事件”的正常节奏。

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

## 9.1.31 2026-06-30 Raspberry Pi 5 部署准备记录

做了什么：

- 新增 `docs/raspberry-pi-deploy.md`，把 Pi 5 到手后的首轮部署步骤整理成可执行文档。
- 文档里补齐了系统依赖、Python 环境、`.env` 配置、前台启动、单路 RTSP 验证、`systemd` 安装、日志查看、24 小时检查项和回滚路径。
- 新增 `edge-agent/scripts/install-systemd-service.sh`，生成并安装 `gohome-edge-agent.service`，让 Pi 侧可以直接走 `systemd` 自启，而不是现场手写 service 文件。
- 在 `edge-agent/README.md` 增加 Pi 5 入口说明，明确树莓派验证走专用部署文档和 `systemd` 脚本，不复用 macOS LaunchAgent 口径。

产物位置：

- `docs/raspberry-pi-deploy.md`
- `edge-agent/scripts/install-systemd-service.sh`
- `edge-agent/README.md`

怎么验证：

- 运行 `bash -n edge-agent/scripts/install-systemd-service.sh`，确认脚本语法有效。
- 人工检查部署文档是否覆盖：
  - Raspberry Pi 5 基础依赖
  - `.env` 配置入口
  - `./run.sh` 前台首启
  - `systemd` 安装与重启
  - `journalctl` 日志查看
  - 24 小时观察项
  - 回滚路径
- 确认 README 已给出 Pi 5 部署文档和脚本的显式入口。

当前结果：

- `通过`

说明：

- 这一轮完成的是“树莓派到货前的部署准备”，不是“树莓派硬件真验收”。
- 现在你明天拿到 Pi 5 后，可以直接按文档和脚本跑首轮部署，不需要再现场拼 `systemd` service 或补部署顺序。
- 真正的 Pi 侧通过标准，仍然要等板子到手后按这份文档跑完 `run.sh -> 单路 RTSP -> systemd -> 重启恢复 -> 24 小时观察` 才算完成硬件验证。

## 9.1.32 2026-06-30 通知自测脚本准备记录

做了什么：

- 新增 `edge-agent/scripts/send-test-notification.sh`，直接调用现有 `POST /api/notify/test`，把本地通知通道自测收成一条命令。
- 支持通过命令行传入标题、正文和 `extra` JSON，避免每次都手写 `curl`。
- 在 `edge-agent/README.md` 的通知配置章节补了自测命令入口，方便配完 Bark / 飞书 / Telegram 后立刻发一条验证消息。

产物位置：

- `edge-agent/scripts/send-test-notification.sh`
- `edge-agent/README.md`

怎么验证：

- 运行 `bash -n edge-agent/scripts/send-test-notification.sh`，确认脚本语法有效。
- 在未配置通知通道时，脚本会命中现有 `/api/notify/test` 路径；通道配置完成后，可直接拿它发送一条真实测试消息。

当前结果：

- `通过`

说明：

- 这一轮完成的是“通知闭环的自测准备”，不是“真实手机送达已通过”。
- 真实通知送达仍取决于你最终选择的通道配置是否可用，例如 Bark Key、飞书 Webhook 或 Telegram Bot 参数。

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

### 10.1 树莓派盒子初始化、启动与自启

目标：让树莓派先有本地盒子身份，再像一台本地视觉盒子一样稳定运行。

要做：

- 同步当前工作区到树莓派。
- 初始化盒子：生成设备 ID、本地密钥、管理员账号 `admin / 123456`、hostname / mDNS、数据目录和日志目录。
- 安装系统依赖、Python 虚拟环境和 `requirements.txt`。
- 前台启动 `edge-agent`。
- 验证 `/health`、`/admin/index.html`、`/ui/index.html`。
- 安装 `systemd` 服务。
- 重启树莓派后确认服务自动恢复。

验收：

- 盒子重启后设备 ID、管理员凭证和数据目录仍然存在。
- `edge-agent` 在树莓派上不改源码即可启动。
- `systemd` 能 start / restart / enable。
- `journalctl` 能看到服务日志。

当前实现命令：

```bash
bash scripts/init-box.sh init
bash scripts/init-box.sh reset-admin
```

`scripts/install-systemd-service.sh` 会自动调用 `scripts/init-box.sh init`，避免安装服务后漏初始化。

### 10.2 树莓派摄像头与实时链路

目标：先用一路真实 RTSP 摄像头跑通本地盒子主链。

要做：

- 接入一路 H.264 / 720p 子码流。
- 本地管理台完成摄像头添加、测试、启停和删除。
- `watch / monitor / events / event_detail` 能读取树莓派本地数据。
- 生成至少一张有效截图和一条可解释事件。

验收：

- 实时画面可打开。
- 抓帧和规则评估成功。
- 事件详情能看到截图、规则解释和处理动作。

### 10.3 手机配网入口

目标：补齐盒子产品化配网入口，保持普通用户流程极简。

要做：

- 新增 `/setup` 页面。
- 第一版先适配手机视口。
- 页面流程只覆盖：连接盒子热点、选择家庭 Wi-Fi、输入密码、连接中、成功提示、回到 `回家` App 或进入管理端。
- 开发阶段可以先不真正开启 Wi-Fi 热点，但页面和状态机要按热点配网设计。
- 不在 `/setup` 放摄像头、算法、视频预览、事件、日志和报警测试。

验收：

- 手机上能完成配网主流程。
- 页面不暴露复杂算法调试信息。
- 配网成功后能看到 `gohome.local/admin` 和局域网 IP 的管理入口提示。
- 切换网络导致当前页面断开时，页面把断连解释为预期状态。

### 10.4 开发管理模式、算法预览与报警诊断

目标：让树莓派现场演示能像路由器后台一样完成管理、检测和诊断。

要做：

- `/admin` 增加登录保护和初始账号规则；开发演示盒子默认 `admin / 123456` 直接可用，正式交付再打开首次改密要求。
- `/admin` 首页展示 IP、Wi-Fi、云连接、服务、CPU、温度、磁盘和日志状态。
- `/admin` 完成摄像头扫描、RTSP 参数、测试、保存、启停和删除。
- `/admin` 增加算法预览能力。
- 选择一个摄像头，在同一真实画面查看全部视觉结果。
- 画面叠加检测结果。
- 展示当前输出、置信度、阈值、规则解释和最近日志。
- 第一批覆盖图像质量、人形检测、长时间无人、久坐/静止、疑似跌倒、用餐候选、夜间活动、火灾候选、摄像头异常。
- 新增 `/admin/alerts` 或等价区域，支持跌倒和火灾候选的测试报警和应急动作。
- 新增 `/admin/logs` 或等价区域，展示服务、拉流、检测、报警和系统状态。

验收：

- 现场能选择摄像头并看到人物、姿态、场景和风险状态的统一实时预览效果。
- 跌倒和火灾候选能触发测试报警。
- 日志诊断能解释“为什么没画面 / 为什么没事件 / 为什么没通知”。

## 10.5 当前推荐执行顺序

为了减少返工，当前开发只按下面顺序推进：

1. 先做 `10.1 树莓派盒子启动与自启`。
2. 再做 `10.2 树莓派摄像头与实时链路`。
3. 再做 `10.3 手机配网入口`。
4. 再做 `10.4 开发管理模式、算法预览与报警诊断`。
5. 然后做事件归并、频控和误报反馈。
6. 然后接真实手机通知或报警通道。
7. 盒子侧通过后再进入最小服务器。
8. 最后再调整 App 前端。

## 11. 后续协作方式

从现在开始，后续开发按以下方式推进：

- 每次只做一个闭环任务，不并行发散。
- 每做完一个功能，就回写本文件的“完成记录”和“验收结果”。
- 只有当前任务明确通过，才进入下一个任务。
- 如需调整方向，先改 `PRD` 和 `Plan`，再改代码和 `Implement`。

## 12. 2026-07-02 盒子配网页与管理后台边界纠偏记录

本轮根据实际页面反馈，先处理入口边界和摄像头配置流程，不把配网、摄像头、算法、视频和事件继续混在一个手机页面里。

已调整：

- `/setup` 收口为手机配网页：只保留家庭 Wi-Fi 选择、密码输入、联网结果和下一步提示。
- `/setup/camera.html`、`/setup/guard.html`、`/setup/finish.html` 不再承载摄像头配置、算法开关、视频预览或检测指标。
- `/admin/index.html`、`/admin/cameras.html`、`/admin/algorithms.html` 改为桌面 Web 管理台，不再使用手机壳和底部导航。
- `/admin/cameras.html` 删除“推荐 / 手动 / 演示”和“高级参数”配置方式。
- 摄像头页只保留局域网扫描、扫描结果选择、房间、摄像头 IP、RTSP 端口、用户名、单一密码字段、频道、主副码流、测试画面和保存启用。
- “测试画面”调用 `/api/cameras/test-connection`，只抓帧验证，不先写入本地摄像头配置。
- “保存启用”才写入本地配置，并继续使用最多 3 路摄像头限制。
- 默认不再自动创建 `demo:living_room` 演示摄像头；启动时会清理历史自动演示源，只有显式设置 `GOHOME_ENABLE_DEMO_CAMERA=1` 才允许生成。
- 摄像头测试页不再从已保存摄像头回填表单；IP 默认空，扫描选择或手动填写后才进入本次测试。
- 表单字段变化和每次测试前都会清空上一张测试截图、指标和摘要；测试失败时不会继续显示旧成功结果。
- `/admin` 三个主页面命名收口为：首页、摄像头配置、视觉算法，不再使用“守护”作为后台页面名。

当前边界：

- 本地 `/admin/cameras` 是安装人员和开发者调试入口，不是正式家属端摄像头配置入口。
- V0 阶段本地配置先写 edge-agent；V1 后 App / 云端成为摄像头与规则配置源，edge-agent 按配置版本同步应用。
- 后续需要补“云端配置下发 -> edge-agent 应用 -> 本地管理台展示同步状态 / 临时覆盖”的真实接口闭环。

## 13. 2026-07-02 树莓派原目录初始化与端口口径

本轮按最新要求纠偏：不再为树莓派创建新的 `gohome-clean` 项目目录，后续测试一律使用原有 `/home/gohome/gohome/edge-agent` 目录。

已调整：

- 删除会部署到新目录的清洁部署入口，避免现场误用。
- 新增 `edge-agent/scripts/reset-runtime-data.sh`，用于在原目录内移动旧 `data` 到 `data.backup-YYYYmmdd-HHMMSS`，再重新初始化运行数据。
- 默认 `--preserve-admin` 模式保留设备 ID、初始化状态和 admin 密码，只清空本地数据库、摄像头、事件、截图、对象上传和算法运行数据。
- `--factory` 模式用于完整出厂化开发测试，会重置设备身份和 admin 登录到 `admin / 123456`，开发演示默认不强制改密。
- `edge-agent/README.md` 已补充树莓派干净测试命令和端口说明。
- 新增 `edge-agent/scripts/install-admin-proxy.sh`，用于在树莓派上安装 nginx 反向代理。
- `8711` 定义为 edge-agent 内部开发端口；产品化访问通过 nginx/Caddy 把 `http://gohome.local/admin` 反向代理到 `127.0.0.1:8711/admin`，不让用户看到端口。

当前可执行命令：

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/reset-runtime-data.sh --preserve-admin
```

完整出厂化开发测试：

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/reset-runtime-data.sh --factory
```

隐藏端口访问管理台：

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/install-admin-proxy.sh
```

## 14. 2026-07-02 摄像头频道与主副码流修正

本轮根据真实摄像头路径规则修正 `/admin/cameras`：

- 页面不再暴露“视频路径”下拉。
- 新增“频道”和“码流”两个明确选择。
- 默认频道为 `1`，默认码流为 `2 副码流`。
- 测试、保存和扫描结果填充都会生成 `rtsp://IP:554/1/2`。
- 后端 `/api/cameras/setup-presets` 默认路径改为 `/1/2`。
- 后端局域网扫描返回的默认 `path` 和 `stream_url` 改为 `/1/2`。

重新清空测试仍使用原目录：

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/reset-runtime-data.sh --factory
```

## 15. 2026-07-02 视觉算法 Pipeline v1

本轮开始进入算法主线，先做工程边界和可演示闭环，不先追求最终模型精度。

已完成：

- 新增 `edge-agent/app/vision/` 算法目录。
- 新增统一结果结构 `AlgorithmResult`。
- 新增 `VisionPipeline`，统一输出 `algorithm_results`。
- 第一批算法模块拆分为：
  - `quality`：画面质量、黑屏/遮挡、低变化。
  - `person`：人形/无人，支持 YOLO 后端和 demo fallback。
  - `fall`：基于人体框比例、面积和位置的跌倒候选。
  - `activity`：用餐/动作候选、静止候选。
  - `fire`：基于高亮暖色区域的火灾视觉线索候选。
- `DetectAgent` 已改为薄封装，现有 worker、API、页面不需要改调用方式。
- `RuleEngine` 已把 `meal_candidate / stillness_candidate / fall_score / fire_score` 写入评估状态。
- 新增 `scripts/verify-vision-pipeline.py`，用于无摄像头验证算法层。

兼容输出：

- 继续保留旧字段：`brightness`、`contrast`、`motion_score`、`person_count`、`people`、`fall_candidate`、`fire_candidate`、`tags`。
- 新增结构化字段：`pipeline_version`、`algorithm_results`、`activity`、`meal_score`、`meal_candidate`、`stillness_candidate`、`fall_score`。

本轮验收：

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
./.venv/bin/python scripts/verify-vision-pipeline.py
```

输出已确认：

- `black_screen=true`
- `fire_candidate=true`
- `demo_person_count=1`
- `algorithm_results=["activity","fall","fire","person","pose","quality"]`

真实 API 验收：

- 使用临时服务 `GOHOME_AGENT_PORT=8727 GOHOME_ENABLE_DEMO_CAMERA=1`。
- 登录 `admin / 123456`。
- 执行 `POST /api/cameras/1/capture`。
- 返回已包含 `snapshot`、`detection_result`、`rule_evaluation` 和 `algorithm_results`。
- demo 摄像头返回 `person_count=1`、`activity.status=meal_candidate`、`model_version=vision-pipeline-v1`。

当前边界：

- 用餐/动作识别目前是候选算法，不直接生成家属告警。
- 跌倒和火灾仍是高优先级候选，后续需要补报警渠道和应急动作测试。
- RTMPose 姿态点正在接入；当前跌倒仍是候选判断，不等同于医疗级或消防级结论。

下一步：

1. 先解决实时画面卡顿和算法预览冻结，避免视频预览、截图和分析分别重复打开 RTSP。
2. 在已验证 YOLO 人形检测和人体存在增强基础上，接入 RTMLib + RTMPose POC，增强 `fall` 和 `activity` 模块。
3. 如果 Pi5 上 RTMPose CPU 帧率不够，再评估 MoveNet 或 Hailo AI HAT+。
4. 做火灾/烟雾专用模型或轻量 ONNX 评估。
5. 增加算法预览页的单算法详情解释。
6. 增加跌倒、火灾测试报警按钮和报警链路验收。

## 16. 2026-07-02 真实配网测试口径

纠偏：配网不能只做本地接口或虚拟页面测试。产品口径必须按“用户拿到烧录好程序的盒子，通电后能看到盒子 Wi-Fi 并完成家庭 Wi-Fi 配网”验收。

本轮调整：

- `gohome-edge-agent.service` 不再依赖 `network-online.target`。
- 改为只依赖 `NetworkManager.service`，避免新盒子无家庭 Wi-Fi 时 `/setup` 启动被网络在线等待拖住。
- 新增 `scripts/prepare-factory-network-test.sh`。
- 该脚本用于真实树莓派模拟出厂网络状态：断开 Wi-Fi、删除已保存的非 `GoHome-*` Wi-Fi 配置、启动 `GoHome-XXXX` 热点、重启 edge-agent。
- `/setup` 收口为单独配网页；普通用户只做家庭 Wi-Fi 配网，摄像头、算法和日志都不在用户配网页暴露。
- `/admin` 保留为开发者 / 安装人员模式，通过 `http://gohome.local/admin` 或局域网 IP 进入。
- nginx 80 端口代理用于去掉 `:8711`，热点下优先打开 `http://10.42.0.1`。
- 增加 captive portal 常见探测路径和热点 DNS 劫持配置，尽量让手机连上 `GoHome-XXXX` 后自动弹出配网页；如手机系统不弹窗，手动打开 `http://10.42.0.1` 作为兜底。

真实验收步骤：

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/install-systemd-service.sh
sudo bash scripts/install-admin-proxy.sh
sudo bash scripts/prepare-factory-network-test.sh --yes
```

预期：

- 手机 Wi-Fi 列表出现 `GoHome-XXXX`。
- 热点密码为 `gohome2026`。
- 手机连接热点后可能自动弹出配网页；如果未弹出，打开 `http://10.42.0.1`。
- 页面能扫描家庭 Wi-Fi。
- 输入家庭 Wi-Fi 密码后，盒子能切回家庭网络。
- 手机也切回家庭网络后，普通用户打开“回家”App 继续绑定；开发者或安装人员可以打开 `http://gohome.local/admin` 或新 LAN IP 的管理台。

风险：

- 执行真实测试会断开当前 SSH。
- 建议接网线、显示器键盘，或准备通过 `GoHome-XXXX` 热点重新进入。
- 如果家庭路由器不支持 mDNS，`gohome.local` 可能不可用，需要从路由器后台或 `hostname -I` 获取新 IP。

## 17. 2026-07-03 算法路线回退与重启记录

本轮根据真实页面反馈和 Pi5 性能风险，先撤回未验证的 YOLO Pose 实验，再按新的算法路线继续。

已撤回：

- 撤回本地未提交的 YOLO Pose 实验代码。
- 删除未纳入主线的 `edge-agent/app/vision/pose_yolo.py` 和临时 `yolo11n-pose.pt` 文件。
- 保留已验证的 YOLO 人形检测、人体存在增强、管理台页面、摄像头配置、真实配网和已有 Pipeline v1。

当前真实状态：

- 树莓派盒子已经能完成真实热点配网测试，手机连接 `GoHome-XXXX` 后能进入配网页。
- 摄像头已经接入，首页能看到实时视频流。
- YOLO 人形检测已能在算法页显示人框。
- 人体存在增强已能补偿坐姿、半身、低置信人形未命中的场景，但仍可能对椅子、床、灯光等区域产生误判。
- 当前算法仍属于“可演示链路”，不是产品级动作识别或跌倒识别。

纠偏后的实现顺序：

1. 新增单路帧源缓存或等价 FrameHub：每路摄像头只开一个 RTSP 读取源，MJPEG 预览、截图和算法分析都读取最近帧。
2. 将算法预览改成异步低频分析：页面实时流保持轻量，分析结果按 1 到 3 秒刷新，避免推理阻塞画面。
3. 保持当前 YOLO 人框作为基础检测；坐姿、半身和人体存在增强继续作为辅助候选，不直接生成高危事件。
4. 接入 RTMLib + RTMPose POC：输出关键点、骨架线、姿态摘要、候选动作和置信度。
5. 将跌倒候选升级为“人框 + 骨架 + 低位/卧姿 + 持续时间 + 无后续起身”的组合规则。
6. 将用餐候选升级为“饭点 + 餐桌/厨房区域 + 人体存在 + 手部/上半身活动线索 + 时间窗”的候选规则。
7. 将命中日志分层：算法预览日志只在 `/admin` 给开发者看；正式事件命中才截帧、入库、频控、生成 `EventCandidate`，并进入后续上传队列。
8. 在 `api/v1` 设备事件上报中补齐结构化算法结果、截图媒体引用和幂等键，为 App 服务器查看事件做准备。

模型路线：

- 首选：RTMLib + RTMPose，用于 Pi5 上的骨架和姿态演示 POC。
- 备用：MoveNet，用于 RTMPose CPU 帧率不足时降级。
- 产品化加速：Hailo AI HAT+ / Hailo Pose。
- 低优先级备用：YOLO11 Pose。
- 暂缓：自训练。没有真实家庭样本、误报反馈、标注规范和验证集前，不做大规模训练。

参考来源：

- RTMLib：`https://github.com/Tau-J/rtmlib`
- MMPose / RTMPose：`https://github.com/open-mmlab/mmpose`
- ONNX Runtime：`https://onnxruntime.ai/`
- Ultralytics Pose：`https://docs.ultralytics.com/tasks/pose/`

## 18. 2026-07-04 开源项目复用审计

本轮按“不重复造轮子”的要求，实际检查候选开源路线的 license、依赖、部署难度和 Pi5 适配性。

### 18.1 当前采用

`Tau-J/rtmlib`

- 地址：`https://github.com/Tau-J/rtmlib`
- 许可：Apache-2.0。
- 适配度：高。
- 采用原因：
  - 直接封装 RTMPose / RTMO / ViTPose 等姿态模型。
  - 依赖主要是 `onnxruntime`、`opencv`、`numpy`，能适配当前 Pi5 Python 3.13。
  - `Body(lightweight)` 内部使用 YOLOX tiny 人体检测 + RTMPose-S，适合先做实时骨架演示。
  - 输出关键点和置信度，可直接映射到管理台 overlay。

采用方式：

- 不直接运行它的 demo 脚本。
- 新增 `edge-agent/app/vision/pose_rtmpose.py`，作为我们的姿态模块。
- 输入使用当前摄像头最新帧，不再让姿态模块自己打开摄像头。
- 输出进入我们的 `VisionPipeline`：`poses`、`pose_fall_score`、`pose_fall_candidate`、`pose_action_hints`。
- 报警接入我们的 `RuleEvaluation -> EventCandidate -> Event -> UploadQueue / Notify` 链路。

### 18.2 暂不采用

`punpayut/Fall-Detection`

- 地址：`https://github.com/punpayut/Fall-Detection`
- 许可：MIT。
- 结论：不作为当前主线。
- 原因：当前树莓派系统是 Python 3.13，`mediapipe` / `tflite-runtime` 依赖不可用或不稳定；继续硬装会拖慢当前真实演示。
- 可保留参考点：30 帧姿态序列、跌倒时序分类和报警链路设计。

`rhafaelc/Fall-Detection-YOLO-MediaPipe`

- 地址：`https://github.com/rhafaelc/Fall-Detection-YOLO-MediaPipe`
- 状态：只有 notebook、报告和演示视频，没有 license、requirements 和可直接复用的模块化代码。
- 结论：不能直接集成到产品代码。

`robmarkcole/fire-detection-from-images`

- 地址：`https://github.com/robmarkcole/fire-detection-from-images`
- 许可：MIT。
- 状态：有 YOLOv5 fire `best.pt`，模型约 14MB，但主要是训练/Gradio 演示项目。
- 结论：不作为当前 Pi5 实时火灾主线。
- 可参考点：火焰检测数据集、YOLO 训练经验、后续火灾模型评估方式。

### 18.3 当前采用决策

1. 跌倒/骨架：采用 RTMLib + RTMPose 路线，先做骨架展示和姿态几何候选。
2. 人形检测：继续使用当前 YOLO11n / YOLO 人形检测和人体存在增强。
3. 用餐/久坐/夜间活动：短期不找“吃饭现成模型”，先基于 RTMPose 骨架、场景区域、时间窗和活动量做候选判断。
4. 火灾：当前先保留轻量颜色/亮度候选；`robmarkcole` 的 YOLOv5 fire 模型只做离线评估，不直接常开上 Pi5。
5. 训练：暂不自训练。等有真实家庭截图、短视频、误报反馈和标注规范后再做。

## 19. 2026-07-04 RTMPose 姿态模块接入记录

本轮把姿态模块主线从旧 MediaPipe/TFLite 方案替换为 RTMLib + RTMPose。

已完成：

- 删除旧的 `edge-agent/app/vision/pose_fall_tflite.py`。
- 删除旧的 `edge-agent/models/third_party/punpayut-fall-detection/` 模型目录。
- 将 `edge-agent/requirements-pose.txt` 改为 RTMPose 依赖：`rtmlib`、`onnxruntime`、`opencv-contrib-python`。
- 新增姿态模块：`edge-agent/app/vision/pose_rtmpose.py`。
- 将姿态模块接入 `VisionPipeline`，新增 `algorithm_results.pose`。
- 新增配置项：
  - `GOHOME_POSE_BACKEND=rtmpose`
  - `GOHOME_POSE_MODE=lightweight`
  - `GOHOME_POSE_RUNTIME_BACKEND=onnxruntime`
  - `GOHOME_POSE_DEVICE=cpu`
  - `GOHOME_POSE_FALL_THRESHOLD=0.78`
  - `GOHOME_POSE_DET_FREQUENCY=8`
  - `GOHOME_POSE_MIN_KEYPOINT_CONFIDENCE=0.30`
  - `GOHOME_POSE_MAX_POSES=1`
  - `GOHOME_POSE_TRACKING=0`
- 新增输出字段：
  - `pose_count`
  - `poses`
  - `pose_skeleton_edges`
  - `pose_action_hints`
  - `pose_fall_score`
  - `pose_fall_candidate`
  - `pose_model_status`
  - `pose_model_message`
  - `pose_model_name`
- 管理台算法页继续使用已有骨架 overlay。
- `/api/cameras/{camera_id}/analysis/live?algorithm=fall` 会在跌倒预览时启用姿态模块。

当前运行策略：

- `GOHOME_POSE_ENABLED=0`，后台常规 worker 默认不强制常开姿态模型。
- 管理台算法预览选择人形、跌倒、用餐、久坐、夜间活动时，临时启用姿态分析。
- 管理台算法预览只读取实时视频流缓存帧，不再为分析接口重新打开 RTSP，避免视频延迟和分析互相阻塞。
- RTMPose 预览默认单人、非跟踪、低频检测，优先保证演示流畅；多人和更高精度留给 Hailo 或云端增强。
- 管理台视频流调整为更激进的低延迟策略：算法页 8fps / 540p / 低质量压缩 / 高丢帧，并为 MJPEG 响应增加禁止缓存和禁止代理缓冲头。
- 摄像头配置页回到极简参数：IP、554 端口、用户名密码、频道和主/副码流；特殊 RTSP 路径以后放到开发者诊断，不进入主配置流程。
- 如果 Pi 上没有安装 `rtmlib`，接口返回 `pose_model_status=unavailable`，服务不崩溃，也不伪造结果。
- 当前跌倒是基于 RTMPose 骨架几何的候选判断，不等同于训练好的跌倒时序模型；后续要用真实样本或专用时序模型增强。

本地验收：

- `python3 -m compileall edge-agent/app` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过，默认姿态状态为 `disabled`。
- `node --check edge-agent/admin/console.js` 通过。
- `git diff --check` 通过。

补充修正：

- `GET /api/event-candidates?status=active` 改为按 `camera_id + event_type` 只返回最新一条安全 / 设备告警，避免旧库中同一摄像头的多条火灾历史在算法页连续刷屏。
- 火灾正式事件频控从默认频控提高到至少 30 分钟；同一个摄像头持续命中火灾候选时，不再 5 分钟生成一条正式事件。
- 新增验证脚本：`edge-agent/scripts/verify-alert-dedupe.py`。
- `python3 edge-agent/scripts/verify-alert-dedupe.py` 通过，验证 3 条历史火灾候选只展示最新 1 条，且火灾频控为 1800 秒。

## 24. 2026-07-04 火灾准确性底座升级

本轮把火灾检测从“单帧暖色启发式”改成“预览线索 + 正式事件候选”双层判断。

已完成：

- `FireAnalyzer` 输出拆分：
  - `fire_candidate`：火灾视觉线索，供算法预览展示。
  - `fire_event_candidate`：正式火灾事件候选，供规则引擎报警。
- 火灾特征从单纯暖色比例升级为：
  - 暖色区域比例。
  - 黄色核心比例。
  - 暖色区域纹理。
  - 红色灯光惩罚。
  - 连通区域大小和占比。
  - 与上一帧的暖色区域变化 / 亮度变化。
- `QualityAnalyzer` 返回 `previous_sample`，用于火灾帧间动态判断。
- `RuleEngine` 正式火灾事件必须同时满足：
  - `fire_event_candidate = true`。
  - `fire_score >= fire_event_score_threshold`，默认 `0.12`。
  - `motion_score >= fire_motion_threshold`，默认 `0.035`。
  - `fire_temporal_score >= fire_temporal_threshold`，默认 `0.018`。
  - 连续确认帧数 `fire_confirm_frames >= 5`。
- `rules` 表新增火灾正式事件阈值字段，后续可由服务器或管理端下发。
- 算法页火灾预览新增“动态”指标，区分“仅视觉线索”和“火灾事件候选”。

本地验收：

- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过：
  - 黑屏检测通过。
  - 火灾视觉线索通过。
  - 静态火灾视觉线索不会成为正式事件候选。
  - 动态火灾样式会成为正式事件候选。
  - 红灯误报回归通过。
- `python3 -m compileall edge-agent/app` 通过。
- `python3 edge-agent/scripts/verify-alert-dedupe.py` 通过。
- `python3 edge-agent/scripts/verify-observation-logs.py` 通过。
- `python3 edge-agent/scripts/verify-upload-queue.py` 通过。
- `node --check edge-agent/admin/console.js` 通过。
- `git diff --check` 通过。

下一步准确性路线：

- 第一优先级不是继续调 UI，而是建立真实样本评测集：
  - 客厅正常白天 / 夜间。
  - 电视暖色画面。
  - 暖色灯。
  - 红色指示灯。
  - 人走动。
  - 半身坐姿。
  - 躺倒 / 弯腰 / 坐沙发。
  - 火焰 / 烟雾测试素材。
- 每次模型或阈值调整必须跑 `precision / recall / false positive`，不能只靠肉眼看一两帧。
- 火灾最终要接专门的火焰 / 烟雾模型；当前颜色 + 动态规则只作为 Pi5 上的轻量底座。
- 本地未安装 `rtmlib` 时，强制姿态分析返回 `pose_model_status=unavailable`，HTTP 链路不会伪造成功。

下一步在树莓派上执行：

```bash
cd ~/gohome/edge-agent
source .venv/bin/activate
pip install -r requirements-pose.txt
grep -q '^GOHOME_POSE_BACKEND=' .env && sed -i 's/^GOHOME_POSE_BACKEND=.*/GOHOME_POSE_BACKEND=rtmpose/' .env || echo 'GOHOME_POSE_BACKEND=rtmpose' >> .env
grep -q '^GOHOME_POSE_MODE=' .env && sed -i 's/^GOHOME_POSE_MODE=.*/GOHOME_POSE_MODE=lightweight/' .env || echo 'GOHOME_POSE_MODE=lightweight' >> .env
grep -q '^GOHOME_POSE_RUNTIME_BACKEND=' .env && sed -i 's/^GOHOME_POSE_RUNTIME_BACKEND=.*/GOHOME_POSE_RUNTIME_BACKEND=onnxruntime/' .env || echo 'GOHOME_POSE_RUNTIME_BACKEND=onnxruntime' >> .env
grep -q '^GOHOME_POSE_DEVICE=' .env && sed -i 's/^GOHOME_POSE_DEVICE=.*/GOHOME_POSE_DEVICE=cpu/' .env || echo 'GOHOME_POSE_DEVICE=cpu' >> .env
grep -q '^GOHOME_POSE_DET_FREQUENCY=' .env && sed -i 's/^GOHOME_POSE_DET_FREQUENCY=.*/GOHOME_POSE_DET_FREQUENCY=8/' .env || echo 'GOHOME_POSE_DET_FREQUENCY=8' >> .env
grep -q '^GOHOME_POSE_MAX_POSES=' .env && sed -i 's/^GOHOME_POSE_MAX_POSES=.*/GOHOME_POSE_MAX_POSES=1/' .env || echo 'GOHOME_POSE_MAX_POSES=1' >> .env
grep -q '^GOHOME_POSE_TRACKING=' .env && sed -i 's/^GOHOME_POSE_TRACKING=.*/GOHOME_POSE_TRACKING=0/' .env || echo 'GOHOME_POSE_TRACKING=0' >> .env
sudo systemctl restart gohome-edge-agent
```

第一次打开算法预览时，RTMLib 会下载 RTMPose / YOLOX ONNX 模型到缓存目录，首次加载会慢。下载完成后再评估延迟、帧率、CPU 和温度。

## 20. 2026-07-04 算法命中证据包与上报口径

本轮在真实算法预览跑通后，补齐“命中怎么解释、怎么给 App 服务器”的工程口径。

已完成：

- `RuleEngine` 生成 `EventCandidate` 时新增 `payload.evidence`。
- `evidence.schema_version = gohome-event-evidence-v1`。
- 证据包包含：
  - 事件类型、级别和摘要。
  - `pipeline_version`、YOLO 模型、RTMPose 模型状态。
  - 相关算法结果，例如 `quality / person / pose / fall / fire`。
  - 人数、骨架数、跌倒分数、火灾分数、亮度、对比度、运动分数。
  - 最多 3 个人框和最多 2 组骨架摘要。
  - 触发规则、阈值、标签和额外上下文。
- `/api/v1/events` 返回中新增顶层 `evidence`、`snapshot_path`、`idempotency_key`。
- 新增开发者接口：`GET /api/events/{event_id}/server-payload`。
- 该接口返回未来 App 服务器可直接接收的 `gohome-device-event-v1` payload。
- 算法页新增“最近命中”，展示后台真实 `EventCandidate`，不是预览页临时伪造记录。

当前产品边界：

- `/admin/algorithms` 的实时预览只用于演示识别效果，不直接制造正式告警。
- 正式告警和留证仍由后台 worker 定时截帧、分析、规则评估后产生。
- 正常活动如用餐、久坐、夜间活动短期作为状态和候选线索，不直接按高危告警通知家属。
- 跌倒、火灾、摄像头离线、黑屏/遮挡、长时间无人/无变化进入 `EventCandidate -> Event` 链路。
- 后续接云端时，上传队列按 `server-payload` 结构 POST 到 App 服务器；截图再由媒体服务或 COS 返回 URL。

本地验收：

- `python3 -m compileall edge-agent/app` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过。
- `node --check edge-agent/admin/console.js` 通过。
- `git diff --check` 通过。

## 21. 2026-07-04 火灾误报刷屏纠偏

真实算法页出现“疑似火灾”候选刷屏：画面中的屏幕/RGB 灯和高亮暖色区域被旧启发式识别为火灾线索，即使事件被频控抑制，后台候选记录仍然污染了演示页面。

本轮处理：

- 火灾算法从单一 `warm_bright_color_ratio` 改为 `warm_yellow_texture_score`。
- 新火灾视觉分数同时检查：
  - 暖色区域比例。
  - 橙黄核心比例。
  - 高亮区域纹理变化。
  - 纯红光区域惩罚。
- `VisionPipeline` 新增 `fire_features`，用于证据包解释。
- 正式火灾候选不再只看单帧视觉分数。
- `RuleEngine` 要求火灾满足：
  - 视觉分数过线。
  - 当前帧存在运动/变化。
  - 连续至少 2 帧确认。
- `event_candidates?status=active` 新增语义：默认排除 `suppressed` 噪声候选。
- 算法页“最近命中”改为拉取 `status=active`，旧的已抑制重复记录不再刷屏。
- `verify-vision-pipeline.py` 新增红光误报回归：橙黄纹理火焰命中，纯红光不命中。

当前边界：

- 这仍是边缘端轻量视觉线索，不等同于产品级火灾专用模型。
- 产品化火灾报警后续应接专用烟火模型，并结合连续帧、声音/烟雾传感器或人工确认策略。

本地验收：

- `python3 -m compileall edge-agent/app` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过，包含 `red_light_fire_candidate=false`。
- `node --check edge-agent/admin/console.js` 通过。
- `git diff --check` 通过。

补充修正：

- 算法预览页的火灾模式不再把单帧视觉线索显示成“应急报警命中”。
- 实时预览现在显示“火灾线索观察 / 未确认火灾线索”，只有后台连续帧规则确认后才进入正式候选。
- “最近命中”列表改为独立 `candidate-card`，不再复用事件列表样式，避免出现只有红色标记和空白行的渲染问题。
- 算法页资源版本更新到 `20260704-firefix-2`，避免浏览器继续加载旧脚本。

## 22. 2026-07-04 本地日志与上传队列

本轮补齐“检测到了怎么截取、事件怎么分类保存、后续怎么给服务器”的基础链路。

职责边界：

- 树莓派本地负责：
  - 定时截帧。
  - 检测结果 `detection_results`。
  - 规则评估 `rule_evaluations`。
  - 事件候选 `event_candidates`。
  - 正式事件 `events`。
  - 命中截图 `snapshots`。
  - 上传队列 `upload_jobs`。
- 服务器负责：
  - 事件长期保存。
  - 截图 / 视频片段对象存储。
  - 数据库存储 COS URL、证据包和处理状态。
  - App 推送、家属查看和长期统计。

已完成：

- 新增 `upload_jobs` 表。
- 正式事件生成后自动入队：
  - `event_upload`：事件、分类、证据包和服务端事件 payload。
  - `media_upload`：事件截图，后续对接 COS 或服务端媒体上传。
- 重复事件被频控抑制时不会生成上传任务。
- 上传队列支持幂等键，避免同一个事件重复排队。
- 新增 API：
  - `GET /api/upload-jobs`
  - `GET /api/upload-jobs/summary`
- 算法页“最近命中”旁边展示上传队列状态，例如待上传、失败、高优先级数量。
- 新增验证脚本：`edge-agent/scripts/verify-upload-queue.py`。

当前上传策略：

- 普通检测日志只本地短期保存，不全量上传。
- 跌倒、火灾、摄像头离线、黑屏/遮挡等正式事件进入上传队列。
- 长时间无人、长时间无变化不再作为周期性正式事件刷屏，先聚合为生活观察区间；后续按老人日志策略同步云端。
- 老人生活日志后续按策略抽样上传，例如定时截帧、饭点、夜间活动、久坐/发呆候选，不按每帧上传。

本地验收：

- `python3 -m compileall edge-agent/app` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-upload-queue.py` 通过，生成 `event_upload + media_upload` 两类任务。
- `node --check edge-agent/admin/console.js` 通过。
- `git diff --check` 通过。

补充约束：

- 事件按类别展示：
  - `safety_alert`：跌倒、火灾。
  - `device_alert`：黑屏/遮挡、摄像头离线。
  - `life_observation`：长时间无变化、长时间无人。
- 火灾分为两级：
  - 实时预览里的 `fire_candidate` 只是视觉线索。
  - 正式火灾事件必须达到更高阈值 `fire_event_score_threshold`，默认至少 `0.075`。
  - 正式火灾事件还必须有画面变化，默认 `motion_score >= 0.025`。
  - 正式火灾事件还必须连续至少 3 帧确认。
- 长时间无变化只在检测到有人存在时生成生活观察记录，空房间不再触发“老人静止”类记录。
- 长时间无人、长时间无变化降级为 `info` 级生活观察，不走高危告警通知，也不进入正式事件上传队列。
- 事件通知只对 `critical` 且属于跌倒、火灾、摄像头离线的事件触发。
- 事件频控按类型区分：
  - 跌倒使用默认频控。
  - 火灾至少 30 分钟。
  - 黑屏/离线至少 15 分钟。
  - 长时间无人/无变化至少 1 小时。
- 算法页最近命中按事件类型展示相关指标：
  - 火灾只显示火灾分数、变化、连续帧。
  - 跌倒只显示人数、骨架、跌倒分数。
  - 生活观察显示人数、静止/无人时长、变化。
  - 不再把每条记录都塞入火灾分数和跌倒分数。

## 23. 2026-07-04 生活观察区间聚合

本轮修正“长时间无变化 / 长时间无人”持续刷屏的问题。

已完成：

- 新增 `observation_logs` 聚合表，用于保存生活观察区间。
- `EdgeWorker` 对 `no_motion / no_person` 做分流：
  - 仍保存 `event_candidates` 作为规则命中痕迹。
  - 候选状态标记为 `aggregated`。
  - 更新或创建一条 `observation_logs`。
  - 不调用 `EventAgent.emit()`，不生成正式 `events`，不进入 `upload_jobs`。
- 恢复闭环：
  - 检测到画面恢复运动时关闭 `no_motion` 区间。
  - 检测到人重新出现时关闭 `no_person` 区间。
- `GET /api/event-candidates?status=active` 从源头排除 `no_motion / no_person`，避免旧库里已提升过的生活观察继续出现在“最近告警”。
- 新增 `GET /api/observation-logs`，管理台单独展示“生活观察”。
- 算法页拆成：
  - “最近告警”：只看安全告警和设备异常。
  - “生活观察”：展示进行中 / 已恢复的观察区间、持续时间、采样次数和最后更新时间。
- 新增验证脚本：`edge-agent/scripts/verify-observation-logs.py`。

本地验收：

- `python3 -m compileall edge-agent/app` 通过。
- `node --check edge-agent/admin/console.js` 通过。
- `python3 edge-agent/scripts/verify-observation-logs.py` 通过：
  - 重复 `no_motion` 合并为 1 条观察区间。
  - 生成 2 条 `aggregated` 候选。
  - 正式事件数为 0。
  - 上传待处理数为 0。
  - 恢复运动后观察区间关闭。
- `python3 edge-agent/scripts/verify-upload-queue.py` 通过，正式高危事件仍生成 `event_upload + media_upload`。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过。
- `git diff --check` 通过。

## 24. 2026-07-04 UR Fall 真实样本回归与跌倒规则补强

本轮开始把跌倒算法从“烟测样本能跑”推进到真实公开数据集回归。第一批接入 UR Fall Detection Dataset 的小规模样本，不再只依赖合成样本或页面观察。

新增脚本：

- `edge-agent/scripts/import-ur-fall-sample.py`
  - 默认下载 `fall-01/fall-02/adl-01/adl-02` 的 cam0 MP4 和逐帧特征 CSV。
  - UR Fall MP4 为左侧深度图 + 右侧 RGB 预览，导入器默认裁剪右半边 RGB，避免深度图干扰 YOLO / RTMPose。
  - 按官方标签处理：`1` 作为躺倒正样本，`-1` 作为未躺倒负样本，`0` 过渡帧默认跳过。
  - 输出 `data/eval/samples/fall/ur_fall/manifest.jsonl`。
- `edge-agent/scripts/run-ur-fall-eval.sh`
  - 一键导入小样本并运行 `eval-fall.py --use-pose`。

算法补强：

- `person_yolo.py` 的人框结果补充 `frame_width / frame_height`，用于后续规则判断画面位置。
- `fall.py` 从单一人框比例升级为组合候选：
  - 原有 YOLO 人框横向倒地候选。
  - `single_low_body`：低位、接触画面底部、面积足够、非细长框的单人体倒地候选。
  - `floor_cluster`：骨架不可用且人体被拆成多个低位片段时，合并低位片段判断贴地人体簇。
- `pipeline.py` 修复 RTMPose 命中跌倒时 `fall.result.data` 未同步写入 `pose_fall_candidate / pose_fall_score` 的问题，避免页面解释和顶层结果不一致。

本地验收：

- `python3 -m py_compile edge-agent/app/vision/fall.py edge-agent/app/vision/person_yolo.py edge-agent/app/vision/pipeline.py edge-agent/scripts/import-ur-fall-sample.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/import-ur-fall-sample.py --fall 01 --adl 01 --force` 通过，生成 10 张真实逐帧样本，4 正 / 6 负。
- 裁剪前 UR Fall 小样本评测为 `TP 0 / FP 0 / TN 6 / FN 4`；确认根因是 MP4 左侧深度图干扰和低位倒地漏检。
- 裁剪右侧 RGB 后，小样本提升到 `TP 1 / FP 0 / TN 6 / FN 3`。
- 加入低位人体簇规则后，小样本达到 `TP 4 / FP 0 / TN 6 / FN 0`。
- 扩展到默认真实样本 `fall-01/fall-02/adl-01/adl-02`，共 20 张，最终达到：
  - `TP 8`
  - `FP 0`
  - `TN 12`
  - `FN 0`
  - `precision = 1.0`
  - `recall = 1.0`
  - `false_positive_rate = 0.0`
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过。
- `edge-agent/scripts/run-vision-smoke-eval.sh` 通过：
  - person / pose / fire visual / fire event 均保持通过。
  - smoke fall 目前只有负样本，保持误报率 0。

边界说明：

- 这次结果只代表 UR Fall 第一批小样本回归通过，不能对外宣称产品级跌倒准确率。
- 下一步需要继续扩大 UR Fall 序列数，再加入真实家庭摄像头自采样本，重点看坐下、弯腰、躺沙发、被遮挡、低光和多人场景误报。
- 正式告警仍应由规则引擎结合连续帧、持续时间、无后续起身、摄像头区域和频控生成，不能只靠单帧候选直接通知家属。

## 25. 2026-07-04 跌倒候选与正式告警分层纠偏

本轮修正一个关键产品逻辑问题：算法层的 `fall_candidate` 不能等同于正式高危告警。单帧候选可以用于管理端预览、画框、骨架和解释，但正式事件必须由规则引擎做连续帧确认。

已完成：

- `RuleEngine` 新增 `fall_confirm_counts`，按摄像头维护跌倒确认计数。
- 规则表新增：
  - `fall_score_threshold`，默认 `0.50`。
  - `fall_confirm_frames`，默认 `2`。
- `rules` 读取、更新、服务端同步合并路径均支持这两个字段。
- 跌倒正式事件生成条件调整为：
  - `fall_candidate = true`。
  - `fall_score >= fall_score_threshold`，或 `pose_fall_score >= pose_fall_threshold`。
  - 连续命中帧数达到 `fall_confirm_frames`。
- 低分单帧候选只进入 `state.fall_state = visual_only`，不生成正式 `EventCandidate`。
- 第一帧强候选只进入 `state.fall_state = confirming`，不直接报警。
- 第二帧连续强候选才生成 `fall_candidate / critical` 正式事件。
- 候选清除后确认计数归零。
- 新增 `edge-agent/scripts/verify-fall-rule-engine.py` 固定该行为，防止后续回退成“单帧即报警”。

本地验收：

- `edge-agent/.venv/bin/python edge-agent/scripts/verify-fall-rule-engine.py` 通过：
  - 低分候选不报警。
  - 第一帧强候选不报警。
  - 第二帧连续强候选生成 1 条正式事件。
  - 清除帧重置确认计数。
- 临时数据库验证通过：
  - 默认 `fall_score_threshold = 0.5`。
  - 默认 `fall_confirm_frames = 2`。
  - `update_rules` 可更新为 `0.6 / 3`。
- `edge-agent/scripts/run-vision-smoke-eval.sh` 通过。
- `edge-agent/scripts/run-ur-fall-eval.sh --no-download` 通过，UR Fall 小样本候选评测仍为 `TP 8 / FP 0 / TN 12 / FN 0`。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-upload-queue.py` 通过。

当前边界：

- 算法预览页仍可以实时显示单帧候选，这用于调试和演示。
- 家属通知、事件证据包、上传队列必须以规则引擎确认后的正式事件为准。
- 下一步要继续把“无后续起身 / 卧地持续时间 / 区域约束”加入跌倒正式事件规则，而不是继续堆单帧判断。

补充修正：

- 真实事件 #1744 证据显示 `fall_score = 0.7218`、`pose_fall_score = 0.0`、`confirm_frames = 2`，页面却显示 `跌倒 0.00`。根因是管理台优先展示 `pose_fall_score ?? fall_score`，当骨架分数为 `0` 时遮掉了真实跌倒分数。
- 管理台已改为显示 `fall_score / pose_fall_score / observed.fall_score / observed.pose_fall_score` 中的最大有效值，并补充展示连续帧和证据类型。
- #1744 同时暴露出真实误报风险：一个低置信 YOLO 横向框 `confidence = 0.2096` 和一个普通人框被 `floor_cluster` 合并后升级为正式告警。
- 跌倒算法进一步收紧：
  - YOLO 单框跌倒候选必须达到 `fall_box_min_confidence >= 0.30`。
  - 默认贴地人体簇至少需要 `fall_floor_cluster_min_fragments = 3` 个低位片段。
  - 两框误合并不再作为正式跌倒候选主证据。
- 新增 `verify-vision-pipeline.py` 回归项：复现 #1744 的“高置信普通人框 + 低置信横向框”形态，要求 `weak_fall_candidate = false`。
- 本地复测：
  - #1744 形态回归：`weak_fall_candidate = false`，`weak_fall_score = 0.271`。
  - UR Fall 小样本仍为 `TP 8 / FP 0 / TN 12 / FN 0`。

## 26. 2026-07-05 视觉算法交互纠偏与本地服务器准备

本轮把“算法预览”和“正式事件”进一步拆清楚，避免页面看起来像单帧命中就直接报警。

已完成：

- 跌倒检测改为规则状态机，不再把单帧 `fall_candidate` 直接当作正式高危事件。
- 跌倒状态包括：
  - `clear`
  - `visual_only`
  - `suspect`
  - `confirming`
  - `confirmed`
  - `recovered`
- 正式跌倒事件需要同一摄像头连续命中，并满足确认帧数 / 持续时间 / 分数阈值。
- 弱证据只用于预览和解释，不生成正式事件。
- 管理台算法页改为按所选算法展示证据：
  - 跌倒页重点展示倒地候选、骨架分数、连续帧和规则阶段。
  - 普通人体不再在跌倒模式下被当成跌倒证据展示。
  - 移除造成误解的黑色空预览块。
- 视频预览和算法推理开始做解耦处理，算法推理优先处理最新帧，避免慢推理拖住页面视频。

树莓派当前状态：

- 设备地址：`192.168.1.12`。
- `gohome-edge-agent` 可通过 systemd 运行。
- 已接入两路天地伟业摄像头：
  - 客厅：`rtsp://192.168.1.5:554/1/2`
  - 书房：`rtsp://192.168.1.11:554/1/2`
- 当前检测模型配置：
  - `GOHOME_DETECTOR_BACKEND=yolo`
  - `GOHOME_YOLO_MODEL=yolo11n.pt`
  - `GOHOME_YOLO_IMGSZ=640`
- 姿态路线：RTMPose lightweight + onnxruntime CPU。

已知状态：

- `upload_jobs` 仍为 `pending` 是预期现象，因为还没有配置 App 服务器：
  - `GOHOME_APP_SERVER_BASE_URL` 为空。
  - `GOHOME_DEVICE_API_TOKEN` 为空。
- 下一步要先做局域网本地 App API，跑通事件和媒体上传闭环，再调整 App/H5 页面从服务器读数据。

本轮验收命令：

```bash
python -m compileall app
python scripts/verify-vision-pipeline.py
python scripts/verify-fall-rule-engine.py
./scripts/run-ur-fall-eval.sh --no-download
```

当前边界：

- UR Fall 小样本通过只能证明规则链路在小样本上有效，不能对外宣称产品级准确率。
- 真实产品还需要继续扩充公开样本和家庭场景负样本，尤其是坐下、弯腰、躺沙发、多人遮挡、宠物/物体遮挡和夜间低光。
- App 和服务器未完成前，管理台只用于开发验证，不作为最终用户端。

## 27. 2026-07-05 本地 App API 服务器闭环起步

已新增局域网本地 App API 服务器：

- 代码：`local-app-server/server.js`
- 验证：`scripts/verify-local-app-server.js`
- 启动命令：`npm run app-server`
- 验证命令：`npm run verify:app-server`

当前支持的闭环接口：

- `POST /api/v1/device/media-assets/upload`
  - 接收树莓派上传的事件截图证据。
  - 存入 `data/app-server/media/`。
- `POST /api/v1/device/events`
  - 接收树莓派上传的正式事件。
  - 关联同一 `edge_event_id` 的媒体证据。
- `GET /api/app/events`
  - 给 H5/App 壳读取事件列表。
- `GET /api/app/events/:id`
  - 给 H5/App 壳读取事件详情。
- `PATCH /api/app/events/:id`
  - 支持标记已处理或误报。
- `POST /api/v1/video/sessions`
  - 给证据图访问发放临时播放票据。
- `GET /api/v1/video/media/snapshots/:path`
  - 返回事件证据图片。

这一步解决的问题：

- 树莓派不再只能把 `upload_jobs` 堆在本地 `pending`。
- App/H5 可以先从服务器读事件和证据，不再把用户端能力继续塞进 `/admin`。
- 后续迁云时，可以替换存储和鉴权实现，但保持边缘端上传协议基本不变。

当前限制：

- 本地服务器用 JSON 文件保存数据，只用于局域网闭环和比赛演示前验证。
- 视频直播仍需要后续接 go2rtc / MediaMTX / WebRTC；当前服务器先解决事件、截图和 App 数据链。

## 28. 2026-07-05 三文档进度核对与 App/服务器边界纠偏

本轮重新核对 `PRD / Plan / Implement` 后，当前方向没有改变：先完成家庭盒子侧的本地视觉闭环，再跑通最小云端 App API 和设备通道，最后把 App/H5 切到云端语义。用户端不能表现为直接接入摄像头、不能暴露 RTSP、端口、底层模型参数或运行日志。

已完成：

- Stitch 新版 20 个手机 App 页面已接入当前工程，并统一挂载：
  - `assets/styles/stitch-app-adapt.css`
  - `assets/scripts/edge-client.js`
  - `assets/scripts/stitch-app-data.js`
  - `assets/scripts/stitch-app-routes.js`
- 已把桌面预览固定为手机 App 宽度，并补 iOS safe-area 适配。
- 已移除主 App 页顶部重复的“回家”、头像和通知入口；保留页面主体和 Stitch 图片资产。
- 本地 App API 服务器已覆盖注册登录、家庭、老人资料、设备绑定码、设备 token、心跳、摄像头配置记录、事件上传、媒体上传、事件查询和证据图读取；当前定位是云端 API 的本地开发替身。
- 摄像头配置语义已纠偏：
  - App/H5 只创建和展示“摄像头配置记录”与同步状态。
  - 家庭盒子负责实际本地视频接入和状态回传。
  - `/api/v1/device/config` 已返回配置版本和摄像头配置，供设备端同步。
  - App 端展示使用“家庭盒子/守护盒”口径，不在用户端文案暴露底层硬件名称。
- `npm run verify:app-server` 通过，覆盖设备配置拉取、事件上传、媒体上传、事件列表、事件详情、状态回写和证据访问。

当前没有偏离的点：

- 符合 PRD：App 不直接访问摄像头，不直接访问盒子局域网地址。
- 符合 Plan：当前进入“最小云端 App API 和设备通道”阶段；已有的是本地模拟，不是正式云端。
- 符合 Implement：管理台继续只作为开发/安装调试入口，用户端只展示状态、事件、规则和证据。

当前未完成：

- 家庭盒子还没有实际拉取云端 `/api/v1/device/config` 并应用摄像头配置。
- 家庭盒子上传队列还没有在真实盒子到云端链路上完成 `pending -> completed` 验收。
- App/H5 还没有把首页、守护页、消息页、事件详情和实时查看全部切到云端真实数据。
- 实时画面仍是临时 MJPEG/证据链路，正式低延迟视频方案还没完成。
- 消息卡片、天气/新闻/日常提醒仍主要是静态 Stitch 内容，还没有接入统一消息生成服务。
- iOS 原生壳、推送、真机安装和生产级鉴权仍未完成。

下一步：

1. 先把最小 App API 部署到云端，而不是继续停留在局域网本地服务器。
2. 再完成云端服务与家庭盒子的联调：配置云端 base URL、设备 token，确认心跳、配置拉取、事件和媒体上传全部成功。
3. 再把 App/H5 关键页面读数改成云端数据：设备状态、摄像头状态、事件列表、事件详情、证据图。
4. 然后做实时查看的正式演示链路，避免页面继续依赖静态图片或后台调试入口。
5. 最后收 App 交互细节：注册登录后的资料填写、设备绑定引导、消息卡片、规则页、我的页和底部五个主导航。

## 29. 2026-07-05 云端产品路径纠偏

本轮进一步确认：`回家` 的正式产品路径不是“App 连本地服务器”或“App 连局域网盒子”，而是“App 连云端，树莓派盒子也主动连云端”。

产品路径校正：

1. 树莓派开机后的 Wi-Fi 配网仍由盒子本地 `/setup` 承担。
   - 第一版可以是手机连接 `GoHome-XXXX` 后打开 `http://10.42.0.1`。
   - 这一步只解决家庭 Wi-Fi，不进入账号、家庭、摄像头、算法和事件。
2. 配网成功后，用户打开 App。
   - App 连接云端服务。
   - App 完成登录、家庭、老人资料、设备绑定和摄像头配置。
3. 摄像头配置的产品入口在 App。
   - App 把摄像头名称、房间、启用状态和必要接入信息保存到云端。
   - 云端生成配置版本。
   - 树莓派主动拉取配置并在本地执行扫描、测试、拉流和检测。
   - 树莓派回传摄像头同步状态、在线状态、最近截图或错误原因。
4. 日常使用时，App 只读云端。
   - 用户离开老人家局域网后仍可查看设备状态、事件、证据和规则。
   - App 不依赖 `127.0.0.1`、树莓派局域网 IP 或摄像头 RTSP。

当前代码状态重新标定：

- `local-app-server` 是云端 App API 的本地开发替身，不是目标部署形态。
- 当前已经具备第一版接口语义：登录、家庭、老人资料、绑定码、设备 token、摄像头配置、心跳、事件、媒体和证据访问。
- 当前还没有公网部署、正式数据库、对象存储、域名和生产级鉴权。
- 当前 edge-agent 已具备事件和媒体上传 worker，但还缺完整的“拉云端摄像头配置 -> 应用本地配置 -> 回传同步状态”闭环。

下一步调整为：

1. 先部署最小云端 App API，允许 App 和树莓派都从外网访问。
2. 再做 `DeviceConfigSync`：
   - 树莓派定期调用云端 `/api/v1/device/config`
   - 比较 `config_version`
   - 写入本地摄像头配置
   - 执行测试抓帧
   - 回传 `sync_status / status / last_seen_at / last_error`
3. 再把 App/H5 主页面切到云端 base URL。
4. 最后再做正式数据库、对象存储、推送、低延迟实时流和 iOS 打包。

## 30. 2026-07-06 文档清理记录

本轮按“只保留 PRD / Plan / Implement 三份核心文档”的要求，清理掉重复、过期或分散的项目文档。

当前唯一有效文档入口：

1. `想家了吗-PRD.md`
2. `想家了吗-Plan.md`
3. `想家了吗-Implement.md`

已删除的独立说明文档：

- `docs/current-status.md`
- `docs/raspberry-pi-deploy.md`
- `edge-agent/README.md`
- `edge-agent/hyperframes/algorithm-demos/DESIGN.md`
- `ios-shell/README.md`
- `local-app-server/README.md`
- `回家-视觉算法开源素材与评测计划.md`
- `想家了吗-场景化图文消息补充需求.md`
- `想家了吗产品方案.md`

说明：

- 被删除文档里的有效方向已经归并到 PRD / Plan / Implement。
- Implement 前文提到这些 README 或补充文档的位置属于历史记录，不再作为当前操作入口。
- 后续新增产品、路线、进度、验收信息时，必须先写入三份核心文档，不再另开零散 Markdown。

## 31. 2026-07-06 本地 App 服务到树莓派配置同步闭环

本轮按“先本地跑通云端语义闭环，再上云”的顺序，补齐 App API 与树莓派之间的摄像头配置同步链路。

改动前存档：

- 本地当前状态已提交并推送：`5e9565b chore: archive current local progress`
- 已打远端 tag：`archive-before-edge-sync-20260706-001736`
- 树莓派 SSH 确认可用：`gohome@192.168.1.12`
- 树莓派代码目录已备份：
  - `/home/gohome/gohome-backups/gohome-before-local-sync-20260706-001845.tar.gz`
  - `/home/gohome/gohome-backups/gohome-before-config-sync-deploy-20260706-003124.tar.gz`

已完成：

- `local-app-server/server.js`
  - 新增 `POST /api/v1/device/sync`，接收盒子回传的设备状态、配置版本、摄像头同步状态和错误原因。
  - `cameraConfigVersion()` 改为只根据期望配置生成版本，不再因为盒子在线状态变化而反复变更。
  - 修复 JSON DB `next_ids` 未按已有记录回补的问题，避免新增摄像头覆盖旧 ID。
  - 修复盒子回报 `deleted / removed` 时 App 服务反向复活已删除摄像头的问题。
- `edge-agent/app/config_sync_agent.py`
  - 新增 `ConfigSyncAgent`，定期调用 App API `GET /api/v1/device/config`。
  - 将 App 摄像头配置写入盒子本地 SQLite 摄像头表。
  - 维护远端 camera_id 到本地 camera_id 的映射。
  - 对 App 删除的摄像头执行本地清理，并通过 `/api/v1/device/sync` 回报。
- `edge-agent/app/main.py`
  - 接入 `config_sync_agent` 启停生命周期。
  - `/health` 和 `/api/device` 暴露 `config_sync_agent.status()`。
- `edge-agent/app/settings.py`
  - 新增 `GOHOME_CONFIG_SYNC_ENABLED`
  - 新增 `GOHOME_CONFIG_SYNC_INTERVAL_SECONDS`
  - 新增 `GOHOME_CONFIG_SYNC_REQUEST_TIMEOUT_SECONDS`
  - 新增 `GOHOME_CONFIG_SYNC_TEST_CAPTURE_ENABLED`
- `scripts/verify-local-app-server.js`
  - 覆盖 App 写摄像头配置、设备拉配置、设备回报 sync、App 读取同步状态。
  - 覆盖删除回报不应复活摄像头。
- `edge-agent/scripts/verify-config-sync-agent.py`
  - 覆盖盒子配置同步 worker 的创建、更新和删除路径。

本地验证：

- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `edge-agent/.venv/bin/python -m py_compile edge-agent/app/config_sync_agent.py edge-agent/app/settings.py edge-agent/app/main.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-config-sync-agent.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-upload-agent.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-observation-logs.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-fall-rule-engine.py` 通过。
- `edge-agent/.venv/bin/python edge-agent/scripts/verify-vision-pipeline.py` 通过。

树莓派验收：

- 已同步代码到 `/home/gohome/gohome`。
- 已重启 `gohome-edge-agent`，服务运行中。
- `/health` 已显示：
  - `config_sync_agent.enabled = true`
  - `config_sync_agent.running = true`
  - `config_sync_agent.configured = true`
  - `config_sync_agent.reason = ready`
- 真实本地闭环已跑通：
  - App API 创建临时摄像头配置 `stream_url = demo:living_room`
  - 树莓派拉取配置并创建本地摄像头映射
  - 树莓派回传 `sync_status = synced`
  - App API 能看到摄像头状态更新
  - App API 删除临时摄像头后，树莓派删除本地映射并回传 `deleted`
  - 删除后 App API 不再残留该临时摄像头

当前状态：

- 本地闭环已经从“只有事件/媒体上传”推进到“App 摄像头配置下发 + 盒子应用 + 状态回传”。
- 当前 App API 中仍有两条无 `stream_url` 的摄像头配置，盒子按预期回报 `pending_local_setup / stream_url_missing`。
- `GOHOME_CONFIG_SYNC_TEST_CAPTURE_ENABLED` 默认关闭，所以新配置默认回报 `configured / synced`；如果要在同步时立即抓帧验证，可在盒子 `.env` 打开。

下一步：

1. 把 App 摄像头配置页的输入收口，确保真实 RTSP / ONVIF 信息能保存到 App API。
2. 用真实摄像头配置跑一次本地闭环：App 提交配置 -> 树莓派应用 -> worker 拉流 -> App 看到在线/错误。
3. 真实事件触发后，验收 `upload_jobs pending -> completed`。
4. 本地闭环稳定后，把 `local-app-server` 接口语义迁移到云端数据库和公网 HTTPS。

## 32. 2026-07-06 App 摄像头配置页接入 RTSP 配置

本轮继续推进“App 页面 -> App API -> 树莓派盒子”的本地闭环，把 App 摄像头配置页从仅保存名称/房间，补齐为可以保存摄像头接入信息。

已完成：

- `connect.html`
  - 新增摄像头 IP / RTSP 地址输入。
  - 新增端口、码流路径、账号、密码输入。
  - 提交按钮固定为“提交给家庭盒子同步”。
  - 脚本版本抬到 `20260706-config-flow-1`，避免手机或 Chrome 继续使用旧缓存。
- `assets/scripts/stitch-app-data.js`
  - `wireConnect()` 改为读取新增表单字段。
  - 支持两种输入方式：
    - 直接填写完整 `rtsp://...`
    - 填写 IP + 端口 + 路径后自动组装 `rtsp://ip:port/path`
  - 仍支持 `demo:living_room` 这类演示源，便于无真实摄像头时验证链路。
  - 提交后调用 `GoHomeEdge.createCamera()` 写入 App API。
  - 提交后调用 `GoHomeEdge.testCamera(camera.id)`，把状态置为等待家庭盒子同步。
- `cameras.html`
  - 脚本版本抬到 `20260706-config-flow-1`。

Chrome 页面级验证：

- 使用 Chrome 打开：
  - `http://127.0.0.1:8788/connect.html?app=1&edge=http://127.0.0.1:8788&family_id=1`
- 填写临时摄像头：
  - 名称：`Chrome验证摄像头-*`
  - 接入地址：`demo:living_room`
- 提交后页面进入：
  - `cameras.html?camera_id=4&app=1`
- 等待树莓派同步后，摄像头管理页显示：
  - `在线`
  - `家庭盒子已接入并回传状态`
- 删除临时摄像头后，摄像头管理页只剩原有两条配置。
- Chrome 控制台错误：0 条。
- 树莓派 `/health` 正常：
  - `config_sync_agent.enabled = true`
  - `config_sync_agent.running = true`
  - `config_sync_agent.configured = true`
  - `last_error = ""`

本地验证：

- `node --check assets/scripts/stitch-app-data.js` 通过。
- `npm test` 通过。

当前状态：

- 页面已经可以把真实 RTSP 信息写入 App API。
- 目前本地 App API 中原有两条摄像头仍无 `stream_url`，所以盒子继续回报 `pending_local_setup / stream_url_missing`，这是旧数据的预期状态。
- 临时 Chrome 验证摄像头已删除，没有保留测试数据。

下一步：

1. 用真实摄像头 RTSP 地址走一遍同样路径，确认盒子端从 `configured/synced` 进一步进入真实抓帧与事件链路。
2. 将摄像头管理页补一个“编辑接入信息”入口，避免用户改 RTSP 时必须删除重建。
3. 跑真实事件上传验收，确认 `upload_jobs pending -> completed`。

## 33. 2026-07-06 摄像头入口与守护页同步修复

本轮根据手机端实际验证反馈，修复“找不到摄像头配置入口 / 设备管理没入口 / 回到守护页不同步”的产品路径问题。

已完成：

- `cameras.html`
  - 手机端顶部新增明确的“添加摄像头”和“回守护”入口。
  - 桌面端“添加新设备”改为“添加摄像头”，统一进入 App 摄像头配置页。
- `assets/scripts/stitch-app-data.js`
  - 摄像头卡片新增“配置”按钮，可进入 `connect.html?camera_id=...` 编辑已有摄像头。
  - 空状态新增“添加摄像头”按钮。
  - `connect.html` 支持新增和编辑两种模式：
    - 新增时必须填写 IP / RTSP / 演示源。
    - 编辑已有流配置时，RTSP、账号、密码留空表示保留服务器现有配置。
    - 编辑缺配置的旧摄像头时，会提示补齐接入信息。
- `monitor.html`
  - 接入 `monitor-live.js`，守护页不再只显示静态示例卡。
  - 新增“设备管理”入口。
  - 快捷入口补齐“设备管理”。
  - 顶部状态显示 App API / 家庭盒子同步状态。
- `assets/scripts/monitor-live.js`
  - 从 App API 读取摄像头列表并渲染到守护页。
  - 在线摄像头显示“家庭盒子已接入并回传状态”。
  - 缺少接入信息的摄像头显示“还缺少 RTSP / 摄像头接入信息”。
  - 守护页链接会携带当前 `camera_id` 跳转到实时画面 / 规则 / 事件页。
- `assets/scripts/stitch-app-routes.js`
  - 修复旧路由脚本捕获 `add` 图标后跳到 `camera_intro.html` 的问题。
  - 带 `data-action` 的业务按钮交给页面脚本处理。
  - 摄像头管理页的“添加摄像头”统一进入 `connect.html`。

Chrome 验证：

- `cameras.html?app=1`
  - 手机端可见“添加摄像头”和“回守护”。
  - 摄像头卡片可见“配置 / 停用 / 删除 / 同步”。
- 点击“添加摄像头”
  - 正确进入 `connect.html?app=1`。
  - 页面可见摄像头 IP / RTSP、端口、码流路径、账号、密码字段。
- 点击旧摄像头“配置”
  - 正确进入 `connect.html?camera_id=2&app=1`。
  - 对缺配置摄像头提示补齐接入信息。
- 打开已有流配置摄像头：
  - `connect.html?camera_id=5&app=1`
  - 页面显示“配置摄像头 / 保存并同步”。
  - RTSP、账号、密码输入框为空，并提示“留空保留当前配置”。
- `monitor.html?app=1`
  - 页面显示 4 台 App API 摄像头。
  - 在线摄像头显示“家庭盒子已接入并回传状态”。
  - 顶部状态显示“服务在线 / YOLO 检测中”。
  - 守护页“设备管理”入口可返回 `cameras.html?app=1`。

本地验证：

- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/monitor-live.js` 通过。
- `node --check assets/scripts/stitch-app-routes.js` 通过。
- `npm test` 通过。
- `git diff --check` 通过。

当前状态：

- App 端摄像头配置、设备管理、守护页同步路径已经打通。
- 旧数据中仍可能存在无 `stream_url` 的摄像头，页面会明确提示“还缺少 RTSP / 摄像头接入信息”。

下一步：

1. 用真实摄像头 RTSP 地址替换演示源跑一次全链路。
2. 验证树莓派 worker 能真实拉流并产生检测摘要。
3. 验证真实事件上传：`upload_jobs pending -> completed`。
4. 本地闭环稳定后，再把 App API / 数据库迁移到云端 HTTPS 服务。

## 34. 2026-07-06 本地 App API 实时画面闭环修复

本轮根据手机端反馈，修复“在线但没画面 / 守护页回来看不到同步 / 页面用假图误导 / 布局溢出”的问题。

已完成：

- `local-app-server/server.js`
  - `POST /api/v1/device/sync` 入库时保存盒子的 `lan_url / service_url`。
  - 摄像头同步入库时保存 `local_camera_id`，用于把 App 端 camera id 映射到树莓派本地 camera id。
  - `GET /api/v1/video/cameras/{id}/stream.mjpg` 先代理到树莓派真实 MJPEG 流。
  - 当前树莓派未重启到新设备流接口时，本地闭环临时使用盒子管理端 cookie 代理旧 `/api/cameras/{local_id}/stream.mjpg`。
  - 不再把旧事件截图伪装成实时流；没有真实帧时保持等待状态。
- `edge-agent/app/main.py`
  - 配置同步运行状态补充 `lan_url / service_url`。
  - 新增设备 token 保护的 `/api/v1/device/cameras/{camera_id}/stream.mjpg`。
  - 新增本地默认设备 token 对设备流接口的兼容认证。
- `watch.html` / `assets/scripts/watch-live.js`
  - 去掉静态假画面。
  - 只有真实视频帧加载成功后才显示“有画面”。
  - 在线但无帧时显示“盒子已在线，但 App API 还没有收到可显示的视频帧。”
- `monitor.html` / `assets/scripts/monitor-live.js`
  - 守护页只对当前 active 摄像头加载真实 `<img>` 视频流。
  - 修复 8 秒定时重渲染后视频控制器仍绑定旧 `<img>`，导致画面变灰的问题。
  - 真实帧返回后，顶部状态、卡片浮层和摘要统一显示“实时画面已返回”。
- `cameras.html` / `assets/scripts/stitch-app-data.js`
  - 摄像头列表改成紧凑状态行，不再展示假图。
  - 手机端按钮文案压缩为“添加 / 守护”，避免竖排和溢出。

真实链路验证：

- 本地 App API 当前摄像头：
  - App camera id: `8`
  - 树莓派 local camera id: `6`
  - 盒子地址：`http://192.168.1.12:8711`
  - 状态：`online / synced`
- 本地 App API 直播接口：
  - `GET http://127.0.0.1:8788/api/v1/video/cameras/8/stream.mjpg?profile=mobile`
  - 返回 `200 multipart/x-mixed-replace`
  - 响应头包含 `X-GoHome-Stream-State: proxied`
  - 响应头包含 `X-GoHome-Proxy-Mode: device-token`
  - 已收到 JPEG 帧。

Chrome 验证：

- `watch.html?camera_id=8&app=1`
  - `watchStageImage.naturalWidth = 640`
  - `watchStageImage.naturalHeight = 360`
  - 状态显示“有画面”
  - 无横向溢出。
- `monitor.html?camera_id=8&app=1`
  - 等待 12 秒后仍有真实画面。
  - `edgeSnapshotImage.naturalWidth = 640`
  - `edgeSnapshotImage.naturalHeight = 360`
  - 顶部状态、浮层、卡片摘要均显示“实时画面已返回”。
  - 无横向溢出。
- `cameras.html?app=1`
  - 无横向溢出。
  - 顶部入口显示“添加 / 守护”。
  - 摄像头卡片是状态行，不再展示假图片。

本地验证：

- `node --check assets/scripts/edge-client.js` 通过。
- `node --check assets/scripts/watch-live.js` 通过。
- `node --check assets/scripts/monitor-live.js` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `python3 -m py_compile edge-agent/app/main.py` 通过。
- `npm test` 通过。
- `git diff --check` 通过。

已同步到树莓派：

- `watch.html`
- `monitor.html`
- `cameras.html`
- `assets/scripts/edge-client.js`
- `assets/scripts/watch-live.js`
- `assets/scripts/monitor-live.js`
- `assets/scripts/stitch-app-data.js`
- `local-app-server/server.js`
- `edge-agent/app/main.py`

当前限制：

- 树莓派旧 `.venv` 仍有历史路径污染，但已新建 Pi 原生 `.venv-pi` 并用它启动当前 edge-agent。
- `.venv-pi` 当前只安装了本地闭环所需最小依赖：FastAPI、uvicorn、OpenCV headless、numpy 等；YOLO / torch / RTMLib 等完整算法依赖还没在 Pi 原生环境恢复。
- MJPEG 实时画面、设备同步、App 后端代理已跑通；算法 worker 可能因为 YOLO 依赖缺失而降级或报模型加载错误，需要单独恢复。
- 当前已切到 systemd 接管，`gohome-edge-agent.service` 使用 `.venv-pi` 启动；完整 Pi 重启后仍需要再做一次实机 reboot 验证。

下一步：

1. 做一次树莓派整机 reboot 验证，确认 `gohome-edge-agent.service` 能随系统自启恢复。
2. 恢复 Pi 原生 YOLO / torch 依赖；恢复前，Pi 运行态保持 `basic`，避免页面假显示“YOLO 检测中”。
3. 用真实事件重新验证事件与媒体上传：`upload_jobs pending -> completed`，App 事件页能看到当前 camera id 的真实证据。
4. 本地闭环稳定后，再迁移 App API / 数据库到云端 HTTPS 服务。

## 35. 2026-07-06 树莓派重启与真实 UI 再验证

本轮继续完成 section 34 的遗留项：重启树莓派 edge-agent 到新的设备 token 视频接口，并清掉守护页、设备管理页中残留的静态假摄像头卡片。

已完成：

- 树莓派运行状态：
  - SSH：`gohome@192.168.1.12`
  - 项目目录：`/home/gohome/gohome/edge-agent`
  - 旧 `.venv` 确认存在 Mac/Homebrew 路径污染，不能继续作为 Pi 运行环境。
  - 新建 Pi 原生环境：`/home/gohome/gohome/edge-agent/.venv-pi`
  - 当前 edge-agent 进程使用 `.venv-pi/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8711`。
- 树莓派接口：
  - `GET /health` 正常。
  - `GET /api/v1/device/cameras/6/stream.mjpg?profile=mobile&fps=2`
  - 使用 `Authorization: Bearer gohome-local-device-token`
  - 返回 `200 multipart/x-mixed-replace`，并收到 JPEG 帧。
- App 后端代理：
  - `GET http://127.0.0.1:8788/api/v1/video/cameras/8/stream.mjpg?profile=mobile`
  - 返回 `200 multipart/x-mixed-replace`
  - 响应头包含：
    - `X-GoHome-Stream-State: proxied`
    - `X-GoHome-Device-Base: http://192.168.1.12:8711`
    - `X-GoHome-Local-Camera-Id: 6`
    - `X-GoHome-Proxy-Mode: device-token`
- `monitor.html`
  - 删除 HTML 初始态里的“客厅 / 卧室”静态假卡片。
  - 初始态只显示“正在读取摄像头”，脚本接管后才渲染真实摄像头和真实视频流。
- `cameras.html`
  - 删除 HTML 初始态里的“客厅主视 / 后院监控 / 玄关走廊”静态假卡片。
  - 新增 `#cameraDeviceGrid`，脚本只向这个明确容器渲染 App 后端摄像头数据。
- `assets/scripts/stitch-app-data.js`
  - 摄像头管理页优先定位 `#cameraDeviceGrid`，避免误选其它 grid。

当前真实数据：

- App camera id：`8`
- 树莓派 local camera id：`6`
- 盒子地址：`http://192.168.1.12:8711`
- 摄像头状态：`online / synced`
- App 后端摄像头列表当前只有一台真实同步摄像头：`客厅 / 智能摄像头`

Chrome 验证：

- `watch.html?camera_id=8&app=1`
  - `#watchStageImage.naturalWidth = 640`
  - `#watchStageImage.naturalHeight = 360`
  - 视频流 URL 走 `/api/v1/video/cameras/8/stream.mjpg`
  - 无横向溢出。
- `monitor.html?camera_id=8&app=1`
  - `#edgeSnapshotImage.naturalWidth = 640`
  - `#edgeSnapshotImage.naturalHeight = 360`
  - 顶部状态显示“实时画面已返回 / App API 已经从家庭盒子拿到实时画面帧。”
  - 摄像头 grid 只有 1 张真实卡片，`imageCount = 1`。
  - 无静态假文本：`客厅主视 / 后院监控 / 玄关走廊 / 卧室 / 检测到活动 / 设备已离线 2小时` 均不存在。
  - 无横向溢出。
- `cameras.html?app=1`
  - 摄像头 grid 只有 1 张真实卡片。
  - `imageCount = 0`，不再展示任何静态摄像头照片。
  - 显示“在线 / 客厅 / 智能摄像头 / 家庭盒子已接入并回传状态”。
  - 无横向溢出。
- 路径验证：
  - 从 `cameras.html?app=1` 点“守护”，进入 `monitor.html?app=1&camera_id=8`，实时画面自动返回。
  - 从 `monitor.html?app=1&camera_id=8` 点“设备管理”，回到 `cameras.html?app=1`，仍显示同步后的真实摄像头。

本地验证：

- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/monitor-live.js` 通过。
- `node --check assets/scripts/watch-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `git diff --check` 通过。

剩余风险：

- 现在的本地闭环已经覆盖“App 页面 -> App 后端 -> 树莓派设备 token 流 -> 真实画面 -> App 页面显示”。
- 还没完成的是 Pi 原生 YOLO/torch 依赖恢复和持久化启动；这影响算法事件稳定性，不影响当前实时画面闭环。
- 上云前仍需要把本地 JSON DB 换成云端数据库，并给 App API 配 HTTPS 域名。

## 36. 2026-07-06 树莓派 systemd 接管与算法状态纠偏

本轮在 section 35 的基础上继续做“下一步”：把 Pi 当前可用运行方式固化到 systemd，并纠正 App 端显示的算法状态。

已完成：

- `edge-agent/run.sh`
  - Python 选择顺序改为：显式 `PYTHON_BIN` -> `.venv-pi/bin/python` -> `.venv/bin/python` -> 系统 `python3`。
  - `.env.local` 先于 `.env` 读取，确保 Pi 本地运行配置可以覆盖仓库默认值。
- `edge-agent/scripts/install-systemd-service.sh`
  - systemd 安装脚本同样优先选择 `.venv-pi`。
  - 安装时把选中的 `PYTHON_BIN` 传给 `init-box.sh`。
- `edge-agent/scripts/init-box.sh`
  - 初始化脚本同样优先选择 `.venv-pi`，避免再次触碰坏的旧 `.venv`。
- 树莓派运行态：
  - `.env.local` 从当前可用环境固化。
  - `gohome-edge-agent.service` 已重装并启用。
  - 当前 systemd 单元：
    - `ExecStart=/bin/bash /home/gohome/gohome/edge-agent/run.sh`
    - `Environment=PYTHON_BIN=/home/gohome/gohome/edge-agent/.venv-pi/bin/python`
  - `systemctl restart gohome-edge-agent` 后可自动恢复。
- 算法状态纠偏：
  - `.venv-pi` 当前没有 `ultralytics / torch / torchvision / rtmlib / onnxruntime`。
  - 最新截图在 YOLO 模式下曾显示 `model_status=model_error`。
  - 为避免页面继续假显示“YOLO 检测中”，Pi `.env.local` 已临时切到 `GOHOME_DETECTOR_BACKEND=basic`。
  - 切换后最新截图显示：
    - `detector_backend=basic`
    - `model_status=basic`
    - `pipeline_version=vision-pipeline-v1`
- `edge-agent/app/main.py`
  - 设备同步上报 runtime 时补充 `detector_backend / yolo_model / yolo_imgsz`。
- `local-app-server/server.js`
  - `POST /api/v1/device/sync` 保存设备上报的 detector 信息。
  - `/api/app/device` 不再写死 `worker_running=true / detector_backend=yolo`，改为返回设备同步后的真实状态。
- Mac 本地 App API：
  - 发现普通 `nohup node local-app-server/server.js` 在当前桌面工具会话退出后会被清理。
  - 已创建用户级 LaunchAgent：`~/Library/LaunchAgents/com.gohome.local-app-server.plist`。
  - 当前本地 App API 由 launchd `KeepAlive` 接管，监听 `http://127.0.0.1:8788`。

验证结果：

- Pi systemd：
  - `systemctl is-enabled gohome-edge-agent` -> `enabled`
  - `systemctl is-active gohome-edge-agent` -> `active`
  - 主进程为 `.venv-pi/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8711`
- Pi health：
  - `/health` 正常。
  - `config_sync_agent.last_error = ""`
  - App camera id `8` 继续映射到 Pi local camera id `6`。
- App API：
  - `/api/app/device` 当前返回：
    - `worker_running=true`
    - `detector_backend=basic`
    - `yolo_model=""`
    - `yolo_imgsz=null`
  - 本地服务由 `com.gohome.local-app-server` LaunchAgent 保持运行。
  - `/api/app/cameras` 当前摄像头 `8` 仍为 `online / synced`。
- 实时流：
  - App 代理 `/api/v1/video/cameras/8/stream.mjpg?profile=mobile` 返回 `200 multipart/x-mixed-replace`。
  - 响应头仍为 `X-GoHome-Proxy-Mode: device-token`。
- 截图 worker：
  - Pi 持续生成 `data/snapshots/camera_6/*.jpg`。
  - 最新截图为 640x360，约每 6 秒刷新。
- 上传链路：
  - `edge-agent/scripts/verify-upload-agent.py` 通过。
  - 覆盖 `/api/v1/device/media-assets/upload` 和 `/api/v1/device/events`。
- 算法脚本：
  - `edge-agent/scripts/verify-vision-pipeline.py` 通过。
  - 注意：该验证覆盖 pipeline 规则和 demo/fallback，不代表 Pi 上 YOLO 已恢复。

当前限制：

- Pi 原生 YOLO/torch 依赖还没恢复，当前运行态是稳定但降级的 `basic`。
- 事件页里已有的最新高危事件仍来自之前 YOLO 正常时的历史数据；需要在 `basic` 或恢复 YOLO 后重新触发当前 camera id `8` 的真实事件，验证新事件能进入 App。
- 已验证 `systemctl restart`；整机 `sudo reboot` 后自启恢复已在后续验证中补齐。
- Mac 本地 launchd 已验证 `launchctl print gui/501/com.gohome.local-app-server` 为 running；仍需要在机器重启后再验证一次。

下一步：

1. 单独处理 Pi 原生 YOLO/torch 安装方案，避免 pip 拉 CUDA 或破坏当前 `.venv-pi`。
2. 触发一条当前摄像头 `8 / local 6` 的新事件，验证 App 事件页、证据图、上传记录都是当前链路生成。
3. 上云前把本地 JSON DB 换成云端数据库，并给 App API 配 HTTPS 域名。

## 37. 2026-07-06 App 摄像头配置与盒子本地 ID 映射修复

本轮继续处理本地闭环稳定性：修复盒子同步后 App 端多出一个不可播放“影子摄像头”的问题。

问题：

- App 中真正配置的摄像头是 `id=8`，盒子本地应用后生成 `local_camera_id=6`。
- 盒子重启/同步时会回报本地摄像头编号，旧逻辑把 `camera_id=6` 当成 App 端新摄像头写入。
- 结果 `/api/app/cameras` 同时出现：
  - `id=6 / source=edge_reported / setup_required / stream_url_missing`
  - `id=8 / source=app_server_config / online / synced`
- 这会误导 App 页面和设备管理，也可能让盒子配置下发里夹杂不可用摄像头。

已完成：

- `local-app-server/server.js`
  - 新增 App 配置摄像头边界：`appConfigCameras()`。
  - `cameraConfigVersion()` 只计算 App 配置摄像头，不再受盒子诊断上报影响。
  - `/api/v1/device/config` 只下发 App 配置摄像头。
  - `/api/app/cameras` 和 `/api/cameras` 只展示 App 配置摄像头。
  - `/api/v1/devices/current/sync-state` 同步状态只展示 App 配置摄像头。
  - `POST /api/v1/device/sync` 写回时，如果上报的 `camera_id` 是盒子本地 ID，会优先匹配已有摄像头的 `local_camera_id`，避免创建重复 App 摄像头。
  - `POST /api/v1/device/events` 入库前也会把盒子本地 `camera_id` 映射成 App 摄像头 ID。
  - 事件 payload 保留 `edge_camera_id` 和 `app_camera_id`，方便后续排查本地 ID 与云端 ID 的映射关系。
  - 未匹配到 App 配置的盒子上报摄像头仍按 `edge_reported` 处理，不参与用户列表和配置下发。
- `scripts/verify-local-app-server.js`
  - 新增验证：App 摄像头先同步为 `local_camera_id=11` 后，盒子只按本地 `camera_id=11` 回报，服务端仍更新原 App 摄像头，不创建第二个摄像头。
  - 新增验证：盒子事件只带本地 `camera_id=11` 时，App 端事件仍落到原 App 摄像头。
- 运行态数据：
  - 已通过 API 删除历史影子记录 `id=6`。

验证结果：

- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `git diff --check` 通过。
- 本地 App API 已重启并健康：
  - `GET /health` 返回 `ok=true`。
- `/api/app/cameras` 当前只返回 1 个摄像头：
  - `id=8`
  - `status=online`
  - `sync_status=synced`
  - `local_camera_id=6`
- `/api/v1/device/config` 当前只下发 1 个摄像头：
  - `camera_id=8`
  - RTSP 为 `rtsp://192.168.1.11:554/1/2`
  - `setup_required=false`
- Pi `/health` 当前正常：
  - `config_sync_agent.running=true`
  - `last_error=""`
  - `last_result.applied.applied=1`
  - `camera_reports[0].camera_id="8"`
  - `camera_reports[0].local_camera_id=6`
- App 代理实时流仍正常：
  - `/api/v1/video/cameras/8/stream.mjpg?profile=mobile` 返回 `200 multipart/x-mixed-replace`
  - `X-GoHome-Proxy-Mode=device-token`
- 事件闭环：
  - 从 Pi `camera_6` 拿最新真实截图并上传到 App API，生成 asset `29`。
  - 手动模拟盒子事件时请求体使用本地 `camera_id=6`。
  - App API 返回事件 `id=122`，已映射为 `camera_id=8`。
  - 事件 payload 中保留：
    - `edge_camera_id=6`
    - `app_camera_id=8`
  - `/api/app/cameras/8/snapshot/latest?allow_missing=1` 返回 `available=true`，证据图为 `camera_6/20260706_224540_259602.jpg`。
  - `/api/app/cameras/8/evaluation/latest` 返回最新候选事件 `id=122`。
  - 验证完成后，已删除人工事件 `122` 和临时 asset `29`，避免演示数据出现假告警。
  - 当前 `camera 8` 没有保留人工事件，因此 `/api/app/cameras/8/snapshot/latest?allow_missing=1` 恢复为 `available=false`；实时流仍正常。
- Chrome 插件验证：
  - Codex Chrome Extension 已安装并启用，native host manifest 正确，Chrome 正在运行。
  - 但 `chrome.user.openTabs()` 与新建/导航标签页调用会卡住。
  - 按插件排查流程，下一步需要获得用户允许后打开一个匹配 Profile 1 的新 Chrome 窗口再重试。

下一步：

1. 用户允许后，用 Chrome 再走一遍 `cameras.html?app=1 -> monitor.html?app=1&camera_id=8`，确认 UI 不再出现影子摄像头，实时画面仍显示且无横向溢出。
2. 单独处理 Pi 原生 YOLO/torch 恢复；恢复前 App 应继续显示 `basic`，不能假显示 YOLO。
3. 进入上云准备：把本地 App API 的 JSON DB/文件存储抽象替换为云端数据库和对象存储。

## 38. 2026-07-06 守护页多摄像头实时画面

背景：

- 当前 App API 已有两路摄像头：
  - App camera `8` -> Pi local camera `6`
  - App camera `9` -> Pi local camera `7`
- 旧守护页虽然会渲染多个摄像头卡片，但只有 URL 中选中的一路会显示实时 `<img>`。
- 用户实际接了两路摄像头，在守护页期望同时看到两路画面。

已完成：

- `assets/scripts/monitor-live.js`
  - 每个摄像头卡片都渲染实时画面区域。
  - 为每路摄像头创建独立 managed stream controller。
  - 选中摄像头仍驱动顶部状态、底部导航和 `camera_id` URL 参数。
  - 非选中摄像头也显示实时画面状态：连接中、等待第一帧、实时画面已返回、重连中。
  - 卡片标题改为 `房间 · 摄像头名`，避免两个摄像头同在“客厅”时无法区分。
  - 重新渲染卡片前会释放旧 stream controller，避免 DOM 替换后继续绑定旧 `<img>`。
- `monitor.html`
  - 更新 `monitor-live.js` cache buster 到 `20260706-multi-camera-1`。

验证结果：

- App API 摄像头列表确认有两路：
  - `id=8 / online / synced / local_camera_id=6`
  - `id=9 / online / synced / local_camera_id=7`
- Pi health 确认配置同步结果：
  - `applied=2`
  - camera `8` 映射 local `6`
  - camera `9` 映射 local `7`
- Pi 侧两路直接流均可用：
  - `/api/v1/device/cameras/7/stream.mjpg` 返回 `200 multipart/x-mixed-replace`
- App 代理两路均可用：
  - `/api/v1/video/cameras/8/stream.mjpg` 返回 `200`
  - `/api/v1/video/cameras/9/stream.mjpg` 返回 `200`
- 代码检查：
  - `node --check assets/scripts/monitor-live.js` 通过。
  - `npm test` 通过。

限制：

- Chrome 插件仍不稳定：新标签导航/DOM 读取调用会超时，因此这次没有完成可靠的 Chrome 自动截图验证。

## 39. 2026-07-06 App 后端数据库迁移起步

背景：

- 当前 `local-app-server` 已经能支撑本地闭环，但持久化仍是 `data/app-server/db.json`。
- 这套 JSON 数据适合本地验证，不适合上云、多人权限、审计、备份和长期运营。
- 为了不破坏已经跑通的 App 页面和树莓派链路，本轮先固定云端数据库目标结构和迁移快照，不直接重写所有接口。

已完成：

- `local-app-server/migrations/001_initial_schema.sql`
  - 新增 PostgreSQL 14+ 初始 schema。
  - 覆盖用户、家庭、家庭成员、老人档案、设备、设备绑定、绑定码、设备 token、摄像头、摄像头密钥、规则、媒体资产、事件、心跳、日程、设备配置版本和审计日志。
  - 设备 token 在云端目标结构中按 `token_hash` 保存，不再要求明文 token 入库。
  - 摄像头 RTSP 和账号密码从 `cameras` 主表拆到 `camera_secrets`，后续需要接真正的密钥管理或加密存储。
- `scripts/export-local-app-db.js`
  - 新增本地 JSON 数据导出脚本。
  - 默认读取 `data/app-server/db.json`，输出 `data/app-server/cloud-seed.json`。
  - 可用 `--input`、`--out` 和 `--stdout` 指定输入输出。
  - 导出格式按 PostgreSQL schema 的表结构组织，作为后续导入云数据库的 seed bundle。
- `package.json`
  - 新增 `npm run db:export`。
- `scripts/apply-postgres-migrations.js`
  - 新增 PostgreSQL 迁移执行脚本。
  - 使用 `GOHOME_DATABASE_URL` 或 `--database-url` 连接数据库。
  - 使用 `schema_migrations` 记录已执行迁移和 checksum，避免重复执行或静默覆盖。
- `package.json`
  - 新增 `npm run db:migrate`。
- `scripts/verify-local-app-server.js`
  - 测试里加入 seed bundle 校验，确认本地闭环数据能映射到云端表结构。

当前真实导出结果：

- 使用当前 `data/app-server/db.json` 导出到 `/tmp/gohome-cloud-seed.json` 成功。
- 当前本地数据映射结果：
  - `users=2`
  - `families=1`
  - `devices=2`
  - `cameras=2`
  - `camera_secrets=2`
  - `media_assets=28`
  - `events=121`

验证结果：

- `node --check scripts/export-local-app-db.js` 通过。
- `node --check scripts/apply-postgres-migrations.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm test` 通过。

当前限制：

- App API 运行时仍然使用 JSON 文件，不是正式数据库。
- 还没有真正连接 PostgreSQL，也没有云端对象存储。
- 还没有把媒体文件从本地文件系统迁移到对象存储。
- 还没有正式用户权限、家庭成员权限、审计日志写入和 APNs 推送。

下一步：

1. 准备一个本地或云端 PostgreSQL 实例，执行 `GOHOME_DATABASE_URL=... npm run db:migrate` 建表。
2. 给 `local-app-server` 增加数据库适配层，先让读写仍保持现有 API 不变。
3. 把媒体存储抽象出来，下一步从本地 `media/` 切到对象存储。
4. 数据库版本地跑通后，再部署到 HTTPS 云服务，让 App 和树莓派都指向云端地址。

## 40. 2026-07-06 App API 第一版 PostgreSQL Store

背景：

- section 39 已经有 PostgreSQL schema 和 JSON 导出快照，但运行时仍只能用 JSON。
- 本轮目标是先让 `local-app-server` 具备可选 PostgreSQL store，保持现有 App 页面、树莓派接口和测试路径不变。

已完成：

- `package.json` / `package-lock.json`
  - 新增 `pg` 依赖。
- `local-app-server/postgres-store.js`
  - 新增 `PostgresStore`。
  - 支持从 PostgreSQL 表读取数据并还原为当前 `local-app-server` 使用的内存结构。
  - 支持把当前内存结构按 `001_initial_schema.sql` 的表结构写回 PostgreSQL。
  - 当前写回方式是第一版粗粒度 mirror：单服务场景可用，不是最终多租户高并发写入模型。
- `local-app-server/server.js`
  - 新增 `createLocalAppServerAsync`。
  - 默认仍使用 JSON store，现有本地运行方式不变。
  - 配置 `GOHOME_APP_STORE=postgres` 或 `GOHOME_DATABASE_URL` 后可走 PostgreSQL store。
  - `/health` 新增 `store` 字段，用于自检当前是 `json` 还是 `postgres`。
  - 设备 token 生成时补充 `token_hash`，设备鉴权支持明文 token 和 hash token 两种匹配。
  - 写入路径改为 `await store.save()`，兼容异步数据库写入。
- `scripts/apply-postgres-migrations.js`
  - 从外部 `psql` 依赖改为纯 Node + `pg` 执行迁移。
  - 部署环境不再必须安装 PostgreSQL 客户端。
- `scripts/verify-local-app-server.js`
  - 增加云端 seed bundle -> 内存结构的反向还原校验。
  - 增加 seed bundle 字段和 PostgreSQL schema 字段的一致性校验。

验证结果：

- `node --check local-app-server/server.js` 通过。
- `node --check local-app-server/postgres-store.js` 通过。
- `node --check scripts/apply-postgres-migrations.js` 通过。
- `node --check scripts/export-local-app-db.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm run db:migrate -- --dry-run` 通过。
- `npm test` 通过。
- `createLocalAppServerAsync({ storeKind: "json" })` 可启动并返回 `/health.store=json`。
- 本地 launchd 托管的 App API 已重启，`GET /health` 返回 `store=json`。
- 重启后 `/api/app/cameras` 仍返回两路摄像头：
  - `id=8 / online / synced / local_camera_id=6`
  - `id=9 / online / synced / local_camera_id=7`
- 重启后 `/api/app/device` 仍返回 `worker_running=true / detector_backend=basic`。

当前限制：

- 还没有连接真实 PostgreSQL 实例做实库写入测试。
- `PostgresStore` 当前是粗粒度整库 mirror，适合本地闭环和云端试点前验证，不是最终生产级表级 repository。
- 媒体仍在本地文件系统，还没有对象存储。
- 正式用户权限、审计日志写入、APNs 推送仍未完成。

下一步：

1. 启一个本地 PostgreSQL 或直接准备云端 PostgreSQL，执行 `GOHOME_DATABASE_URL=... npm run db:migrate`。
2. 用 `GOHOME_APP_STORE=postgres GOHOME_DATABASE_URL=... npm run app-server` 跑一遍同样的 App/树莓派闭环。
3. 若 Postgres 闭环通过，再把媒体存储抽象成 local/object 两种后端。
4. 然后进入 HTTPS 云部署和 Pi `GOHOME_APP_SERVER_BASE_URL` 切云端。

## 41. 2026-07-07 亲情关怀主线与模型内容策略

背景：

- 当前硬件、摄像头、App API 和本地闭环进展较快，但产品体验仍偏“安全监控”。
- 用户明确指出亲情关怀部分不够，和“回家”的产品初衷有距离。
- 本轮先更新 PRD 和 Plan，明确亲情关怀是产品主线，不是硬件跑通后的装饰功能。

已完成文档调整：

- `想家了吗-PRD.md`
  - 将“每日亲情关怀卡片”写入子女端 App 的 P0 能力。
  - 新增亲情关怀数据流：设备状态、生活节律、事件摘要、日历、天气、联系记录、老人兴趣偏好 -> care-service -> model-service / image-service / content-service -> message-service -> App 卡片。
  - 明确模型 API 只生成候选文案、问候建议和非证据型配图，不决定安全告警。
  - 明确生图模型由平台侧接入 `wan2.7` 或等价能力，但只用于非证据卡片。
  - 明确公众号文章、短视频、自媒体内容推荐必须基于授权、白名单或合规来源，不做未经授权抓取和全文搬运。
  - 新增 `CarePreference / CareCard / ContentSource / ContentRecommendation / ModelGenerationJob` 对象定义。
- `想家了吗-Plan.md`
  - 将 `T7 回家消息与陪伴消息` 升级为 `T7 亲情关怀、回家消息与陪伴消息`。
  - 将执行顺序拆成五批：
    1. P0：每日关怀卡片、问候建议、联系入口、规则模板兜底。
    2. P0.5：文本模型 API 生成更自然的标题、正文和问候建议，失败时回退模板。
    3. P1：平台侧生图模型能力，如 `wan2.7`，用于非证据型卡片配图。
    4. P1.5：用户手动订阅或白名单来源的内容推荐链接。
    5. P2：自动搜索自媒体视频、公众号文章和跨平台内容召回。
  - 补充最小接口范围：
    - `GET /api/v1/app/care-cards/today`
    - `POST /api/v1/internal/care-cards/generate`
    - `GET /api/v1/families/{family_id}/care-preferences`
    - `PUT /api/v1/families/{family_id}/care-preferences`
    - `GET /api/v1/model-providers`，平台内部只读兼容接口
    - `PUT /api/v1/model-providers/{provider_id}`，不开放给用户配置，后续由平台 env / Secret Manager 管理

当前决策：

- 先做 P0 本地闭环，不等上云。
- 亲情关怀第一版不依赖模型 API，先用结构化事实和模板生成可用卡片。
- 文本模型 API 第二步接入，用于润色和个性化表达。
- 生图第三步接入，且只用于非证据型卡片。
- 外部视频和公众号文章推荐后置，不进入当前优先开发项。

已完成 P0 本地实现：

- `local-app-server/server.js`
  - 本地 JSON DB 新增 `care_preferences / care_cards / model_providers / model_generation_jobs / content_sources / content_recommendations` 运行结构，其中 `model_providers` 仅作平台模型能力元数据和历史兼容预留。
  - 新增 `GET /api/v1/app/care-cards/today`。
  - 新增 `POST /api/v1/internal/care-cards/generate`。
  - 新增 `GET /api/v1/families/{family_id}/care-preferences`。
  - 新增 `PUT /api/v1/families/{family_id}/care-preferences`。
  - 新增平台内部只读兼容接口 `GET /api/v1/model-providers`。
  - `PUT /api/v1/model-providers/{provider_id}` 不开放给用户配置，模型底层配置由平台 env / Secret Manager 管理。
  - `CareCard` 第一版使用模板规则生成，不调用模型 API。
  - 事件依据只统计最近 24 小时的未处理事件，避免历史事件堆积误导每日关怀。
- `assets/scripts/edge-client.js`
  - 新增 `v1CareCardToday / v1GenerateCareCard / v1CarePreferences / v1UpdateCarePreferences`，模型底层配置不进入普通前端 SDK。
- `companionship.html`
  - 新增“今日关怀”真实数据卡片区域。
  - 新增“亲情消息”真实消息列表容器。
  - 接入 `assets/scripts/companionship-live.js`。
- `assets/scripts/companionship-live.js`
  - 优先读取 `CareCard` 并渲染今日关怀卡片。
  - 保留原 `MessageCandidate` 消息列表能力。
- `scripts/verify-local-app-server.js`
  - 增加亲情关怀偏好、今日关怀卡片、强制生成卡片、平台模型能力只读状态验证。

原因：

- 当前产品最缺的是“每天能看到家里怎么样”的温度，不是更多外部内容。
- 模型 API 和生图会增加成本、失败率和审核需求，所以必须有模板兜底。
- 自媒体内容、公众号文章和视频推荐涉及来源授权、平台规则、内容安全和推送噪音，过早接入会偏离本地闭环。

下一步实现建议：

1. 首页同步接入今日关怀卡片摘要，不只在陪伴页显示。
2. 接文本模型 provider，先只做文案生成，不接生图。
3. 把 CareCard 文案生成结果写入 `model_generation_jobs`，保留模板回退。
4. 生图和内容推荐等本地卡片主链稳定后再做。

当前限制：

- 当前只实现模板生成，未接真实模型 API。
- 生图 provider 只有配置占位，未调用 `wan2.7`。
- 内容推荐只完成文档和数据结构预留，未接外部内容来源。
- 当前运行态最近 24 小时还有高优先级事件，关怀卡会优先提示“先看重要提醒”，符合安全优先规则。

验证结果：

- `node --check local-app-server/server.js` 通过。
- `node --check assets/scripts/edge-client.js` 通过。
- `node --check assets/scripts/companionship-live.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm test` 通过。
- 本地 App API 已重启。
- `GET /api/v1/app/care-cards/today?family_id=1` 返回 `care-1-2026-07-07`。
- `GET /api/v1/model-providers` 返回模板文本 provider 和禁用态 `wan2.7` 生图 provider。

## 42. 2026-07-07 亲情关怀 PostgreSQL schema 与迁移映射补齐记录

背景：

- 上一轮已经把每日关怀卡片接入 JSON 本地闭环，但上云前还缺 PostgreSQL 表、导出映射和反向还原校验。
- 如果不补这层，本地页面能显示关怀卡片，但切到云数据库时 `CareCard / CarePreference / ModelProvider / ContentRecommendation` 会丢。

已完成：

- `local-app-server/migrations/001_initial_schema.sql`
  - 新增 `care_preferences`。
  - 新增 `care_cards`。
  - 新增 `model_providers`。
  - 新增 `model_generation_jobs`。
  - 新增 `content_sources`。
  - 新增 `content_recommendations`。
- `scripts/export-local-app-db.js`
  - 将 JSON store 中的亲情关怀偏好、每日关怀卡片、模型 provider、模型生成任务、内容来源和内容推荐导出为云端 seed bundle。
  - 保留 `wan2.7` 这类生图 provider 配置状态，但不导出 API key 明文。
- `local-app-server/postgres-store.js`
  - 将新表加入 `TABLE_ORDER / DELETE_ORDER`。
  - 支持从 PostgreSQL 表反向还原到当前本地 App API 使用的 JSON 内存结构。
- `scripts/verify-local-app-server.js`
  - 增加 `care_preferences / care_cards / model_providers` 的导出和反向还原断言。
  - 继续校验 seed bundle 字段必须存在于 PostgreSQL schema。
- `想家了吗-Plan.md`
  - 更新第一批数据库表结构草案，明确当前 `001_initial_schema.sql` 已覆盖的表。
  - 将 `message_candidates / notifications / device_logs` 标记为后续拆分，不抢在 CareCard 主链之前。

验证结果：

- `node --check local-app-server/postgres-store.js` 通过。
- `node --check scripts/export-local-app-db.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm run db:migrate -- --dry-run` 通过。
- `npm test` 通过。

当前仍未完成：

- 还没有连接真实 PostgreSQL 实例做写入测试。
- 文本模型 API 尚未真正接入，`model_generation_jobs` 现在是数据结构预留。
- `wan2.7` 生图 provider 尚未调用，只保留配置位。
- 内容推荐仍只做来源和推荐对象预留，不接自动搜索。

下一步：

1. 首页接入今日关怀摘要，让产品首页也能看到“今天家里怎么样”。
2. 接文本模型 API，生成标题、正文和问候建议，并把请求结果写入 `model_generation_jobs`。
3. 本地 Postgres 或云 Postgres 跑通后，再进入对象存储和 HTTPS 云部署。

## 43. 2026-07-07 后台服务配置页与模型密钥策略记录

状态：本节记录的是已废弃的中间方案。第 44 节已经纠偏为“模型底层配置由平台方通过服务器环境变量或云端 Secret Manager / KMS 管理，普通用户和用户端 App 不配置模型 API”。

废弃原因：

- 页面维护 provider、model、API key 或 secret ref 会把平台内部能力误导成普通用户配置。
- 即使不回显明文 key，前端提交 key 的产品路径也不适合作为 App 用户流程。
- 本地阶段统一改为服务器环境变量；云端阶段统一接 Secret Manager / KMS。

保留结论：

- API key 不能放在前端、localStorage 或普通业务表里。
- 页面只能做平台内部只读状态检查。
- 真正生效方案见第 44 节。

## 44. 2026-07-07 模型配置产品边界纠偏记录

背景：

- 用户指出模型 API 底层配置是 App / 平台提供方的内部配置，不应该让普通家属用户配置。
- 上一版后台页偏工程化，容易误导为用户可填写 provider、key、Base URL 和 Prompt。

纠偏决策：

- 用户端 App 不展示模型配置入口。
- 家属用户只配置老人资料、兴趣、提醒频率、内容偏好和联系人，不配置模型底层参数。
- 平台方内部只需要两类模型能力：
  - 多模态语言模型：根据日历、热点信息、天气预报、设备状态、摄像头状态、事件和老人资料生成每日关怀卡片内容。
  - 生图模型：根据卡片内容生成 1:1 温馨可爱漫画图文卡片，且只用于非证据型关怀卡片。
- `base_url / api_key / model / prompt` 由平台方在服务器环境变量或云端 Secret Manager / KMS 配置。
- 运营后台只做内部只读状态检查，不提供给普通用户填写 key、Base URL、模型名或 Prompt。

已调整：

- `local-app-server/server.js`
  - 移除页面提交 API key 写入本地 secret 文件的产品路径。
  - 新增平台模型能力读取逻辑：
    - `multimodal-language`
    - `care-card-image`
  - 本地环境变量支持：
    - 多模态语言模型：`GOHOME_MULTIMODAL_BASE_URL / GOHOME_MULTIMODAL_API_KEY / GOHOME_MULTIMODAL_MODEL / GOHOME_CARE_CARD_PROMPT`
    - 兼容文本模型变量：`GOHOME_TEXT_MODEL_BASE_URL / GOHOME_TEXT_MODEL_API_KEY / GOHOME_TEXT_MODEL`
    - 兼容 OpenAI 风格变量：`OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL`
    - 生图模型：`GOHOME_IMAGE_BASE_URL / GOHOME_IMAGE_API_KEY / GOHOME_IMAGE_MODEL / GOHOME_CARE_IMAGE_PROMPT`
    - 兼容 wan / DashScope 变量：`GOHOME_WAN_BASE_URL / GOHOME_WAN_API_KEY / GOHOME_WAN_MODEL / DASHSCOPE_BASE_URL / DASHSCOPE_API_KEY`
  - `GET /api/v1/ops/service-config` 返回两类能力状态、默认 prompt、环境变量指引和密钥策略。
  - `PUT /api/v1/model-providers/{provider_id}` 不再允许页面写入底层配置。
- `ops.html`
  - 改为平台内部只读状态页。
  - 页面不再有 API key 输入框、Base URL 输入框、Prompt 编辑框或保存按钮。
- `assets/scripts/ops-live.js`
  - 改为只读渲染两类模型能力。
- `assets/scripts/edge-client.js`
  - 移除前端写模型 provider 的 SDK 方法。
- `scripts/verify-local-app-server.js`
  - 验证普通 App token 不能写模型底层配置。
  - 验证后台只读接口返回两类模型能力。

验证要求：

- 普通用户路径不能出现模型底层配置。
- 平台内部后台只能看到是否已配置和 env 指引，不回显明文 key。
- 后续接文本模型 API 时，只读取平台侧配置，不从用户表单读取 key。

## 45. 2026-07-07 本地平台模型 env 配置记录

背景：

- 平台方先在本地配置两类模型能力，用户自行填写 API key。
- API key 继续只放服务器本地 env，不进入前端、不进入普通业务数据库、不提交到 git。

已完成：

- 新增根目录 `.env.example`，作为可提交的模板。
- 新增根目录 `.env`，已被 `.gitignore` 忽略，用于本机填写真实 key。
- `local-app-server/server.js`
  - 在读取默认端口、模型配置等常量前加载 `.env` 和 `.env.local`。
  - 系统真实环境变量优先；`.env.local` 可覆盖 `.env` 中的本地配置。
  - `GET /api/v1/ops/service-config` 返回 `env_files`，便于确认服务是否吃到 env 文件。
- `scripts/verify-local-app-server.js`
  - 验证模型能力状态接口不返回 `base_url` 明文。
  - 验证模型能力状态接口不返回 API key 或脱敏 key 片段。

当前本地模型配置：

- 多模态语言模型：
  - `GOHOME_MULTIMODAL_BASE_URL=https://api.siliconflow.cn/v1/chat/completions`
  - `GOHOME_MULTIMODAL_MODEL=Qwen/Qwen3.5-27B`
  - `GOHOME_MULTIMODAL_API_KEY=` 由平台方本机填写
- 生图模型：
  - `GOHOME_IMAGE_BASE_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`
  - `GOHOME_IMAGE_MODEL=wan2.7-image`
  - `GOHOME_IMAGE_API_KEY=` 由平台方本机填写

使用方式：

1. 在根目录 `.env` 填入 `GOHOME_MULTIMODAL_API_KEY` 和 `GOHOME_IMAGE_API_KEY`。
2. 重启 `com.gohome.local-app-server`。
3. 打开 `ops.html?app=1` 或读取 `/api/v1/ops/service-config`，确认两类模型能力从“待配置”变为“已配置”。

注意：

- 不要把真实 key 写进 `.env.example`、文档或前端代码。
- 云端部署时不复制本地 `.env`，改接云厂商 Secret Manager / KMS。

## 46. 2026-07-07 多模态语言模型关怀卡片接入记录

背景：

- 本地 `.env` 已配置硅基流动多模态语言模型 `Qwen/Qwen3.5-27B`。
- 下一步需要让“今日关怀”从模板兜底升级为模型生成，但不能让模型失败影响 App 基础可用性。

已完成：

- `local-app-server/server.js`
  - `generateCareCard` 改为异步生成。
  - 生成今日关怀卡片时，优先调用平台侧多模态语言模型。
  - 模型成功时使用模型返回的 `title / body / facts / suggested_actions / image_brief`。
  - 模型失败、超时或返回格式不合格时，自动回退 `care-template-v2`。
  - 每次模型调用写入 `model_generation_jobs`：
    - `purpose=care_card_generation`
    - `model=Qwen/Qwen3.5-27B`
    - `prompt_version=care-card:default`
    - `input_hash`
    - `output_status=succeeded/failed`
    - `request_payload / response_payload`
  - job 不保存 API key。
  - 模型请求默认超时提高到 60 秒，可用 `GOHOME_MODEL_REQUEST_TIMEOUT_MS` 调整。
  - 对 Qwen 推理型返回做了适配：
    - 请求加 `response_format={type:"json_object"}`
    - 请求加 `enable_thinking=false`
    - 请求加 `thinking_budget=128`
    - 输出 token 提高到 1600
- `.env.example`
  - 新增 `GOHOME_CARE_MODEL_CALLS=1` 作为外部模型调用开关。
  - 新增 `GOHOME_MODEL_REQUEST_TIMEOUT_MS=60000`。
- `scripts/verify-local-app-server.js`
  - 测试默认关闭真实模型调用，避免本地回归消耗真实 API。
  - 增加本地 mock Chat Completions 服务，验证模型成功路径能生成 `model:mock-care-model` 卡片并写入成功 job。

真实验证：

- `/api/v1/ops/service-config` 显示：
  - `multimodal-language.configured=true`
  - `care-card-image.configured=true`
- 第一次真实调用在 20 秒超时后回退模板。
- 提高超时后，模型返回 `reasoning_content`，`message.content` 为空，导致 JSON 校验失败。
- 关闭 thinking 后真实调用成功：
  - `generated_by=model:Qwen/Qwen3.5-27B`
  - `model_generation_jobs.output_status=succeeded`
  - App 今日关怀接口能读到模型生成卡片。

当前边界：

- 已接通：多模态语言模型生成每日关怀文案。
- 暂未接通：DashScope `wan2.7-image` 生图真实调用。
- 生图下一步应做成任务式调用，避免打开 App 页面就立刻产生图片生成成本。

## 47. 2026-07-07 “我的-关怀推送”配置闭环

背景：

- 用户明确要求关怀卡片推送是核心功能之一，不是普通通知设置。
- 配置应放在“我的”里，普通家属用户只配置关怀偏好，不配置模型 API、Base URL、Key 或 Prompt。
- 第一版要先本地跑通配置保存和卡片生成上下文；真正到点推送等云端 scheduler、notification-service 和 APNs 接入后执行。

已完成：

- `privacy.html`
  - 在“我的”页新增“关怀推送”入口，进入 `care_schedule.html`。
- `care_schedule.html`
  - 新增关怀推送设置页。
  - 支持设置每日推送时间、开启状态、卡片内容类型、关怀重点、老人兴趣、上次回家日期、回家提醒阈值、定位开关占位和纪念日。
  - 支持“立即生成”，用于本地验证保存后的配置是否进入今日关怀卡片。
- `assets/scripts/care-schedule-live.js`
  - 读取 / 保存 `metadata.care_card_schedule`。
  - 立即生成前先保存当前配置，再调用 `/api/v1/internal/care-cards/generate`。
- `local-app-server/server.js`
  - `CarePreference.metadata.care_card_schedule` 增加标准化。
  - 每日卡片生成上下文包含关怀推送配置。
  - facts 会纳入回家间隔、老人兴趣、纪念日数量和用户填写的关怀重点。
- `scripts/export-local-app-db.js` / `local-app-server/postgres-store.js`
  - 导出和恢复 `care_preferences.metadata`，避免上云 seed 丢失关怀推送配置。
- `scripts/verify-local-app-server.js`
  - 增加关怀推送配置保存、模型上下文、seed 导出和恢复断言。

当前边界：

- 已完成：用户端配置、后端持久化、模型上下文和立即生成闭环。
- 已完成：DashScope `wan2.7-image` 生图任务已接入本地闭环，完整记录见下一节。
- 暂未完成：云端定时任务、真实 APNs 定时推送、定位距离自动更新。
- 下一步应优先做云端化前的数据和任务边界：把本地 PostgreSQL 跑通后，再把 `care_card_schedule` 接到云端 scheduler。

## 48. 2026-07-07 每日关怀 1:1 生图卡片接入记录

背景：

- 用户确认每日关怀应是“图片展示”的图文卡片，不只是文字摘要。
- 模型 API 由 App 提供方配置，普通家属用户不配置 Base URL、Key、模型名或 Prompt。
- 生图只能用于非证据型关怀表达，不能替代告警证据、真实截图或老人真实影像。

已完成：

- `local-app-server/server.js`
  - 新增 DashScope 生图调用链路。
  - 根据模型/接口自动区分：
    - `wan2.7-image`：同步 JSON 文生图结构，不使用 `X-DashScope-Sse`。
    - `wan2.6-image` 图文混排：保留 `enable_interleave + stream` 兼容路径。
    - 其他异步任务端点：保留 `X-DashScope-Async` + task 轮询路径。
  - 生图 prompt 使用卡片标题、正文、事实摘要、老人兴趣和模型返回的 `image_brief`。
  - 默认生成 1:1 `1024*1024` 图片。
  - 供应商返回的临时图片 URL 会立即下载到 `data/app-server/media/care-cards/...`。
  - `CareCard.image_url` 只保存本地 `snapshot_path`，不保存供应商临时 URL。
  - 生图任务写入 `model_generation_jobs`，`purpose=care_card_image_generation`，不保存 API key。
  - 已生成但缺图的旧 `CareCard` 会自动补图；失败时标记 `failed_provider` 并保留文字卡。
- `companionship.html` / `assets/scripts/companionship-live.js`
  - 完整“今日关怀”卡改为图文结构。
  - 增加固定 1:1 图片容器。
  - 图片加载时使用透明态而不是 `display:none + lazy`，避免浏览器不触发加载。
  - 图片失败时显示产品化占位，不暴露模型或接口错误。
  - 修正 facts 渲染，避免把模型文本直接拼进 `innerHTML`。
- `scripts/verify-local-app-server.js`
  - 默认关闭真实模型和真实生图调用，避免 `npm test` 消耗真实 API。
  - 增加 mock DashScope 同步生图服务，验证：
    - 请求参数为 1:1。
    - 返回图能下载落本地 media asset。
    - `CareCard.image_mode=generated`。
    - 通过 `/api/v1/video/media/snapshots/...` 可读取图片。
    - seed bundle 导出和 PostgreSQL 反向还原包含新增媒体资产。
- `.env.example`
  - 新增 `GOHOME_CARE_IMAGE_CALLS`、`GOHOME_CARE_IMAGE_SIZE`、`GOHOME_IMAGE_REQUEST_MODE`。
  - 默认生图尺寸为 `1024*1024`。

真实验证：

- 使用本地 `.env` 中的真实 `Qwen/Qwen3.5-27B` 和 DashScope `wan2.7-image` 配置强制生成今日关怀。
- 结果：
  - `generated_by=model:Qwen/Qwen3.5-27B`
  - `image_mode=generated`
  - `image_url=care-cards/2026-07-07/30-care-1-2026-07-07.png`
  - 图片媒体接口返回 `200 image/png`，文件大小约 2.8MB。
  - 图片本身为有效 PNG，当前旧图尺寸为 `1024 x 1792`；新默认生成尺寸已切到 `1024 x 1024`。
- 内置浏览器验证：
  - 桌面宽度：图片加载完成，容器比例 `1.0`，无横向溢出。
  - 手机宽度 `390x844`：图片加载完成，容器比例 `1.0`，无横向溢出。

当前边界：

- 已完成：本地 API、模型调用、媒体落库、陪伴页完整卡展示和回归测试。
- 首页和陪伴页都展示 1:1 今日关怀图文卡；点开陪伴页查看完整正文、事实和动作。
- 暂未完成：云端 scheduler 定时生成、真实 APNs 推送、定位距离自动更新、白名单内容推荐。

## 49. 2026-07-07 用户端页面信息架构纠偏

背景：

- 用户反馈首页、守护、规则、事件和陪伴的页面语义混乱：示例式“今日居家提醒”不属于真实产品能力，“调整睡眠模式”偏离需求；守护页把“检测说明”误写成“规则设置”；事件页仍叫“消息中心”；陪伴页把安全事件显示成“亲情消息”。
- 本轮按产品边界重新拆分：关怀归亲情关怀，安全告警归事件，规则开关归我的，检测说明只解释本轮视觉结果。

已完成：

- `index.html` / `assets/scripts/home-live.js`
  - 删除首页独立“今日居家提醒”和“调整睡眠模式”。
  - 首页首屏改为“今日关怀”1:1 图文卡预览。
  - “家庭状态”改为盒子状态和摄像头数量，不再伪造温湿度。
  - 常用入口改为 2x2 图片式入口：守护画面、事件记录、设备管理、关怀推送。
- `monitor.html`
  - 守护页快捷入口中的“规则设置”改为“检测说明”，跳转 `detection.html`。
  - 规则开关不再作为守护快捷入口出现。
- `detection.html` / `assets/scripts/detection-live.js`
  - 页面标题改为“检测说明”。
  - 文案明确这是检测事实和提醒依据，不是规则配置页。
  - 顶部返回改回守护页，不再默认回实时观看。
- `events.html` / `assets/scripts/events-live.js`
  - 页面从“消息中心”收敛为“事件记录”。
  - 移除天气、服药、相册等静态生活提醒示例。
  - 接入真实事件列表 DOM，显示摄像头、时间、状态和处理入口。
- `companionship.html` / `assets/scripts/companionship-live.js`
  - 陪伴页首屏改为每日关怀卡片。
  - 删除静态“互动建议”模块。
  - “亲情消息”改为“关怀提醒”，并过滤掉 `alert` 或带事件来源的安全消息，避免安全事件和亲情关怀混线。
  - 关怀图容器改为 1:1，旧 4:7 图片用 `object-contain` 保留完整内容；新生成图片默认 1:1。
- `assets/scripts/stitch-app-routes.js`
  - 底栏第三项统一为“事件”，保留“消息”作为旧文本兼容路由。
  - 新增“检测说明”“事件记录”“关怀推送”等入口路由。

验证：

- `node --check` 覆盖本轮修改的前端脚本。
- `git diff --check` 通过。
- `npm test` 通过。
- 内置浏览器手机视口 `390x844` 验证：
  - 首页、守护、检测说明、事件、陪伴均无横向溢出。
  - 首页和陪伴页关怀图容器比例均为 `1.0`。
  - 可见页面不再出现“今日居家提醒”“调整睡眠模式”“消息中心”“亲情消息”。
  - 守护页不再显示“规则设置”快捷入口，改为“检测说明”。

当前边界：

- 当前已经生成的旧关怀图片仍是 4:7 资源，页面会完整显示在 1:1 容器内。
- 重新生成后，默认请求尺寸为 `1024*1024`。
- 联系节奏里的“3 天 / 45 分钟”仍是前端占位，后续需要接真实联系记录、定位和回家记录。

## 50. 2026-07-07 用户端信息架构与安全区二次收口

背景：

- 用户再次确认页面不能为了有功能强塞入口和跳转，必须符合家属端浏览和操作逻辑。
- 用户要求按审美重新调整前端页面，并明确处理 iPhone 刘海区和底部安全区。
- 本轮基于 `design-taste-frontend` 做移动端产品重审，按“信任优先、家庭关怀、轻 iOS 原生感”收口。

已完成：

- `assets/styles/stitch-app-adapt.css`
  - 增加本地 Material Symbols 字体，避免断网或 Google Font 未加载时图标显示成英文文本。
  - 统一主 Tab 页顶部安全区、二级页顶部安全区、底部导航安全区和桌面手机壳宽度。
  - 固定底部导航实色背景，减少滚动内容透出。
- `index.html` / `assets/scripts/home-live.js`
  - 首页保留“今日关怀”完整 1:1 图文卡片作为首屏主内容。
  - 新增“关怀卡片”历史流，后续每天生成后向下沉淀，符合刷信息流的浏览逻辑。
  - 删除首页 2x2 强入口，不再把守护、事件、设备管理、关怀推送都塞在首屏。
  - 隐藏用户端不需要看的模型来源，不再暴露 `model:Qwen...`。
- `monitor.html` / `assets/scripts/monitor-live.js`
  - 守护页只保留状态和实时画面，不再放设备管理、规则设置、检测说明等重复模块。
  - 摄像头卡片只保留“看画面”，配置入口收敛到顶部“设备”。
  - 用户端文案不再暴露 `App API / YOLO / edge-agent` 等工程词。
- `events.html` / `event_detail.html`
  - 事件页只保留安全事件时间线。
  - 事件详情承接“提醒依据”，解释规则和检测事实，不再把检测说明做成独立主流程。
- `privacy.html` / `cameras.html` / `rules.html`
  - “我的”承担家庭成员、关怀推送、设备管理、通知、规则、隐私。
  - 设备管理页底部导航 active 归到“我的”，不再归到“守护”。
  - 家庭成员文案从“共享位置”改为“共享守护”，避免提前承诺定位能力。
  - 规则页只展示当前真实支持能力，并用“视觉模型 / 家庭盒子服务”替代底层工程名。
- `care_schedule.html`
  - 关怀设置保持每日推送、内容类型、关怀重点、老人兴趣、回家提醒和纪念日。
  - 纪念日继续按每年同月同日进入关怀卡片上下文。
- `watch.html` / `assets/scripts/watch-live.js`
  - 实时查看页主动作从“看检测”改为“回守护”，检测依据不再作为主流程入口。
  - 文案不再暴露 `App API / YOLO`。
- `assets/scripts/stitch-app-routes.js`
  - 保留统一路由兜底，避免页面旧路由脚本抢跳。

验证：

- 使用本机 Chrome headless 以 `390 x 844` 移动视口验证：
  - 首页、守护、事件、事件详情、实时查看、陪伴、我的、关怀设置、规则、设备管理均 `scrollWidth = clientWidth = 390`。
  - Material Symbols 没有退化成 `home / security / history` 等英文文本。
  - 主 Tab 页滚到底后，最后一个可操作按钮没有被底部导航遮挡。
  - 首页和陪伴页没有再请求旧的 `/api/v1/internal/messages/generate`，404 已清除。
- `node --check` 已覆盖本轮修改的前端脚本。

当前边界：

- 当前仍是本地 App API 替身，正式上云后需要把同一套接口迁移到云端服务。
- 首页历史卡片当前只有今日一张，后续随着定时生成自然沉淀多张。
- 定位距离、联系记录、节假日内容推荐和 APNs 定时推送仍未完成，不能在演示中说成正式能力。

## 51. 2026-07-07 关怀推送页重排记录

背景：

- 用户指出 `care_schedule.html` 仍像后台表单，视觉堆叠、模块重复，不符合家属端 App 设置页的浏览逻辑。
- 本轮继续按 `design-taste-frontend` 做移动端重排，但只作用于关怀推送页，不改变已有后端字段契约。
- 产品边界继续保持：普通家属只配置每日推送、卡片内容、关怀重点、兴趣、回家提醒和纪念日；模型 API、Base URL、Key、Prompt 仍由平台侧配置，不暴露给用户。

已完成：

- `care_schedule.html`
  - 顶部改为轻 iOS 设置页结构：返回、标题、今日关怀入口。
  - 首屏新增“每日关怀卡片”概览，明确推送时间、开启状态、内容数量和首页展示关系。
  - “每日推送”和“推送时间”合并为行式设置，减少后台表单感。
  - “卡片内容”改为多行可扫读选项，并把文案收敛到家里状态、问候话题、养生小贴士、天气问候、回家间隔、节日问候和纪念日。
  - “老人关心的话题”保留两列轻量选项，用于问候话题和后续合规内容推荐。
  - “回家提醒”去掉旧的定位开关占位，只展示上次回家日期和超过多少天提醒，避免提前承诺定位距离。
  - “纪念日”改成名称一行、日期和删除一行，保证 `1956-11-06` 这类日期在 390 宽度下完整显示。
  - 页面顶部、左右和底部使用 `env(safe-area-inset-*)`，底部保存动作避开 Home Indicator。
  - 去掉本页不再需要的 Tailwind CDN 和 Google 字体外链，改用本地 Material Symbols 和本地中文字体，避免 console 噪音。
- `assets/scripts/care-schedule-live.js`
  - 顶部概览从表单实时同步推送时间、开启状态和内容数量。
  - 保存时不再把旧的 `location_tracking_enabled` 占位开关写成开启。

验证：

- `node --check assets/scripts/care-schedule-live.js` 通过。
- `git diff --check -- care_schedule.html assets/scripts/care-schedule-live.js` 通过。
- 使用本机 Google Chrome headless 以 `390 x 844` 移动视口验证：
  - 首屏和底部视口均为 `scrollWidth = clientWidth = 390`。
  - 所有输入、按钮和链接都在视口内。
  - 底部固定动作区距离视口底部约 `50px`，不会压到 Home Indicator。
  - 纪念日日期输入宽度约 `273px`，`1956-11-06` 可完整显示。
  - Material Symbols 使用本地字体，没有退化为英文图标文本。
  - console 无 warning、error 和 404。
  - 页面可见文案不包含 `API / Base URL / Prompt / YOLO / edge-agent` 等工程词，也不包含旧错文案。

当前边界：

- 本页仍是“配置保存和立即生成”闭环；真正每天到点推送仍要等云端 scheduler、notification-service 和 APNs。
- 回家提醒当前基于手动日期和天数，联系记录、到家记录和定位授权仍未接入。

## 52. 2026-07-07 全局 App 页面视觉与安全区统一

背景：

- 用户认可 `care_schedule.html` 的重排方向，要求其他全部用户端页面按同一审美统一，并明确 iOS 刘海区必须预留。
- 本轮定位为视觉和布局统一，不改变后端接口、数据库字段、DOM id、页面业务归类和路由契约。

已完成：

- `assets/styles/stitch-app-adapt.css`
  - 统一 Stitch 页面主色、卡片、按钮、输入框、底部导航和本地字体。
  - 对普通根页面直接增加顶部 `env(safe-area-inset-top)` 处理，不再依赖运行时脚本补页面 class。
  - 底部导航收敛宽度、标签单行省略，避免 390 宽度下挤出屏幕。
  - 首页和陪伴页的今日关怀图统一为 1:1 视觉容器，并去掉旧暖黄色占位的突兀感。
  - 补齐 `primary-fixed` 等 Tailwind 辅助 token 覆盖，避免局部旧蓝色残留。
- `assets/styles/app.css`
  - 统一纪念模式、检测说明、平行世界等页面的绿灰视觉体系。
  - 修正 `app-phone-shell` 与 `app-topbar` 的安全区分工，避免 iOS 上顶部安全区重复叠加。
  - 修复平行世界聊天输入行和底部导航的窄屏溢出风险。
  - 补齐 Tailwind 工具类颜色映射，避免局部文字和底部导航继续露旧色。
- 全部根 HTML 页面
  - 移除 Google Fonts 外链，改用本地 Material Symbols 和本地中文字体。
  - 刷新共享 CSS 版本号，减少浏览器旧缓存影响。
  - 补空 favicon，清除 `/favicon.ico` 404 噪音。
- `cameras.html`
  - 摄像头管理页底部导航 active 从“我的”改回“守护”，符合设备和摄像头属于守护路径的产品归类。

验证：

- 使用本机 Chrome headless 以 `390 x 844` 移动视口覆盖 27 个根页面：
  - `welcome / onboarding / login / parent_profile / family / device_binding / camera_intro / connect`
  - `index / monitor / watch / events / event_detail / companionship / privacy / care_schedule / cameras / rules / family_members / notifications / privacy_data`
  - `detection / memorial_home / digital_human / memory_gallery / voice_archive / ops`
- 审计结果：`problemCount = 0`。
  - 无横向溢出。
  - 无控件越界。
  - 无 404。
  - `digital_human.html` 聊天输入和底部导航不再挤出视口。
  - 首页、守护、陪伴、我的、设备管理、平行世界和关怀推送已抽样截图检查。
- `npm test` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/stitch-app-routes.js` 通过。

当前边界：

- 本轮只做用户端页面视觉统一和安全区修复，没有改变云端化、APNs、定位距离、节假日内容推荐等未完成能力。
- `ops.html` 仍是平台侧服务后台页面，只做轻量视觉统一，不作为普通家属端入口。

## 53. 2026-07-08 产品路径和真实状态修复

背景：

- 用户指出 App 已经能看到盒子和摄像头，但登录后首页仍显示未配置；事件、陪伴、规则、我的页面存在旧事件、错误跳转、管理员身份、重复设置入口和 iOS 安全区问题。
- 本轮按产品路径修复：本地闭环阶段优先相信家庭盒子和摄像头真实运行状态，账号绑定只作为云端关联，不再阻断首页进入已连接状态。

已完成：

- `assets/scripts/home-live.js`
  - 首页改为先读取家庭盒子、摄像头和事件状态，只要有启用摄像头或盒子在线，就展示已连接状态，不再因为缺少设备绑定显示“待绑定 / 待接入”。
  - 首页关怀卡片改为横向滑动卡片流，并新增位置与回家模块；没有真实定位时显示“距离待授权”，不伪造距离。
  - 首页过滤已恢复在线摄像头对应的旧离线事件，消息卡也只承接当前启用摄像头的事件。
  - 修复“无高优先级告警”被误判成“需关注”的问题。
- `assets/scripts/events-live.js` / `assets/scripts/event-detail-live.js`
  - 事件列表和详情过滤已恢复在线的旧离线事件。
  - 将 `edge-agent`、拉流失败、无帧返回等工程文案转成家属可理解的事件说明。
- `companionship.html` / `assets/scripts/companionship-live.js`
  - 陪伴页删除重复的关怀推送设置入口，只保留今日关怀内容和联系动作。
  - 联系动作改为“发消息 / 打电话”；打电话读取老人资料中的手机号或家里电话，缺失时提示补充。
  - 修复 actions/source 为对象时显示 `[object Object]` 的问题，移除普通关怀提醒强跳事件页或实时画面的逻辑。
- `parent_profile.html` / `assets/scripts/stitch-app-data.js` / `local-app-server/server.js`
  - 老人资料增加手机号、家里电话和城市字段，并写入本地 App API。
  - 本地服务记录最近登录 / 注册用户，`/api/users/me` 不再固定返回默认管理员。
  - “我的”页展示家属账号和家庭关系，并用盒子运行状态或在线摄像头判断“家庭盒子已连接”。
- `rules.html` / `assets/scripts/rules-live.js`
  - 规则页开关改为移动端 toggle，整行可点。
  - 保存反馈改为“已同步到家庭盒子 / 等待家庭盒子下一轮检测读取”。
- `assets/styles/stitch-app-adapt.css` / `assets/styles/app.css`
  - App 模式强制预留顶部安全区，浏览器预览中 `env(safe-area-inset-top)` 为 0 时也保留 iOS 刘海区空间。
- `local-app-server/server.js`
  - 关怀卡片生成只统计当前启用摄像头的近 24 小时事件，并忽略已恢复在线的旧离线事件。
  - 本地 DB 今日关怀卡片已重新生成，首页和事件页状态保持一致。

验证：

- `npm test` 通过。
- `git diff --check` 通过。
- `node --check` 覆盖本轮修改的前端脚本和 `local-app-server/server.js`。
- 使用 Chrome / Playwright 以 `390 x 844` iPhone 视口验证：
  - 首页不再显示“待绑定 / 未配置 / 待接入”，显示 2 路摄像头在线和横向关怀卡片流。
  - 事件页没有旧离线事件和工程错误，显示当前平稳。
  - 陪伴页不显示 `[object Object]`，不再出现普通关怀跳事件或实时画面的动作。
  - 我的页不显示 `回家管理员 / admin@gohome.local`，徽章显示“家庭盒子已连接”。
  - 规则页 toggle 宽高为 `52 x 30`，点击整行可改变并保存。
  - 首页、事件、陪伴、我的、规则均无横向溢出，首个内容块距离顶部约 `52-72px`，避开刘海区。

当前边界：

- “发消息”当前在 Web 阶段尝试打开 `weixin://`，正式 iOS App 阶段需要接系统分享或微信能力。
- 电话能力依赖老人资料已填写手机号或家里电话。
- 定位距离仍未接入 iOS 授权和定位服务，当前只展示“距离待授权”。

## 54. 2026-07-08 主路径前端产品化重排

背景：

- 用户指出首页、守护、事件、陪伴、我的和设备管理仍有旧原型痕迹：卡片边界重、模块像强塞入口、陪伴与守护互跳、设置入口重复、刘海区和布局观感需要继续统一。
- 本轮目标不是新增后端能力，而是把已经跑通的盒子、摄像头、事件和关怀卡片按产品浏览逻辑重新归类。

已完成：

- `index.html` / `assets/styles/stitch-app-adapt.css`
  - 刷新资源版本，继续保留首页“今日推送”横向信息流、完整关怀卡片预览、位置与回家模块和家庭状态。
  - 首页不再使用 2x2 强入口填充首屏。
- `monitor.html` / `assets/scripts/monitor-live.js`
  - 守护页重排为“实时状态 + 摄像头画面”，只展示盒子同步状态、检测状态、摄像头画面和看画面动作。
  - 动态摄像头卡片改为统一卡片样式，多路摄像头均保留实时画面；普通在线状态不再显示“看事件”之类跨模块动作。
- `events.html` / `assets/scripts/events-live.js`
  - 事件页重排为安全事件时间线，只承接盒子、摄像头和规则生成的真实事件。
  - 事件卡片只保留时间、房间、事件摘要、处理状态和事件详情入口。
- `companionship.html` / `assets/scripts/companionship-live.js`
  - 陪伴页重排为完整今日关怀卡片、关怀依据和联系动作。
  - 清理普通关怀提醒跳事件或实时画面的兜底逻辑；发消息只尝试微信跳转，打电话继续读取老人资料手机号或家里电话。
  - 待办提醒详情不再暴露提醒 ID、状态、来源对象等工程化字段。
- `privacy.html`
  - “我的”改为家庭设置中心：家庭成员、关怀推送、设备管理、守护规则、通知设置、隐私与数据。
  - 资料卡保留家属账号身份和家庭盒子连接状态，不再显示管理员身份。
- `cameras.html` / `assets/scripts/stitch-app-data.js`
  - 设备管理页重排为“摄像头与盒子”，明确 App 只提交配置和查看状态，摄像头接入由家庭盒子完成。
  - 摄像头列表动态卡片更新为更紧凑的配置、启停、删除、同步操作。
- `rules.html` / `assets/scripts/rules-live.js`
  - 规则页资源版本刷新。
  - “守护服务未运行”改为“等待盒子同步”，避免把工程运行状态直接暴露给家属。
- `assets/scripts/stitch-app-routes.js`
  - 删除陪伴页“视频看看 / 视频”兜底跳实时画面的旧规则，避免无意义跨模块跳转。

验证：

- `node --check` 覆盖：
  - `assets/scripts/monitor-live.js`
  - `assets/scripts/events-live.js`
  - `assets/scripts/companionship-live.js`
  - `assets/scripts/stitch-app-data.js`
  - `assets/scripts/stitch-app-routes.js`
  - `assets/scripts/rules-live.js`
- `git diff --check` 覆盖本轮修改文件。
- 本地服务 `http://127.0.0.1:8788/index.html?app=1` 返回 200，服务仍监听 `8788`。
- 使用 Chrome 验证：
  - 首页：`bodyWidth = 430`，今日推送 6 张，关怀图片可见。
  - 守护页：识别 2 路摄像头，等待后两路实时画面均返回 `640 x 360` MJPEG 帧。
  - 事件页：无旧离线事件时展示“今天暂时没有告警”。
  - 陪伴页：完整关怀图片可见，页面不再出现普通关怀跳事件或实时画面的入口。
  - 我的页：设置入口 6 个，不显示管理员账号。
  - 设备管理页：展示 2 路在线摄像头。
  - 主路径页面无横向溢出；首页横向推送流的卡片超出属于容器内横向滑动内容。

当前边界：

- Tailwind CDN warning 仍存在，这是当前静态原型遗留的构建方式问题，不影响本地演示，但正式上云前应改为本地构建产物。
- 首页热点、节假日、天气和定位仍只使用现有上下文，不伪造真实天气接口和真实定位距离。
- 真实定时推送、APNs、微信正式跳转、iOS 定位授权仍未完成，后续进入云端和 iOS 阶段处理。

## 55. 2026-07-08 二级页面产品边界收敛

背景：

- 主 Tab 页面重排后，仍有若干二级页保留旧原型文案和布局：通知页写了微信服务号、短信、自动电话和免打扰突破；家庭成员页写了管理员和虚假活跃时间；隐私页写了云端录像、健康报告分析等未完成能力；实时查看页还显示 `mobile / monitor / detail` 英文档位。
- 本轮继续按“当前真实做到哪里就写到哪里”的原则收敛二级页面。

已完成：

- `watch.html` / `assets/scripts/watch-live.js`
  - 实时查看页补齐 iOS 刘海预留。
  - 视频档位从 `mobile / monitor / detail` 改为“流畅 / 守护 / 清晰”。
  - 错误文案从“本机服务”收敛为“家庭服务”。
  - 浏览器验证当前可返回实时画面。
- `event_detail.html` / `assets/scripts/event-detail-live.js`
  - 事件详情页资源版本刷新。
  - 页面副标题从“本机规则事件”改为“守护事件”。
  - 事件说明中的“本机守护服务”改为“家庭盒子”。
  - 房间兜底从“本机测试”改为“家庭摄像头”。
- `family_members.html`
  - 家庭成员页改成设置子页，不再显示底部 Tab。
  - 删除“管理员”“3 小时前活跃”等不真实状态。
  - 页面只展示家属账号、被守护人和待邀请家人，邀请链接标注为正式账号体系后启用。
- `notifications.html`
  - 通知页改为真实边界说明：安全事件提醒、每日关怀卡片、站内消息为当前本地演示可验证能力。
  - iOS 推送、电话、短信作为正式渠道状态展示，不再伪装成已接通。
  - 删除“微信服务号”“电话自动拨打”“突破免打扰模式”等当前没有实现的能力。
- `privacy_data.html`
  - 隐私页改为“只上传必要结果”。
  - 明确当前云端只承接事件、截图、规则和账号配置；长期录像和定位距离未启用。
  - 删除“云端录像保存 7 天”“健康数据报告分析”等未完成能力。
- `assets/styles/stitch-app-adapt.css`
  - 新增二级页通用列表、状态标签、开关和说明面板样式，减少页面各自拼 Tailwind 的不一致感。

验证：

- `node --check` 覆盖：
  - `assets/scripts/watch-live.js`
  - `assets/scripts/event-detail-live.js`
  - `assets/scripts/stitch-app-data.js`
  - `assets/scripts/stitch-app-routes.js`
- `git diff --check` 覆盖本轮修改文件。
- 使用 Chrome 验证：
  - `watch.html` 无横向溢出，实时画面可见，档位显示“流畅 / 守护 / 清晰”。
  - `event_detail.html` 无横向溢出，可展示事件详情和处理按钮。
  - `family_members.html` 无横向溢出，只保留返回，不显示底部 Tab。
  - `notifications.html` 无横向溢出，不再出现微信服务号、自动电话、免打扰突破等误导能力。
  - `privacy_data.html` 无横向溢出，不再出现云端录像保存和健康报告分析。

当前边界：

- 通知设置当前仍是产品策略页，未接正式保存接口；正式推送要等云端 notification-service 和 iOS APNs。
- 家庭成员邀请仍待正式账号体系和云端权限模型。
- 隐私数据导出、账号注销仍待云端数据库和账号系统完成。

## 56. 2026-07-08 入口与配置流程页收敛

背景：

- 主路径页面已经按首页、守护、事件、陪伴、我的重新归类，但登录、老人资料、家庭空间、盒子关联、摄像头配置引导和添加摄像头页仍有旧 Stitch 原型痕迹。
- 这些页面属于首次配置和设备维护路径，不能出现无动作按钮、错误硬件文案或和当前产品路径不一致的说法。

已完成：

- `login.html` / `assets/scripts/stitch-app-data.js`
  - 关闭按钮补上返回首页动作。
  - “获取验证码”在本地演示阶段会填入演示验证码，避免静态按钮无反馈。
  - 隐藏未接通的第三方登录视觉入口，避免微信/Apple 登录被误认为已实现。
- `parent_profile.html`
  - 页面主文案从“称呼 TA”改为“补全被守护人资料”。
  - 明确手机号、家里电话和城市用于关怀卡片、电话联系和回家提醒。
  - 返回按钮补上明确返回路径。
- `family.html`
  - “创建数字陪伴空间”改为“设置家庭空间”，明确家庭盒子、摄像头和关怀卡片归属到同一家庭。
  - 主按钮改为“继续配置家庭盒子”，和后续盒子关联路径一致。
- `device_binding.html`
  - 页面从“绑定守护伴侣”收敛为“连接家庭盒子”。
  - 两个入口改为“扫描盒子二维码”和“输入盒子序列号”，用于关联已完成本地 Wi-Fi 配网的家庭盒子。
  - 路由表同步新增新文案匹配，避免点击后无响应。
- `camera_intro.html`
  - 顶部从“添加设备”改为“摄像头配置”。
  - 第三步从“扫码配对”改为“App 内保存”，符合 App 提交 RTSP / 房间配置、盒子本地接入摄像头的路径。
  - “开始配置”改成真实链接，直接进入 `connect.html`。
  - 隐私文案改为“家庭盒子本地分析，云端只保存必要事件、截图和配置”，不再暗示连续视频上传。
- `connect.html`
  - 去掉无动作的“自定义”按钮，改为非点击说明。
  - “家庭盒子 · 本地接入”从假按钮改为静态状态块。
  - 清空名称按钮补充中文无障碍说明。
  - 顶部摄像头说明区收紧，减少首屏白板感。
- `assets/styles/stitch-app-adapt.css`
  - 新增登录、资料、家庭、盒子、摄像头引导和添加摄像头页的统一移动端样式。
  - 这些流程页统一预留 iOS 刘海区，顶部返回按钮改为轻量圆形控件，页面背景、卡片、输入框和底部动作条风格与主 App 保持一致。
  - 隐藏老人资料页旧装饰图，移除没有产品意义的装饰块。

验证：

- `npm test` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/stitch-app-routes.js` 通过。
- `git diff --check` 通过。
- 使用本机 Chrome + Playwright 以 `390 x 844` 手机视口验证：
  - `login.html`、`parent_profile.html`、`family.html`、`device_binding.html`、`camera_intro.html`、`connect.html` 均为 `clientWidth = scrollWidth = 390`。
  - 上述页面均无脚本错误。
  - 顶部安全区约 `110px`，首屏内容避开刘海区域。
  - 关闭、返回、验证码、开始配置、盒子二维码、序列号和提交摄像头配置路径均有真实动作或统一路由接管。

当前边界：

- 本地演示登录仍是验证码替身，不是正式短信验证码。
- 盒子二维码和序列号当前生成本地绑定码用于闭环演示，正式生产需要云端设备注册、二维码签名和设备归属校验。
- 摄像头自定义房间暂未做输入 UI，当前只保留客厅、餐厅、玄关、卧室四个常用位置。

## 57. 2026-07-08 本地闭环自检与用户态事件过滤

背景：

- 当前 App 已经能通过本地 App API 看到家庭、老人资料、盒子、两路摄像头、今日关怀卡片和页面状态。
- 旧的 `camera_offline` 原始事件在摄像头恢复在线后仍会留在原始事件表里，如果直接暴露给首页、事件页和摘要，会造成“摄像头在线但仍显示高危离线”的产品矛盾。
- 本轮目标是让后端承担用户态过滤，前端不用各自猜哪些事件应该隐藏；同时新增一个可重复运行的本地闭环自检命令。

已完成：

- `local-app-server/server.js`
  - 新增用户态事件过滤逻辑：已恢复在线摄像头对应的旧 `camera_offline` 事件不再出现在 App 用户事件列表。
  - `/api/app/events`、`/api/events`、`/api/v1/events` 默认返回用户可见事件。
  - `/api/app/summary/today`、`/api/summary/today`、`/api/v1/summary/today` 的事件数量、未处理数量和高危数量只统计用户可见事件。
  - `/api/v1/app/messages` 也使用同一套用户态事件过滤，避免消息卡片重新出现旧离线提醒。
  - 原始事件不删除，仍保留在数据库和导出链路里，用于审计、排障和云端迁移。
  - 新增设备绑定自愈：当已有 App 摄像头配置明确了 `family_id + device_id`，但历史数据缺少 `device_bindings` 时，自动补一条正式绑定记录；如果已有设备 token 或绑定码生成的正式绑定，则以正式绑定为准，不再从摄像头归属重复补默认家庭绑定。
  - 新增老人资料持久化兜底：读取默认老人资料时会为家庭落一条 `elder_primary`，避免页面能显示默认资料但导出云端 seed 时 `elder_profiles=0`。
- `scripts/verify-local-closed-loop.js`
  - 新增只读本地闭环自检脚本。
  - 覆盖服务健康、登录、家庭、老人资料、关怀推送配置、今日关怀图片、盒子可见性、设备同步、摄像头在线、用户态事件摘要、模型配置和主页面可访问性。
  - 不创建家庭、不新增摄像头、不强制调用模型生成，适合日常自检。
- `package.json`
  - 新增 `npm run verify:local-loop`。
- `scripts/verify-local-app-server.js`
  - 增加“摄像头恢复在线后，旧离线事件在用户接口隐藏，但原始事件仍进入 seed bundle 和恢复数据库”的回归断言。
- 树莓派盒子
  - 已通过 SSH 更新 `/home/gohome/gohome/edge-agent/app/config_sync_agent.py`，更新前已在盒子侧备份原文件。
  - 已重启 `gohome-edge-agent` systemd 服务。
  - 盒子当前 `health` 显示 `worker_running=true`，配置同步线程运行中，且 `rules-ac0b74eb5153` 已应用并回传。

当前自检结果：

```bash
npm run verify:local-loop
```

结果为 `23 passed, 1 warnings, 0 failed`。

当前 warning：

1. 老人手机号和家里电话为空，所以“打电话”动作不能直接拨号。

验证：

- `node --check scripts/verify-local-app-server.js` 通过。
- `node --check scripts/verify-local-closed-loop.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过，当前只剩老人电话未填写 warning。
- `git diff --check` 通过。

下一步：

1. 补老人手机号 / 家里电话保存和演示数据，验证“打电话”动作能直接拨号。
2. 上云前把 `local-app-server` 当前 JSON store 跑通到 PostgreSQL store，并保持 `npm test` 与 `npm run verify:local-loop` 双通过。
3. 再做 HTTPS 云服务部署和树莓派 `GOHOME_APP_SERVER_BASE_URL` 切云端。

## 58. 2026-07-08 PostgreSQL 上云前验收脚本与老人联系字段补齐

背景：

- 当前老人资料接口已经支持手机号和家里电话，陪伴页“打电话”动作也读取这些字段。
- 但上云迁移层原本没有把 `phone / mobile_phone / home_phone` 写入 PostgreSQL schema、seed bundle 和反向恢复，切到云数据库后会丢失拨号所需字段。
- 本机当前没有可用的 `psql / postgres / initdb / docker`，无法直接启动真实 PostgreSQL；因此先补一条拿到数据库连接串即可运行的验收命令。

已完成：

- `local-app-server/migrations/001_initial_schema.sql`
  - `elder_profiles` 增加 `phone`、`mobile_phone`、`home_phone`。
- `scripts/export-local-app-db.js`
  - seed bundle 导出老人手机号、手机号码和家里电话。
  - 即使历史 JSON 还没有显式保存老人资料，也会为每个家庭导出一条默认 `elder_primary`。
- `local-app-server/postgres-store.js`
  - PostgreSQL 表反向恢复到本地内存结构时保留老人联系电话。
- `scripts/verify-local-app-server.js`
  - 增加老人联系字段导出和恢复断言。
- `scripts/verify-postgres-loop.js`
  - 新增真实 PostgreSQL 闭环验证脚本。
  - 有 `GOHOME_DATABASE_URL` 时会运行迁移、启动 PostgresStore 版本的本地 App API、验证健康检查、用户、家庭、摄像头、摘要和模型能力接口。
  - 默认要求空数据库，避免误覆盖已有云库数据；非空库只允许显式传 `--allow-non-empty`。
- `package.json`
  - 新增 `npm run verify:postgres-loop`。

验证：

- `node --check scripts/verify-postgres-loop.js` 通过。
- `node --check scripts/export-local-app-db.js` 通过。
- `node --check local-app-server/postgres-store.js` 通过。
- `npm run db:migrate -- --dry-run` 通过。
- `npm run db:export -- --out /tmp/gohome-cloud-seed.json` 通过，当前导出 `elder_profiles=1`。
- `npm test` 通过。
- `npm run verify:postgres-loop -- --help` 可显示使用说明。
- 当前无 PostgreSQL 连接串时，`npm run verify:postgres-loop` 会明确报错 `GOHOME_DATABASE_URL or --database-url is required for Postgres loop verification`，不会假装通过。

下一步：

1. 准备一个空 PostgreSQL 数据库，执行：

```bash
GOHOME_DATABASE_URL='postgres://...' npm run verify:postgres-loop
```

2. 通过后，再用同一个连接串临时启动 PostgresStore 版 App API：

```bash
GOHOME_APP_STORE=postgres GOHOME_DATABASE_URL='postgres://...' npm run app-server
```

3. App API 的 Postgres 版本验证稳定后，再部署 HTTPS 云服务，并把树莓派盒子的 `GOHOME_APP_SERVER_BASE_URL` 从本地 `8788` 切到云端地址。

## 59. 2026-07-08 注册登录数据边界与家庭隔离收口

背景：

- 用户指出当前“随便输一个账号都能登录，还能读取原来的数据”，这会让本地闭环看起来通了，但产品语义是错的。
- 正确产品路径必须是：账号登录后只能读取自己加入的家庭；新账号不能直接看到旧家庭、旧设备、旧摄像头和旧事件。
- 本地固定 `GOHOME_APP_TOKEN` 仍需保留给自检脚本和当前盒子联调兼容，但浏览器 App 不能再自动拿这个演示 token 当作登录态。

已完成：

- `local-app-server/server.js`
  - 新增 App 会话 token：登录 / 注册返回 `app_...` 会话 token。
  - 新增 `family_members` 数据归属：家庭、设备绑定、摄像头、事件、关怀卡片等 App 侧读取均按当前用户可访问家庭过滤。
  - 未知账号登录返回 `401`，已存在账号重复注册返回 `409`。
  - 新注册账号默认没有家庭，必须创建家庭或加入家庭后才能看到设备和摄像头。
  - 旧 JSON 数据兼容迁移：如果旧库只有默认家庭和当前家属账号，但缺少 `family_members`，会把默认家庭补给当前家属账号，避免已接通的盒子和摄像头在本地升级后消失。
  - 摄像头截图、评估结果、实时流和媒体文件读取增加家庭权限校验，避免知道 camera id / media path 后跨家庭读取。
- `assets/scripts/edge-client.js`
  - 浏览器不再从 `/health` 自动写入本地演示 token。
  - 如果浏览器里残留旧的本地演示 token，连接服务时会清掉，避免未登录状态读取旧家庭。
- `assets/scripts/stitch-app-data.js`
  - 登录页手机号表单改为调用 `login`，不再静默调用 `register`。
  - 登录成功后，有家庭则进入首页；无家庭才进入老人资料 / 建家流程。
- `assets/scripts/stitch-app-routes.js`
  - 删除登录表单 `submit -> parent_profile.html` 的旧路由劫持，登录跳转由真实登录结果决定。
- `scripts/export-local-app-db.js`
  - seed bundle 导出真实 `family_members`，不再把所有家庭都挂到第一个用户。
- `local-app-server/postgres-store.js`
  - PostgreSQL 反向恢复时保留 `family_members`，避免切库后账号家庭关系丢失。
- `scripts/verify-local-app-server.js`
  - 增加未知账号登录失败、重复注册失败、新账号无默认家庭、跨家庭访问拒绝等回归断言。
  - 后续 App 侧接口测试全部使用真实登录会话 token，而不是固定演示 token。

验证：

- `node --check local-app-server/server.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `node --check scripts/export-local-app-db.js` 通过。
- `node --check local-app-server/postgres-store.js` 通过。
- `npm test` 通过。
- 重启 `com.gohome.local-app-server` 后，`npm run verify:local-loop` 通过：
  - `23 passed, 1 warnings, 0 failed`
  - 当前唯一 warning 仍是老人手机号 / 家里电话为空。
- 浏览器真实验证：
  - 未登录打开 `http://127.0.0.1:8788/index.html?app=1` 不再读取默认家庭、盒子和摄像头。
  - 使用已有手机号账号 `13818462550` 登录后，首页显示默认家庭、家庭盒子已同步、2 路摄像头和今日关怀卡片。

当前边界：

- 本地手机号登录仍是验证码替身，不是真实短信 OTP。
- 还没有做正式“首次注册 / 邀请加入家庭”完整产品流；当前注册接口已具备隔离语义，但登录页主流程仍偏演示。
- 老人手机号和家里电话仍为空，导致“打电话”动作不能直接拨号。
- 云端 Postgres 真实连接串尚未提供，`verify:postgres-loop` 还没有对真实云库跑过。

下一步：

1. 补老人手机号 / 家里电话配置和演示数据，消除本地闭环唯一 warning，并让打电话动作可验证。
2. 收口首次注册 / 已有账号登录 / 无家庭建家 / 加入家庭的 App 产品流，避免注册和登录混在一起。
3. 用空 PostgreSQL 数据库跑 `GOHOME_DATABASE_URL='postgres://...' npm run verify:postgres-loop`。
4. Postgres 版 App API 验证稳定后，再部署 HTTPS 云服务并把树莓派盒子切到云端地址。

## 60. 2026-07-08 老人联系电话配置入口收口

背景：

- 本地闭环唯一 warning 是老人手机号 / 家里电话为空，导致“打电话”动作不能直接拨号。
- 不能为了消除 warning 写入假号码；必须让用户在 App 里补充真实联系电话。
- 资料页此前只适合首次添加，已有家庭从“我的”进入时没有清晰入口，也没有预填已有老人资料。

已完成：

- `assets/scripts/stitch-app-data.js`
  - `parent_profile.html` 现在会读取当前家庭的 `elder_primary` 资料。
  - 已有资料时自动预填称呼、关系、城市、老人手机号和家里电话。
  - 已有资料时页面文案切换为“家人资料 / 编辑被守护人资料 / 保存资料”。
  - 保存后按 `next` 参数回跳；从“我的”进入时保存后返回“我的”，首次流程仍可继续到家庭 / 设备绑定。
  - 未登录直接打开资料页会回到登录页，不再静默失败。
- `privacy.html`
  - “我的”设置列表新增“家人资料”入口，说明为“称呼、城市、手机号和家里电话”。
- `assets/scripts/companionship-live.js`
  - 陪伴页读取老人联系电话。
  - 有电话时按钮使用 `tel:` 直接拨号。
  - 无电话时按钮文案改为“补电话”，点击进入家人资料页，不再伪装成可拨号。
- `assets/scripts/stitch-app-routes.js`
  - 增加“家人资料”路由识别。

验证：

- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/companionship-live.js` 通过。
- `node --check assets/scripts/stitch-app-routes.js` 通过。
- `npm test` 通过。
- `git diff --check` 通过。
- 重启 `com.gohome.local-app-server` 后，`npm run verify:local-loop` 通过：
  - `23 passed, 1 warnings, 0 failed`
  - warning 仍是老人手机号 / 家里电话为空，这是因为还没有真实号码，不是配置链路缺失。
- 浏览器真实验证：
  - `privacy.html?app=1` 显示“家人资料”入口。
  - `parent_profile.html?app=1&next=privacy.html` 预填 `张阿姨 / 杭州`，手机号和家里电话为空，保存按钮可用。
  - `companionship.html?app=1` 无电话时显示“补电话 / 先补充电话”，且没有 `tel:` 链接。

当前边界：

- 还没有用户提供真实老人手机号或家里电话，所以本地闭环 warning 保留。
- 保存真实号码后，应重新跑 `npm run verify:local-loop`，预期 warning 消失。

下一步：

1. 用户在“我的 -> 家人资料”填写真实老人手机号或家里电话。
2. 重新跑 `npm run verify:local-loop`，确认 `elder contact` 变为通过。
3. 然后继续收口首次注册 / 已有账号登录 / 无家庭建家 / 加入家庭的产品流。

## 61. 2026-07-08 登录 / 注册入口与播放凭证用户绑定收口

背景：

- 登录页虽然已接后端真实 `login`，但视觉和交互仍是旧的“一键登录”原型，容易让人误以为随便输入即可进入。
- 旧登录页还保留微信 / Apple 等未实现入口，点击路由曾会直接跳资料页，不符合产品路径。
- 新增手机号账号回归测试后发现一个真实后端问题：媒体播放 ticket 只校验票据存在，没有把签发用户带到后续媒体请求，跨账号状态下可能误 403 或误授权。

已完成：

- `login.html`
  - 改为明确的“已有账号 / 首次创建”分段入口。
  - 移除不可用的“一键登录”、微信登录和 Apple 登录视觉入口。
  - 本地阶段验证码按钮改为“演示验证码”，点击仍只填入 `000000`，不伪装成真实短信。
- `assets/scripts/stitch-app-data.js`
  - 登录模式调用 `GoHomeEdge.login`。
  - 首次创建模式调用 `GoHomeEdge.register`。
  - 前端不再用默认手机号兜底；手机号必须是 11 位。
  - 新账号创建后进入老人资料 / 建家流程，不读取旧家庭。
- `assets/scripts/stitch-app-routes.js`
  - 登录页只保留协议跳转；删除未实现第三方登录和旧“一键登录”直跳资料页映射。
- `local-app-server/server.js`
  - 手机号账号本地验证码收紧为 `000000` 或账号保存的验证码，不再“手机号存在 + 任意 4 位以上验证码”即可登录。
  - 播放 ticket 绑定签发用户，后续媒体 / 视频请求用 ticket 也能按正确用户做家庭权限校验。
- `scripts/verify-local-app-server.js`
  - 增加手机号注册、重复注册、错误验证码失败、正确验证码登录、新手机号账号无家庭的回归断言。
  - seed bundle 和 Postgres 反向恢复校验同步覆盖无家庭手机号账号。

验证：

- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/stitch-app-routes.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm test` 通过。
- 重启 `com.gohome.local-app-server` 后，`npm run verify:local-loop` 通过：
  - `23 passed, 1 warnings, 0 failed`
  - warning 仍是老人手机号 / 家里电话为空。
- 浏览器验证 `http://127.0.0.1:8788/login.html?app=1`：
  - 默认显示“已有账号”，提交按钮为“登录”。
  - 切换“首次创建”后提交按钮变为“创建账号”。
  - 页面不再显示“一键登录 / 微信登录 / Apple 登录”。

当前边界：

- 本地验证码仍是演示替身 `000000`，不是正式短信 OTP。
- 新账号创建后的“创建家庭 / 加入家庭 / 邀请码加入”还需要继续产品化；当前先进入老人资料并由现有流程创建家庭。
- 真实拨号仍依赖用户填写老人手机号或家里电话。

下一步：

1. 继续收口首次注册后的建家 / 加入家庭路径，避免新账号流程过于隐式。
2. 用户补充真实老人手机号或家里电话后，重新跑 `npm run verify:local-loop` 消除唯一 warning。
3. 准备真实 PostgreSQL 连接串，跑 `npm run verify:postgres-loop` 后再进入 HTTPS 云部署。

## 62. 2026-07-08 App 稳定性加固：移除 Tailwind CDN 运行时依赖

背景：

- 浏览器稳定性烟测发现主路径页面虽无白屏、无横向溢出、无前端错误覆盖层，但每页都会出现 `cdn.tailwindcss.com should not be used in production` 警告。
- 当前产品后续要进入云端和 iOS App/WebView，页面基础样式不能依赖运行时 CDN 和 `tailwind.config` 全局变量，否则离线、网络抖动或 CDN 超时会导致样式不可控。

已完成：

- `tailwind.config.js`
  - 更新为当前 H5/App 原型实际使用的绿色主题、颜色、字号、间距和字体 token。
- `assets/styles/tailwind.css`
  - 通过本地 Tailwind CLI 重新生成，包含当前 HTML 和前端脚本里使用的 utility classes。
- `package.json`
  - 新增 `npm run build:css`，后续改页面样式后可稳定重新生成本地 CSS。
- 所有根目录 HTML
  - 将 `https://cdn.tailwindcss.com?plugins=forms,container-queries` 替换为 `assets/styles/tailwind.css?v=20260708-local-1`。
  - 移除旧的 `<script id="tailwind-config">tailwind.config = ...</script>`，避免本地模式下引用不存在的 `tailwind` 全局变量。
- `scripts/verify-local-app-server.js`
  - 新增静态断言：HTML 不允许再包含 `cdn.tailwindcss.com` 或 `tailwind.config`。

验证：

- `npm run build:css` 通过。
- `node --check tailwind.config.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `rg -n "cdn\\.tailwindcss\\.com|tailwind\\.config" --glob "*.html"` 无结果。
- `git diff --check` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `23 passed, 1 warnings, 0 failed`
  - warning 仍是老人手机号 / 家里电话为空。
- 浏览器插件首次烟测通过：
  - `login / index / monitor / events / companionship / privacy / cameras / rules / care_schedule / parent_profile` 页面均非空。
  - 无错误覆盖层、无 relevant console error、无横向溢出。
- Browser 插件在 CSS 切换后的复测阶段连接超时；改用 Chrome headless 抽测 `index / monitor / companionship / privacy / login`：
  - 页面均生成截图。
  - DOM 非空。
  - 均引用本地 Tailwind CSS。
  - 未发现错误覆盖层。

当前边界：

- Chrome headless 在当前机器上需要外部超时杀进程，但截图和 DOM 已生成；这是验证工具调用方式问题，不是页面未渲染。
- 本地 CSS 已覆盖当前 HTML/JS 中的类；以后新增 Tailwind class 后必须执行 `npm run build:css`，否则新类不会进入静态 CSS。
- 联系老人拨号的唯一 warning 仍需要用户填写真实手机号或家里电话。

下一步：

1. 继续做页面和交互层面的稳定性烟测，重点是注册后建家、加入家庭、摄像头配置和规则保存。
2. 填写真实老人联系电话后复跑 `npm run verify:local-loop`。
3. 在上云前，把 `npm run build:css && npm test && npm run verify:local-loop` 作为固定本地发布前检查。

## 63. 2026-07-08 首次注册后的创建 / 加入家庭路径收口

背景：

- 上一轮已经把登录页改成“已有账号 / 首次创建”，但新账号后的家庭路径仍不够产品化。
- 旧逻辑中 `parent_profile.html` 会在无家庭时通过 `ensureFamily()` 隐式创建“我的家”，这会让账号、家庭、老人资料和盒子绑定的顺序不清晰。
- PRD 当前要求：App 登录或创建账号后，必须显式创建家庭空间或加入家庭空间，再填写老人资料、绑定盒子和配置摄像头。

已完成：

- `local-app-server/server.js`
  - `publicFamily` 返回本地邀请码 `join_code`，格式为 `GH-{familyId}-{校验码}`。
  - 新增 `POST /api/families/join` / `POST /api/v1/households/join`，当前账号可通过邀请码加入已有家庭。
  - `family_members` 成员数会同步回家庭 `member_count`，避免加入家庭后人数不准。
- `assets/scripts/edge-client.js`
  - 新增 `GoHomeEdge.joinFamily({ code })`。
- `login.html` + `assets/scripts/stitch-app-data.js`
  - 首次创建账号后进入 `family.html?mode=setup`，不再直接进入老人资料页。
  - 已有账号登录后，如果没有家庭，也进入 `family.html?mode=setup`。
- `family.html`
  - 页面明确分为“创建家庭并填写资料”和“加入已有家庭”。
  - 加入家庭需要输入家人给的邀请码。
  - 已有家庭时展示家庭邀请码，并给出“填写资料 / 绑定盒子”下一步。
- `assets/scripts/stitch-app-data.js`
  - 家庭创建成功后进入 `parent_profile.html?family_id=...&next=device_binding.html?family_id=...`。
  - 加入家庭成功后进入首页，直接读取该家庭数据。
  - `parent_profile.html` 如果当前账号没有家庭，会回到家庭设置页，不再隐式创建家庭。
  - “创建家庭”和“保存资料”按钮增加 `data-action`，避免全局文字路由抢在真实提交逻辑前跳转。
- `scripts/verify-local-app-server.js`
  - 增加邀请码格式、错误邀请码失败、正确邀请码加入家庭、新账号加入后能看到家庭、seed bundle 保留 3 条 `family_members` 的回归断言。

验证：

- `node --check local-app-server/server.js` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/edge-client.js` 通过。
- `node --check scripts/verify-local-app-server.js` 通过。
- `npm run build:css` 通过。
- `npm test` 通过。
- 重启 `com.gohome.local-app-server` 后，`npm run verify:local-loop` 通过：
  - `23 passed, 1 warnings, 0 failed`
  - warning 仍是老人手机号 / 家里电话为空。
- 静态检查：
  - `family.html?app=1` 已包含“创建家庭并填写资料”“加入已有家庭”和 `familyJoinCode` 输入。
  - `git diff --check` 通过。

当前边界：

- 当前邀请码是本地闭环可验证的简化码，不是正式云端邀请链接、二维码签名或过期机制。
- 正式家庭邀请仍需云端邀请表、过期时间、角色权限、撤销和审计。
- 加入家庭后当前先进入首页；是否要求补自己的关系/昵称，留到家庭成员正式权限模型处理。

下一步：

1. 继续验证新注册用户真实浏览路径：注册 -> 创建家庭 -> 填老人资料 -> 绑定盒子 -> 摄像头配置。
2. 用户补真实老人手机号或家里电话，消除唯一闭环 warning。
3. 再进入 PostgreSQL 真实连接串验证和 HTTPS 云部署。

## 64. 2026-07-08 守护规则、亲情关怀规则和关键交互修复

背景：

- 用户反馈守护规则里人形、无人和跌倒无法勾选，且 App 规则页没有和盒子视觉算法字段对齐。
- 老人资料页“身份称呼”选中态不明显。
- 陪伴页“发消息”会被全局文字路由误跳到事件页，不符合产品逻辑。
- 关怀推送页只有“7 类内容 + 每天一次”，没有体现每日汇总卡和分类触发规则的关系。
- 首页和关怀图文卡片需要继续贴合温暖、场景化、电商生活方式卡片风格。

已完成：

- `rules.html` + `assets/scripts/rules-live.js`
  - 规则页不再用 `detector_backend === "yolo"` 强行禁用人形、无人和跌倒开关。
  - 保存规则时不再因为前端判断而把 `person_detection_enabled`、`fall_detection_enabled` 强制置 false。
  - 新增 `activity_detection_enabled` 和 `fire_detection_enabled` 两个盒子规则开关，对应盒子 rule_engine 已有字段。
  - 页面文案改为“盒子视觉算法”，显示基础视觉、YOLO、RTMPose 或演示视觉管线的状态，不再把底层后端名暴露成用户理解成本。
- `local-app-server/server.js`
  - `/api/device` 返回 `vision_capabilities`，包含质量、运动、人形、无人、跌倒候选、活动候选和明火候选能力摘要。
  - `defaultCareSchedule()` 和 `normalizeCareSchedule()` 增加 `delivery_rules`，用于保存每日汇总、异常即时、节日提前、纪念日提前和回家间隔阈值。
  - 关怀文本和生图默认提示词更新为温暖、场景化、生活方式卡片方向，强调 1:1 方形、标题和短句清晰、主题和推送信息相关。
- `parent_profile.html` + `assets/scripts/stitch-app-data.js` + `assets/styles/stitch-app-adapt.css`
  - 称呼卡片点击后同步输入框、`aria-pressed` 和唯一选中态。
  - 选中卡片增加深色边框、内描边和勾选标记，避免看不出当前选择。
- `companionship.html` + `assets/scripts/companionship-live.js`
  - “发消息”改为 `button[data-action="contact-wechat"]`，不再使用空 `href`。
  - 点击后不再跳事件页，也不伪装成已接入微信；本地 Web 显示“iOS App 内会接入微信跳转”。
  - “打电话”继续读取老人手机号或家里电话，已填写时使用 `tel:`。
- `care_schedule.html` + `assets/scripts/care-schedule-live.js`
  - 新增“推送规则”区域：每日汇总、家里异常、节日问候、纪念日和回家间隔。
  - 页面明确“一张每日汇总卡负责日常关怀，异常和特殊日期按规则触发提醒”。
  - 保存时写入 `delivery_rules`：
    - `daily_digest`
    - `home_status.daily_digest_plus_exception`
    - `holidays.holiday_window`
    - `anniversaries.annual_window`
    - `visit_reminder.threshold`
  - 纪念日继续按每年同月同日提醒，不回到出生年份。
- `assets/scripts/home-live.js`
  - 首页信息流文案收敛为家属可读的关怀信息，不再使用后台口吻。
  - 天气、热点、定位等未接入数据继续明确边界，不伪造实时天气和距离。

验证：

- `node --check assets/scripts/rules-live.js` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/companionship-live.js` 通过。
- `node --check assets/scripts/care-schedule-live.js` 通过。
- `node --check assets/scripts/home-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm run build:css` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `24 passed, 0 warnings, 0 failed`
  - 已验证老人联系电话存在，闭环 warning 清零。
- `git diff --check` 通过。
- Chrome 实测：
  - 首页登录真实家属 session 后显示默认家庭、盒子已同步、2 路摄像头和 6 张今日推送卡。
  - 规则页人形、无人、跌倒、活动、明火开关均不禁用，跌倒开关可勾选并恢复。
  - 家人资料页默认选中“母亲”，点击其他称呼会同步输入框和唯一选中态。
  - 陪伴页“发消息”停留在陪伴页并显示本地 Web 限制说明，不再误跳事件页。
  - 关怀推送页保存后，服务端 `care_card_schedule.delivery_rules` 已持久化。
  - 首页和关怀推送页截图未发现明显横向溢出。

当前边界：

- 当前本地 Web 不接微信，只做正确占位提示；正式微信跳转放到 iOS App 阶段。
- 当前本地闭环已保存分类推送规则，但真正按时间触发每日推送、异常即时推送、节日提前推送和 APNs 送达仍属于云端 scheduler / notification-service 阶段。
- 当前定位距离仍未接 iOS 定位授权，不伪造手机与家的真实距离。
- 天气和内容推荐已接平台 provider：天气已跑通和风天气，内容搜索已换入有效 Tavily key 并通过本地闭环；外部文章视频推荐仍需要白名单、过滤和内容质量控制后再作为正式推送能力。

下一步：

1. 进入云端前的数据库和服务准备：复跑 PostgreSQL store 验证，确认 `delivery_rules`、规则字段、老人联系电话和家庭成员过滤可迁移。
2. 最小云部署后，把本地 `8788` 语义迁移到 HTTPS 云端，保持 App/H5 不直连盒子局域网。
3. 云端跑通 scheduler / notification-service / APNs 后，再做 iOS App 封装和微信 / 系统分享跳转。

## 65. 2026-07-08 天气和热点内容 Provider 接入

背景：

- 用户指出天气和热点内容还没有真实跑通，问天气是否需要 API、热点是否可以用 Tavily。
- 产品判断：天气必须走天气 provider；Tavily 只适合做老人兴趣话题、文章和视频候选，不适合替代天气 API。
- 模型、天气、搜索 key 均由 App 服务提供方通过 env 配置，普通用户不能在 App 页面配置。

已完成：

- `.env.example`
  - 新增平台侧数据源配置：
    - `GOHOME_WEATHER_PROVIDER`
    - `GOHOME_QWEATHER_BASE_URL`
    - `GOHOME_QWEATHER_GEO_BASE_URL`
    - `GOHOME_QWEATHER_API_KEY`
    - `GOHOME_QWEATHER_AUTH_MODE`
    - `GOHOME_SEARCH_PROVIDER`
    - `GOHOME_TAVILY_BASE_URL`
    - `GOHOME_TAVILY_API_KEY`
    - `GOHOME_TAVILY_MAX_RESULTS`
    - `GOHOME_PROVIDER_REQUEST_TIMEOUT_MS`
  - 本地 `.env` 已写入用户提供的和风天气 key 和 Tavily key；`.env` 已在 `.gitignore` 中，不进入代码仓库。
- `local-app-server/server.js`
  - 新增 `weatherRuntimeConfig()`、`contentSearchRuntimeConfig()` 和 provider 短缓存，避免首页连续刷新反复打外部 API。
  - 新增和风天气 provider：
    - 城市搜索使用 `geoapi.qweather.com/v2/city/lookup`。
    - 实时天气使用 `devapi.qweather.com/v7/weather/now`。
    - 兼容短 API Key 的 query 鉴权，也保留 `GOHOME_QWEATHER_AUTH_MODE=bearer` 给新版 token。
  - 新增 Tavily Search provider：
    - 默认 `POST https://api.tavily.com/search`。
    - 先用 `Authorization: Bearer`，401/403 时兼容重试 body `api_key`。
    - 返回结果清洗成 `title/url/source/summary/topic`。
  - `GET /api/v1/families/{family_id}/weather-signals` 不再返回固定假天气，改为真实 provider 或明确 unavailable。
  - 新增 `GET /api/v1/families/{family_id}/content-recommendations`。
  - `careCardFacts()` 改为异步，关怀卡生成时会读取真实 weather/content signal。
  - 模型上下文增加 `weather`、`content_recommendations`、`content_search`，provider 不可用时明确告诉模型不要编造天气或热点。
- `assets/scripts/edge-client.js`
  - 新增 `v1ContentRecommendations()`。
- `assets/scripts/home-live.js`
  - 首页信息流天气卡优先展示真实 `weather-signals`。
  - 首页话题候选卡优先展示 Tavily 返回结果；无结果或 provider 失败时明确显示“内容搜索源暂不可用”。
  - Chrome 验证当前首页 6 张卡片，天气卡显示 `QWeather · 实时信号`，话题候选卡显示 Tavily 未返回；未发现横向溢出。
- `scripts/verify-local-closed-loop.js`
  - 自检新增 `weather provider` 和 `content search`。
  - provider 不可用时输出 warning，不把假数据算作通过。
- `scripts/verify-local-app-server.js`
  - 测试环境默认关闭外部 weather/search provider，避免单元回归依赖外网。

验证：

- `node --check local-app-server/server.js` 通过。
- `node --check assets/scripts/home-live.js` 通过。
- `node --check assets/scripts/edge-client.js` 通过。
- `npm test` 通过。
- 真实本地接口验证：
  - 和风天气已跑通：`weather.available=true`，`provider=qweather`，城市为上海，返回实时天气和温度。
  - Tavily 换入有效 key 后已跑通：`content.available=true`，返回 3 条候选。
- `npm run verify:local-loop`：
  - `26 passed, 0 warnings, 0 failed`

当前边界：

- 天气已经从假数据切到真实 provider。
- Tavily 代码链路已经跑通，但当前搜索结果还只是候选，需要继续优化查询词、来源白名单、负面内容过滤和内容安全策略，避免把不适合家属关怀语境的新闻直接展示成温暖话题。
- “每天几点自动推送什么消息”仍需云端 scheduler / notification-service / APNs；本地 Web 只负责设置和即时生成/展示，不伪装成真实手机推送。

下一步：

1. 优化 Tavily 查询词、来源白名单、负面内容过滤和候选打分，先让首页话题候选更贴近“温暖、可聊、适合老人兴趣”的产品语境。
2. 继续验证新注册用户完整路径：注册 -> 创建家庭 -> 填老人资料 -> 绑定盒子 -> 摄像头配置 -> 首页关怀卡。
3. 上云前跑 PostgreSQL store 验证，确认 provider 配置仍只走 env/Secret Manager，不进入普通用户数据库配置。

## 66. 2026-07-08 Tavily Key 更新后闭环通过

背景：

- 用户提供新的 Tavily key，用于替换上一轮鉴权失败的 key。

已完成：

- 本地 `.env` 更新 `GOHOME_TAVILY_API_KEY`，保留 `GOHOME_SEARCH_PROVIDER=tavily` 和 `GOHOME_TAVILY_BASE_URL=https://api.tavily.com/search`。
- 重启 `com.gohome.local-app-server`，让本地服务重新读取 `.env`。
- 直接调用 `GET /api/v1/families/{family_id}/content-recommendations` 验证：
  - `available=true`
  - `provider=tavily`
  - `recommendations.length=3`
  - 候选结果包含标题、来源和 URL。

验证：

- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - `weather provider - qweather 上海 阴 34C`
  - `content search - tavily 3 candidate(s)`

当前边界：

- Tavily 已经跑通，但第一批候选里可能出现偏泛新闻、负面消费新闻或不够温暖的内容。
- 下一步不再只是“能搜到”，而是要把内容候选做成产品能力：白名单来源、老人兴趣匹配、负面词过滤、内容摘要重写和频率控制。

## 67. 2026-07-08 首页关怀信息架构收口

背景：

- 首页此前把“今日关怀主卡”“今日推送信号”和历史卡混在一起展示，导致同类文案重复出现，且旧历史卡里的泛化标题继续污染首页观感。
- 用户明确要求首页先做好：图文卡片要温暖、有场景感；首页内容应围绕家里情况、天气、日历、回家间隔、老人兴趣和历史关怀，不要为了功能强塞跳转。

已完成：

- `index.html`
  - 新增 `最近关怀` 横滑历史卡区域。
  - 首页顺序收口为：家庭状态摘要 -> 今日关怀主视觉卡 -> 最近关怀 -> 今日信号 -> 位置与回家 -> 家庭状态。
- `assets/scripts/home-live.js`
  - 今日关怀主卡不再被塞进“今日信号”流，信号流只保留天气、日历、回家间隔、话题候选和家庭状态。
  - 首页主卡有生成图时，图片承担完整图文内容，图片下方只展示生成依据和两个事实点，不再重复图片标题正文。
  - 历史关怀卡展示层新增文案清洗，旧卡片中的“家里一切平稳 / 聊聊家常”等泛化标题不会继续出现在首页。
  - Tavily 候选不再把原始新闻标题直接暴露到首页，只作为“可聊话题”候选。
- `assets/styles/stitch-app-adapt.css`
  - 重做首页主卡、最近关怀卡和今日信号卡样式，减少生硬边框和大块渐变。
  - 顶部安全区统一预留 `safe-area-inset-top`，普通浏览器也保留最小手机安全区，避免 iOS 刘海区域压住首屏内容。
- `local-app-server/server.js`
  - 默认关怀文案提示词禁止“家里一切平稳 / 聊聊家常”等占位句。
  - 服务端增加模型输出后处理：模型标题若仍出现泛化句或超长标题，会用真实天气、回家间隔或老人兴趣改写。
  - 生图提示词禁止品牌字样、logo、角标、水印、奖章和无关徽章。
- `.env.example` / 本地 `.env`
  - `GOHOME_MODEL_REQUEST_TIMEOUT_MS` 调整为 `120000`，减少 Wan 生图超时。
  - API key 仍只在本地 `.env`，代码和 `.env.example` 只保留变量名。

验证：

- 强制重新生成今日关怀卡成功：
  - 标题：`上海闷热，提醒喝水`
  - 图片：`image_mode=generated`
- `node --check assets/scripts/home-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - 今日关怀卡为新标题，图片为 `generated image/png`。
- 浏览器验证：
  - 普通视口和 `390 x 844` 手机视口均无 body 横向滚动。
  - 首页旧文案 `家里一切平稳 / 聊聊家常` 出现次数为 0。
  - 390 x 844 下主卡和底部导航未互相挤压。

当前边界：

- 首页视觉与信息架构已经先收口，但 Tavily 候选仍需要下一步做来源白名单、负面词过滤和更稳定的老人兴趣匹配。
- 历史卡里的旧图片本身可能仍包含旧文字；首页展示层会对旧泛化历史卡改用占位缩略图，避免继续露出旧生成图。后续可提供“重生成历史卡图片”能力。

### 67.1 首页重复与远程关怀动作修正

修正点：

- 首页今日主卡如果已经生成完整 1:1 图文卡，页面不再在图片下方重复渲染标题、正文和事实条。
- `最近关怀` 只展示历史卡，不再把今天这张主卡重复展示为缩略卡。
- 旧历史卡如果没有可用高质量缩略图，展示为文字型历史卡，不再出现空白大块占位。
- 服务端关怀文案增加不可行动作过滤：
  - 禁止“递茶、端水、送到手边、陪在身边”等需要家属在现场的动作。
  - 高温天气卡固定为“电话提醒喝水、少久晒、聊晚饭和近况”这类远程可执行动作。
  - 高温天气卡正文不再让模型自由发挥老人近期兴趣，避免编造“听戏、最近看的节目”等无依据内容。

本次强制重生成今日卡：

- 标题：`上海闷热，提醒喝水`
- 正文：`今天上海阴，34°C，适合电话提醒喝水、少久晒，再聊聊晚饭和近况。`
- 图片：`image_mode=generated`

验证：

- `npm test` 通过。
- `npm run verify:local-loop` 通过，`26 passed, 0 warnings, 0 failed`。
- 浏览器验证首页：
  - 今日主卡 copy 区域隐藏。
  - 最近关怀不包含今天主卡标题。
  - `递杯茶 / 递茶 / 端水 / 送到手边 / 陪在身边 / 听戏` 出现次数为 0。

### 67.2 首页刷新、内容源和图文主卡稳定性修正

修正点：

- 首页移除 60 秒自动 `setInterval(render)`，不再周期性整页重拉家庭、天气、内容和图片，避免用户看到“页面老刷新 / 主图闪回占位”。
- 今日关怀主卡改为首屏主视觉：有 1:1 生图时，图片本身承载完整标题和短句，页面不再在图片下方重复正文。
- `今日灵感` 保留天气、内容搜索、日历、回家提醒和家庭状态，但只作为生成依据展示，不把它们做成强跳转入口。
- Tavily 内容搜索增加质量过滤：
  - 过滤英文结果、政治新闻、负面消费新闻、诈骗/防骗/恐吓型标题和医疗诊断类内容。
  - 查询词改为上海本地、健康生活、适合聊天、养生和节气方向。
  - 允许上海本地媒体、卫健委和权威媒体来源；首页展示层把长机构标题改写为“可聊时令养生”等产品语言。
- 服务端高温天气卡继续强制落到远程可执行动作：电话提醒喝水、少久晒、聊晚饭和近况。

本次强制重生成今日卡：

- 标题：`上海闷热，提醒喝水`
- 正文：`今天上海阴，34°C，适合电话提醒喝水、少久晒，再聊聊晚饭和近况。`
- 图片：`image_mode=generated`

验证：

- `node --check assets/scripts/home-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过，`26 passed, 0 warnings, 0 failed`。
- 浏览器 390 x 844 验证：
  - 今日关怀图加载成功，图片为 `1024 x 1024`。
  - 首页 `scrollWidth = clientWidth = 390`，无横向溢出。
  - 今日主卡 copy 区域隐藏，不重复展示图片里的标题正文。
  - 首页坏词 `递杯茶 / 递茶 / 端水 / 送到手边 / 陪在身边 / 家里一切平稳 / 家里一切安稳 / 聊聊家常` 出现次数为 0。

### 67.3 “我的-关怀推送”作为内容偏好唯一来源

背景：

- 用户确认首页热点、天气、养生、防诈骗、老人兴趣和内容区域等能力，必须和“我的”里设置的关怀推送配置吻合。
- 产品边界：普通家属只配置内容偏好；模型 Base URL、Key、Prompt、天气 provider 和 Tavily provider 仍由服务提供方通过 `.env` 配置。

已完成：

- `care_schedule.html`
  - 关怀推送页新增内容类型：本地热点、防诈骗、文娱兴趣。
  - 新增“内容区域”配置，支持城市、区县和常用区域快捷按钮。
  - 老人兴趣扩展为本地生活、健康养生、防诈骗、电视节目、社区活动、节气饮食等可选项。
- `assets/scripts/care-schedule-live.js`
  - `care_card_schedule` 保存 `content_types.local_hotspots / anti_fraud / culture_entertainment / weather`。
  - 保存 `content_region.city / district`，为空时由后端回落到老人资料城市/区县。
  - `delivery_rules` 按内容类型拆分，不再只有“每天一次”的粗粒度设置。
- `parent_profile.html` / `assets/scripts/stitch-app-data.js`
  - 老人资料增加区县字段，作为内容区域默认值。
- `assets/scripts/edge-client.js`
  - `v1ContentRecommendations()` 支持传 `district`，避免显式调用时丢失区县。
- `local-app-server/server.js`
  - `defaultCareSchedule()` / `normalizeCareSchedule()` 支持新内容类型、内容区域和拆分后的投递规则。
  - 新增 `contentSearchTasksFromPreferences()`：按“我的”里开启的模块拆成 Tavily 搜索任务，例如本地热点、健康养生、防诈骗、文娱兴趣、问候话题。
  - `fetchContentRecommendations()` 增加 `content_recommendations_enabled` 总开关判断，新用户未开启内容推荐时不会因为默认 schedule 自动搜索。
  - `careCardFacts()` 和 `/api/v1/families/{family_id}/content-recommendations` 都读取同一份 `care_card_schedule`，并把城市/区县传入天气、内容搜索和每日关怀卡生成上下文。

验证：

- `node --check assets/scripts/care-schedule-live.js` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/edge-client.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm run build:css` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - `weather provider - qweather 上海 阴 34C`
  - `content search - tavily 3 candidate(s)`
  - `cameras configured - 2 enabled`
  - `camera online - 2/2`
- 直接调用 `GET /api/v1/families/1/content-recommendations` 验证：
  - `provider=tavily`
  - 返回 3 条候选。
  - 搜索任务按配置拆成 `local_hotspots / health_tips / culture_entertainment / elder_interest_topics`。
- Chrome 390 x 844 登录态验证：
  - 关怀推送页回填 `默认家庭 / 上海`。
  - 已勾选 `home_status / elder_interest_topics / local_hotspots / health_tips / culture_entertainment / weather / visit_reminder / holidays / anniversaries`。
  - 无横向溢出，`scrollWidth = clientWidth = 390`。

当前边界：

- 当前真实配置里的 `content_region` 为空，因此内容搜索回落到老人资料里的城市“上海”；后续用户在“我的 -> 关怀推送”填城市/区县后会覆盖默认区域。
- 首页已经能读取同一内容源，但首页视觉和信息密度仍需要下一轮继续优化：把多任务候选包装成更像成熟 App 首页的信息流，而不是简单展示 provider 结果。

### 67.4 首页今日信号信息流与安全区补强

背景：

- 用户继续要求首页先做好，信息要来自真实天气、内容搜索、日历、回家间隔和“我的 -> 关怀推送”设置，不能再像后台模块或泛泛卡片堆砌。
- 当前首页已经接上 QWeather 和 Tavily，但展示层仍有三类问题：
  - 天气文案没有充分转成远程可执行动作。
  - 内容源和 fallback 文案偏技术说明。
  - 首页信息流边界和阴影仍偏机械，顶部安全区需要再压实。

本次修正：

- `assets/scripts/home-live.js`
  - 天气卡根据雨、高温、低温和降温等条件改写成远程关怀动作，例如提醒带伞、路滑慢一点、喝水和少久晒。
  - 内容推荐来源从裸域名改为用户可读来源，如上海卫健委、上观新闻、人民网、新华社、央视和光明网。
  - 本地热点、养生、文娱兴趣和问候开场卡片不再显示 provider 结果或技术 fallback，而是改成适合电话/微信开场的关怀文案。
  - `今日可聊` 改成 `今日信号`，并继续从 `care_card_schedule.content_types` 读取“我的”设置作为唯一来源。
- `assets/styles/stitch-app-adapt.css`
  - 重新压缩首页信号卡间距、阴影和边界，第一张天气卡作为信息流头条，其余卡片保持双列扫读。
  - 首页、守护、事件、陪伴和我的主页面底部统一预留底部导航空间。
  - 首页主内容顶部安全距提升到 `calc(28px + safe-area)`，避免 iOS 刘海区域压住首屏内容。
- `index.html`
  - 更新首页说明文案和静态资源版本，避免浏览器缓存旧首页。
- `local-app-server/server.js`
  - 生图提示词增加约束：图片主视觉必须贴合当天主题，不生成泛泛家庭关怀模板，不画后台 UI、按钮面板、促销角标或信息堆叠卡。

验证：

- `node --check assets/scripts/home-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm run build:css` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - `weather provider - qweather 上海 大雨 26C`
  - `content search - tavily 3 candidate(s)`
  - `care card image - generated image/png`
  - `cameras configured - 2 enabled`
  - `camera online - 2/2`
- Chrome 首页验证：
  - 首页渲染 8 张今日信号卡。
  - 首页没有 `递杯茶 / 递茶 / 端水 / 送到手边 / 陪在身边 / 家里一切平稳 / 家里一切安稳 / 聊聊家常 / 多陪陪家人`。
  - 首页不再显示 `QWeather / wsjkw.sh.gov.cn / sghexport.shobserver.com / news.gmw.cn` 等裸技术来源。
  - 主内容顶部计算安全距为 `58px`，底部主内容预留 `124px`，固定底部导航不压住最后内容。

当前边界：

- 首页使用 Tavily 候选做关怀话题上下文，但仍只作为家属端“可聊信号”，不默认向老人推送外链。
- 真正的每日到点推送、异常即时推送、APNs 和 iOS 定位授权仍属于云端 scheduler / notification-service / iOS 阶段。

### 67.5 关怀推送配置源头整理

背景：

- 首页今日信号已经按“我的 -> 关怀推送”读取内容偏好，但设置页本身还偏字段堆叠，用户不容易理解勾选后首页会出现什么、哪些内容会即时提醒或提前提醒。
- 普通家属不应该看到 `scheduler / APNs / 云端阶段 / 本地闭环` 这类开发和后端实现词。

本次修正：

- `care_schedule.html`
  - 新增“当前配置预览”，直接说明：
    - 首页会展示哪些模块。
    - 内容搜索按哪个城市/区县和兴趣筛选。
    - 每日卡、异常、节日、纪念日和回家间隔分别如何触发。
  - 新增“推荐组合”：
    - 基础关怀：家里状态、天气、节日和回家提醒。
    - 日常推荐：加入本地、养生和文娱，让首页更丰富。
    - 安心提醒：额外打开防诈骗和异常即时提醒。
  - 新增自定义老人兴趣输入，允许家属添加老人关注的内容。
  - 清理页面可见开发词，改成普通用户能理解的产品文案。
  - 顶部安全区改为最小 `34px` 预留，避免页面贴近刘海区域。
- `assets/scripts/care-schedule-live.js`
  - 增加 `contentTypeMeta` 和 `presets`，推荐组合会真实写入 `content_types / interest_topics / message_focus / exception_push_enabled`。
  - 自定义兴趣会动态添加到话题网格，勾选后随 `interest_topics` 保存。
  - 配置预览会随时间、区域、内容类型、兴趣、节日提前天数、纪念日提前天数和回家间隔实时更新。
  - 保存仍使用原来的 `CarePreference.metadata.care_card_schedule`，没有新增第二套配置源。

验证：

- `node --check assets/scripts/care-schedule-live.js` 通过。
- `node --check assets/scripts/home-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - 天气、Tavily、今日关怀图、设备绑定、两路摄像头和主页面均通过。
- Chrome 验证 `care_schedule.html?app=1`：
  - 首屏可见配置预览、每日汇总卡、推荐组合和推送规则。
  - 推荐组合可切换并实时更新预览。
  - 自定义兴趣可添加并勾选，但未提交保存，不污染当前真实配置。
  - 页面没有 `scheduler / APNs / 云端阶段 / 本地闭环 / Base URL / API Key` 等普通用户不该看到的词。
  - `document.body.scrollWidth <= document.body.clientWidth`，无横向溢出。

当前边界：

- 关怀推送页已经保存完整规则，但真实每日到点推送、异常即时推送和 iOS 推送送达仍需云端任务与 iOS 通知通道实现。

### 67.6 守护规则与盒子视觉能力对齐

背景：

- 用户反馈“守护规则”里人形、无人和跌倒勾选状态和盒子实际视觉算法不一致，页面看起来像能配，但配置没有和盒子能力绑定。
- 当前家庭盒子在线且规则同步正常，但盒子回传的视觉后端为 `基础视觉检测`；这意味着质量检测、运动检测、活动状态和烟火候选可以执行，人形、长时间无人和跌倒候选需要盒子端启用人形或姿态模型后才应开放。

本次修正：

- `local-app-server/server.js`
  - `deviceVisionCapabilities()` 不再只看 `detector_backend`，同时兼容盒子回传的 `runtime.vision_capabilities`、`runtime.pose_enabled`、`runtime.worker` 等字段。
  - App 的 `/api/app/device` 会标准化返回 `person_detection / no_person_detection / fall_candidate / activity_candidate / fire_candidate / pose_detection`。
- `edge-agent/app/main.py`
  - 盒子配置同步上报和本机 `/api/device` 增加 `vision_capabilities`，让 App 服务端能按真实能力展示规则开关。
- `rules.html`
  - 盒子视觉算法每一项新增状态标记：可用、需人形模型、需姿态模型或盒子未支持。
  - 通知区域清理开发实现词，改成普通家属能理解的说明。
- `assets/scripts/rules-live.js`
  - 初始化时先读取盒子能力，再渲染规则开关。
  - 不支持的算法项会禁用并取消勾选，保存时不会再把无效规则发给盒子。
  - 若旧规则里已有当前盒子无法执行的算法项，页面会自动校准为关闭并保存。
  - 保存状态优先按 `desired_rule_version === applied_rule_version` 判断，显示“已同步到家庭盒子 / 待同步 / 盒子未运行”。
  - 待同步时增加轻量后续轮询，不需要手动刷新也能更新为“已生效”。

验证：

- `node --check assets/scripts/rules-live.js` 通过。
- `node --check local-app-server/server.js` 通过。
- `python3 -m py_compile edge-agent/app/main.py` 通过。
- 重启本地 App 服务 `http://127.0.0.1:8788`，服务健康检查通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `26 passed, 0 warnings, 0 failed`
  - `device visible - edge-042714be475b91da`
  - `edge worker - reported running`
  - `rules applied - rules-037e17c81a12`
  - `cameras configured - 2 enabled`
  - `camera online - 2/2`
- 接口验证：
  - `/api/app/device` 返回当前盒子能力：人形、无人、跌倒为不可用，活动和烟火为可用。
  - `/api/rules` 已校准为 `person_detection_enabled=false`、`fall_detection_enabled=false`、`activity_detection_enabled=true`、`fire_detection_enabled=true`。
  - `/api/v1/device/config` 下发给盒子的规则与 `/api/rules` 一致。
  - `/api/rules/runtime` 显示 `desired_rule_version` 和 `applied_rule_version` 一致。
- Chrome 验证 `rules.html?app=1`：
  - 人形、长时间无人、疑似跌倒显示为不可用且禁用。
  - 活动状态、明火或烟火显示为可用且可配置。
  - 页面没有横向溢出。
  - 页面没有 `APNs / 云端阶段 / 本地闭环 / provider / scheduler / Base URL / API Key` 等普通用户不该看到的词。
  - 状态显示“已同步到家庭盒子”。

当前边界：

- 当前盒子回传的是基础视觉检测，所以人形、无人和跌倒暂时被正确禁用；如果要开放这三项，需要在盒子端启用人形或姿态模型，并让同步上报带回对应能力。
- 守护规则已经能保存、下发、盒子应用并在 App 显示同步状态；下一步应继续补“真实事件反馈质量”，确认事件页展示的候选事件、规则证据和当前两路摄像头检测结果完全一致。

### 67.6.1 2026-07-10 树莓派 YOLO 真实运行环境恢复

背景：

- 盒子管理台实时画面中有人，但“人形 / 无人”始终显示人数 0。
- 排查确认 `.env.local` 覆盖仓库 `.env`，实际运行的是 `GOHOME_DETECTOR_BACKEND=basic`。
- 此前为了规避 Python 3.13 环境缺少 `torch / ultralytics` 导致的模型错误，曾主动降级到 basic；算法开关可以同步，但 basic 不具备真实人形检测能力。

本次恢复：

- 真实设备为 aarch64、8GB 内存，Python 3.13.5。
- 在现有 `.venv-pi` 安装并验证：
  - `torch==2.10.0`
  - `torchvision==0.25.0`
  - `ultralytics==8.4.91`
- `requirements-yolo.txt` 锁定上述 ARM64 兼容版本，避免后续安装拉取更大的未验证版本。
- 使用当前两路摄像头真实截图运行 `yolo11n.pt`：
  - 首次模型预热约 2.3 秒。
  - 后续 416 尺寸单帧推理约 90-95ms。
  - 两路画面均识别到真实人物并返回检测框和置信度。
- Pi 正式配置恢复为 `GOHOME_DETECTOR_BACKEND=yolo`，模型为 `yolo11n.pt`，推理尺寸设为 416。

验证结果：

- `/api/device` 已返回 `detector_backend=yolo`、`person_detection=true`、`yolo_imgsz=416`。
- 最新持久化分析中，摄像头 13 检测到 1 人，摄像头 14 检测到 3 人，均为 `model_status=ready`。
- 无头 Chrome 验证管理台人形预览：实时画面显示真实人形框、人数 1、置信度 63%、模型 `yolo11n.pt`、分析延迟 132ms，页面无横向溢出。
- 云端 `/api/app/device` 已同步返回 YOLO 后端及人形、长时间无人、跌倒候选能力；盒子当前规则已启用人形检测。
- 本节完成时只恢复了 YOLO；后续 67.6.2 已继续恢复原 RTMPose 运行环境和 worker 姿态采样，当前状态以 67.6.2 为准。

### 67.6.2 2026-07-10 原视觉算法失效根因与 RTMPose 恢复

历史事实：

- 旧算法不是未实现。盒子数据库共有 2357 条 `pose_model_status=ready` 的历史快照，包含 `pose_count / keypoints / pose_fall_score`。
- 第一条姿态成功记录为 2026-07-05，最后一条旧环境成功记录为 2026-07-06 20:06（北京时间）。
- 旧 `.venv` 的 `pyvenv.cfg` 和 Python 链接指向 Mac `/opt/homebrew/...`，目录中同时存在 macOS Mach-O OpenCV 动态库和 Linux aarch64 包，属于跨机器复制造成的环境污染。
- 2026-07-06 19:46 新建 `.venv-pi`，当时只安装 FastAPI、uvicorn、基础 OpenCV 和 numpy；22:27 systemd 重启后优先使用 `.venv-pi`，因此此前仍在内存中工作的 YOLO 和 RTMPose 在进程重启后一起消失。
- `.env.local` 切到 `basic` 是对缺失依赖的临时显示纠偏，不是算法失效根因。

恢复与根治：

- `.venv-pi` 已恢复完整 Pi 原生视觉依赖：
  - `torch==2.10.0`
  - `torchvision==0.25.0`
  - `ultralytics==8.4.91`
  - `onnxruntime==1.27.0`
  - `rtmlib==0.0.15`
  - `opencv-contrib-python==4.10.0.84`
- 保留并复用原模型：`yolo11n.pt`、YOLOX tiny ONNX、RTMPose-S ONNX。
- `requirements-pose.txt` 改为继承 `requirements-yolo.txt`，标准姿态安装不再生成“只有姿态依赖或只有基础依赖”的半套环境。
- 新增 `scripts/install-pi-vision-runtime.sh`：只允许 Linux aarch64，检测到 Homebrew、`/Users/` 或 Windows 路径时拒绝继续。
- 新增 `scripts/deploy-to-pi.sh`：部署时强制排除 `.venv / .venv-pi / data / .env / .env.local`，不再允许开发机环境覆盖盒子运行环境和设备数据。
- 新增 `scripts/verify-vision-runtime.py`，并写入 systemd `ExecStartPre`；每次启动前检查 Pi Python、torch、ultralytics、YOLO 权重、onnxruntime、rtmlib 和 RTMPose 模型缓存，任一缺失则服务不进入假运行状态。
- YOLO 和 RTMPose 模型实例增加进程内推理锁，避免管理台、worker 和多摄像头请求同时进入共享模型。
- RTMPose 在 `tracking=false` 时使用无状态 `Body` 推理器，不再进入 RTMLib 0.0.15 的 `PoseTracker` tracking 分支。原配置 `tracking=0 + det_frequency=8` 会在跳过检测的中间调用拿到空人体框；即使频率改为 1，RTMLib 仍可能误入 tracking 分支并修改上一帧框。历史数据库中已有 560 条姿态推理错误；两路摄像头共享实例时不能跨摄像头 tracking，因此每个“姿态采样帧”必须独立完成人体检测和姿态推理。
- 姿态短缓存状态从矛盾的 `disabled + 有骨架` 改为 `cached`，并明确显示沿用时长；缓存骨架不会直接生成跌倒告警。

验证：

- systemd 启动前检查全部通过，服务重启后 6 秒内恢复，`ExecStartPre.status=0`。
- 最终无状态 Body 修复后，20 个并发跌倒预览请求全部返回 RTMPose `ready`，`error/unavailable` 为 0。
- 修复后连续观察 5 轮 worker，两路共 10 次自动姿态采样全部为 RTMPose `ready`，新错误 0；两路摄像头均持续写入真实骨架数据。
- Chrome 验证摄像头 13 跌倒预览：2 人、2 组骨架、34 个关键点、36 条骨架线，组合模型显示 `yolo11n.pt + RTMPose-lightweight (onnxruntime/cpu)`。
- 盒子 `/api/device` 返回 `person_detection=true / pose_detection=true / yolo_runtime=true / pose_runtime=true`；云端 `/api/app/device` 已同步返回 `person_detection=true / pose_detection=true`。

当前边界：

- 姿态链路已经恢复为原有实际模型，不再是待做 POC。
- 跌倒仍属于候选检测，需要人框、骨架、连续帧、持续时间和恢复状态共同确认；下一步应补真实跌倒/非跌倒样本评估和误报反馈，而不是继续更换模型路线。

### 67.7 事件页真实反馈与旧离线评估修复

背景：

- 用户继续要求核对进度和逻辑质量，上一轮已经把规则和盒子能力对齐；这一轮继续检查“守护事件真实反馈”。
- 当前用户态事件列表和首页摘要已经是 0 条，说明旧离线事件没有继续污染用户事件列表。
- 但发现 `/api/app/cameras/{id}/evaluation/latest` 仍从旧的离线事件反推最近评估，导致摄像头实际在线时，评估接口还显示旧的 `camera_offline` 状态。这会影响检测页、事件页空态和用户对系统是否还在工作的判断。

本次修正：

- `local-app-server/server.js`
  - `latestCameraEvaluationPayload()` 过滤已恢复的旧离线事件。
  - 如果当前摄像头在线且没有新的规则命中，评估接口返回：
    - `camera_state=online`
    - `candidates=[]`
    - `explanation=摄像头在线，最近没有命中需要家属确认的规则。`
  - 这样事件列表、首页摘要和每路摄像头最近评估保持一致。
- `assets/scripts/events-live.js`
  - 事件页不再只显示空态文案。
  - 没有待确认事件时，展示每路启用摄像头的最近同步状态卡。
  - 卡片显示“房间 · 摄像头名”、在线状态、是否命中告警规则和最近同步时间。
  - 正常检测不会被伪装成事件，点击摄像头状态卡进入对应守护页。
- `assets/styles/stitch-app-adapt.css`
  - 新增摄像头检测状态卡样式，保持紧凑、低边界、无横向溢出。
- `scripts/verify-local-closed-loop.js`
  - 自检新增每路在线摄像头的最新评估断言。
  - 如果摄像头在线但评估接口仍返回 `offline`，自检会直接失败。

验证：

- 重启本地 App 服务 `http://127.0.0.1:8788` 后接口验证：
  - 摄像头 8：`camera_state=online`、`candidates_len=0`。
  - 摄像头 9：`camera_state=online`、`candidates_len=0`。
  - `/api/app/events?acknowledged=false` 返回 0。
  - `/api/app/summary/today` 返回 `open_events=0`、`critical_events=0`。
- `node --check local-app-server/server.js` 通过。
- `node --check assets/scripts/events-live.js` 通过。
- `node --check scripts/verify-local-closed-loop.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `28 passed, 0 warnings, 0 failed`
  - 新增检查：
    - `camera evaluation - 智能摄像头 online 0 candidate(s)`
    - `camera evaluation - 智能摄像头2 online 0 candidate(s)`
- Chrome 验证 `events.html?app=1`：
  - 页面标题为 `2 路摄像头在线，暂无异常`。
  - 两张摄像头状态卡分别显示：
    - `客厅 · 智能摄像头 在线`
    - `客厅 · 智能摄像头2 在线`
  - 两张卡都显示 `未命中告警规则`。
  - 页面无横向溢出。
  - 页面没有旧工程错误文案和普通用户不该看到的开发词。

当前边界：

- 事件页现在能说明“系统在检测但没有异常”，不再让用户以为事件反馈断了。
- 当前本地 App 服务仍没有持久化每帧正常检测记录，只保存告警事件和设备同步状态；后续如果要展示更细的“最近 10 次检测历史 / 画面质量趋势”，需要盒子侧把规则评估摘要作为非告警 telemetry 上报到 App 服务。

### 67.8 首页、守护、检测、事件状态口径统一

背景：

- 上一轮修复了事件页和评估接口，但检测页、守护页仍可能在没有最新截图时显示“等待规则 / 等待检测摘要”，和 `evaluation/latest` 的在线状态不一致。
- 用户需要看到的是同一条产品事实：摄像头在线、盒子在跑、当前没有命中需要确认的规则。

本次修正：

- `assets/scripts/detection-live.js`
  - 检测页在没有最新截图时也会读取 `/api/app/cameras/{id}/evaluation/latest`。
  - 如果评估状态是在线且无候选，页面显示：
    - `摄像头在线，暂无异常`
    - `未命中规则`
    - `摄像头在线，最近没有命中需要家属确认的规则。`
  - 检测页能力说明改为读取 `device.vision_capabilities`，不再硬写 YOLO 口径。
  - 人形/无人、跌倒能力显示和守护规则页一致：当前基础视觉检测下显示“需模型”。
- `assets/scripts/monitor-live.js`
  - 守护页在没有最新截图时也读取最近评估。
  - 若评估在线且无候选，则展示“暂无异常 / 未命中规则 / 家里平稳”，不再只显示“等待检测摘要”。
- `monitor.html` / `detection.html` / `events.html`
  - 更新脚本和样式版本号，避免浏览器继续使用旧缓存。

验证：

- `node --check assets/scripts/detection-live.js` 通过。
- `node --check assets/scripts/monitor-live.js` 通过。
- `node --check assets/scripts/events-live.js` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `28 passed, 0 warnings, 0 failed`
  - 两路摄像头在线。
  - 两路最新评估均为 `online 0 candidate(s)`。
- Chrome 验证：
  - `monitor.html?camera_id=8&app=1`
    - 显示 `实时画面已返回`
    - `画面在线 / 继续观察 / 无待处理`
  - `detection.html?camera_id=8&app=1`
    - 显示 `摄像头在线，暂无异常`
    - 显示 `未命中规则`
    - 规则摘要为 `摄像头在线，最近没有命中需要家属确认的规则。`
    - 人形和跌倒能力说明与当前基础视觉能力一致。
  - `events.html?app=1`
    - 显示 `2 路摄像头在线，暂无异常`
    - 两路摄像头状态卡均为在线、未命中告警规则。
  - 三个页面均无横向溢出。
  - 三个页面均没有旧工程错误文案和普通用户不该看到的开发词。

当前边界：

- 三个页面的用户态状态口径已经统一。
- 仍未做“正常检测历史趋势”，因为当前本地服务没有持久化非告警评估流水；若需要趋势图，需要盒子侧额外上报正常检测摘要。

### 67.9 新用户路径、账号隔离和用户可见文案复核

背景：

- 用户要求继续核对进度，明确“什么时候需要用户处理再提醒”。
- 当前主账号、家庭、盒子、两路摄像头、天气、Tavily、关怀卡片和事件空状态已经通过本地闭环，但还需要把“注册 / 登录后是否串数据”做成可重复自检。
- 同时页面里仍残留少量工程词或本地联调词，容易让普通家属误以为 App 直接依赖开发服务。

本次修正：

- `scripts/verify-local-closed-loop.js`
  - 新增临时新账号路径自检。
  - 自检会注册临时账号，确认新账号默认：
    - 没有继承旧家庭。
    - 没有继承旧摄像头。
    - 没有继承旧盒子绑定。
  - 随后创建临时家庭并保存老人资料，确认老人称呼、手机号和家里电话能按账号家庭持久化。
  - 测试结束后会重新登录原主账号，避免本地默认账号停留在临时账号。
- `login.html` / `assets/scripts/stitch-app-data.js`
  - 登录页按钮从“演示验证码”改为“获取验证码”。
  - 本地联调仍自动填入验证码，但不再把“演示”作为用户界面文案。
- `assets/scripts/app-shell-live.js`
- `assets/scripts/connect-live.js`
- `assets/scripts/detection-live.js`
- `assets/scripts/rules-live.js`
- `assets/scripts/login-live.js`
- `privacy.html`
  - 把普通用户可见的 `edge-agent`、`这台 Mac`、`演示视觉`、`本地演示通知` 等词替换为产品语言：
    - 家庭盒子服务。
    - 家庭盒子负责拉流和检测。
    - 基础视觉 / 基础视觉管线。
    - 关怀提醒、告警通知和到家提醒设置。

验证：

- `node --check scripts/verify-local-closed-loop.js` 通过。
- `node --check assets/scripts/stitch-app-data.js` 通过。
- `node --check assets/scripts/app-shell-live.js` 通过。
- `node --check assets/scripts/connect-live.js` 通过。
- `node --check assets/scripts/detection-live.js` 通过。
- `node --check assets/scripts/rules-live.js` 通过。
- `node --check assets/scripts/login-live.js` 通过。
- `npm run verify:local-loop` 通过：
  - `36 passed, 0 warnings, 0 failed`
  - 新增检查包括：
    - `new user family isolation - no inherited family`
    - `new user camera isolation - no inherited cameras`
    - `new user device isolation - no inherited box binding`
    - `new user elder profile - 测试长辈 021-00000000`
    - `active user restore - 家属`
- 浏览器手机宽度验证：
  - `index.html`：默认家庭、母亲、2 路摄像头、天气、热点/养生/文娱/日历/位置与回家模块均显示；无横向溢出。
  - `login.html?app=1`：手机号验证码入口显示“获取验证码”，无演示字样，无横向溢出。
  - `privacy.html?app=1`：显示家属、默认家庭、母亲、家庭盒子已连接，不显示管理员身份。
  - `cameras.html?app=1`：显示两路摄像头在线，说明“App 只提交配置和查看状态，画面、检测和事件都由盒子同步回来”，无横向溢出。

当前边界：

- 临时新账号自检会在本地 JSON 数据库留下测试账号和测试家庭记录；它们不影响当前主账号数据。若比赛演示前需要清爽数据库，需要补一个只清理 `verify-*` 自检数据的维护脚本。
- 当前本地验证码仍是联调替身，不是真实短信服务。上云和原生 iOS 前，需要接正式短信验证码、Apple/微信登录或明确比赛演示账号方案。
- 下一步应继续做“上云前收口”：
  - 清理或归档自检数据。
  - 把本地 JSON 当前真实家庭数据导出到 PostgreSQL seed。
  - 用 `GOHOME_APP_STORE=postgres` 跑同样的 `verify:local-loop`。
  - Postgres 通过后，再部署 HTTPS 云端 App API。

### 67.10 自检临时数据清理与闭环脚本防污染

背景：

- 67.9 新增的新用户隔离自检会创建 `verify-*` 临时账号和 `流程自检-*` 临时家庭。
- 如果每次本地闭环都留下这些数据，比赛演示库会变脏，也会干扰后续上云 seed。

本次修正：

- `local-app-server/server.js`
  - 新增本机 / ops 维护接口：`POST /api/v1/internal/verify-data/cleanup`。
  - 清理范围只包括：
    - `verify-*@gohome.local` 临时账号。
    - `流程自检-*` 临时家庭。
    - 上述临时账号 / 临时家庭关联的会话、家庭成员、老人资料、设备绑定、绑定码、摄像头、媒体、事件、日历、关怀偏好、关怀卡片、模型任务、内容源和内容推荐。
  - 不会删除默认家庭、真实家属账号、真实盒子、真实摄像头和真实关怀卡片。
- `scripts/cleanup-verify-data.js`
  - 新增维护脚本。
  - 默认 dry-run，只展示可清理数据。
  - `--apply` 才执行删除。
- `package.json`
  - 新增 `npm run db:cleanup-verify`，用于执行清理。
- `scripts/verify-local-closed-loop.js`
  - 新用户隔离自检结束后会恢复主账号，并自动调用清理接口。
  - 后续每次 `npm run verify:local-loop` 都不会再留下 `verify-*` 临时账号和 `流程自检-*` 临时家庭。

本次实际清理：

- dry-run 命中：
  - 4 个 `verify-*` 临时账号。
  - 4 个 `流程自检-*` 临时家庭。
  - 4 条临时会话。
  - 4 条临时家庭成员关系。
  - 4 条临时老人资料。
- 执行 `npm run db:cleanup-verify` 后共清理 20 条临时记录。
- 清理后数据库只保留：
  - `admin@gohome.local`
  - `84622435@qq.com`
  - `13818462550@phone.gohome.local`
  - `默认家庭`
  - 默认家庭下两路在线摄像头。

验证：

- `node --check local-app-server/server.js` 通过。
- `node --check scripts/cleanup-verify-data.js` 通过。
- `node --check scripts/verify-local-closed-loop.js` 通过。
- 重启 `com.gohome.local-app-server` 后 `/health` 正常。
- `npm run db:cleanup-verify` 通过。
- `npm test` 通过。
- `npm run verify:local-loop` 通过：
  - `37 passed, 0 warnings, 0 failed`
  - 新增 `verify data cleanup - 5 record(s) removed`。
- 再次 dry-run 清理显示：
  - `Targets: 0 user(s), 0 family/families`
  - `Total removable records: 0`

当前边界：

- 自检数据污染问题已解决。
- 下一步进入 PostgreSQL 上云前验证：先导出当前 JSON seed，再用真实 PostgreSQL 连接串跑 `npm run verify:postgres-loop`。这一步需要用户提供可用的 PostgreSQL 连接串或确认使用哪个云数据库。

### 67.11 上云前 JSON Seed 导出复核

背景：

- 自检临时数据清理完成后，可以把当前本地 JSON 运行态导出为云端 seed，用于下一步 PostgreSQL 验证。

本次执行：

- 运行 `npm run db:export`。
- 输出文件：
  - `data/app-server/cloud-seed.json`
- schema：
  - `001_initial_schema`

导出结果：

- `users=3`
  - `admin@gohome.local`
  - `84622435@qq.com`
  - `13818462550@phone.gohome.local`
- `families=1`
  - `默认家庭`
- `family_members=2`
  - 管理员与当前家属账号均在默认家庭内。
- `elder_profiles=1`
  - 被守护人：母亲。
  - 城市：上海。
  - 手机号已导出。
  - 家里电话当前为空；不影响当前拨号闭环，因为手机号存在。
- `device_bindings=1`
  - 默认家庭绑定当前家庭盒子。
- `cameras=2`
  - 两路摄像头都归属默认家庭和当前家庭盒子。
- `camera_secrets=2`
  - 两路摄像头的接入密钥配置已进入 seed，后续云端需要迁移到 Secret Manager / KMS，不应长期明文存数据库。
- `care_preferences=1`
- `care_cards=3`
- `media_assets=49`
- `events=124`
- `model_generation_jobs=59`
- `verify_users=0`

验证：

- seed 中没有 `verify-*` 临时账号。
- seed 中没有 `流程自检-*` 临时家庭。
- 默认家庭、老人资料、盒子绑定和两路摄像头关系完整。

当前边界：

- PostgreSQL 真实闭环还没跑，因为缺少 `GOHOME_DATABASE_URL`。
- 下一步需要用户提供一个空 PostgreSQL 数据库连接串，或确认使用哪个云数据库。

### 67.12 阿里云轻量服务器部署与盒子切云端

时间：2026-07-09

本轮目标：

- 先把 App/H5 + App API 从本地 `127.0.0.1:8788` 推到云端公网 IP。
- 云端使用 PostgreSQL，不再依赖本地 JSON 作为运行库。
- 盒子继续留在老人家局域网，但把配置同步、心跳和上传目标切到云端。

云端服务器：

- 公网地址：`http://139.196.223.58`
- 系统：Ubuntu 24.04
- 运行目录：`/opt/gohome/app`
- 服务：
  - `gohome-app.service`：Node App API + H5，监听 `127.0.0.1:8788`
  - `nginx`：公网 `80` 反向代理到 App API
  - `postgresql`：本机 PostgreSQL 16
- 已新增 2G swap。
- 当前资源占用验证：
  - `gohome-app`、`nginx`、`postgresql` 均为 `active` + `enabled`
  - 内存可用约 1.1G，磁盘剩余约 32G

安全处理：

- 第三方模型、天气、Tavily、数据库、App token、设备 token 均保存在服务器 `.env` 或 `/opt/gohome` 私有文件中。
- 没有把 key/token 写入代码或文档。
- `/health` 已移除本地调试 token，不再向公网暴露内部 App token。
- 启动日志里的 App token / Device token 已改为脱敏输出。

数据库与迁移：

- 已创建云端 PostgreSQL 用户和数据库。
- `npm run verify:postgres-loop -- --allow-non-empty` 已在云端通过。
- 云端 Postgres 当前写入 251 行业务数据。
- 云端验证结果：
  - 用户：`家属`
  - 家庭：`默认家庭`
  - 摄像头：2 路
  - 关怀推送：已开启，`08:30`
  - 关怀内容类型：9 类
  - 关怀卡片：3 张

本轮修复：

- `PostgresStore` 写入 JSONB 字段时统一序列化数组/对象，修复 `care_preferences.interests` 写入 PostgreSQL 失败的问题。
- `cloud-seed` 导出时会把历史事件里已不存在的 `camera_id` 置空，保留事件文案、房间、截图关系，避免旧摄像头 ID 卡住外键。
- `data/app-server/cloud-seed.json` 已重新导出。
- 本地 `npm test` 通过。

盒子切云端：

- 盒子 SSH：`gohome@192.168.1.12`
- 设备 ID：`edge-042714be475b91da`
- 已备份并更新盒子 `/home/gohome/gohome/edge-agent/.env.local`：
  - `GOHOME_APP_SERVER_BASE_URL=http://139.196.223.58`
  - `GOHOME_DEVICE_API_TOKEN` 使用云端生成的设备 token
- 已重启 `gohome-edge-agent`。
- 盒子侧验证：
  - `config_sync_agent.app_server_base_url` 已为 `http://139.196.223.58`
  - `config_sync_agent.last_error` 为空
  - 2 路摄像头配置均已同步
  - 规则版本已应用：`rules-037e17c81a12`
  - `upload_agent` 已启用、运行中、配置完成，目标为云端地址
- 云端侧验证：
  - 云端能看到设备 `edge-042714be475b91da` 在线
  - 设备 `last_seen_at` 已更新到切云端后的时间
  - 云端 2 路摄像头均为 `online / synced`

当前边界：

- 当前已跑通“云端 App API + PostgreSQL + 盒子心跳/配置同步”。
- 事件上传 agent 已指向云端并 ready；本轮没有强造假告警污染事件列表。实际画面抓拍成功，但未命中规则，所以没有生成新上传事件。
- 外网实时直播还没有真正穿透。云端可以承接配置、事件、截图和状态；如果用户手机离开老人家局域网后仍要看实时视频，需要下一步做盒子到云端的视频隧道/中继，例如 WebRTC、反向 WebSocket/MJPEG 中继或云端 TURN/relay。
- 当前公网只有 HTTP；iOS 真机、摄像头权限、Service Worker、正式推送和上架前仍需要 HTTPS。没有备案域名时，可以先用临时隧道或非备案域名/CDN 方案做演示 HTTPS。

下一步：

1. 用公网地址做一次页面级验收：登录、首页、守护、事件、陪伴、我的、设备管理、规则设置。
2. 补“云端视频中继”最小方案，让手机离开家庭局域网后仍能看到实时画面。
3. 做云端 scheduler / notification-service：按关怀推送规则定时生成卡片、调用天气和 Tavily、触发 App 推送。
4. 接 HTTPS，再进入 iOS WebView/原生壳打包。

### 67.13 登录入口改为手机号口径

时间：2026-07-09

问题：

- 用户端登录页不应该暴露内部账号概念。
- 历史实现中前端把手机号拼成 `手机号@phone.gohome.local` 再提交给后端，这属于工程实现细节，不符合产品口径。

本轮处理：

- `login.html` 文案改为“手机号登录 / 手机号码 / 验证码”。
- 前端登录/注册提交改为 `{ phone, code }`，不再在浏览器侧拼内部 email。
- 服务端兼容 `{ phone, code }`，内部自动映射到既有手机号账号格式，历史数据无需迁移。
- `publicUser` 返回 `phone`，已有 `@phone.gohome.local` 历史账号会自动解析手机号。
- 家庭页、首页、App 壳等用户展示点改为手机号优先，不再回退显示内部 email。
- PostgreSQL seed 导出和恢复补齐 `users.phone`。

验证：

- `npm run db:export` 通过。
- `npm test` 通过。
- 本地 `POST /api/auth/login` 使用 `{ phone: "13818462550", code: "000000" }` 登录成功。
- 公网 `http://139.196.223.58/login.html` 源码确认只显示手机号和验证码口径。
- 公网 `POST /api/auth/login` 使用手机号登录成功，并返回 `phone=13818462550`。

### 67.14 新用户配置路径和设备认领口径确认

时间：2026-07-09

本轮目标：

- 先把产品路径写回 PRD / Plan，再开始改代码，避免继续按演示数据或局域网直连逻辑扩张。
- 明确“盒子已联网以后，App 里到底怎么一步步完成配置”。

已确认的产品路径：

1. 盒子通电。
2. 未联网时走 `GoHome-XXXX` 热点和 `/setup`，只完成 Wi-Fi 配网；已联网时直接打开 App。
3. App 手机号登录或注册。
4. 创建或加入家庭。
5. 填写老人资料。老人资料未完成前，用户不能进入完整主功能。
6. 绑定守护盒。
   - 正式产品：扫盒身、包装盒或说明卡二维码。
   - 当前树莓派没有二维码贴纸：先用云端或 `/admin` 生成的临时绑定码过渡。
   - 局域网发现和 BLE 只作为辅助发现或配网能力，不能作为设备归属依据。
7. 配置至少一路摄像头。
8. 盒子从云端拉取摄像头配置，在老人家局域网内测试并回传同步状态。
9. 配置完成后进入首页、守护、事件、陪伴和我的。

出厂二维码口径：

- 每台正式盒子出厂前必须生成稳定 `device_id`、设备序列号、设备密钥和一次性认领凭证。
- 二维码只承载 `sn + claim_code`，不承载 IP、RTSP 地址或摄像头密码。
- App 扫码后把 `sn + claim_code` 发给云端；云端确认设备存在、未绑定、凭证有效后，才把设备绑定到当前家庭。
- 绑定成功后认领凭证失效；售后重绑需要解绑、恢复出厂或运营后台重新签发。

云端数据口径：

- 云端 `.env` 和服务密钥继续保留，包括模型、天气、Tavily、数据库、App token 和设备服务密钥。
- 云端业务数据验收应为空：不预置演示用户、默认家庭、默认摄像头和默认关怀卡片。
- 盒子可以作为未绑定设备持续上报心跳，但 `family_id` 必须为空；只有 App 完成认领后才写入家庭归属。
- 新手机号默认不能读取旧家庭、旧摄像头、旧关怀卡片或旧事件。

已更新文档：

- `想家了吗-PRD.md`
  - 更新标准家庭版使用链路。
  - 新增设备绑定和认领规则。
  - 修正设备安装流程为 App 登录、家庭、老人资料、扫码或绑定码认领、摄像头配置。
- `想家了吗-Plan.md`
  - 新增 `14.7 新用户配置向导和设备认领`。
  - 云端验收清单加入空业务数据、新用户配置向导和未绑定设备状态。
  - 下一步顺序调整为先做配置向导 / 设备认领 / 空云端验收，再做视频中继、推送和 iOS。

当前边界：

- 本条是产品路径和文档确认记录，代码尚未开始改。
- 当前云端仍带有上一轮 seed 进去的默认家庭、默认摄像头和关怀卡片；下一步需要清空云端业务数据但保留服务器 `.env`。
- 当前设备绑定页仍偏开发口径，下一步要改成“扫码绑定 / 输入绑定码”的用户口径。
- 当前后端设备心跳逻辑需要修正，避免未绑定设备自动落到默认家庭。

下一步：

1. 后端补设备认领 / 绑定码模型，并修复未绑定设备自动归属默认家庭的问题。
2. 前端补新用户配置向导，未完成家庭、老人资料、盒子绑定和摄像头配置前不进入主功能。
3. 云端执行空业务数据重置，保留 `.env` 和设备服务能力。
4. 用一个全新手机号从云端完整跑通注册、家庭、老人资料、绑定盒子、配置摄像头、盒子同步和首页进入。

### 67.15 新用户配置路径和设备认领代码落地

时间：2026-07-09

本轮处理：

- 后端新增设备认领接口：
  - `GET /api/device-claims/available`
  - `POST /api/device-claims/claim`
- 设备正式绑定前保持未归属状态：
  - 未认领盒子可以上报心跳和在线状态，但不自动落到默认家庭。
  - 未认领盒子拉取 `/api/v1/device/config` 时不返回家庭摄像头配置。
  - 未归属设备上报的摄像头和事件不会出现在新用户 App 里。
- 收紧旧兼容入口：
  - `POST /api/device-bindings` 不再允许不带盒子码直接绑定当前盒子。
  - 绑定必须通过盒身二维码内容、序列号或临时绑定码完成认领。
- 新用户首页配置门槛已落地：
  - 未登录：只提示登录。
  - 已登录但无家庭：只提示创建家庭。
  - 有家庭但无老人资料：只提示填写老人资料。
  - 有老人资料但未绑定盒子：只提示绑定设备。
  - 已绑定但无启用摄像头：只提示配置摄像头。
  - 只有以上步骤完成后才加载首页关怀卡片、天气、热点、事件和实时状态。
- 修复前端新用户 setup 模式：
  - setup 模式下隐藏今日关怀、定位、历史卡片等主内容，避免未配置时提前显示假首页。
  - 线性配置页统一补 iOS 安全区，登录、家庭、老人资料、设备绑定、摄像头配置页顶部按钮不再贴近刘海区域。
- 验证脚本补充真实路径断言：
  - 新手机号默认没有家庭。
  - 未认领盒子可被云端发现。
  - 未认领盒子拿不到摄像头配置。
  - 不带盒子码直接绑定会失败。
  - 输入序列号认领后，家庭能看到绑定关系。

浏览器验证：

- iPhone 窄屏 `390x844` 下验证 `index.html?app=1`：
  - 新用户只显示配置引导。
  - 底部导航隐藏。
  - 主内容区隐藏。
  - 横向溢出为 `0`。
  - 无前端错误日志。
- 验证 `device_binding.html?app=1`：
  - 家庭选择、盒子码输入、云端发现列表正常显示。
  - 输入临时盒子序列号后绑定成功，并跳转到 `connect.html` 摄像头配置页。
  - 设备绑定页和摄像头配置页顶部安全区正常，横向溢出为 `0`。

验证命令：

- `node --check local-app-server/server.js`
- `node --check assets/scripts/home-live.js`
- `node --check scripts/verify-local-app-server.js`
- `git diff --check`
- `npm test`

当前边界：

- 本地路径已跑通，云端业务数据还没有执行清空重置。
- 当前正式二维码贴纸还没有实物生产流程；本地和云端先用序列号 / 临时绑定码过渡。
- 下一步上云前，需要把云端保留 `.env`，清空演示业务数据，再用全新手机号从公网完整验收一次。

### 67.16 云端部署新用户路径并清空业务数据

时间：2026-07-09

本轮处理：

- 使用 SSH key `~/.ssh/gohome_cloud_ed25519` 连接阿里云主机 `139.196.223.58`。
- 云端应用目录：`/opt/gohome/app`。
- 云端当前不是 git checkout，因此本轮采用压缩包部署：
  - 本地打包 App / H5 / local-app-server / scripts / docs。
  - 排除 `.env`、`node_modules`、`data`、`.git`、盒子侧大目录和本地模型文件。
  - 上传到云端后解包到 `app_next`。
  - 保留远端 `.env`。
  - 安装依赖、语法检查后切换目录并重启 `gohome-app.service`。
- 部署前已做备份：
  - 远端应用备份：`/opt/gohome/backups/app-20260709-161536.tgz`
  - 远端数据库备份：`/opt/gohome/backups/db-20260709-161536.sql.gz`
  - 清业务数据前数据库备份：`/opt/gohome/backups/db-before-business-reset-20260709-162757.sql.gz`

本轮修复：

- 云端新建家庭时触发 `elder_profiles_pkey` 冲突。
- 根因：PostgreSQL `elder_profiles.id` 是主键，但导出 seed 时多个家庭都可能用 `elder_primary` 作为 id。
- 修复：导出时使用 `family_id:elder_id` 作为 `elder_profiles.id`，确保跨家庭唯一。
- 已提交：`cb18499 fix: make elder profile seed ids family scoped`。

云端业务数据重置：

- 已清空：
  - `users`
  - `families`
  - `family_members`
  - `elder_profiles`
  - `device_bindings`
  - `binding_codes`
  - `device_tokens`
  - `cameras`
  - `camera_secrets`
  - `events`
  - `media_assets`
  - `care_preferences`
  - `care_cards`
  - `model_generation_jobs`
  - `content_sources`
  - `content_recommendations`
- 已保留：
  - 服务器 `.env`
  - 模型 / 天气 / Tavily 等环境变量配置
  - PostgreSQL 连接配置
  - 当前树莓派盒子设备记录
- 已删除旧自检盒子 `edge-check`。
- 当前保留的真实盒子：
  - `device_id=edge-042714be475b91da`
  - 设备码 / 当前临时序列号：`GH-475B91DA`
  - 状态：`online`
  - 认领状态：`claimable`

验证结果：

- 公网健康检查：
  - `http://139.196.223.58/health`
  - `store=postgres`
  - `events=0`
  - `assets=0`
- 数据库最终计数：
  - `users=0`
  - `families=0`
  - `cameras=0`
  - `events=0`
  - `care_cards=0`
  - `device_bindings=0`
  - `devices=1`
- 新用户公网验证：
  - 注册成功。
  - 默认家庭数量为 0。
  - `/api/device-claims/available` 返回 1 台可认领设备。
  - 不带设备码直接绑定会返回 400。
  - 未绑定盒子拉 `/api/v1/device/config` 时 `cameras=0`。

当前云端测试路径：

1. 打开 `http://139.196.223.58/index.html?app=1`。
2. 用全新手机号注册。
3. 创建家庭。
4. 填老人资料。
5. 进入设备绑定页。
6. 输入设备码 `GH-475B91DA` 绑定当前树莓派盒子。
7. 进入摄像头配置页添加摄像头。
8. 等盒子从云端拉配置并回传同步状态。

当前边界：

- 当前公网仍是 HTTP，不是 HTTPS。
- 正式产品二维码尚未生成贴纸；当前用 `GH-475B91DA` 作为这台树莓派的临时设备码。
- 云端已经具备“空业务数据 + 可认领盒子”的真实新用户起点。

## 72. 2026-07-09 云端关怀内容搜索质量收口

背景：

- 视频中继、云端登录态和盒子同步恢复正常后，下一步回到首页关怀内容质量。
- 云端已配置和风天气、Tavily、多模态语言模型和生图模型，但 Tavily 候选仍可能抓到旧文章、过季节日内容或不符合模块意图的新闻。

本轮修复：

- `contentSearchTasksFromPreferences()` 按“我的 -> 关怀推送”设置拆分搜索任务：
  - 本地热点：`topic=news`，`time_range=week`，围绕当前日期、城市、民生、社区活动和便民服务。
  - 健康养生：`time_range=month`，围绕当月老年健康、节气、饮食和作息。
  - 防诈骗：`topic=news`，`time_range=month`，必须命中诈骗、反诈、转账、冒充等语义。
  - 文娱兴趣：`topic=news`，`time_range=month`，围绕戏曲、电视节目、社区文化和活动。
  - 问候话题：使用当前日期、内容区域和老人兴趣生成候选。
- Tavily 请求显式关闭自动参数，增加 `topic`、`time_range`、`include_domains` 和图片关闭项。
- 搜索结果新增 `module`、`search_topic`、`time_range`、`published_at` 等字段，便于首页和模型上下文判断来源。
- 内容安全过滤增强：
  - 过滤旧年份内容。
  - 按模块限制最大时效。
  - 过滤过季节日内容，如 7 月不再展示端午养生候选。
  - 过滤不符合模块意图的候选，如保险宣传日不再作为防诈骗提醒。
  - 清洗标题中的频道前缀，例如 `[午夜新闻]`。

云端验证：

- 云端 `gohome-app.service` 重启后为 `active`。
- `/health` 仍为 `store=postgres`。
- 使用当前家庭强制生成今日关怀卡成功：
  - 关怀卡由 `Qwen/Qwen3.5-27B` 生成文案。
  - 生图模型生成 1:1 图片成功。
  - 内容候选保留 2026-07-09 上海本地热点和 2026-07-08 文娱内容。
  - 旧文章、过季端午养生和无关保险宣传反诈候选已被过滤。

当前边界：

- Tavily 仍只作为家属端“可聊话题候选”，不是直接向老人推送外链。
- 若某个模块当天没有合格候选，首页应显示产品化兜底说明，而不是硬塞无关新闻。
- 真正每日到点推送、异常即时推送和 APNs 送达仍属于云端 scheduler / notification-service / iOS 阶段。

## 73. 2026-07-09 scheduler / notification-service 本地闭环

背景：

- 用户确认下一步要做云端 scheduler / notification-service。
- 目标不是先接 APNs，而是先让服务端真的按“我的 -> 关怀推送”配置生成 App 内消息、通知送达记录和可审计调度记录。

本轮新增：

- 新增数据库迁移 `002_notifications.sql`：
  - `app_messages`：App 内消息，承接每日关怀、事件提醒和测试消息。
  - `app_push_tokens`：App 安装与 push token 登记，只保存 hash 和 preview，不保存明文 token。
  - `notification_deliveries`：通知送达记录，当前可记录 `queued / simulated / app_message_only`。
  - `scheduler_runs`：调度运行记录，保存 scope、result、错误信息和时间。
- `local-app-server/server.js` 新增通知服务能力：
  - `runNotificationScheduler()`：统一调度入口。
  - 每日汇总卡：到达配置时间或手动 force 时生成今日关怀卡，并写入 `care_card` + `app_message` + `notification_delivery`。
  - 异常即时提醒：未处理事件会生成事件型 App 消息和通知记录。
  - 没有 APNs provider 时不伪装真推送，记录为 App 内送达或模拟送达。
  - `GOHOME_SCHEDULER_ENABLED=1` 时可开启后台循环，默认关闭，便于本地测试和云端灰度。
- 新增 / 补齐 API：
  - `POST /api/v1/internal/scheduler/run`
  - `GET /api/v1/internal/scheduler/status`
  - `POST /api/v1/internal/messages/generate`
  - `GET /api/v1/app/messages`
  - `GET /api/v1/app/messages/{message_id}`
  - `PATCH /api/v1/app/messages/{message_id}`
  - `GET /api/v1/notifications/deliveries`
  - `POST /api/v1/notifications/test`
  - `GET /api/v1/app/push-tokens`
  - `POST /api/v1/app/push-tokens`
  - `DELETE /api/v1/app/push-tokens/{app_install_id}`
  - `POST /api/v1/app/push-test`
- PostgresStore 和 seed 导出已支持新表。
- `scripts/verify-local-app-server.js` 已加入通知链路验证：
  - 注册 push token。
  - 手动跑 scheduler。
  - 读取 App 消息。
  - 标记消息已读。
  - 查询送达记录。
  - 执行 push-test。
  - 校验 seed bundle 可恢复新表。

本地验证：

- `node --check local-app-server/server.js`
- `node --check local-app-server/postgres-store.js`
- `node --check scripts/export-local-app-db.js`
- `node --check scripts/verify-local-app-server.js`
- `npm test`

当前边界：

- 当前仍未接 APNs；没有 APNs provider 时，只生成 App 内消息和模拟 / App 内送达记录。
- 后续 iOS 原生 App 接入后，需要把真实 APNs token 登记到 `app_push_tokens`，再接 APNs provider 发送。
- 当前后台循环需要通过 `GOHOME_SCHEDULER_ENABLED=1` 打开；本地默认用手动 endpoint 验证，避免开发时反复触发模型和生图。

## 74. 2026-07-09 通知页真实展示与云端运行态复核

背景：

- scheduler / notification-service 已经具备后台生成 App 内消息、通知投递记录和调度记录的能力。
- 但用户端 `notifications.html` 仍是静态说明页，不能直接看到“关怀消息是否生成、投递是否记录、iOS token 是否登记”。

本轮新增：

- 新增 `assets/scripts/notifications-live.js`。
- `notifications.html` 改成真实通知状态页：
  - 读取当前家庭 `app_messages`。
  - 读取 `notification_deliveries`。
  - 读取 `app_push_tokens`。
  - 展示打开中消息数、投递记录数、iOS token 数。
  - 展示最近消息和最近投递记录。
  - 支持“生成测试通知”和“推送链路测试”。
  - 没有 APNs 或 iOS token 时明确显示站内消息 / 模拟送达，不伪装正式推送。
- 首页通知图标改为明确链接到 `notifications.html`。
- 首页和陪伴页的 `care_card` 消息标签改为“关怀”，`test` 消息标签改为“测试”。

本地验证：

- `node --check assets/scripts/notifications-live.js`
- `node --check assets/scripts/companionship-live.js`
- `node --check assets/scripts/home-live.js`
- `npm test`
- 使用本机 Chrome + Playwright 打开 `http://127.0.0.1:8788/notifications.html?app=1`：
  - 无控制台错误。
  - 移动端 `393px` 宽度无横向溢出。
  - 点击“生成测试通知”后：
    - 打开中消息从 `5` 变为 `6`。
    - 投递记录从 `0` 变为 `1`。
    - 最近投递状态为 `站内已记录`。

云端部署：

- 已同步以下文件到 `/opt/gohome/app`：
  - `notifications.html`
  - `index.html`
  - `assets/scripts/notifications-live.js`
  - `assets/scripts/companionship-live.js`
  - `assets/scripts/home-live.js`
- 云端服务：
  - `gohome-app.service=active`
  - `/health` 返回 `store=postgres`
- 云端验证：
  - 当前家庭：`妈妈的家`
  - `app_messages=1`
  - 首条消息类型：`care_card`
  - `notification_deliveries=1`
  - 首条投递状态：`app_message_only`
  - `app_push_tokens=0`

Git：

- 已提交并推送：`345c58a feat: show live notification delivery state`

## 75. 2026-07-09 云端运行态复核与下一步边界

本轮复核目的：

- 用户要求查看当前进度、未完成事项和下一步。
- 本轮不做功能扩张，先复核代码、文档、云端服务和树莓派真实运行态。

代码和测试状态：

- 本地 Git 工作区干净。
- 最新提交：
  - `345c58a feat: show live notification delivery state`
  - `be00fed feat: add care notification scheduler`
  - `eaa1eb0 fix: tighten care content search quality`
  - `cd9b4d8 feat: relay live preview frames through cloud`
- 本地 `npm test` 通过。

云端服务状态：

- 云端主机：`139.196.223.58`
- 云端应用目录：`/opt/gohome/app`
- `gohome-app.service=active`
- `/health`：
  - `store=postgres`
  - `app_server_base_url=http://139.196.223.58`
- 云端 scheduler 运维接口已验证：
  - `enabled=true`
  - 最近后台任务均为 `succeeded`
  - 当前跳过原因为 `daily_not_due_or_already_sent`，表示今日关怀已经生成，不重复推送。

树莓派盒子状态：

- SSH：`gohome@192.168.1.12`
- `gohome-edge-agent=active`
- `/health` 返回：
  - `worker_running=true`
  - `config_sync_agent.running=true`
  - `config_sync_agent.configured=true`
  - `last_config_version=device-config-ac10e8ec5f9c`
  - `rules.applied=true`
  - `live_relay_agent.running=true`
  - `live_relay_agent.configured=true`
  - `fps=8`
  - `active_cameras=[9,10]`
- 盒子当前从云端同步 2 路摄像头：
  - 远端 `camera_id=1`，本地 `local_camera_id=9`，名称 `冰箱上`，状态 `online / synced`
  - 远端 `camera_id=2`，本地 `local_camera_id=10`，名称 `智能摄像头2`，状态 `online / synced`

当前云端业务态：

- 家庭数量：`1`
- 当前家庭：`id=2`，`name=妈妈的家`
- 可认领设备：`0`
- 设备绑定：`1`
- 摄像头：`2`
  - `冰箱上`：`online / synced`
  - `智能摄像头2`：`online / synced`
- App 消息：`1`
  - 类型：`care_card`
- 通知投递：`1`
  - 状态：`app_message_only`
- iOS push token：`0`

当前真实进度判断：

- 已经完成“最小云端 App API + PostgreSQL + 树莓派盒子连云 + 2 路摄像头配置同步 + 实时帧中继 + 关怀卡片 + 站内通知记录”的验证。
- 当前不再是纯本地闭环，但也还不是正式 iOS 商业版。
- 当前处在 V0 到 V1 之间，正在做 V1 家庭试点版的最小云闭环。

仍未完成：

- HTTPS。
- iOS 原生 App 或 WebView 壳。
- APNs 真推送和 iOS push token 登记。
- 正式短信验证码。
- 正式出厂二维码和一次性认领凭证生产流程。
- 完整破坏性新用户公网验收。
- 7 天或至少 24 小时稳定性报告。
- 姿态骨架、火灾候选、误报反馈和算法质量评估产品化。
- 视频链路最终架构选择和压测。

完整新用户公网验收边界：

- 当前唯一真实盒子已经绑定到 `妈妈的家`。
- 因为当前可认领设备数为 `0`，不能在不影响现有演示数据的情况下，用另一个全新手机号重新认领同一台盒子。
- 如果要做“从空云端开始”的完整新用户验收，必须先备份数据库，并明确允许：
  - 清空当前业务数据，或
  - 解绑当前盒子并恢复 `claimable` 状态。
- 默认不执行破坏性重置，避免破坏当前已经跑通的云端演示家庭。

下一步推荐：

1. 先做非破坏性公网验收：
   - 用当前账号验证公网登录、首页、守护、实时画面、摄像头、事件、关怀、通知、规则同步。
2. 补 HTTPS：
   - 若已有备案域名，优先用子域名反代到当前服务。
   - 若暂时没有域名，比赛演示可继续 HTTP；但 iOS 真机和 APNs 前必须解决 HTTPS。
3. 再决定是否做破坏性新用户验收：
   - 用户确认后再备份、清业务数据或解绑盒子。
4. HTTPS 和完整公网路径通过后，再进入 iOS 壳、push token 登记和 APNs。

## 76. 2026-07-10 破坏性完整新用户公网验收

背景：

- 用户明确允许做破坏性完整新用户公网验收。
- 目标是验证“空云端 -> 新手机号注册 -> 创建家庭 -> 填老人资料 -> 认领真实盒子 -> 重建摄像头配置 -> 盒子同步 -> 首页 / 守护 / 关怀 / 通知可用”。

安全措施：

- 操作前已做完整数据库备份：
  - `/opt/gohome/backups/db-before-full-new-user-20260709-235352.sql.gz`
- 操作前已导出当前业务配置备份：
  - `/opt/gohome/backups/business-before-full-new-user-20260709-235352.json`
- 业务配置备份包含当前家庭、老人资料、设备绑定、2 路摄像头接入配置和关怀偏好；文件权限为 `600`，不在对话和日志中输出 RTSP 密码。

清理方式：

- 第一次尝试使用 SQL heredoc 清理时因为 shell 引号问题触发事务回滚，未清除业务数据，也未删除设备记录。
- 随后改用 Node/pg 在事务中逐表 `delete`，避免 `truncate ... cascade` 误伤 `devices` 表。
- 清理后保留：
  - 云端 `.env`
  - PostgreSQL 连接
  - 第三方模型、天气、Tavily 配置
  - 真实树莓派设备记录 `edge-042714be475b91da`
- 清理后删除：
  - users / families / family_members / elder_profiles
  - device_bindings / binding_codes / device_tokens
  - cameras / camera_secrets
  - events / media_assets
  - care_preferences / care_cards / model_generation_jobs / content_sources / content_recommendations
  - app_messages / notification_deliveries / scheduler_runs / audit_logs / device_config_versions

清理后状态：

- `users=0`
- `families=0`
- `device_bindings=0`
- `cameras=0`
- `events=0`
- `care_cards=0`
- `app_messages=0`
- `notification_deliveries=0`
- `devices=1`
- 设备 `edge-042714be475b91da` 的 `family_id=null`，可重新认领。

公网新用户路径：

- 使用公网地址 `http://139.196.223.58`。
- 使用全新手机号注册，注册后 `families_before_count=0`，确认新用户没有继承旧家庭。
- 创建家庭：
  - `id=10`
  - `name=妈妈的家`
- 写入老人资料：
  - `display_name=母亲`
  - `relationship=母亲`
  - `city=上海`
  - 老人手机号已写入
  - 家里电话当前为空
- 认领盒子：
  - 清理后 `claimable_before_count=1`
  - 使用当前临时设备码认领成功
  - 绑定设备：`edge-042714be475b91da`
  - `device_bindings=1`
- 从备份恢复并通过 API 重建 2 路摄像头：
  - `id=1`，`name=冰箱上`
  - `id=2`，`name=智能摄像头2`
  - 两路均有 stream config，密码已设置。

盒子同步验证：

- 通过公网 App API 登录新手机号后轮询：
  - 家庭：`妈妈的家`
  - 设备绑定：`active`
  - 摄像头 1：`online / synced`
  - 摄像头 2：`online / synced`
- 树莓派无需人工 SSH 修改即可从云端重新拉取新家庭的摄像头配置并回传状态。

实时画面验证：

- 通过公网 App API 创建播放会话。
- 请求 `/api/v1/video/cameras/1/stream.mjpg?playback_ticket=...`。
- 返回：
  - HTTP `200`
  - `content-type=multipart/x-mixed-replace`
  - 首包 `1435 bytes`
- 结论：新用户绑定后的云端实时画面链路可用。

关怀与通知验证：

- 当前家庭今日关怀卡接口正常：
  - `GET /api/v1/app/care-cards/today?family_id=10`
  - 返回关怀卡，图片 URL 已生成。
- 关怀历史当前有 2 张：
  - `2026-07-09`
  - `2026-07-10`
  - 不是同一天重复，数据库唯一约束正常。
- App 消息：
  - `count=1`
  - 类型：`care_card`
  - 状态：`open`
- 通知投递：
  - `count=1`
  - 状态：`app_message_only`
- iOS push token：
  - `0`
  - 符合当前未接 iOS 原生 App 和 APNs 的阶段。
- scheduler 状态：
  - `enabled=true`
  - 最近后台任务均为 `succeeded`
  - 跳过原因：`daily_not_due_or_already_sent`

页面级验证：

- 使用公网 H5、新账号 token 和 iPhone 宽度 `393px` 验证：
  - `index.html?app=1`
  - `monitor.html?app=1`
  - `notifications.html?app=1`
  - `companionship.html?app=1`
  - `privacy.html?app=1`
- 所有页面：
  - `bodyWidth=393`
  - `innerWidth=393`
  - 无横向溢出。
- 验证时为了避免实时视频和图片资源拖住 `networkidle`，页面检查拦截了图片 / MJPEG 资源；因此控制台中出现的资源失败来自测试拦截，不代表线上页面脚本错误。
- 实时画面已通过接口首包单独验证。

当前结论：

- 破坏性完整新用户公网路径已跑通。
- 当前云端不再是旧演示家庭数据，而是通过新手机号重新完成家庭、老人资料、设备认领、摄像头配置和盒子同步后的真实状态。
- 当前新家庭 ID 为 `10`，真实盒子已重新绑定，2 路摄像头在线同步。

仍未完成：

- HTTPS。
- iOS 原生 App / WebView 壳。
- iOS push token 登记和 APNs 真推送。
- 正式短信验证码。
- 正式出厂二维码和一次性认领凭证生产流程。
- 家里电话仍为空；如果比赛演示需要点击“打电话”直接拨家里电话，需要在家人资料里补充家里电话。
- 长时间稳定性报告仍未形成，下一步应至少跑 24 小时观察。

下一步建议：

1. 先补 HTTPS，或明确比赛演示阶段继续使用 HTTP。
2. 若继续做 iOS，先做 WebView 壳和登录态保持，再接 push token 登记。
3. 继续观察树莓派 24 小时：心跳、配置同步、实时帧中继、CPU / 温度 / 内存、摄像头断流恢复。
4. 比赛前补一份演示账号、设备码、摄像头状态、关怀卡片和通知链路自检清单。

## 77. 2026-07-10 App 设备解绑与重新认领

本轮把设备绑定从单向认领补成可反复测试的完整生命周期。

- 新增 `DELETE /api/device-bindings/{binding_id}`，仅家庭所有者可执行。
- App 设备绑定页新增“解绑”入口和二次确认。
- 解绑不清除盒子 Wi-Fi，不停止盒子连云；设备身份和序列号继续保留。
- 解绑会撤销旧家庭绑定、清空设备和设备令牌的家庭归属，并移除该盒子在旧家庭下的摄像头接入配置。
- 历史事件和关怀记录不随解绑删除，但旧家庭不再接收该盒子的新配置、画面和事件。
- 设备心跳和同步不再信任盒子自行上报的 `family_id`，避免解绑后被旧配置自动绑回。
- PostgreSQL 新增 `003_device_transfer.sql`，允许设备令牌在未绑定家庭时继续有效。
- 自动化已覆盖绑定、解绑、旧家庭编号回传防恢复和新家庭重新认领。
- 本地真实页面已验证：解绑后设备卡片消失、主按钮恢复为“绑定盒子”、盒子出现在可认领列表，页面无脚本报错。

## 78. 2026-07-10 云端测试环境重置

用户确认当前没有需要保留的重要业务数据后，云端按“保留设备身份、清空业务数据”的口径完成重置。

重置前备份：

- 数据库：`/opt/gohome/backups/db-before-device-transfer-20260710-102335.sql.gz`
- 应用文件：`/opt/gohome/backups/app-before-device-transfer-20260710-102335.tar.gz`

云端部署与迁移：

- 已应用 `003_device_transfer.sql`。
- `gohome-app.service` 为 `active`，存储仍为 PostgreSQL。
- 云端真实 App 解绑验证成功：旧绑定撤销，2 路摄像头接入配置移除，盒子恢复为可认领。

重置后数据：

- `users=0`
- `families=0`
- `device_bindings=0`
- `cameras=0`
- `events=0`
- `care_cards=0`
- `app_messages=0`
- `devices=1`

保留设备：

- `device_id=edge-042714be475b91da`
- `serial_number=GH-475B91DA`
- `family_id=null`
- `status=online`
- `claim_status=claimable`

清空后连续观察设备 `last_seen_at` 仍在更新，证明 App 解绑和业务清理不会影响盒子的 Wi-Fi 与主动连云。下一次测试可直接从全新手机号注册开始，再依次创建家庭、填写老人资料、绑定盒子和配置摄像头。

## 79. 2026-07-10 新用户、事件证据与登录稳定性复验

本轮从 section 78 的空业务环境重新执行完整 App 路径。

新用户路径：

- 测试手机号注册后家庭数量为 0，只能进入家庭配置流程。
- App 页面顺序通过：`手机号创建 -> 创建妈妈的家 -> 填写妈妈资料和联系电话 -> 发现 GH-475B91DA -> 绑定盒子 -> 添加摄像头`。
- 从私有备份恢复 2 路摄像头接入信息后，树莓派首次轮询即回传两路 `online / synced`。
- 首页配置向导解除，显示盒子已同步和 2 路摄像头；守护页两路真实画面均加载。

规则和事件：

- App 规则页的人形、跌倒、活动和火焰开关均可操作。
- 云端目标规则版本与树莓派已应用版本一致。
- 树莓派生成明确标记为测试的 `manual_test` 事件，并通过真实上传队列发送截图和事件。
- 修复上传代理本地摄像头 ID 到 App 摄像头 ID 的映射，并让云端媒体记录从摄像头配置反推出家庭和设备归属。
- 复验事件使用本地 camera 14，正确映射到 App camera 15；媒体资产记录包含 `family_id=10`、真实设备 ID 和约 73KB JPEG。
- App 事件列表显示测试事件，事件详情证据图为 640x360，图片请求无错误。

实时帧清理：

- 发现 `GOHOME_LIVE_FRAME_UPLOAD_ENABLED=1` 与 `live_relay` 重复，导致 2 万余条定时帧上传任务和近千条无事件媒体记录。
- 树莓派已关闭定时帧永久上传并保留实时中继，清除 20143 条 `live_frame` 队列任务。
- 云端清除 956 条未关联事件的媒体记录和文件，事件证据资产保留。
- `.env.example` 默认改为 `GOHOME_LIVE_FRAME_UPLOAD_ENABLED=0`。

登录稳定性：

- 新增 `004_app_sessions.sql`，App session 持久化到 PostgreSQL。
- 数据库仅保存 token SHA-256 摘要，不保存明文 token。
- 同一个登录 token 在 `gohome-app.service` 重启前后访问用户、事件接口均返回 200。
- 服务重启后事件证据 JPEG 仍返回 200，登录状态不再因进程重启丢失。

## 80. 2026-07-10 RTMPose 跌倒误报根因修复与实机回归

本轮先恢复并确认原 YOLO + RTMPose 路线，再针对历史高分记录做实拍复验。数据库历史记录中存在大量 `pose_fall_score >= 0.78`，抽查发现空客厅沙发、远处半身和正常坐姿曾被判为跌倒。

根因：

- RTMPose 原逻辑只要求 4 个可见关键点即可计算跌倒分数，低置信家具骨架也能进入告警判断。
- 正面坐姿的肩髋区域宽度刚好超过高度 `1.45` 倍时，旧通用宽高比规则会覆盖真实竖直躯干方向并返回 `lying`。
- RTMLib 0.0.15 的人体检测偶发返回空内部结果，单帧会报 `'NoneType' object is not subscriptable`。
- MJPEG 长连接存在时，systemd 默认会等待 90 秒关闭服务，影响部署和恢复速度。

实现：

- `RtmposeAnalyzer` 新增：
  - `pose_fall_min_confidence=0.36`
  - `pose_fall_min_visible_keypoints=8`
  - `pose_fall_min_core_keypoints=2`
- 每组骨架新增 `raw_fall_score`、`fall_evidence_eligible` 和 `fall_quality`；顶层新增 `raw_pose_fall_score` 与 `pose_fall_rejected_low_quality`。
- 低质量高分骨架保留关键点和原始分数，但移除 `fall_candidate` 行为提示，不进入正式跌倒候选。
- 肩、髋均可见时优先使用肩髋中点方向判断卧姿；通用宽高比仅用于肩髋不完整的骨架。
- RTMPose 特定 `NoneType` 瞬态错误只重试一次，成功时标记 `pose_inference_retried`，二次失败仍返回 `error`。
- `install-systemd-service.sh` 增加 `TimeoutStopSec=15`，盒子现有服务已应用。
- `eval-fall.py` 报告增加原始姿态跌倒分数和低质量拒绝数量。
- `verify-vision-pipeline.py` 增加低质量骨架、受控重试、正面坐姿和横向跌倒姿态回归。
- 在 Git 忽略的 `data/eval/samples/fall/home_false_positive` 中保存 6 张家庭私有实拍负样本及 manifest；样本已同步到测试 Pi，但不提交到代码仓库。

树莓派最终验证：

```text
家庭负样本: TN=6, FP=0, errors=0
UR Fall: TP=8, TN=12, FP=0, FN=0, errors=0
两路实机并发预览: 20/20 ready, errors=0, fall_candidates=0
```

同时通过：

- `verify-vision-runtime.py --require-yolo --require-pose --smoke`
- `verify-vision-pipeline.py`
- `verify-fall-rule-engine.py`
- `verify-alert-dedupe.py`
- `run-vision-smoke-eval.sh`

当前仍保持 `fall_detection_enabled=0`。本轮证明的是已知家庭误报被压制且现有 UR Fall 小样本召回未下降，不代表医疗级准确率。正式开启前仍需当前家庭视角的安全模拟跌倒正样本和更长时间正常活动负样本。

## 81. 2026-07-10 人形假置信度修复与公开样本扩展

用户在空客厅的人形预览中看到 3 个 50%-71% 的人体候选。复查原始结果后确认，这些框来自 `presence_skin` 和 `presence_upperbody` 的肤色/Haar 启发式增强，电视柜、沙发和窗户纹理被错误框选；页面又把启发式分数包装成“增强置信度”并计入 `person_count`，造成了模型识别出 3 个人的假象。

实现修复：

- `person_yolo.py` 默认关闭 `presence_classical_enhancement_enabled`；需要回归经典候选时必须显式开启。
- YOLO 低置信候选继续保留真实 `model_confidence`，删除固定增加 `0.24` 的分数包装。
- 肤色/Haar 候选改为输出 `candidate_score`、`confidence_kind=heuristic` 和 `confidence=null`，不再伪装模型置信度。
- `pipeline.py` 和 `pose_rtmpose.py` 增加 `person_evidence_eligible`。启用姿态复核但没有可信骨架时，经典候选不能进入人数和后续人形规则。
- 人形算法预览加入 RTMPose；低质量姿态仍可留作调试数据，但不能确认人体或参与跌倒 refinement。
- 管理台只绘制可信姿态骨架；低置信 YOLO 显示“等待骨架复核”，经典启发式显示“候选分，不作为人数和模型置信度结论”。
- `verify-vision-pipeline.py` 增加经典增强默认关闭和显式开启的回归断言。

实机回归：

```text
空客厅摄像头连续 5 次: person_count=0, people=[], pose_count=0, pose_status=ready
有人摄像头连续 5 次: person_count=1, pose_status=ready/cached
```

新增公开样本工具：

- `import-gmdcsa24-sample.py` / `run-gmdcsa24-eval.sh`：从 MIT 许可的 GMDCSA24 仓库抽取 Subject 1 的跌倒和 ADL 视频帧，覆盖睡床、阅读、坐姿、走动和弯腰。
- `import-wikimedia-indoor-negatives.py` / `run-wikimedia-person-negative-eval.sh`：通过 Wikimedia Commons API 下载 5 张人工确认无人的室内负样本，并在 manifest 保存每张图片的来源和许可。
- `vision_dataset_catalog.json` 已登记 GMDCSA24 与 Wikimedia 室内负样本。
- UR Fall 导入范围扩大到 8 组跌倒和 10 组 ADL，共 88 帧。
- 公共数据 runner 新增 `--eval-only`，盒子只同步抽帧和 manifest 时可以直接复验，不要求重复下载原视频。
- `eval_vision_common.py` 新增并记录姿态跌倒阈值、姿态质量门控参数；YOLO 输入尺寸默认改为 416，修复离线评测默认 `pose threshold=0.90 / imgsz=960` 与盒子生产配置 `0.78 / 416` 不一致的问题。
- `run-vision-smoke-eval.sh` 优先使用 `.venv-pi`，修复盒子系统 Python 缺少 OpenCV 时的假失败。
- 原始公开视频、抽帧、manifest 和家庭私有画面均位于 `edge-agent/data/`，已被 Git 忽略；仓库只提交导入器、runner、catalog 和评测说明。

树莓派评测：

```text
Wikimedia 空室内: count=5, TN=5, FP=0, errors=0
GMDCSA24: count=22, TP=6, FP=4, TN=10, FN=2, precision=0.60, recall=0.75, FPR=0.2857
UR Fall 扩展: count=88, TP=29, FP=0, TN=56, FN=3, precision=1.00, recall=0.90625, FPR=0
```

以上结果统一使用盒子当前生产参数：`yolo11n.pt / confidence=0.20 / imgsz=416 / pose_fall_threshold=0.78 / pose quality=0.36, 8 visible, 2 core`。GMDCSA24 的 4 个误报全部为正常睡床，说明单帧横向骨架无法区分“睡在床上”和“跌倒在地”；其 2 个漏报以及 UR Fall 的 3 个漏报来自人体大部分出画或骨架证据不足。后续不能靠继续放宽或收紧一个单帧阈值解决，必须进入视频时序和场景区域阶段：

1. 实现视频序列 evaluator，验证活动/站坐、快速下降、低位持续和恢复状态。
2. 增加床、沙发和非地面区域配置，区分正常卧躺与异常卧地。
3. 扩充出画、遮挡、低光、轮椅、躺沙发和当前家庭视角安全模拟跌倒样本。
4. 正式跌倒通知继续保持 `fall_detection_enabled=0`，直到上述时序和区域规则完成并经过连续观察。

## 82. 2026-07-10 自动场景图与正式跌倒时序评测

本轮纠正了“让用户手动画床/沙发区域”的产品方向。普通 App 不新增画区域流程，仍只要求用户选择安装房间；盒子利用现有 YOLO 模型自动识别固定家具，管理台展示识别结果仅用于研发复核。

实现：

- `person_yolo.py` 将 YOLO 类别扩展为 `person + chair + couch + bed + dining_table`，在同一轮推理中输出 `scene_objects`，避免重复加载和重复推理。
- 新增 `scene_context.py`：
  - 按 `camera_id` 跟踪场景对象。
  - 默认 2 帧稳定、12 帧容错。
  - 合并同类重叠或包含框。
  - 床和沙发输出为 `normal_lying_surface`。
  - 姿态或倒地人框与区域重合超过 28% 时写入场景上下文。
- `pipeline.py` 输出 `scene_objects / scene_zones / normal_lying_zones / scene_map_status`，并把场景上下文同步到人框、骨架和算法解释。
- 场景对象进入跟踪前，会按“场景框被人框/骨架覆盖的面积比例”过滤；覆盖达到 55% 的家具候选不写入场景图，修复 UR Fall `fall-05` 中蜷缩人体被误识别为沙发的问题。
- `rule_engine.py` 新增站坐历史和下降转变：
  - 无近期站坐证据的单帧卧姿为 `awaiting_transition`。
  - 稳定床/沙发中的卧姿为 `normal_lying_zone`。
  - 正式确认需要水平目标匹配、至少 0.12 的归一化垂直下降以及运动或更大位移证据。
  - 下降过程确认后可沿同一倒地目标继承，后续持续帧不重复要求下降。
  - 任何倒地候选帧都不能覆盖原来的站坐基线。
- `worker.py` 在正式跌倒规则开启时每轮运行姿态；普通活动观察仍按间隔采样。
- `console.js / styles.css` 在跌倒预览叠加自动场景虚线框，并显示 `自动场景 / 时序状态 / 复核进度 / 持续时间`。
- `main.py` 对 `/favicon.ico` 返回 204，清理管理台浏览器中唯一的 404 控制台噪声。
- 新增 `eval-fall-sequences.py`，按 `sequence_id` 和帧时间顺序运行 DetectAgent + RuleEngine，报告序列级 TP/FP/TN/FN。
- GMDCSA24 和扩展 UR Fall runner 同时输出单帧候选报告与正式时序报告。

回归结果：

```text
合成场景：重复沙发框合并为 1 个稳定区域，卧姿正确标记 normal_lying_zone
规则状态机：无转变高分卧姿不报警；站坐到下降连续 2 帧可确认；沙发卧姿始终不报警
真实沙发帧：3 人，1 人横躺；沙发区域 2 帧稳定，卧姿区域重合 88.8%，事件 0
GMDCSA24 序列：TP=2, FP=0, TN=5, FN=2, precision=1.0, recall=0.5
UR Fall 序列：TP=8, FP=0, TN=10, FN=0, precision=1.0, recall=1.0
```

管理台浏览器验证：

- 跌倒页显示 `自动识别沙发` 虚线框。
- 元数据正确显示自动场景、时序状态、复核帧和持续时间。
- 页面无横向溢出，实时识别正常。
- 真实运行服务保持 active，正式配置仍为 `fall_detection_enabled=0`。

当前限制：

- 公开数据集结果只用于工程回归；UR Fall 当前 18 段和 GMDCSA24 当前 9 段规模仍不足以宣称产品级准确率。
- GMDCSA24 的两个漏报说明人体出画和稀疏抽帧仍是主要召回瓶颈，下一步需要更密视频采样和当前家庭视角的安全模拟跌倒。
- 自动场景图当前为进程内缓存，服务重启后约两帧自动重建；普通用户不需要也不应该手动配置区域。
- 正式跌倒通知继续保持关闭，待长期家庭负样本与安全模拟正样本验收后再由用户确认开启。

## 83. 2026-07-10 守护规则默认全开启

用户最终确认新用户、新家庭和新盒子的产品默认状态应为全部守护能力开启。该产品决策取代此前算法安全验证阶段临时保持 `fall_detection_enabled=0` 的部署口径，但不改变跌倒事件的严格确认条件。

实施要求：

- App 服务 `defaultRules()` 中离线、黑屏、无活动、人形、跌倒、活动状态、烟火和通知全部为 `true`。
- 真实云端运行规则和树莓派本地规则同步迁移为全开启，不能只修改前端勾选状态。
- 跌倒正式事件继续要求“站坐基线 -> 下降 -> 低位持续”，并排除自动识别的床/沙发正常卧躺区域。
- 服务测试增加八个默认开关的显式断言，后续改动如误将任一能力默认关闭，测试必须失败。
- 云端 PostgreSQL 通过现有 `care_rules` 表持久化 `edge_rules` 配置；用户主动关闭某项能力后，服务重启不得把它错误恢复为默认值。
- 修复 App 守护设置中人形检测与长时间无人联动开关调用不存在的 `isSupported()` 导致点击报错；统一使用页面现有的盒子能力判断函数。
- 修复规则自动保存与手动保存并发时后一次修改被忽略的问题；保存过程中产生的新修改会排队再次提交，避免页面开关与云端/盒子实际值不一致。

实际验收：

- 本地 `npm test` 和相关 JavaScript 语法检查通过。
- 本地 App 在 390px iPhone 视口下八项开关均显示开启，可点击保存，无横向溢出、控制台错误或页面异常。
- 云端服务部署后连续重启两次，八项规则仍全部开启，证明 PostgreSQL 规则持久化生效。
- 云端 App 页面显示“已同步到家庭盒子 / 已生效”，期望规则版本与盒子已应用版本一致。
- 树莓派本地数据库八项开关均为 `true`，配置同步与实时帧中继代理均正常运行。
- 两路云端摄像头保持 `online / synced`，公网 MJPEG 请求均返回 `200`、`cloud_relay` 和有效首帧；事件接口保持可读。

## 84. 2026-07-10 家庭级规则、生产事件闭环与公网验收

家庭规则与权限：

- 新增 `family_rules` 运行态，PostgreSQL 继续使用现有 `care_rules` 表，以每个家庭一条 `edge_rules` 记录持久化。
- `/api/rules`、`/api/rules/runtime`、设备配置版本和规则版本均按家庭计算；盒子只收到自身绑定家庭的摄像头和规则。
- 家庭记录持久化唯一 `created_by_user_id`；即使历史数据里存在多个 owner，也只有创建者可以修改规则或解绑盒子。
- `PUT /api/rules` 增加家庭创建者权限校验；成员 GET 返回 `can_edit=false`，App 将全部规则输入和保存按钮切为只读。
- 新家庭八项守护能力仍默认全部开启。
- 删除 `normalizeDb()` 中把最后活跃无家庭账号自动加入所有现有家庭的旧兼容迁移，修复重启后的越权继承风险。

解绑与清理：

- 解绑设备时旧设备 token 改为 `revoked`，不再保留“无家庭但有效”的 token。
- PostgreSQL 导出不再把无家庭 token 回落到默认家庭。
- 验收数据清理补齐设备、绑定、token、心跳和家庭规则，解决 PostgreSQL 外键阻止清理的问题。

真实算法事件闭环：

- 新增 `edge-agent/scripts/emit-public-fall-validation.py`。
- 在真实树莓派上使用 UR Fall `fall-01` 序列和当前生产参数运行 YOLO、RTMPose、自动场景图及跌倒时序状态机。
- 前两帧保持 `clear`，随后进入 `awaiting_transition / suspect / confirming`，第 8 帧在持续约 5.2 秒后进入 `confirmed` 并生成 `fall_candidate`。
- 本地事件 ID 为 `1870`，云端事件 ID 为 `128`；事件明确标记 `public_dataset_replay / test_event=true`。
- 证据 JPEG 约 20KB，可通过鉴权播放；App 事件页可见，消息和通知投递记录均能关联该事件。
- 上传队列最终为 `pending=0 / failed=0 / completed=158`。

公网新用户验收：

- 新增 `scripts/verify-cloud-onboarding.js` 和 `npm run verify:cloud-onboarding`。
- 阿里云 PostgreSQL 环境通过 13 项：新账号隔离、创建家庭、老人资料、八项默认规则、成员只读、绑定临时盒子、摄像头配置下发、App 在线同步、家庭规则隔离、解绑、旧 token 失效和完整清理。
- 验收使用临时家庭和设备，不解绑真实树莓派；结束后临时用户、家庭、设备、token、心跳和规则均已删除。
- 最终真实家庭仍为“妈妈的家”，2 路摄像头 `online / synced`，规则全开且版本一致，公网 MJPEG 均返回 `cloud_relay`。
- 本地闭环最终为 `37 passed / 0 warnings / 0 failed`；本地 JSON 明确作为开发副本，真实盒子以云端家庭规则为准。

按用户决定，本轮不等待 24 小时观察报告。下一步进入 HTTPS 和 iOS 壳，不继续扩展无关 H5 页面。

## 85. 2026-07-11 SQLite 稳定性、自动保留和 App 清理闭环

运行观察发现：

- 云端连续约 13 小时无重启、5xx、调度失败和数据库异常。
- 盒子连续约 14 小时无自动重启，双路中继、配置同步和上传队列正常，观察期没有新增真实误报。
- 盒子 `agent.db` 达到 4.9GB，快照目录达到 9.7GB，数据目录约 15GB。
- Python 的 SQLite 连接上下文只提交事务但不关闭连接，进程数据库句柄在 50-100 个间波动。

实现：

- `Storage.connect()` 改为显式关闭的上下文管理器，连接设置 30 秒超时和 `busy_timeout`。
- 初始化启用 WAL、`synchronous=NORMAL` 及清理所需索引。
- 新增 `prune_runtime_history()`，按依赖顺序清理候选、规则评估、检测结果和快照。
- 新增 `cleanup-runtime-history.py` 与 `verify-runtime-retention.py`。
- worker 每小时分批自动清理，默认普通数据保留 24 小时；异常被记录但不结束工作线程。
- 配置同步支持 `cleanup_runtime_history` 维护命令，执行结果回传云端。
- 云端新增 `POST /api/v1/devices/current/cleanup`，仅家庭创建者可调用。
- `GET /api/app/device` 返回存储容量、保留时长、维护结果和管理权限。
- App 摄像头与盒子管理页新增存储状态、容量进度和“立即清理”按钮。

实机清理结果：

```text
event_candidates deleted: 102815
rule_evaluations deleted: 145886
detection_results deleted: 138183
snapshots deleted: 138182
snapshot files deleted: 138182
events retained: 1870
SQLite integrity_check: ok
agent.db: 4.9GB -> 1.2GB
snapshots: 9.7GB -> 2.0GB
disk usage: 45% -> 24%
```

清理后验证：

- 两路摄像头继续 `online / synced`。
- 两路公网 MJPEG 均返回 `200 / cloud_relay`，5 秒分别收到约 460KB 和 433KB。
- 上传队列 `pending=0 / failed=0 / completed=158`。
- 八项守护规则保持全开，事件 1870 条完整保留。
- App 清理命令已实测下发、执行并回传 `completed=true`。
- 数据库句柄通常为 0，短时事务结束后立即回落；worker、视频中继和配置同步持续运行。
- 本地闭环 `37 passed / 0 warnings / 0 failed`，App 服务、配置同步、保留策略和现有边缘测试全部通过。

## 86. 2026-07-11 腾讯云 HTTPS 空库部署

- 腾讯云实例：Ubuntu 24.04，4 核 4GB；现有 `www.ai2shx.club` Next.js 服务继续使用 3000 端口。
- GoHome 独立部署在 `/opt/gohome/app`，监听 `127.0.0.1:8788`，由 `gohome-app.service` 管理。
- 新装 PostgreSQL 16，创建独立 `gohome` 数据库和角色；API 密钥从旧环境迁移，但业务数据未迁移。
- Nginx 新增 `gohome.ai2shx.club` 独立站点，支持 MJPEG 长连接和关闭代理缓冲。
- Let’s Encrypt 证书已签发并启用自动续期，证书当前有效期至 2026-10-09。
- 新增 `GOHOME_SEED_DEFAULT_DATA=0`，生产空库不再生成旧演示管理员和默认家庭。
- 空库确认：`users=0 / families=0 / cameras=0 / events=0 / assets=0 / care_cards=0`。
- 树莓派云端地址已切换为 `https://gohome.ai2shx.club`，配置同步使用 HTTPS 且无错误。
- 真实盒子已在腾讯云登记为 `claimable`，当前数据库保持 `devices=1 / bindings=0`。
- `verify:cloud-onboarding` 在腾讯云通过 13 项并自动清理临时账号、家庭、设备、规则和 token。
- 真实用户已完成局域网绑定和两路摄像头配置；阿里云 `gohome-app.service` 已停止并禁用，旧目录和数据库暂时保留。

最终云端事件验收：

- 使用 UR Fall 公开序列通过生产 YOLO、RTMPose、自动场景和跌倒时序状态机生成本地事件 `1871`。
- 事件截图上传成功，上传队列最终为 `pending=0 / failed=0 / completed=160`。
- 腾讯云生成 1 条 `fall_candidate` 高危测试事件、2 个媒体资产、2 条 App 消息/通知投递记录。
- 事件摘要为“算法闭环验收：公开样本命中疑似跌倒”，载荷明确包含 `test_event` 和 `public_dataset_replay`，未冒充家庭真实告警。
- 两路摄像头继续保持 `online / synced`，配置同步与实时帧中继无错误。

## 87. 2026-07-11 局域网安全绑定实现

已实现：

- 生产环境增加 `GOHOME_ALLOW_CLOUD_DEVICE_CLAIMS=0`，全局待认领设备列表返回空数组，序列号/设备 ID 直接认领返回 403。
- 云端一次性绑定凭证改为 16 位加密随机十六进制值，默认 5 分钟有效，使用后立即失效。
- 绑定凭证只允许家庭创建者签发。
- 云端 token 兑换增加跨家庭占用校验，设备仍绑定其他家庭时返回 409。
- App 绑定页删除设备码输入和“云端发现”，改为“搜索并绑定盒子”。
- H5 顶层导航到 `http://gohome.local:8711/pair`；盒子自动向 `https://gohome.ai2shx.club` 兑换 token，并回跳 App。
- 盒子增加 `/api/lan/discovery` 和 `/pair`，校验固定云端回跳 origin 与启动后 15 分钟配对窗口。
- 配置同步、实时视频中继和事件上传改为优先使用本地签发的 `device_token.txt`，不再被静态 bootstrap token 覆盖。
- 生产盒子启用 `GOHOME_REQUIRE_ISSUED_DEVICE_TOKEN=1`；未绑定时配置同步、视频中继和上传代理保持未配置状态，避免空家庭同步和数据库外键错误。
- 云端解绑后旧 token 保持撤销；再次局域网配对成功会安全覆盖盒子本地旧 token。

本地验证：

- JavaScript 与 Python 语法检查通过。
- `npm test` 通过，新增高熵凭证、单次消费、跨家庭防抢绑和生产环境关闭全局认领断言。
- `npm run verify:local-loop`：`37 passed / 0 warnings / 0 failed`。

待实机验证：

1. 部署腾讯云和树莓派，生产环境设置 `GOHOME_ALLOW_CLOUD_DEVICE_CLAIMS=0`。
2. 重启盒子开启 15 分钟窗口，从空账号走注册、家庭、老人资料、局域网绑定和双摄像头配置。
3. 验证规则、双路视频、事件、关怀卡和 App 解绑后重新绑定。

## 88. 2026-07-11 iOS 壳第一阶段

已完成：

- 现有 `GoHomeShell.xcodeproj` 默认入口由局域网开发地址改为 `https://gohome.ai2shx.club/index.html?app=1`。
- SwiftUI 不再让 WebView 覆盖系统安全区；iPhone 16 Pro 模拟器已确认 Dynamic Island 和 Home Indicator 留白正确。
- WKWebView 使用持久化数据存储，支持登录态保存、侧滑返回、内联视频、新窗口接管和 Web 内容进程恢复。
- 导航白名单限制为腾讯云产品域名和 `.local` 盒子；电话、短信和微信 scheme 交由系统打开。
- H5 原生桥增加 `openExternalURL`，陪伴页“发消息”在 iOS 壳中打开微信，电话继续使用 `tel:`。
- 增加本地网络、Bonjour、定位权限文案和 `_gohome._tcp` 服务声明。
- 第一阶段不提前声明 APNs entitlement，避免真机安装被尚未配置的推送 capability 阻塞；确认 Apple Developer 推送权限后再开启。
- 树莓派部署 Avahi `_gohome._tcp:8711` 广播；Mac `dns-sd` 已发现“回家守护盒子 - gohome”。
- 新增 1024px AppIcon：深绿家庭轮廓与暖色爱心，并在 iPhone 16 Pro 模拟器主屏验证显示正常。
- 干净 DerivedData 构建通过，未出现 Swift 编译或 asset catalog 警告；本地后端回归继续通过。

待真机：

1. 选择真实 Apple 开发团队和 iPhone，完成自动签名安装。
2. 验证本地网络授权、`gohome.local` 绑定、双路视频、拨号、微信和定位。
3. 确认 Apple Developer/APNs capability 后启用 `GoHomePushEnabled` 并上传真机 push token。

## 89. 2026-07-11 统一视觉感知算法审计与方案验证

本节只记录审计和设计结论，算法实现尚未开始。用户确认三份文档后再进入代码修改。

审计范围：

- 边缘采集：`camera_agent.py`
- worker 调度与落盘：`worker.py`
- 视觉流水线：`vision/pipeline.py`
- 人形与场景：`vision/person_yolo.py`
- 姿态：`vision/pose_rtmpose.py`
- 活动、跌倒、火灾：`vision/activity.py / fall.py / fire.py`
- 自动场景：`vision/scene_context.py`
- 时序规则：`rule_engine.py`
- 事件、上传与存储：`event_agent.py / upload_agent.py / storage.py`
- 云端事件、模型、调度和通知：`local-app-server/server.js`
- App 事件列表、详情与确认：`events-live.js / event-detail-live.js`

确认可复用能力：

- 双路摄像头、实时流和算法抽帧已经解耦。
- YOLO 人形和家具、RTMPose 骨架、画面质量、活动、跌倒、火灾已由同一 VisionPipeline 编排。
- 已有自动床/沙发区域、姿态质量门控、站坐到下降的跌倒时序、恢复状态和事件去重。
- 已有事件截图、上传队列、幂等事件上传、云端消息和 App 确认/误报反馈链。

确认的主要缺口：

1. 当前 worker 以 5 秒间隔逐路处理，每轮都保存 JPEG、snapshot、detection_result 和 rule_evaluation。
2. 当前姿态只能粗分 lying、standing_or_sitting、seated_or_half_body、upper_body、low_body，不能满足站坐蹲躺独立片段。
3. 当前没有跨帧稳定 person track ID，姿态缓存主要按摄像头组织。
4. 当前 no_person 是单摄像头边缘状态，不是家庭级跨摄像头 12 小时未见老人。
5. 当前事件生命周期只有 acknowledged/resolution，不能表示云端复核中、已确认、已拒绝和降级。
6. 当前通知幂等到事件级，调度器重复扫描时不会形成每分钟提醒记录。
7. 旧摄像头 observation log 可能继续保持 open，需要随摄像头停用或删除关闭。

真实数据审计：

- 当前盒子规则：两路摄像头、5 秒采样、八项守护能力开启。
- 审计时数据库约有 `snapshots=29569 / detection_results=29567 / rule_evaluations=29806 / event_candidates=15809`。
- `no_person` aggregated 候选约 13216 条，说明按采样生成候选的数据粒度过细。
- 当前仍存在属于旧摄像头的开放 no_person observation，最长超过 57 小时，验证了摄像头生命周期清理缺口。
- 盒子进程约 38% CPU、温度约 56℃、系统可用内存约 6.3GB；当前阶段不需要先购买 AI HAT+。

模型配置与能力探测：

- 腾讯云配置 `Qwen/Qwen3.5-27B + SiliconFlow chat/completions`，Key 已配置。
- 使用公开跌倒证据图实际发送 `image_url` 请求，HTTP 200；模型返回 `person_count=1 / posture=lying / emergency=false / confidence=0.95`。
- 结果证明该配置具备图片理解能力，也证明单帧只能判断姿态，不能代替边缘端的跌倒时序和持续时间。
- `wan2.7-image` 与阿里云 Key 已配置，继续仅用于关怀卡生图。

回归验证：

- `verify-vision-pipeline.py` 通过：人形、姿态缓存、姿态质量、活动、火灾、自动场景均正常。
- `verify-fall-rule-engine.py` 通过：低分视觉候选、无下降等待、确认、恢复、床/沙发抑制和跌倒全帧姿态采样均正常。
- `verify-alert-dedupe.py` 通过：事件去重和火灾 1800 秒频控正常。

最终技术决策：

- 不推倒现有 YOLO、RTMPose、自动场景和跌倒状态机。
- 新增统一人体轨迹、姿态片段、姿态因子图、家庭存在状态和云端复核层。
- 把“每帧记录”改成“内存时序 + 状态片段 + 代表证据”。
- 快速跌倒/强火灾由边缘端先进入 verifying 事件；云端模型负责复核和解释，不成为网络单点故障。
- 普通姿态不进入事件列表，只进入时段和每日活动摘要。
- 管理台最终合并为一个视觉感知页面，内部代码仍保持三层模块边界。

下一步状态：等待用户确认 PRD、Plan、Implement 后，按 Plan 14.19 阶段 1 开始实现。

## 90. 2026-07-11 统一视觉感知阶段 1 与测试证据隔离

本轮已完成 Plan 14.19 阶段 1，未开始姿态细分类、云端图片复核和 12 小时家庭级未见老人。

核心实现：

- 新增 `vision/temporal.py` 和 `TemporalObservationEngine`，使用人框 IoU 与归一化中心距离为同一摄像头的人体分配稳定 `c{camera}-p{sequence}` track ID。
- 每路摄像头保留最多 48 条结构化时序观察，不在新模块中复制原始大帧。历史中包含人数、track、姿态、运动、安全候选和代表快照引用。
- SQLite 新增 `presence_sessions`，有人时合并同一片段，无人、摄像头离线、停用或删除时关闭。
- worker 新增启动对账，自动关闭已不存在摄像头的历史开放 observation/presence 片段。
- 摄像头生命周期清理统一重置时序轨迹、previous frame、pose 计数、最新评估、直播上传计时和跌倒/火灾规则状态。
- `no_person / no_motion` 不再先写 `event_candidates` 再标记 aggregated，而是直接更新合并观察日志。

数据集画面根因与修复：

- 旧的公开样本验收会把数据集帧保存为真实摄像头事件证据。
- 云端中继在暂时没有 live frame 时，旧逻辑会无区分选取该摄像头最新 asset，导致公开样本进入 App 实时画面。
- 媒体上传现在明确标记 `live_preview / event_evidence / validation_evidence`，并通过 PostgreSQL `metadata` 跨重启保留分类。
- 摄像头预览仅允许实时内存帧或 `live_preview`；事件证据只在事件详情使用。
- `test_event=true` 的事件不进入用户事件、评估状态、推送、关怀摘要或正式数据迁移。腾讯云旧测试事件和资产已在持久化时清理。
- 同时修复旧测试消息被过滤后、通知投递仍引用已删消息导致的 PostgreSQL 外键失败。

验证结果：

- Mac 本地：`npm test` 通过，本地闭环 `37 passed / 0 warnings / 0 failed`。
- 新增回归：`verify-temporal-observation-engine.py / verify-presence-sessions.py / verify-observation-logs.py` 通过。
- 树莓派：新增回归、视觉流水线、跌倒状态机、火灾去重和上传队列全部通过。
- 真实盒子启动后历史孤儿观察片段从 6 条开放状态清理为 0。
- 真实运行观察 15 秒，`no_person` 与 `no_motion` 候选增长均为 0；上传队列 `pending=0 / failed=0`。
- 腾讯云重启并跨调度周期后无新的 scheduler 外键错误。
- 公网两路 MJPEG 均返回 `cloud_relay`，帧来源为 `live`，未返回 `asset` 或公开数据集证据。

运行状态：两路公网实时中继已恢复。盒子 worker 观察期间曾记录 `192.168.1.5:554` 短时路由不可达，后续 live relay 已恢复两路上传；该类网络波动不转换为长时间未见老人。

下一步：按 Plan 14.19 阶段 2 实现 `standing / sitting / squatting / bending / lying / upper_body / unknown` 细分类和姿态片段状态机。

## 91. 2026-07-11 姿态细分类与 PostureEpisode

本轮完成 Plan 14.19 阶段 2，不改变阶段 1 的媒体隔离、人体轨迹和观察片段边界。

姿态分类：

- 新增 `vision/posture.py` 和 `PostureClassifier`。
- 可解释因子包含躯干相对竖直方向、整体宽高比、膝关节角度、髋膝竖直距离、髋踝紧凑度和膝髋水平展开比。
- 输出新标签 `standing / sitting / squatting / bending / lying / upper_body / unknown`。
- 每组 pose 新增 `posture_confidence / posture_factors / posture_classifier_version / posture_legacy`。
- 旧的 `standing_or_sitting / seated_or_half_body / low_body` 继续在跌倒分数、活动提示和站坐基线中兼容，不因标签迁移破坏旧数据。
- 蹲姿在弯膝和紧凑度之外要求膝间距相对髋间距明显增大，修复正面坐姿被错分为蹲姿。

姿态片段：

- `TemporalObservationEngine` 会将人框与最佳重叠骨架合并，把姿态和姿态置信度写入同一 track。
- 候选姿态需要置信度至少 0.40、最少 2 个样本且持续 3 秒才稳定。
- 短暂标签变化不立即关闭已稳定片段；新标签达标后才以 `posture_changed` 关闭原片段。
- track 超过 TTL 未见时以 `track_expired` 关闭；摄像头停用、删除、离线和历史孤儿状态使用统一运行态清理。
- SQLite 新增 `posture_episodes`，存储 camera、track、posture、起止时间、确认时间、样本数、平均/最高置信度、场景区域、代表快照和关闭原因。
- 新增本地研发查询接口 `/api/posture-episodes`；普通 App 尚不展示原始姿态片段。

验证：

- `verify-posture-classifier.py`：站、坐、蹲、弯腰、躺、上半身和未知样本通过。
- `verify-posture-episodes.py`：3 秒前不开片段、稳定后开启、抖动不切换、稳定切换和 track 过期关闭通过。
- 原视觉流水线、跌倒状态机、火灾去重、上传队列、配置同步、保留策略和 App 服务回归全部通过。
- 真实树莓派检测到 `sitting` 片段，也检测到 `lying + couch-1 + normal_lying_zone=true` 片段，沙发卧躺未生成跌倒事件。
- UR Fall 单帧：`TP=29 / FP=0 / FN=3`；时序：`TP=8 / FP=0 / FN=0`。
- GMDCSA24 单帧：`TP=6 / FP=4 / FN=2`；时序：`TP=2 / FP=0 / FN=2`。数值与改造前一致，说明新姿态标签未降低既有跌倒回归结果。
- 公网两路 MJPEG 仍为 `cloud_relay / live`，上传队列无 pending 或 failed。

当前边界：

- 这是可解释几何 baseline，不是已训练的医疗动作识别模型。
- 多人交叉、长时间遮挡或大幅移动仍可能产生 track ID 切换，后续数据集需单独评估 ID switch。
- 普通姿态片段仅用于活动摘要和安全时序，不直接生成用户告警。

下一步：进入 Plan 14.19 阶段 3，实现姿态因子图、快速跌倒证据束和 180 秒非床/沙发地面卧躺事件。

## 92. 2026-07-11 姿态因子图、长时间倒地与证据包

本轮完成 Plan 14.19 阶段 3，未开始云端多模态复核、家庭级 12 小时未见老人和每分钟持续提醒。

核心实现：

- 新增 `vision/pose_factor_graph.py` 和 `PoseFactorGraphEngine`，按稳定人体 track 维护最近 20 秒直立基线和非正常区域连续躺卧状态。
- 每个 track 输出当前姿态与置信度、姿态几何因子、归一化中心、下降位移、水平距离、运动分数、人体宽高比、场景区域、躺卧起点与持续时长。
- 快速跌倒因子由近期直立、明显下降、空间一致、低位/横卧、运动和非床/沙发条件加权形成；该结果作为原 `RuleEngine` 的附加证据，原 YOLO、RTMPose、下降状态机、多帧确认和恢复逻辑继续保留。
- `prolonged_floor_lying` 只在同一 track、`lying`、姿态置信度达标、非床/沙发、连续 180 秒且未恢复时创建；同一连续片段只创建一个候选，恢复后再次发生才创建新候选。
- `TemporalObservationEngine` 的环形历史增加紧凑 track 姿态记录，并可生成最多 3 张代表快照、姿态变化序列、时间窗口和 track ID 的证据包。
- 事件证据升级为同时包含 `pose_factor_graph` 和 `temporal_evidence_bundle`；App 事件列表与详情增加“长时间倒地”标签、解释和处理建议。
- worker 首次启动时关闭旧进程遗留的开放 observation、presence 和 posture 状态，姿态片段关闭原因记录为 `worker_restart`，防止服务重启后旧片段伪持续。

验证结果：

- 本地新增 `verify-pose-factor-graph.py`：直立到倒地因子分数 `0.92`，181 秒非正常区域躺卧命中，床/沙发抑制和两帧恢复通过。
- 本地新增 `verify-prolonged-floor-rule.py`：首次事件、同片段去重、恢复后再次事件、安全事件分类和证据包传递通过。
- 姿态分类、姿态片段、人体轨迹、presence、observation、上传队列、上传代理、配置同步、保留策略、事件去重、原跌倒状态机、视觉流水线和 `npm test` 全部通过。
- 真实树莓派部署后两路摄像头保持 `online / synced`，实时中继为两路 `8 FPS`，配置同步无错误，上传队列仅有 `completed=163`，无 pending 或 failed。
- UR Fall 单帧 `TP=29 / FP=0 / FN=3`，序列 `TP=8 / FP=0 / FN=0`。
- GMDCSA24 单帧 `TP=6 / FP=4 / FN=2`，序列 `TP=2 / FP=0 / FN=2`。结果与阶段 2 一致，本阶段未降低既有基线。
- 实机重启验证：旧开放 track `c23-p41` 被关闭并标记 `worker_restart`，新进程只保留当前真实观测片段。

当前边界：

- 因子图是可解释规则 baseline，不是医疗级跌倒诊断；GMDCSA24 序列仍有 2 个漏报，阶段 7 需结合更多完整视频序列和困难负样本改进。
- 当前 `prolonged_floor_lying` 创建一条安全事件并进入通知链；“同一事故每分钟提醒直到 App 确认”属于阶段 5 的 SafetyIncident/投递状态改造，尚未实现。
- 当前证据包已准备好，但尚未发送给 Qwen 多模态接口；云端复核状态、严格 JSON 校验、超时和重试属于阶段 4。

下一步：进入 Plan 14.19 阶段 4，实现云端图片复核任务、严格 JSON 结果、超时重试和事件复核状态，不改变边缘端离线可告警能力。

## 93. 2026-07-11 云端视觉复核任务与 Qwen 实测

本轮完成 Plan 14.19 阶段 4，不改变边缘跌倒、长时间倒地和火灾事件的离线可告警能力。

任务与事件状态：

- 复用已有 PostgreSQL `model_generation_jobs`，新增 `purpose=vision_event_verification` 任务契约；metadata 保存事件、媒体、尝试次数、最大次数和下次重试时间。
- `fall_candidate / prolonged_floor_lying / fire_candidate` 在事件图片存在且模型已配置时自动创建任务。
- 设备事件先完成事件、App 消息和通知投递入库，再通过后台任务异步复核；模型请求不在设备上传请求的关键路径上。
- 事件 `payload.verification` 状态覆盖 `pending / verifying / retrying / confirmed / rejected / uncertain / failed / unavailable`。
- `confirmed` 表示图片支持边缘提醒，`rejected` 表示图片暂未看到明确紧急线索，`uncertain` 表示证据不足；三种状态均不自动删除、确认或隐藏原始事件。

模型输入与输出：

- 输入包含当前事件证据图片、事件类型、房间、边缘规则、指标、flags、`PoseFactorGraph` 和 `temporal_evidence_bundle`。
- 图片以请求时内存构造的 data URL 发送，任务表不保存图片 base64，不保存 API Key。
- 严格 JSON 字段为 `person_count / posture / surface / emergency / confidence / reason / suggested_event_type`。
- 姿态、表面和事件类型使用固定枚举；额外字段、缺字段、非法枚举、非布尔 emergency、人数或置信度越界全部视为失败并重试。
- 默认请求超时 30 秒，最多 3 次，退避为 5 秒、30 秒和 120 秒；最终失败后事件继续以边缘判断展示。
- `wan2.7-image` 未参与安全事件复核。

App 与运维：

- 事件列表显示“云端正在复核证据”“支持这条提醒”“暂未看到明确紧急线索”或“证据不足”。
- 事件详情对 pending/retrying 状态最多轮询 10 次，不刷新整页、不影响用户确认和误报操作。
- 新增运维状态和手动执行接口 `/api/v1/internal/vision-verifications/status` 与 `/run`，仅 ops 权限可访问。
- ops 模型能力列表新增 `vision-event-verification`，普通用户不能查看或修改模型 Base URL、Key 和提示词。

验证：

- 模拟模型第一次返回额外字段时被严格拒绝，任务进入 `retrying`；第二次返回合法 JSON 后进入 `confirmed`，尝试次数为 2。
- 模拟任务验证图片以 `image_url` 传入、结构化上下文包含姿态因子、任务请求不含 API Key、任务 metadata 可通过 PostgreSQL 导出和恢复。
- 新增 `verify-vision-verification-live.js`，使用 UR Fall 公开样本调用真实 `Qwen/Qwen3.5-27B`。
- 真实模型一次成功：`person_count=1 / posture=lying / surface=floor / emergency=true / confidence=0.92 / suggested_event_type=fall_candidate`。
- 腾讯云生产探针任务一次成功；测试事件、测试媒体和对应复核任务已清理，且导出层已统一排除验证事件关联 job。
- `npm test` 通过；完整本地产品闭环继续为 `37 passed / 0 warnings / 0 failed`。
- 腾讯云 `gohome-app.service` 保持 active，`/health` 返回 200，部署后无新增服务错误。

当前边界：

- 当前模型实际收到一张事件当前截图和多帧结构化摘要。时序证据包记录的开始、转折、当前最多 3 张快照中，只有事件当前截图已上传到云端；多图上传尚未完成。
- 单图视觉复核不能证明跌倒过程或 3 分钟持续时间，相关时间事实仍以盒子时序状态机为准。
- 复核结果尚未形成独立 `SafetyIncident` 生命周期，也未实现每分钟提醒直到 App 确认；这属于阶段 5。

下一步：进入 Plan 14.19 阶段 5，实现家庭级 `FamilyPresenceState`、12 小时长期未见、设备离线抑制和同一事故持续提醒投递。

## 94. 2026-07-11 FamilyPresenceState、长期未见与 SafetyIncident

边缘存在上报：

- SQLite 新增 `camera_presence_status()` 聚合查询，不新增逐帧业务表。
- 每路摄像头随 10 秒配置同步上报最近观测、历史最后见人、近一小时观察样本、人物样本、预期样本和覆盖率。
- 覆盖率按实际样本数除以规则采样间隔推导的预期样本数，上限为 1；查询使用 `julianday` 正确处理 ISO 时区时间。

家庭存在状态：

- 云端摄像头 metadata 持久化 presence，家庭 metadata 持久化 `FamilyPresenceState`。
- 有效观察要求至少一台启用摄像头，且全部启用摄像头 `online / synced`、报告不超过 120 秒、近一小时覆盖率至少 0.50。
- 家庭最后见人时间取所有摄像头最大值，任一路见人立即重置未见时长。
- 摄像头离线、同步异常、报告过期或覆盖不足时状态为 `suspended`，不创建长期未见事件。
- 家庭关怀配置 metadata 支持 `presence_monitoring.mode=away/travel/hospital/paused`、`enabled=false` 或 `paused_until`，状态为 `paused` 时不计时。
- 默认阈值为 43200 秒；达标后只创建一条家庭级 `long_absence`，再次见人后自动解决为 `person_seen_again`。

SafetyIncident 与提醒：

- 新建 `fall_candidate / prolonged_floor_lying / fire_candidate / long_absence` 自动带 incident ID、active 状态、开始时间和提醒计数。
- 不回填历史事件，避免部署时把旧未确认事件批量转成提醒洪峰。
- 初始事件消息作为第一次告知；事故满 1 分钟后，调度器按 `event_id + minute bucket` 创建幂等提醒消息和投递记录。
- 同一分钟重复调度不会增加 reminder_count 或重复消息。
- App 标记已处理或误报后，incident 立即变为 acknowledged 并停止提醒；长期未见重新见人时变为 resolved。

验证：

- 边缘同步测试验证 presence 字段、人物样本和最后见人时间。
- 云端测试使用 60 秒阈值验证 long_absence 创建、同分钟提醒去重、见人自动解决、travel 暂停抑制和事件确认停止提醒。
- 本地 App 服务测试通过，完整产品闭环继续为 `37 passed / 0 warnings / 0 failed`。
- 真实树莓派两路覆盖率均为 `0.8194`；最近人物样本分别正常上报，配置同步无错误。
- 腾讯云家庭状态为 `observing / coverage_valid`，`valid_camera_count=2`，默认阈值 43200 秒；未生成误报 long_absence。
- 部署后历史 `incident-reminder` 数为 0，证明旧事件未被批量迁移；实时中继恢复两路 8 FPS 且无错误。

当前边界：

- APNs 尚未接入，持续提醒当前写入 App 消息和 notification delivery 模拟记录；iOS 系统通知需真机 token 和 Apple capability。

下一步：进入 Plan 14.19 阶段 6，合并视觉感知管理页面，并在普通 App 展示家庭存在状态、观察覆盖与暂停守护设置。

## 95. 2026-07-11 统一视觉感知页面与家庭存在交互

家庭存在 API：

- 新增 `GET /api/v1/families/:id/presence-state`，返回家庭存在状态、有效摄像头数量、最后见人时间、长期未见阈值、暂停模式和每路摄像头观察状态。
- 每路摄像头统一计算 `observation_valid / observation_reason / report_age_seconds`；离线、配置未同步、报告超过 120 秒或覆盖率低于 50% 分别返回明确原因。
- `valid_camera_count` 改为真实有效摄像头数量，不再因任一路无效而把所有摄像头都显示为无效。
- 新增 `PUT /api/v1/families/:id/presence-monitoring`，只有家庭创建者可以修改 `active / away / travel / hospital / paused / paused_until`。
- 通用 care preferences 接口检测到普通成员修改 `presence_monitoring` 时返回 403，避免权限绕过。

普通 App 守护页：

- 重构 `monitor.html + monitor-live.js`，首页状态改为家庭级“家里此刻”，展示有效画面、最近见到人和平均观察覆盖。
- 双路摄像头使用紧凑两列布局，每路显示真实视频、名称、观察有效性、当前姿态、覆盖率和最后见人时间。
- 10 秒数据轮询只更新文字与状态，不销毁或重建视频节点，避免画面周期性等待第一帧。
- 待确认提醒只展示 `payload.incident.status=active` 的 SafetyIncident，历史未确认事件不再冒充正在持续的紧急事故。
- 家庭状态与单路卡片共用服务端有效性结果，不再出现家庭提示覆盖不足、单路却显示有效观察的矛盾。

外出与暂停守护：

- 新增 `presence_settings.html` 和 `presence-settings-live.js`，并只在“我的”保留一个入口。
- 支持正常守护、临时外出、旅行、住院或陪护、暂停到指定时间；定时暂停要求恢复时间晚于当前时间。
- 页面展示明确选中态；受邀成员可查看当前模式但所有输入和保存按钮保持只读。
- 页面和守护页均使用 `viewport-fit=cover` 与统一安全区变量，390px 视口无横向溢出。

统一视觉感知研发页：

- `detection.html` 从“检测说明”升级为“视觉感知”，同页保留摄像头切换、真实视频流、人体框、抓帧和规则证据。
- 新增当前姿态、track、自动场景区域、姿态持续时间、火灾状态与分数、姿态因子图和云端视觉复核摘要。
- 历史候选超过 10 分钟后明确标记为“历史记录”，不再显示为当前需要确认。
- 规则证据对象和数组经过结构化摘要，不再把 `[object Object]` 暴露到页面。
- 删除 `assets/images/elderly-alone.jpg` 默认画面引用；没有实时帧或真实抓拍时显示空状态，公开数据集不能进入摄像头画面。
- 普通守护页不提供工程模型详情入口，内部 YOLO、姿态、时序和云端复核继续保持代码模块边界。

验证：

- `npm test` 通过，家庭创建者修改、普通成员 403、暂停与恢复状态均有服务端回归。
- `npm run verify:local-loop` 为 `37 passed / 0 warnings / 0 failed`。
- Chrome 390x844 验证守护、暂停设置和视觉感知页面，三页 `scrollWidth === clientWidth`，无横向溢出。
- 自动检查确认页面不再引用数据集占位图，不包含 `[object Object]`，定时暂停图标不再溢出。

腾讯云部署与验证：

- 实现文件同步到 `/opt/gohome/app`，服务端脚本语法检查通过，`gohome-app.service` 重启后为 active，`/health` 返回 PostgreSQL store。
- `https://gohome.ai2shx.club` 已发布新的守护、外出暂停和视觉感知页面，Nginx 返回 200。
- 家庭创建者账号线上验证 `away -> active` 成功，最终恢复 `mode=active`；家庭状态为 `observing`，`valid_camera_count=2`。
- Chrome 390x844 线上实测守护页两张视频均为真实 `640x360` 帧，`scrollWidth === clientWidth`，active incident 为 0，页面无脚本错误。
- 线上视觉页源码不再引用 `elderly-alone.jpg`，公开样本不能作为实时画面回退。

当前边界：阶段 6 已完成本地与腾讯云闭环。下一步进入阶段 7 数据集扩充、困难负样本标注和骨架时序模型评估；在替换现有可解释状态机前必须先达到序列级回归指标。

## 96. 2026-07-12 数据就绪审计与跌倒基线历史修复

数据就绪审计：

- 新增 `audit-vision-dataset-readiness.py`，递归读取本地 JSONL manifest，统计图片、唯一序列、正负序列、来源、缺失文件、姿态类别、火灾时序、数据划分和跨 split 泄漏。
- 新增 `verify-dataset-readiness-audit.py`，使用临时数据验证序列聚合、正负分类、姿态标签和 readiness gate。
- 当前原始评测集为 `132` 张图片、`131` 条 manifest 记录；复用已有 GMDCSA24 原视频生成密集帧后，本地为 `240` 张图片、`239` 条记录，但唯一跌倒/ADL 序列仍为 `27`，没有把重复抽帧冒充新增序列。
- 跌倒规则回归 gate 通过：正序列 `12`、负序列 `15`、公开数据源 `2` 个。
- 产品试点 gate 未通过：家庭困难负样本只有 `6` 张，低于当前审计门槛 `50`。
- 姿态片段、火灾时序和可训练时序模型 gate 未通过：缺少按完整序列标注的六类姿态、火灾正负视频及序列隔离的 train/validation/test。

评测改造：

- `eval-fall-sequences.py` 增加逐帧 diagnostics，保存 person/pose 数、fall/pose 分数、目标、下降距离、运动分数、场景抑制、阶段和候选类型。
- `import-gmdcsa24-sample.py` 新增 `--temporal-samples`，从已经下载的原视频均匀生成有序密集帧；默认稀疏导入行为保持兼容。
- `run-gmdcsa24-eval.sh` 默认保留原 22 帧单帧评测，同时使用每视频 12 帧的密集集合运行正式时序评测。

算法根因与修复：

- 原规则会在每个非跌倒帧覆盖 `fall_upright_states`，跌倒过程中的弯腰或半坐帧会替换真正的站立/坐姿基线，导致最终躺倒下降距离不足。
- 现在只把 standing/sitting 及兼容旧标签写入基线，弯腰、蹲姿、低位和上半身不再作为直立基线。
- 每路摄像头保留 20 秒、最多 24 个基线目标，并记录各自观测时间；跌倒目标从横向距离匹配的历史中选择垂直下降最明显的可解释基线。
- 内部时间字段不进入事件 JSON，事件证据仍保持可序列化。
- 新增回归验证：站立后经过弯腰帧，强跌倒帧仍必须进入 suspect 并保留 transition confirmed。

结果：

- GMDCSA24 密集 9 段：`TP=3 / FP=0 / TN=5 / FN=1 / recall=0.75`，改造前为 `TP=2 / FN=2 / recall=0.50`。
- UR Fall 18 段保持 `TP=8 / FP=0 / TN=10 / FN=0`。
- 家庭困难负样本保持 `TN=6 / FP=0`。
- 剩余 GMDCSA24 `fall-01` 在一次强 lying 帧后连续两帧 person/pose 均为 0，之后只恢复低置信水平人框；证据不足以满足多帧正式事件，不通过单帧报警消除该 FN。
- 所有 edge `verify-*.py` 功能回归通过；Mac `verify-vision-runtime.py` 仅报告本地 `.venv` 含 Homebrew 路径，不属于算法失败，树莓派部署后使用 `.venv-pi` 单独验收。
- `npm test` 通过。

树莓派部署：

- 使用 `deploy-to-pi.sh` 同步代码，明确排除 `.venv*`、设备数据、日志和环境变量，没有覆盖盒子运行数据。
- Pi `.venv-pi` 验证 Python aarch64、Torch CPU、Ultralytics、YOLO 模型、ONNX Runtime、RTMLib 和 2 个 RTMPose checkpoint 全部通过。
- Pi 上 `verify-fall-rule-engine / verify-pose-factor-graph / verify-dataset-readiness-audit` 通过。
- `gohome-edge-agent.service` 重启后 active；配置同步和实时中继 agent 均 running，无 last_error。
- 两路摄像头 `online / synced`，观察覆盖率约 `0.836`，实时中继 `8 FPS`。
- 腾讯云家庭状态保持 `observing`，`valid_camera_count=2 / camera_count=2`，说明算法代码更新未破坏 App、云同步和长期未见判断。

当前结论：现有样本够当前比赛版本做规则回归和演示，不够训练或替换骨架时序模型。样本集暂时冻结；下一步优先观察真实运行事件、误报反馈和姿态片段统计，没有新困难场景前不继续扩充公开样本。

## 97. 2026-07-12 树莓派统一实时感知页面

产品结构：

- `edge-agent/admin/algorithms.html` 删除“预览算法”下拉框和 `algorithmDemo` 演示卡，只保留摄像头选择、抓帧和唯一真实视频画面。
- 侧栏算法开关继续作为研发配置入口；YOLO、RTMPose、场景、时序、跌倒和火灾保持独立代码模块，但不再拆成多个产品预览模块。
- 右侧统一显示当前感知目标、检测帧、人物数、骨架数、场景目标、火灾状态、画面状态、最近安全记录和生活观察。

统一分析与叠加：

- `/api/cameras/{camera_id}/analysis/live?algorithm=unified` 启用姿态分析并允许复用可信骨架缓存，不改变正式 worker 和事件规则路径。
- 实时叠加层同时消费 `people / poses / scene_objects / scene_zones / fall_candidate / fire_candidate / black_screen`。
- 前端按 track ID 或目标框重叠把人物和姿态合并，显示“人物编号 · 中文姿势 · 置信度”；没有稳定 track 时使用当前画面序号。
- 场景目标支持床、沙发、椅子、餐桌和电视；稳定多帧目标显示“场景已学习”，当前帧目标显示模型置信度。
- 跌倒、火灾和摄像头异常在同一画面右上角显示状态，正常时显示“安全状态正常”。

质量与验证：

- `run-vision-smoke-eval.sh` 通过：人物、姿态、跌倒、火灾视觉和火灾事件均无回归错误。
- JavaScript `node --check`、Python `py_compile` 和 `git diff --check` 通过。
- 代码通过 `deploy-to-pi.sh` 部署，未覆盖 Pi `.venv-pi`、设备数据、日志或环境变量；`gohome-edge-agent.service` 重启后 active。
- Playwright 使用真实 Pi 页面验证：算法下拉 `0`、演示卡 `0`、实时状态“实时识别中”、请求参数为 `algorithm=unified`、控制台错误 `0`、`scrollWidth === viewportWidth`。
- 实机画面识别到沙发、电视和椅子并正确叠加；正常卧躺位于沙发区域时场景关系仍参与跌倒误报抑制。

当前边界：统一页展示的是当前实时分析结果；姿态持续时间、完整 track 生命周期和云端复核结论仍以 worker 持久化数据和正式事件链为准，不能用一次预览结果替代正式告警判断。

## 98. 2026-07-12 屏幕内容抑制、跌倒语义与视频流恢复

屏幕内容抑制：

- `VisionPipeline` 在场景跟踪形成稳定 `tv` 区域后，对人物框和姿态框计算目标区域被电视区域包含的比例。
- 包含比例至少 `0.86` 且目标面积不超过电视区域 `0.90` 的结果记录到 `screen_content_suppressed`，并在人物计数、姿态、活动、跌倒和时序前移除。
- 真实人物站在电视前但身体明显超出屏幕区域时不会被过滤；回归测试同时覆盖“屏幕人物被过滤”和“真实人物保留”。

姿态与跌倒：

- 统一页不再依据原始单帧 `fall_candidate` 显示跌倒，只读取规则评估的 `fall_stage`。
- `standing / sitting / lying / upper_body` 始终作为姿态展示；只有 `suspect / confirming / confirmed` 显示跌倒过程。
- `awaiting_transition` 表示只有当前低位或卧姿、缺少此前站坐和快速下降证据；`normal_lying_zone` 表示床或沙发正常卧躺，两者均不显示为跌倒事件。
- 修复 `_refine_people_with_pose()` 场景字段覆盖：人物框或骨架任一命中床/沙发，合并结果都保留 `normal_lying_zone=true` 和对应场景信息。

视频流恢复：

- `CameraAgent.mjpeg_frames()` 不再因一次 `read/retrieve` 失败结束 HTTP 视频连接，而是释放并重新打开 RTSP capture。
- 近黑帧始终不覆盖上一有效预览；连续达到确认帧数后主动释放并重开 RTSP。正式黑屏或遮挡仍由独立 worker 的质量分析产生事件，不依赖 MJPEG 预览是否保持最后有效帧。
- 管理页在视频请求仍然失败时使用 `0.8s` 起步、最大 `8s` 的指数退避自动重连。
- 新增 `verify-camera-stream-resilience.py`，验证读取失败后重开、短暂黑帧保持和后续有效帧恢复。

验证：

- `verify-vision-pipeline.py` 新增电视屏幕、真实人物保留和沙发区域合并回归，全部通过。
- `verify-fall-rule-engine.py`、完整视觉 smoke、UR Fall 18 段和 GMDCSA24 密集 9 段回归通过。
- UR Fall 保持 `TP=8 / FP=0 / TN=10 / FN=0`；GMDCSA24 保持 `TP=3 / FP=0 / TN=5 / FN=1`。
- 真实 Pi 连续 5 轮页面采样均为 `black_screen=false`、亮度约 `129`、`fall_stage=clear`、视频 `640x360`、控制台错误 `0`。
- 本地误报事件 `#1877` 已通过事件接口标记为 `false_positive`；活跃候选查询新增 JSON resolution 过滤，不再把误报显示为最近安全记录。

## 99. 2026-07-12 姿态人体一致性、云端复核反馈与黑屏恢复

姿态误检根因与修复：

- 空沙发场景中 RTMPose 产生了 `confidence=0.329 / body_aspect=3.375` 的横向假骨架；原管线已经标记 `person_evidence_eligible=false`，但仍把候选放入 `analysis.poses`，导致缓存、计数和前端继续绘制。
- `RtmposeAnalyzer` 现在只把通过姿态质量门的候选写入 `poses`；低置信、关键点不足或核心点不足的候选写入 `rejected_poses`，跌倒分清零并记录拒绝阶段和原因。
- `VisionPipeline` 增加第二层人体一致性门：结合真实 YOLO 人框、稳定家具区域、骨架置信度、人体宽高比和家具重叠，拒绝无人物对应的超宽家具骨架。
- 拒绝骨架会同步从短时缓存清除，不进入活动时序、人物补全、跌倒规则和页面；前端 `snapshotPoses()` 仍做防御性过滤，旧数据也不会绘制。
- 回归覆盖空沙发假骨架、真实 YOLO 对应躺姿和无 YOLO 但高置信遮挡坐姿。UR Fall 保持 `TP=8 / FP=0 / TN=10 / FN=0`，GMDCSA24 保持 `TP=3 / FP=0 / TN=5 / FN=1`。

云端模型复核反馈：

- 腾讯云新增 `GET /api/v1/device/vision-verifications`，按盒子设备令牌和设备 ID 过滤事件，只返回该设备的复核状态、结果、模型、重试次数和脱敏错误。
- 树莓派新增 `/api/cloud-verifications` 代理；本地管理台“云端模型复核”面板展示 pending、verifying、retrying、confirmed、rejected、uncertain、failed 和 unavailable。
- 真实空沙发截图完成 Qwen 复核：`person_count=0`、`posture=unknown`、`surface=sofa`、`emergency=false`、`confidence=0.95`、`suggested_event_type=none`，云端决策为 `rejected / downgrade`。
- 首次真实调用暴露视觉复核独立 30 秒超时，生产环境已设置 `GOHOME_VISION_VERIFICATION_TIMEOUT_MS=120000`；任务随后一次成功。API Key 不进入接口、页面或日志。

视频黑屏恢复：

- MJPEG 连续读取到近黑解码帧时始终输出上一有效帧；达到确认帧数后主动重开 capture，避免黑图进入浏览器。
- 启动阶段尚无有效帧时不发布黑图，先重连等待有效帧。
- `verify-camera-stream-resilience.py` 覆盖一次读取失败、连续 5 张黑帧、第二次重连和恢复帧，确认黑帧全部被抑制。

实机验收：

- 树莓派 camera 23 连续 20 条分析均为 `person_count=0 / pose_count=0 / fall_candidate=false / black_screen=false`，假骨架只在诊断拒绝列表中。
- Chrome 实机页面为 `0 人 / 0 组骨架`，骨架 SVG 线条数为 0，云端复核显示“已排除”和 95% 置信度，控制台错误为 0。
- 连续 15 秒浏览器像素采样平均亮度为 `122.8-125.4`，视频保持 `640x360`，未出现黑帧。
- 树莓派 `gohome-edge-agent` 与腾讯云 `gohome-app` 均为 active，部署后日志无新增 error、read failed 或 near-black 记录。

## 100. 2026-07-12 云端 SafetyIncident 事件编排

状态机：

- 视觉安全事件创建后 incident 初始状态为 `verifying`；长期未见等不依赖视觉模型的安全事件直接进入 `confirmed`。
- 模型结果聚合为 `confirmed / rejected / uncertain`，并把每次迁移记录到 `incident.transitions`，包含来源、时间、触发 event ID 和复核状态。
- 历史 `active` 状态继续允许持续提醒，避免升级后旧事故停止工作。

复核消息：

- confirmed 创建 `incident-verification-{incident_id}-confirmed` 高优先消息和幂等 notification delivery。
- rejected 先归档原始告警和分钟提醒，再创建“刚才的异常已经排除”说明消息；原始事件和证据仍保留。
- uncertain 或模型最终失败创建“这条异常需要你确认”高优先消息，边缘事件不会因模型失败消失。
- 验证事件不创建 App 消息，避免真实模型探测污染用户消息列表。

跨摄像头关联：

- 同一家庭、同一事件类型、默认 45 秒窗口内且尚未结束的事件共享 incident ID。
- 主事件保存 `source_event_ids / source_camera_ids`；关联摄像头事件保留独立截图和模型任务，但不重复创建初始消息和投递。
- App 家庭事件列表只展示主事件；按单摄像头筛选时仍可查看该摄像头的原始证据事件。
- 聚合规则为 confirmed 优先，其次 uncertain/failed/unavailable，再次 verifying，只有全部 rejected 才排除。

确认与提醒：

- 分钟提醒只由 incident 主事件生成，避免两个摄像头产生双倍提醒。
- 用户确认任一关联事件时，所有同 incident 事件统一 acknowledged，关联开放消息归档，持续提醒停止。
- long_absence 自动恢复继续进入 resolved，不与人工 acknowledged 混用。

验证：

- `npm test` 和完整 `verify-local-app-server.js` 通过，覆盖模型二次重试确认、复核结果消息、幂等投递、跨摄像头去重、主事件列表、全 incident 确认和 PostgreSQL 导出恢复。
- 腾讯云真实空沙发验证事件初始为 verifying，Qwen 返回 `person_count=0 / emergency=false / confidence=0.95 / suggested_event_type=none` 后自动转 rejected。
- 云端任务记录 `orchestration_status=rejected`、状态迁移来源为 `vision_verification`；验证事件的 `orchestration_message_id` 为空，证明没有生成用户消息。
- 腾讯云 `gohome-app.service` 保持 active，部署后无新增服务错误。

## 101. 2026-07-12 猫狗独立识别与安全链路隔离

边缘识别：

- `person_yolo.py` 在现有 YOLO11 单次推理中增加 COCO `cat=15 / dog=16`，返回独立 `pets / pet_count / pet_types`；人物、宠物和家具仍由一次模型调用完成。
- 宠物对象显式标记 `person_evidence_eligible=false / pose_eligible=false / fall_evidence_eligible=false`，不进入人物补全、RTMPose、活动历史、跌倒候选或 PresenceSession。
- `pipeline.py` 对宠物单独执行稳定电视区域抑制，并关联沙发、床、椅子等稳定场景；输出宠物信息但不改变 `person_count`。

持久化与云端：

- DetectionResult 的 `objects` 和置信度摘要新增猫狗目标、边界框、场景关系和宠物置信度；完整 analysis 继续原样留存。
- 事件 evidence 新增 `metrics.pet_count` 和 `objects.pets`，不把宠物写入人物或跌倒候选。
- 云端视觉复核上下文新增完整 `objects`；默认 Qwen 提示明确猫狗不计入 `person_count`，宠物在地面、床或沙发上不能作为人物跌倒证据。

研发管理页：

- 统一真实画面新增独立宠物框和“猫/狗 + 置信度 + 场景”标签，目标列表使用“宠”类型，不与人物编号混排。
- 无人物但有宠物时显示“当前未看到人，检测到 N 只宠物”，状态仍为正常感知，不显示安全告警。
- 人数指标调整为“人 / 宠物”，原人物、骨架、场景、火灾和画面状态结构不变。

验证与部署：

- `verify-vision-pipeline.py` 新增单猫隔离、事件证据和电视宠物抑制回归，结果为 `pet_count=1 / person_count=0 / fall_candidate=false`。
- `verify-fall-rule-engine.py`、完整视觉 smoke 和 `npm test` 通过。
- UR Fall 序列保持 `TP=8 / FP=0 / TN=10 / FN=0`；GMDCSA24 密集序列保持 `TP=3 / FP=0 / TN=5 / FN=1`。
- 代码部署到真实树莓派后 `gohome-edge-agent` active，双路实时中继继续运行；camera 23/24 最新落库均包含 `pet_count/pets`，当前空画面为 `person_count=0 / pet_count=0 / fall_candidate=false / model_status=ready`。
- 腾讯云 `gohome-app` 已同步新复核提示和 evidence objects 上下文，服务重启后 active；生产未配置自定义视觉提示词，因此使用本次更新的默认提示。

当前边界：App 尚未收到实时宠物状态，只有安全事件证据和研发管理页已打通。下一步需要在真实猫狗画面上验证置信度、电视抑制、家具遮挡和双摄性能，再把最近宠物活动时间与类型加入设备状态同步和普通 App 家庭状态；本阶段不做宠物身份、健康、情绪或宠物告警。

## 102. 2026-07-12 盒子事件日志与云端 SafetyIncident 对账

事件数据链：

- 腾讯云新增 `GET /api/v1/device/event-log`，使用已签发设备令牌过滤当前盒子的事件，返回 `edge_event_id / cloud event_id / incident / verification / resolution / acknowledged`。
- 树莓派 `UploadAgent` 新增事件日志读取；`GET /api/event-log` 按本地 Event ID 聚合本地事件、event/media upload job 和云端事件。
- 云端收到本地事件后以 `edge_event_id` 回连，上传状态依次为 local_only、pending、uploading、failed 或 cloud_received；联网恢复后沿用原幂等任务，不创建第二条事件。

管理页面：

- 新增 `/admin/events.html` 和主导航“事件日志”。页面只展示正式 Event，不展示普通姿态、PresenceSession、PostureEpisode、observation log 或未晋级候选。
- 每条记录展示盒子触发、证据上传、云端接收和模型/incident 状态四段链路，并显示本地/云端 ID、摄像头、时间、规则证据、模型原因和技术日志。
- 支持按状态和类型筛选、自动刷新、查看本地证据；云端 incident 为最终状态，盒子后台没有“标记已处理/已收到”操作。

误报反馈：

- 云端新增 `POST /api/v1/device/events/{edge_event_id}/feedback`，当前只接受 `false_positive`，并校验事件属于当前设备。
- 误报会给关联事件写入 `manual_feedback.source=edge_admin`，将同 incident 事件统一转为 rejected，记录 transition，归档开放消息和持续提醒，原始事件与截图不删除。
- 盒子新增 `POST /api/events/{local_event_id}/false-positive`；只有云端成功后才更新本地 resolution，避免本地已排除、云端仍告警的状态分叉。

验证与部署：

- `verify-local-app-server.js` 覆盖设备事件日志、edge ID 映射、confirmed 状态和误报后 rejected 状态。
- `verify-upload-agent.py` 覆盖云端日志读取和误报提交；`npm test`、Python 编译、JavaScript 语法、视觉流水线和跌倒规则回归全部通过。
- 使用模拟真实结构的三类事件完成 Chrome headless 1440x1000 和 390x844 页面检查；桌面四段链路完整，移动端无首屏侧栏阻塞。
- 真实树莓派聚合返回 cloud_ok=true；本地 `#1877` 对应云端 `#7`。历史本地 `false_positive` 已通过新接口同步，云端结果为 `resolution=false_positive / incident=rejected`。
- `gohome-edge-agent` 和腾讯云 `gohome-app` 部署后均为 active。

当前边界：盒子事件日志是研发与运维入口，不替代普通 App 事件页。App 后续应读取同一 SafetyIncident 时间线和多摄像头证据；不得根据盒子本地 acknowledged 字段另建用户事故状态。

## 103. 2026-07-12 宠物活动状态上报与 App 守护展示

盒子持久化：

- cameras 表新增 `last_pet_seen_at / last_pet_count / pet_types_json`，通过 `_ensure_column` 兼容现有树莓派数据库。
- `create_snapshot()` 只在 analysis 的 `pet_count > 0` 时更新摄像头宠物状态；空帧不会抹掉最近活动，也不会修改人物字段。
- `camera_presence_status()` 返回宠物最近时间、数量和类型；原 `last_person_seen_at / person_samples / observation_coverage` 计算保持不变。

云端 presence：

- 设备同步接收并规范化每路 `last_pet_seen_at / last_pet_count / pet_types`。
- `familyPresenceState()` 聚合家庭最近宠物活动，默认 `GOHOME_PET_ACTIVITY_RECENT_SECONDS=21600`，输出 `last_pet_seen_at / pet_types / pet_activity_recent`。
- absence 起点、持续秒数和 long_absence 仍只读取人物时间；宠物活动不参与有效观察判断，也不解决长期未见事件。

App 守护页：

- 家庭状态增加“宠物活动”事实，每路摄像头增加宠物活动行。
- 最近宠物时间晚于人物时间且仍在近期窗口时，标题显示“暂未看到老人，检测到猫/狗活动”；正文明确宠物不会重置老人未见计时。
- long_absence 状态下若有近期宠物活动，补充宠物事实但继续要求联系老人。
- 待确认事件兼容新 incident 状态 `verifying / confirmed / uncertain`，不再只识别历史 `active`。

验证与部署：

- `verify-config-sync-agent.py` 创建一张人物快照和一张 `person_count=0 / pet_count=1 / cat` 快照，验证人物样本仍为 1，同时宠物状态正确上报。
- `verify-local-app-server.js` 验证宠物字段进入云端和家庭状态，并断言宠物活动后 `absence_seconds` 仍按两分钟前的人物时间计算。
- `npm test`、视觉流水线、跌倒规则、Python 编译和 JavaScript 语法均通过。
- 树莓派 camera 23/24 当前 coverage 均约 `0.8417`，最近人物数据正常；宠物字段均为 null/0/[]，没有用测试数据污染真实设备。
- 腾讯云 PostgreSQL 两路 cameras metadata 均已收到宠物空状态，服务与盒子均为 active。
- 线上 `monitor.html`、`monitor-live.js` 和样式已更新，并提升到 `20260712-pet-presence-1` 静态资源版本，避免浏览器继续使用旧缓存。

当前边界：代码闭环已完成，但尚未用真实猫狗入镜验证家庭环境置信度。下一步应在当前双摄环境做真实猫、狗、电视宠物画面、家具遮挡和跨摄像头重复命中测试；没有真实命中前不宣称宠物识别已完成现场验收。

## 104. 2026-07-12 App 事件详情统一 SafetyIncident 时间线

前端：

- `event_detail.html` 新增紧凑的“处理进度”区域，不新增独立页面或跨模块跳转。
- `event-detail-live.js` 从 `payload.incident.source_camera_ids / transitions` 和 `payload.verification` 生成真实时间线。
- 首项固定来自当前事件的盒子检测事实；多摄像头佐证只在来源摄像头大于 1 时显示；模型、恢复和用户操作只在对应数据存在时显示。
- 终态映射为 rejected=已排除、resolved=已恢复，并锁定重复处置按钮；confirmed 仍保留用户确认入口。
- 所有动态文案经过 HTML 转义，长文本保持在移动端容器内。

服务端与测试：

- `publicEvent()` 增加 `updated_at`，未改变现有事件、incident、verification 和媒体字段结构。
- `verify-local-app-server.js` 增加详情更新时间和 incident transitions 契约断言。
- `npm test`、`node --check` 和 `git diff --check` 通过。
- 使用 Chrome 以 390x844 渲染包含双摄佐证和云端确认的事件，时间线共 4 项，`scrollWidth=viewportWidth=390`，控制台无错误。

部署：

- 本地 8788 服务重启后健康检查正常，真实历史事件接口可兼容没有 SafetyIncident 的旧记录。
- 腾讯云仅同步 `event_detail.html / event-detail-live.js / server.js`，没有覆盖环境变量、PostgreSQL 数据或其他项目。
- `gohome-app` 重启后 active，`https://gohome.ai2shx.club/health` 返回 `store=postgres`，线上静态资源版本为 `20260712-incident-timeline-1`，近 5 分钟无 warning/error。

当前边界：App 时间线已复用统一事故状态，但当前云端只上传事件主截图；跌倒过程的多帧关键证据仍主要保存在盒子结构化时序包。后续若增加多图证据，应沿用同一 incident，不新增第二套告警生命周期。

## 105. 2026-07-12 跌倒关键帧上传、云端三图复核与宠物误识别修正

盒子上传：

- `enqueue_event_upload_jobs()` 从事件 `evidence.temporal_evidence_bundle.snapshots` 读取代表帧，去除当前主截图重复项后最多追加 2 个 `event_keyframe` 媒体任务。
- 关键帧优先级为 4、主截图为 5、事件 JSON 为 10，确保事件提交时媒体资产已经存在；所有任务使用 snapshot/event 幂等键。
- `UploadAgent` 汇总同事件已完成媒体任务，提交 `evidence_media_assets`，每项包含 asset、before/transition/current 角色、采集时间、snapshot_id 和姿态摘要。

云端复核：

- 媒体上传记录新增 `evidence_frame_role`；事件入口校验资产必须属于当前设备和相同 edge_event_id，防止设备引用其他家庭资产。
- 视觉任务保留主 `asset_id` 兼容字段，同时新增最多 3 个 `asset_ids` 和 `evidence_frame_count`。
- Qwen 请求按时间顺序发送最多 3 个 `image_url`，单图上限 8MB、序列总上限 18MB；结构化上下文新增 evidence_frames。
- `publicEvent()` 返回经过权限控制的 `evidence_media`，App 使用资产播放票据加载，不直接暴露存储路径。

App：

- 事件主截图下新增关键帧横滑区，标签为事发前、姿态变化、当前画面；少于 2 张可用图时自动隐藏。
- 模型 pending/verifying 文案会说明正在复核几张关键帧；原 SafetyIncident 时间线保持不变。
- Chrome 390x844 实测 3 张图 naturalWidth 均为 320，页面 scrollWidth 与 viewportWidth 均为 390，无失败请求。

生产验证：

- `emit-public-fall-validation.py` 新增 `--vision-verification-probe`，从 UR Fall 正序回放中保存 3 张隐藏关键帧。
- 真实盒子 event 1878 上传 asset 8/9/10，云端 event 8 的 Qwen 任务 11 一次成功。
- 模型结果：`person_count=1 / posture=fallen / surface=floor / emergency=true / confidence=0.92`，原因明确为“第一张站立，后续两张倒地于地面”。
- 验证事件未进入正式 PostgreSQL 导出；本地 event、3 张 snapshot、4 个上传任务以及云端 3 个临时媒体文件均已清理。
- 修复 `createIncidentReminderMessage()` 未排除 validation event 的问题，验证事件不再生成每分钟提醒或用户消息。

宠物误识别：

- 现场 camera 24 曾把右侧固定物体以 dog=0.2819 写入近期宠物活动，确认不是实际宠物。
- `pet_yolo_confidence` 默认值从 0.25 提升到 0.40，人物、姿态和跌倒阈值未改。
- 已清空两路摄像头错误宠物状态；后续连续帧均为 pet_count=0，云端字段同步为空。

验证与部署：

- `npm test`、上传队列、UploadAgent、TemporalObservationEngine、视觉流水线、跌倒规则和长时间倒地回归全部通过。
- 树莓派和腾讯云服务均为 active，本地与云端健康检查正常，部署后无 warning/error。

当前边界：三图复核已经证明云端模型能理解跌倒过程，但正式现场报警仍需真实人体安全演练才能验收通知到达、每分钟提醒、App 确认和恢复结束。不得通过制造危险跌倒来测试，应使用安全模拟动作或公开序列探针验证算法。

## 106. 2026-07-12 可信姿态恢复与 SafetyIncident 自动结束

盒子：

- Storage 新增 `latest_unresolved_event()`，只查同摄像头未 acknowledged 且没有 resolution 的 fall_candidate/prolonged_floor_lying。
- `resolve_event_from_edge()` 在本地事件 payload 保存 person_upright_again、resolved_at 和 recovery_evidence。
- `enqueue_event_state_upload()` 创建 priority=8 的 `event_state_upload`，幂等键包含 event/state/resolution，断网后可重试。
- Worker 的恢复判定要求 RuleEngine fall_stage=recovered、person_state=visible，并存在同一 track 连续稳定 standing/sitting 姿态，置信度至少 0.45；squatting 不属于恢复证据。
- 无骨架、人物离场、0.44 站姿不会修改事件；0.82 站姿写入一次恢复任务，后续帧不会重复排队。

云端：

- 新增 `POST /api/v1/device/events/{edge_event_id}/state`，当前只接受 resolved + person_upright_again。
- 接口校验事件属于当前设备、事件类型是 fall_candidate/prolonged_floor_lying，且证据姿态和置信度达标。
- 同一 incident 的所有关联事件统一 acknowledged=true、resolution=person_upright_again、incident.status=resolved。
- 事件 payload 保存 edge_recovery 证据，主事件 transitions 追加 source=edge_recovery；所有关联提醒通过 archiveIncidentMessages 归档。
- 已有 App 确认和 edge false-positive 路径保持不变。

验证：

- `verify-observation-logs.py` 覆盖无姿态、低置信姿态、可信站姿和重复帧幂等。
- `verify-upload-agent.py` 覆盖 event_state_upload 请求契约和完成状态。
- `verify-local-app-server.js` 覆盖弱恢复 400、强恢复 resolved、多次提交单 transition、已有开放提醒归档和验证事件无开放消息。
- 视觉流水线、跌倒规则、长时间倒地和 npm 全量回归通过。
- 腾讯云隐藏生产契约事件：standing=0.44 返回 400；standing=0.82 返回 200，resolution=person_upright_again、incident=resolved、transition=edge_recovery。
- 云端重启后 PostgreSQL 中该测试 edge_event_id 数量为 0；树莓派和腾讯云均 active，近 5 分钟无 warning/error。

当前边界：服务端能够按分钟创建并归档提醒投递，但尚未做 iOS 真机 APNs 到达验收。自动恢复采用保守策略，若老人离开画面或姿态模型暂时失效，系统宁可继续提醒，也不会未经证据自动宣布安全。

## 107. 2026-07-12 iOS 真机启动、性能修复与生产目录清理

iOS 真机：

- macOS 26.5.2、Xcode 26.6 和 iOS 26.5 平台组件已安装，真实 iPhone 完成配对、开发者信任、签名构建和安装。
- App Bundle ID 为 `com.gohome.family`，显示名为“回家”，真实加载 `https://gohome.ai2shx.club/index.html?app=1`。
- 原生壳新增品牌启动状态、失败重试和网页完成后的淡出切换；WKWebView 避免初始化阶段重复加载同一 URL。

性能：

- 修复 HTTPS App 每页错误探测 `127.0.0.1:8711` 的旧逻辑，云端统一使用同源 API，健康检查在会话内短时复用。
- 静态服务按 HTML、版本化脚本样式、字体和图片分别设置缓存；增加 ETag、Last-Modified 和 304，字体不再每页重复下载。
- iOS WebView 使用系统中文字体并关闭高开销背景模糊，保留布局、视频和真实业务功能。
- API 客户端增加按账号隔离的 sessionStorage 缓存。用户、家庭、老人资料和关怀设置缓存 5 分钟，天气和热点缓存 10 分钟，设备和摄像头缓存 10 秒，事件和消息缓存 3 秒，实时快照不缓存；POST/PUT/PATCH/DELETE 成功后清空缓存。

清理：

- 删除零引用的 `connect-live.js / family-live.js / login-live.js` 和 29 张零引用图片，共删除 32 个文件、772 行旧代码。
- 删除 16 个 HTML 中重复维护的内联路由表，只保留 `stitch-app-routes.js` 公共导航，共减少 506 行重复代码。
- 树莓派 `run.sh` 不再把 8 个算法演示视频作为生产启动条件；重启后两路摄像头在线、规则同步正常、云端转发保持 8 FPS。
- 清理 Pi 上 `.env.local.backup-*`、旧源码、测试日志、测试 PID 和临时验证文件，未触碰正式 `.env/.env.local`、数据库、模型和运行日志。
- `deploy-to-pi.sh` 排除评估、样本导入和 QA 回归脚本，并在部署后清理旧 QA 文件；Pi 正式 scripts 目录只保留运行、安装、配网、维护和 `verify-vision-runtime.py`。
- 腾讯云 `/opt/gohome/app/scripts` 只保留 PostgreSQL migration 和 export 工具，App 与 nginx 均保持 active。

验证：

- API 缓存命中与写操作失效使用独立 Node 探针验证。
- `npm test` 和本地完整闭环均通过，闭环结果为 37 passed / 0 warnings / 0 failed。
- 腾讯云首页、守护、事件、陪伴、我的和登录页均只加载公共导航；云端健康检查返回 PostgreSQL store。
- 树莓派 vision preflight 全部通过，服务、配置同步、双摄像头和 live relay 正常。

当前边界：`app-shell.html` 仍被盒子 public pilot 服务引用，`detection.html` 仍由实时画面页引用，纪念模式页面仍是完整互链。它们不是零引用垃圾文件，必须先迁移服务入口和产品导航后再删除。APNs 仍未开启，因此本轮不修改原生推送 entitlement，也不需要重新安装 App。

## 108. 2026-07-16 双摄实时视频 8 FPS 节拍修复

根因：

- 两路摄像头原始子码流均为 `640x360 / 15 FPS`，连续 6 秒实测解码约 `14.4 FPS`，摄像头和树莓派算力不是本次低帧率根因。
- 原 `drop_stale_frames` 会在每次输出前连续 `grab` 4 到 8 帧；盒子后台请求 8 FPS、`drop=8` 时实际只输出约 `1.77 FPS`。
- MJPEG 生成器在完成解码和 JPEG 编码后仍固定休眠完整帧周期，处理耗时没有从节拍中扣除，进一步降低了实际 FPS。

修复：

- 新增基于绝对 deadline 的节拍计算，解码和编码耗时从等待时间中扣除；落后超过一个周期时重置 deadline，避免积累延迟。
- 盒子 `default / detail / monitor / mobile` 四档统一为 8 FPS，低延迟读取统一 `drop=1`。
- 盒子管理后台、算法页、设备流默认参数和 live relay 默认参数统一为 `8 FPS / drop=1`。
- 云端直连盒子的回退转码档位同步为 `8 FPS / drop=1`；公网 App 主路径仍使用盒子上传到云端内存中继，不把实时预览写成永久媒体资产。

验证：

- 新增 `verify-camera-stream-pacing.py`，覆盖处理耗时扣除、落后 deadline 重置和四档配置一致性。
- 原黑屏抑制与断流重连回归继续通过。
- 树莓派双路请求 8 FPS 后实测分别为 `7.69 FPS` 和 `7.68 FPS`。
- 双路云端 live-frame 上传日志稳定为每路约 8 次/秒，HTTP 均返回 200。
- 连续双路中继时 edge-agent CPU 约 `42.5%`（按单核 100% 计）、RSS `609.7MB`、温度 `56.2C`、1 分钟负载 `0.62`，仍有充足余量。

算法边界：实时播放 FPS 与算法推理频率继续分离。视频样本用于跌倒时序评估；常规人物、姿态、场景、火灾候选和云端多帧复核不对播放的每一帧都运行，避免双摄推理抢占视频链路。

## 109. 2026-07-16 路由器重启后的双摄恢复与共享 RTSP 读取

现场根因：

- 盒子地址未变化，仍为 `192.168.1.12`；两台摄像头当前地址为 `192.168.1.3` 和 `192.168.1.11`。
- 路由器重启后，原客厅摄像头地址发生变化；当时盒子和云端只剩 `.3` 一路配置，`.11` 摄像头本身在线但已不在配置列表。
- 旧 `mjpeg_frames()` 为每个观看者单独打开 RTSP。摄像头源为 15 FPS、订阅输出为 8 FPS，读取线程没有持续排空源帧，TCP Receive-Q 曾积压约 77KB，随后出现 HEVC 参考帧错误、30 秒读取超时和云端实时帧中断。
- 盒子管理页仍在轮询已删除的 camera 23，产生连续 404；这不是云端 App 主链路，但增加了无效请求和诊断噪声。

修复：

- `CameraAgent` 新增每摄像头共享读取器：每个物理摄像头只保持一个 RTSP 连接，后台线程按摄像头原始速率持续读取，只缓存最新帧。
- live relay、盒子管理页和其他 MJPEG 订阅共同消费最新帧，不再重复打开 RTSP，也不让未读取帧积压在 TCP 队列。
- 读取失败由共享读取器统一重连；持续近黑帧可请求共享读取器重建连接，原有效帧保留逻辑继续生效。
- OpenCV 的 8 秒打开超时和 5 秒读取超时改为在 `VideoCapture` 创建时传入；FFmpeg 同时设置 `rw_timeout=5s`，避免路由器重启后单次读取阻塞约 30 秒。
- 通过正常 App 配置接口恢复第二路“书房摄像头”，云端 camera 3 同步为盒子 local camera 25；原“冰箱上”保持 cloud camera 2 / local camera 24。

验证：

- 新增共享流回归：两个订阅者只打开 1 个 capture，测试期间源读取 38 帧，最新帧缓存可用。
- 新增超时参数回归：打开超时 8000ms、读取超时 5000ms 均在创建 capture 时生效。
- 断流重连、黑帧抑制和 8 FPS 节拍回归继续通过。
- 双摄运行时各只有一条 RTSP TCP 连接，Receive-Q 持续为 0。
- 云端两路实时帧接收均为 8.0 FPS；公网 HTTPS App 经登录、摄像头列表、播放票据和 MJPEG 完整路径实测约 7.2 到 7.3 FPS。
- 云端两路摄像头均为 `online / synced`；首页和健康接口 TTFB 约 0.17 到 0.19 秒，服务器不是本次卡顿瓶颈。

当前边界：本轮恢复了当前 IP 和双摄数据，但产品级 DHCP 漂移自动恢复尚未实现。下一阶段必须把摄像头稳定身份从单纯 IP 升级为 ONVIF UUID、序列号或 MAC，并在地址变化后自动更新云端配置；演示前先在路由器设置 DHCP 地址保留。

## 110. 2026-07-16 云端摄像头配置唯一真相与盒子严格镜像

问题：

- 产品要求所有摄像头增删、启停和参数修改均在云端 App 完成，盒子只执行云端版本。
- 原 ConfigSyncAgent 只清理 `camera_map` 中曾经映射过、后来被云端删除的摄像头；通过盒子后台直接创建且未进入 camera_map 的本地旁路摄像头会长期保留，导致云端和盒子列表分叉。
- 盒子绑定云端后，本地 `/api/cameras` 的 POST/PATCH/DELETE 仍可写数据库，后台页面也仍展示保存、启停和删除按钮。
- 仅依赖盒子本地 device_bindings 判断云端托管不可靠：真实盒子持有云端签发令牌并成功同步配置，但本地绑定表可能为空；设备归属事实必须以云端签发令牌为准。

修复：

- ConfigSyncAgent 将云端 `cameras` 数组视为完整权威快照。每次成功获取配置后，除当前版本映射出的 local camera 外，所有本地摄像头都被删除并回报 `cloud_authoritative_reconcile`。
- 新增 `camera_config_authority`：启用配置同步、配置了云端地址，且存在云端签发设备令牌或本地绑定记录时，模式为 `cloud_managed`。
- cloud_managed 模式下，盒子 POST/PATCH/DELETE 摄像头接口统一返回 409；扫描、测试连接、抓帧和诊断仍允许。
- `/api/device` 返回 `camera_config_authority`，盒子后台据此显示云端托管状态。
- 摄像头后台在 cloud_managed 模式只显示“测试”和“云端同步”，保存按钮禁用，启停和删除按钮移除；脚本版本升级为 `20260716-cloud-camera-authority-1`。

验证：

- 回归先证明额外本地摄像头会导致列表为 2，修复后云端只保留 1 路时本地旁路摄像头被删除并回报 deleted。
- 权限回归覆盖：已绑定家庭、持有云端令牌、未绑定安装模式和关闭同步的本地模式。
- 真实盒子当前 authority 为 `cloud_managed / local_mutation_allowed=false / cloud_claimed=true`。
- 真实管理员登录后对 camera 24 发起无变化 PATCH，返回 409，正式摄像头数据未修改。
- 当前云端与盒子配置版本均为 `device-config-93a5e83a8b8f`，映射为 cloud 2 -> local 24、cloud 3 -> local 25。

产品契约：云端 App 写入配置后生成新 config_version；盒子拉取完整快照、事务应用并回传每路 local_camera_id、sync_status 和错误；App 只有收到盒子确认后才显示 synced。盒子后台不再构成第二份正式配置源。

## 111. 2026-07-16 实时分析帧同步与空沙发假骨架修复

延迟根因：

- 管理页的摄像头画面是持续 8 FPS 更新的 MJPEG，框、骨架和姿态则来自独立 `/analysis/live` 请求。
- 旧前端在 unified/person 模式每 7 秒、fall/meal/stillness 每 9 秒才再请求，并允许沿用 8 秒姿态缓存。
- 分析接口没有返回被分析图片，前端只能把旧坐标画在已变化的视频上；另一个 6 秒后台刷新还会将数据库旧截图盖回当前画面。

实现：

- `CameraAgent` 缓存帧增加递增 `frame_id` 和 UTC `captured_at`，同一张像素的多次读取保持同一帧标识。
- 实时分析接口返回与结果原子对应的 JPEG data URL、帧标识和采集时间，不写入正式截图库。
- 管理页第一张分析帧到达前保留 MJPEG，到达后只在该对应帧上画人框、骨架和场景。帧请求串行执行，完成后 180ms 启动下一次，不并发、不积压。
- 前端通过 generation、camera id、algorithm 和 `captured_at` 四层校验拒绝过期响应；算法页的 6 秒辅助刷新不再读取旧 snapshot。
- 管理预览禁用姿态缓存，不将任何旧骨架继续画在新帧上；`DetectAgent` 增加全局推理锁，避免 worker 与管理预览并发使用同一模型实例。

误识别根因与修复：

- 真实书房画面复现空沙发靠垫被 RTMPose 拼成 `confidence=0.36` 的横向“躺姿”，且没有可靠 YOLO 人形佐证。
- 旧家具一致性门只拒绝宽高比大于 2.4 的超宽骨架，该假骨架未达比例因而漏过。
- `VisionPipeline` 对没有 YOLO 人形对应的 pose-only 候选新增 0.42 最低置信门；低置信骨架只留在 `rejected_poses` 诊断中，不进入人数、姿态、活动、跌倒和页面叠加。
- 回归保留有 YOLO 支持的真实躺姿和无 YOLO 但高置信的遮挡坐姿，避免为降误报粗暴关闭姿态能力。

验证：

- 新增 `verify-live-analysis-frame-sync.py` 和 `verify-detect-agent-serialization.py`；`verify-vision-pipeline.py` 新增低置信 pose-only 拒绝与真实姿态保留回归。
- 本地共享流、8 FPS 节拍、摄像头超时、视觉流水线、Python 编译、JavaScript 语法和 diff 检查通过。
- 真实树莓派页面分析更新约 0.5–0.7 秒，单次推理约 0.30–0.50 秒，帧龄通常 0.0–0.3 秒；连续超过 13 秒无旧截图回跳。
- 书房空画面连续 25 帧均为 `person_count=0 / pose_count=0`，低置信骨架只在拒绝列表；双摄切换、管理页无脚本错误，`gohome-edge-agent.service` 保持 active。

当前边界：本轮修复的是管理预览的帧时序和一个现场低置信误报类型，不等于正式 worker 已经达到跌倒动作所需的高频采样。下一步仍需实施“常态低频 + 人物/快速位移触发高频”分层调度，并用安全模拟片段验收。

## 112. 2026-07-17 EACP 连续姿态感知重构决策

实机复核：

- 关闭算法管理页后，`/analysis/live` 额外请求停止，盒子温度从约 79 摄氏度降至约 61 摄氏度；常态 CPU 约 10%-12.5%，正式 worker 推理时短时约 104%。
- 页面关闭后正式算法没有停止。数据库继续产生双路 `snapshots / detection_results / rule_evaluations`，相邻同路记录间隔约 6.1 秒。
- 当前约 6 秒并非树莓派硬件极限，而是 `EdgeWorker` 顺序处理两路摄像头后再按 `capture_interval_seconds=5` 固定等待的直接结果。
- 管理页完整 YOLO+RTMPose 单次实测约 0.30-0.50 秒，持续请求约 1.5-2 FPS 时会造成高 CPU 和高温；双摄 CPU 无法直接用“每个播放帧都跑完整模型”的方式达到 8 FPS。
- 当前外层 YOLO 和 RTMLib `Body` 内部人体检测存在重复计算；现有骨架 cache 只沿用旧坐标，不是真正的连续关键点跟踪；现有人体 track 主要依赖 IoU 和中心距离。

确认方案：

- 下一阶段统一采用 `Event-Adaptive Continual Pose Tracking`（EACP，事件自适应连续姿态感知）。
- 每路摄像头独立维护最新帧、轨迹、风险模式和推理 deadline；共享模型执行器不得共享跨摄像头轨迹状态。
- 空闲约 1 FPS 人体锚点，人物或明显运动后约 2 FPS 姿态锚点，快速下降等风险期间目标 3-5 FPS；视频和轻量跟踪继续约 8 FPS。
- OC-SORT/KLT 产生的 `tracked` 结果只用于连续展示、运动趋势和触发升频；只有新鲜 `observed` 模型锚点可以进入正式姿态、跌倒、恢复和事件证据。
- 快速跌倒目标调整为动作触发后约 1.5-3 秒形成边缘临时候选，App 先提醒，云端三图复核异步更新同一 SafetyIncident。
- 优先消除 YOLO 与 RTMPose 重复人体检测，再评估 RTMO 或 AI HAT+；不得把购买 HAT+ 当作修复调度架构的替代方案。

实施边界：

- 本轮只更新 PRD、Plan 和 Implement，未修改生产算法、正式 worker、规则数据库、树莓派文件或云端服务。
- 用户已明确要求先审阅完整重构方案，再开始实现。实施从只读指标和失败回归开始，随后按最新帧调度、推理去重、连续跟踪、风险升频、增量时序模型和可选硬件加速分批推进。
- 不允许临时把采样间隔粗暴改为 1 秒后宣称完成；该做法会持续运行重复完整模型，可能重新造成高温，也不解决双摄公平、历史帧丢弃、骨架连续性和告警证据边界。

## 113. 2026-07-17 EACP P0/P1 最新帧独立调度

实现：

- 新增 `AdaptiveInferenceScheduler`，每路摄像头独立维护 deadline、in-flight、active/risk 保持时间、锚点计数、实际 FPS、推理耗时、帧龄和 deadline miss。
- 调度频率为 idle 1 秒、active 0.5 秒、risk 0.25 秒；风险和活跃保持分别为 5 秒、8 秒。到期摄像头按最早 deadline 和风险优先级选择，同级按摄像头稳定轮转。
- `EdgeWorker` 每次只处理一台到期摄像头，不再完成双摄整轮后读取 `capture_interval_seconds=5` 作为固定 sleep；模型忙时不建立历史帧队列。
- idle 只执行人物/场景/火灾锚点，首次可信人物或明显运动使该路进入 active，之后每个调度锚点启用 RTMPose；手动“抓取并分析”继续完整运行姿态，不受 idle 降频影响。
- 每条分析增加 `eacp-analysis-runtime-v1`，记录 mode、是否请求姿态和调度器版本；`/api/rules/runtime` 返回每路实际 FPS、帧龄、耗时和 deadline miss。

持久化与事件安全：

- 算法频率与持久化频率解耦。`capture_interval_seconds=5` 继续作为普通 JPEG、Snapshot、DetectionResult 和 RuleEvaluation 的常态落盘间隔，不再控制守护算法频率。
- 所有锚点仍更新内存 TemporalObservation、PoseFactorGraph 和 RuleEngine；普通高频锚点不重复写完整图片和 analysis JSON。
- 人物 `无 -> 有`、`有 -> 无`、risk 模式、黑屏、跌倒、火灾和长时间地面躺卧立即持久化；任何非生活观察候选如果出现在非持久化帧，会先补写当前证据再创建事件。
- DetectionResult 落盘前重新挂接当前 snapshot 到 temporal evidence，保证事发前、转折和当前证据链不缺当前帧。
- RuleEngine 允许没有持久化 snapshot 的普通内存评估，但正式安全候选仍必须获得真实 snapshot ID。

回归：

- 新增调度器、worker 集成和持久化节流三组红绿回归，覆盖双摄公平、start-to-start 节拍、过期 deadline 丢弃、模式保持、姿态按模式启停、普通锚点不放大写入、人物状态切换立即落盘和当前证据帧挂接。
- 跌倒状态机、长时间倒地、TemporalObservation、PoseFactorGraph、姿态分类、观察日志、事件去重、恢复上传、DetectAgent 串行、配置同步和完整 VisionPipeline 回归全部通过。
- 部署脚本排除新增 QA 文件，树莓派生产目录只同步运行模块；YOLO、ONNX Runtime、RTMLib 和 RTMPose 模型预检通过。

实机结果：

- 算法页关闭时，camera 24 idle 实测约 0.99 FPS，camera 25 约 1.00-1.15 FPS；单次锚点约 0.14-0.17 秒，帧龄约 0.16-0.24 秒。
- 连续 120 秒两路共处理 261 个新鲜锚点，Snapshot、DetectionResult 和 RuleEvaluation 各只新增 48 条，符合两路每 5 秒一条的持久化预算。
- CPU 多数采样约 65%-68%，姿态短时加载时峰值约 180%；两分钟窗口温度最高 69.2 摄氏度，后续模型短时活跃时瞬时 73.6 摄氏度并回落至 65.9 摄氏度，当前 throttling 位为 0，未发生实时热降频。
- 两路本地 MJPEG 分别实测 7.97 FPS 和 7.98 FPS；live relay 配置 8 FPS、双路 active、云端返回成功且无 relay error。
- 配置同步继续使用 `device-config-93a5e83a8b8f`，双路在线并 synced；worker runtime `last_error` 为空。

当前边界：P0/P1 已部署，但还不是完整 EACP。现有 RTMPose 仍包含内部人体检测，OC-SORT/KLT 连续跟踪尚未接入；真实人物 active 2 FPS、risk 3-5 FPS、300ms 风险触发和 1.5-3 秒边缘候选尚未完成安全动作验收。下一阶段先做 P2 推理链去重，再进入 P3 连续跟踪。

## 114. 2026-07-17 EACP P2 推理链去重

实现：

- `VisionPipeline` 将同一轮 YOLO 已产生的人框传给 `RtmposeAnalyzer`，RTMLib `RTMPose(image, bboxes=...)` 只对人物 ROI 执行姿态头，不再在每个姿态锚点中重复运行 `Body` 内部 YOLOX。
- 外层没有可用人框时仍保留懒加载 RTMLib YOLOX 回退检测，用于遮挡或外层检测漏失；回退检测器和外部人框路径共用同一 RTMPose 实例，不重复驻留姿态模型，也不共享跨摄像头跟踪状态。
- 修正 RTMLib 空框语义：回退检测没有人体框时直接返回无骨架，不再把空框交给 RTMPose 后退化为整图姿态推理，避免空沙发家具假骨架、无效 CPU 消耗和瞬态 `NoneType` 错误。
- 顶层 `analysis_json`、姿态算法结果和错误结果均增加 `pose_detection_source / pose_external_box_count`，明确区分 `external_person_boxes / rtmlib_detector_fallback / disabled`。
- 修复部分遮挡人物只有单侧肩关键点时 `_action_hints` 读取另一侧空点导致异常的问题；单侧肩、手腕和鼻点现在可正常形成上半身动作提示，不再被误报为模型推理失败。
- 没有 YOLO 对应的低置信 pose-only 候选继续执行 0.42 人体一致性门，只保留在 `rejected_poses`，不进入人数、姿态、活动、跌倒或页面叠加。

回归：

- `verify-vision-pipeline.py` 覆盖外部人框复用、内部检测器不被调用、无外部框时回退、回退空框不执行整图姿态、顶层来源字段、单侧肩关键点和原家具假骨架门。
- AdaptiveInferenceScheduler、EdgeWorker、5 秒持久化节流、跌倒状态机、长时间倒地、TemporalObservation、PoseFactorGraph、观察日志、配置同步、姿态片段、PresenceSession、告警去重和 Python 编译回归全部通过。
- 代码检查点为 `08837fa / 5990c1a / a3e4b06 / b55546a`，均已推送 `origin/main`；部署脚本未覆盖 Pi `.env.local`、数据库、截图、模型或虚拟环境，视觉运行时预检全部通过。

树莓派实机结果：

- 使用 camera 25 当天真实历史人物帧做同帧 A/B。外层 YOLO 中位数约 0.250 秒；旧 `Body` 姿态阶段约 0.461 秒，外部人框直送姿态头约 0.068 秒，姿态阶段减少 85.3%。
- 完整模型链中位数由约 0.711 秒降至 0.318 秒，减少 55.3%。最终生产 `VisionPipeline` 在高置信真人帧上返回 `pose_detection_source=external_person_boxes / pose_model_status=ready / person_count=1 / pose_count=1 / posture=sitting`，连续 5 次中位数约 0.326 秒。
- 首轮在线观察发现空画面回退路径产生 5 条姿态错误，由此定位并修复空框整图推理；最终版本重启后连续 120 秒，两路各持久化 23 条记录，camera 25 两次进入 active 回退路径，新增姿态错误为 0。
- 最终观察期间 live relay 持续运行、双路 active、`last_error` 为空；温度约 60.6-62.8 摄氏度。单独 A/B 压力进程与正式服务并行时温度短时到 76 摄氏度，进程退出后回落，该数字不作为生产常态温度。

当前边界：P2 已完成并部署，但仍不是完整 EACP。当前只有新鲜 `observed` 模型锚点，没有 OC-SORT/KLT 的 `tracked / expired` 连续关键点流；尚未完成双摄真实人物 active 2 FPS、risk 3-5 FPS、300ms 风险升频和 1.5-3 秒边缘候选安全动作验收。下一阶段进入 P3 连续跟踪，不能用姿态 ROI 加速数字替代风险事件端到端验收。

## 115. 2026-07-17 EACP P3a 连续关键点与管理页接入

连续跟踪实现：

- 新增每摄像头独立 `ContinualPoseTracker`，使用 KLT 金字塔光流和前后向误差校验在模型锚点之间传播可信关键点；同时校验最少有效点、有效点比例和骨架几何尺度。
- 状态统一为 `observed / tracked / coasting / expired`。`observed` 来自新鲜 RTMPose 锚点；`tracked` 是 KLT 成功传播；光流短暂失败时在正式锚点年龄 600ms 内进入 display-only `coasting`，最多延续到 1.2s；人物离开、展示宽限耗尽或质量门限失败后进入 `expired` 并删除骨架和彩色帧。
- `tracked` 强制设置 `fall_evidence_eligible=false / person_evidence_eligible=false`，不进入 RuleEngine、PoseFactorGraph、TemporalObservation、PostureEpisode、恢复判断、持久化证据或正式事件。
- 独立后台线程按约 7.5 FPS 消费共享摄像头最新帧，不依赖管理页是否打开；没有锚点时不复制帧，不额外占用空闲内存带宽。

同帧管理接口与页面：

- 跟踪器只在有效窗口内保存与坐标严格对应的最新彩色帧；`latest_frame()` 在同一锁内返回像素、`frame_id`、跟踪载荷和模型锚点分析上下文，过期后不返回旧帧。
- 新增受盒子管理员会话保护的 `GET /api/cameras/{camera_id}/continual-pose/live`。接口返回同一 `frame_id` 的 JPEG 与骨架，`tracked` 人框明确标记为 `display_only`；没有有效骨架时只返回摄像头最新帧和空姿态。
- 统一视觉感知页改为约 140ms 读取后台 EACP 结果，不再每 180ms 调用 `/analysis/live` 重跑完整 YOLO+RTMPose。管理页关闭后算法照常运行，打开页面只编码和显示现成结果。
- 实线骨架表示 `observed` 模型锚点；淡色虚线表示 `tracked` KLT 补帧；更淡的虚线表示 `coasting` 最后可信叠加层。状态栏显示来源、锚点年龄、有效点数和 FB 误差，并明确写出“跟踪帧只补足画面连续性，不作为报警证据”。

回归与实机结果：

- 合成平移回归得到 `dx=5 / dy=3`，保留 9 个有效点；同帧像素、`frame_id` 和分析上下文一致，漂移帧被拒绝，600ms 过期后旧显示帧被删除，两路摄像头状态隔离。
- API 契约回归确认 `same_frame=true / tracked_display_only=true / formal_evidence_isolated=true / expired_pose_hidden=true`；页面契约确认不再调用完整实时分析接口，并保留旧响应和旧摄像头结果拒绝门。
- 真实走动测试中 camera 24 累计 `observed=4741 / tracked=15002 / expired=2726`，最近有效跟踪 14 点、FB 误差 0.1193；camera 25 累计 `observed=10386 / tracked=34862 / expired=5157`，最近有效跟踪 9 点、FB 误差 1.1218。人物离开后状态正常回到 empty/expired，没有旧骨架残留。
- 代码通过 Pi 的真实 OpenCV 回归、视觉运行时预检、Python 编译、JavaScript 语法、调度回归和 diff 检查；服务重启后 `gohome-edge-agent.service=active`，日志无连续跟踪异常，温度从启动瞬时高值回落到约 64.2 摄氏度。

当前边界：P3a 已完成，但完整 P3 仍缺 OC-SORT 多人轨迹和遮挡后身份恢复；P4 的快速下降触发、risk 3-5 FPS、300ms 升频和 1.5-3 秒跌倒候选尚未完成。管理页连续骨架是研发可视化，不代表 KLT 补帧已经成为安全证据。管理员登录后的双摄页面视觉切换仍需做一次人工浏览器验收。

## 119. 2026-07-19 EACP P3a.3 覆盖层有界承接

问题根因：

- P3a.1 已经把视频底图与姿态覆盖层解耦，但 KLT 在某一帧出现 `forward_backward_error`、`insufficient_points` 或其它光流失败时，跟踪器仍立即返回 `expired`，所以人物还在底图中时框和骨架会瞬间消失。
- 600ms 正式模型新鲜度门与展示连续性被错误地当成同一个门限；延长正式证据窗口会污染安全逻辑，不能采用。

实现：

- `ContinualPoseTracker` 保留正式 `max_age_seconds=0.6`，增加 `max_display_age_seconds=1.2`。KLT 失败且锚点仍在展示窗口内时返回 `state=coasting`，保存最后一次可信姿态、当前底图和失败原因；超过 1.2s 仍按 `expired` 清除。
- `coasting` 的人物姿态标记 `tracking_source=last_good_overlay`、`display_only_stale=true`，并强制关闭 `formal_evidence_eligible / fall_evidence_eligible / person_evidence_eligible`。它不进入 RuleEngine、TemporalObservation、PoseFactorGraph、PostureEpisode、恢复判断、事件持久化或云端上传。
- 管理 API 接受 `coasting` 作为显示状态；前端保留单条 MJPEG 底图，人物框与骨架以更淡的虚线呈现，状态栏显示“等待模型锚点”。不重连视频、不请求分析 JPEG、不提高模型频率。
- 运行指标增加每摄像头 `coasting_count` 与最近失败原因，便于区分真实人物离开、光流失败和锚点超时。

回归与部署：

- `verify-continual-pose-tracker.py` 验证光流失败进入 `coasting`、正式证据全关闭、1.2s 后 `expired`、摄像头状态隔离和计数器。
- `verify-continual-pose-live-api.py` 验证管理接口可显示 `coasting` 但不泄漏人物或跌倒证据；`verify-continuous-overlay-console.py` 验证页面显示承接状态且保持单一视频底图。
- 本地与 Pi 的 Python/OpenCV、视觉运行时、页面契约和 JavaScript 语法检查通过。2026-07-19 定向部署后，Pi 服务 active、双路 online/synced、live relay 8 FPS、温度约 63.7-75.2 摄氏度、`throttled=0x0`，运行约 20 秒 camera 24/25 的 `coasting_count` 分别为 133/51，`continual_pose_error` 和 `last_error` 均为空。

当前边界：P3a.3 只解决显示覆盖层的短暂闪烁，不等于完成 P3b 多人 OC-SORT 身份恢复、P4 风险升频或跌倒端到端验收；正式告警仍必须等待新鲜 `observed` 模型证据和既有时序规则。

## 116. 2026-07-17 EACP P3a.1 连续视频与姿态覆盖层解耦

问题根因：

- P3a 管理页在检测到有效骨架后停止 MJPEG，并持续请求、显示带像素的分析 JPEG；骨架短暂过期后又重启 MJPEG。
- `observed / tracked / expired` 在短时间切换时会带动整张底图切换，造成闪烁、等待首帧和额外 JPEG 编码负载。

实现：

- `ContinualPoseTracker.latest_metadata()` 返回每路最新跟踪状态、分析上下文、源画面尺寸和骨架，不复制或编码彩色帧。
- `GET /api/cameras/{camera_id}/continual-pose/live` 默认返回无 `image_url` 的覆盖层 snapshot，兼容未刷新的旧页面也不会持续编码 JPEG；只有显式 `include_frame=true` 才返回同帧图片，供研发精确帧复核。
- 统一视觉感知页删除第二张 `analysisFrame`，始终保持一条 640x360、目标 10 FPS 的 MJPEG 底图；约 140ms 轮询只更新人物框、骨架、姿态、风险标签和状态指标。
- 骨架过期只清空覆盖层，不停止、重连或替换视频流；页面不再传输 base64 分析 JPEG。
- 实机部署前发现 camera 25 的正常沙发躺卧已被场景层正确标记为 `normal_lying_zone=true / overlap=0.992`，但调度器仍读取原始 `fall_candidate=0.96`，使该路长期保持 risk 并把 CPU 推到约 235%。调度器现优先保留快速下降、地面低位和火灾风险；只有床/沙发正常躺卧且没有独立下降因子时降为 active，正式 RuleEngine 和事件阈值不变。
- P3a.1 不修改 EACP 调度、RTMPose、KLT、姿态分类、跌倒因子、RuleEngine、事件阈值或云端复核语义；既定 P3b 仍为 OC-SORT 多人轨迹。

回归：

- 新增 `verify-continuous-overlay-console.py`，锁定单一连续视频底图、无像素元数据轮询和分析 JPEG 切换删除。
- `verify-continual-pose-tracker.py` 验证元数据保留 320x240 源尺寸且不包含帧像素。
- `verify-continual-pose-live-api.py` 验证轻量接口保留骨架与尺寸、没有 data URL，`tracked` 仍不能进入正式证据。
- `verify-live-analysis-frame-sync.py` 更新为连续视频覆盖层契约；调度、双摄 worker、跌倒状态机和上传/云端复核回归保持通过。

实机验收：

- 管理页只有一个 `mjpegStream`，自然尺寸 640x360；`analysisFrame` 数量为 0，页面无脚本错误。
- camera 25 连续采样覆盖 `tracked / observed / expired` 三种状态，10 次采样的 MJPEG `src` 完全一致；覆盖层随骨架状态从安全标记到完整骨架变化，视频未重连。
- 切换至 camera 24 后只更换一次视频地址，约 1.8 秒内画面就绪，空白层保持隐藏；切回 camera 25 后仍保持单流。
- 真实画面中两名人物、两组骨架、坐/躺姿态和沙发场景框均能同时显示。正常沙发躺卧回归为 active，非正常区域躺倒仍进入 risk，坐姿裸人框分数不再单独触发 risk。

当前边界：P3a.1 已完成实机交付，但现场两路同时有人时纯 CPU 仍约 216%，温度约 81.8 摄氏度，说明双路 active 姿态推理预算仍未达持续温度目标。本轮没有擅自加入全局单槽位；该问题继续归入既定 P3b/P4 的多人轨迹、风险调度和硬件加速评估。

## 117. 2026-07-18 EACP P3a.2 多摄推理预算与热保护

实现：

- 新增 `SystemResourceMonitor`，通过树莓派 thermal sysfs 低成本读取温度，并按 `normal / warm / hot / critical` 分级；不可用平台返回 unknown，不阻断 worker。
- `AdaptiveInferenceScheduler` 增加全局冷却 deadline。温度升高时只延长下一次模型推理间隔，风险模式冷却短于 active/idle；视频、中继、配置同步、KLT 连续跟踪、事件状态机和云端复核不受影响。
- 调度排序改为风险优先，同时增加 3 秒 starvation guard，保证其他启用摄像头仍获得基础巡检；没有改成静态单摄或永久全局单槽位。
- worker runtime 增加温度、阈值、当前热状态、全局冷却、状态切换次数和最近切换，供管理端与云端诊断读取。
- 新增资源监控、热冷却、风险优先和防饿死回归；原双摄公平、正常沙发卧躺抑制、非正常区域躺倒风险、worker、Python 编译和 diff 检查继续通过。

树莓派结果：

- 部署前温度约 77.9 摄氏度、主进程约 101% CPU，`get_throttled=0xe0000` 表明历史上发生过频率限制、热降频或软温控，但当前低位状态位为 0，不是正在降频。
- 定向同步 4 个运行文件，不修改 `.env`、模型、数据库和摄像头配置；远端回归通过后重启，`gohome-edge-agent=active`、health 正常、两路摄像头 `online/synced`、live relay 仍为 8 FPS。
- 重启后短时观察温度约 71.6-74.7 摄氏度，runtime 资源状态为 normal；两路均为 active，模型锚点有效频率约 1.8/0.78 FPS，`last_error` 和 `continual_pose_error` 为空。
- 重启后日志未出现新的 Traceback、database locked、读取失败或中继错误。历史 `0xe0000` 会保留到整机重启，不能用它判断当前仍在热降频。

当前边界：P3a.2 解决持续高温下的受控降级和多路预算，不代表 P3b/P4 已完成。下一步仍是 OC-SORT 多人轨迹、KLT 快速下降触发风险升频、同一 SafetyIncident 的边缘候选与云端异步复核，以及真实坐下、蹲下、弯腰、沙发卧躺和跌倒动作验收。

## 118. 2026-07-19 盒子 SQLite 锁与上传线程稳定性

问题根因：

- 盒子重启后，配置同步线程按云端维护命令清理历史 `rule_evaluations / detection_results / snapshots`；同一时间上传线程尝试 claim `upload_jobs`。
- SQLite 连接已有 30 秒 busy timeout，但清理事务与高频页面读取/事件写入叠加时，上传线程收到 `database is locked` 后未捕获异常，daemon 线程退出，造成事件证据无法继续上传。

修复：

- `Storage.connect()` 的 SQLite timeout 和 `PRAGMA busy_timeout` 提升至 120 秒，让短上传事务等待有界维护事务完成。
- `UploadAgent.process_once()` 将锁异常转换为可重试结果；`UploadAgent._run()` 捕获未预期的存储/网络异常并继续下一轮，不允许后台线程静默死亡。
- 新增 `verify-upload-lock-retry.py`，验证锁异常不会退出上传 daemon；EACP 调度、worker、Python 编译和部署脚本检查继续通过。

实机验证：

- 定向部署 `storage.py / upload_agent.py`，远端回归通过后重启盒子。
- 重启后 `gohome-edge-agent=active`、配置同步 `running=true`、两路摄像头 `online/synced`、live relay `8 FPS`。
- `upload_agent.running=true`，重启后成功上传 camera offline 事件，`last_error` 为空；后续 5 分钟无新的 `database is locked / Traceback / ERROR`。
- 双路有人时 CPU 短时约 200%，温度约 72-74 摄氏度，当前 `throttled=0`；这仍然要求后续 P3b/P4 降低纯 CPU 双路 active 的持续成本。

## 120. 2026-07-20 EACP P3b/P4 算法代码收口

本轮先完成算法闭环，未改管理页面。当前唯一正式运行链仍为：

`CameraAgent -> AdaptiveInferenceScheduler -> DetectAgent/VisionPipeline -> TemporalObservationEngine -> PoseFactorGraphEngine -> RuleEngine -> EventAgent/UploadAgent`

P3b 内嵌人体轨迹：

- `vision/temporal.py` 从逐轨迹贪心 IoU/中心距离匹配升级为 observation-centric 全局分配。
- 每路独立维护人体轨迹、归一化框速度和有限历史；预测框参与匹配，最多 2 秒短遮挡窗口，超过窗口的新人物不得继承旧 track 的姿态/跌倒历史。
- 全局分配覆盖多人交叉、快速位移、短时漏检恢复、轨迹替换和摄像头隔离；家庭人数较少时使用有界 bitmask 动态规划，人数异常升高时退化为有界贪心，避免引入 SciPy/BoxMOT。
- 该实现采用 OC-SORT 的观测中心、速度预测和全局关联目标，但不是未经评估直接安装的上游 boxmot/OC-SORT 包，管理端不得写成已安装第三方 OC-SORT。

P4 风险升频边界：

- `ContinualPoseTracker` 对可信 KLT `tracked` 帧计算单帧向下位移速度与锚点累计向下位移，只产生 `risk_hint`。
- `risk_hint` 由 `EdgeWorker.observe_stream_frame` 交给调度器，唤醒该路正式 YOLO/RTMPose 锚点并暂时进入 `risk` 频率。
- `risk_hint.formal_evidence_eligible=false`；`tracked/coasting` 不进入 TemporalObservation、PoseFactorGraph、RuleEngine、恢复判断、姿态片段或云端事件证据。
- 没有新的 `observed` 模型锚点时，快速下移提示不能生成跌倒事件；床/沙发正常躺卧仍保持 `active`。

验证结果：

- 人体轨迹回归覆盖稳定轨迹、多人交叉、短遮挡、快速姿态位移、长时间替换和跨摄像头隔离。
- KLT/worker 回归覆盖显示连续性、快速向下升频提示和正式证据隔离。
- 本地 30 个边缘回归脚本通过；`npm run verify:app-server` 的事件、三图媒体和云端视觉复核闭环通过。整仓 `npm test` 仍被首页已有阻塞式加载文案检查拦截，与本轮算法无关。
- 部署树莓派后，模型运行时、双摄在线、配置同步、视频中继无错误；单服务进程 CPU 约 131-150%，温度约 61.5-65.3 摄氏度，`throttled=0x0`。
- 未宣称真人跌倒端到端、目标 3-5 FPS 风险采样、1.5-3 秒边缘候选和现场云端复核已经完成；这些必须在用户可模拟动作时执行。

## 121. 2026-07-20 EACP 非侵入式验收会话

实现：

- 新增 `EacpAcceptanceService`，支持 `walking / fast_sit / squat / sofa_lying / simulated_fall / custom` 单摄像头会话；状态落在盒子本地有界 JSON，可开始、查看、结束和清理。
- 服务只聚合正式 runtime、事件、候选、上传任务和云端复核。它不修改模型、阈值、规则或摄像头配置，不创建测试事件，也没有建立第二套跌倒状态机。
- 调度器增加最近 64 条风险信号和累计计数，连续跟踪器增加 KLT 风险提示计数与时间戳；worker 仅转发风险来源。这些字段只用于测量首次提示时延和风险升频，不进入正式证据。
- 新增受管理员会话保护的 `/api/eacp-acceptance` 开始、状态、结束和清理接口。无新增安全事件时不请求云端复核；发生正式安全事件后按 edge event ID 关联三帧证据、上传任务和云端多模态结果。

验证：

- 服务回归验证 2 秒内 7 个新锚点为 3.5 FPS、首次风险提示 0.3 秒、三帧证据、事件和媒体上传完成、云端 `confirmed` 结果关联，以及正常走动场景出现安全事件时判定失败。
- API 回归验证四个操作函数及管理员保护前缀；调度器、KLT 连续跟踪、worker、实时叠加、上传代理、上传队列、视觉管线、时序观察和跌倒规则共 11 项定向回归通过，Python 编译和 diff 检查通过。
- 代码已同步树莓派并重启单一 `gohome-edge-agent.service`。模型运行时预检通过，双摄中继保持 8 FPS，配置同步与中继无错误；短时观察 CPU 约 179%、温度约 71.1-74.7 摄氏度、`throttled=0x0`，日志无 warning 级异常。温度已接近 75 摄氏度目标上限，仍需在真人风险升频验收时继续观察。
- 未登录访问验收 API 返回 401，证明管理员保护生效；使用管理员会话完成一次 `custom` 空会话实机冒烟。6.4 秒内 camera 24 增加 12 个正式模型锚点、约 1.87 FPS 和 44 个跟踪帧，双摄仍由正式调度运行；没有候选、事件或云端复核请求，清理后本地会话文件已删除。当前仍不得宣称真人跌倒、风险 3-5 FPS 或云端三图现场闭环已经验收通过。

## 122. 2026-07-20 多人误触发根因修复与证据口径收口

实机事件 `#2047` 的原图显示两人坐沙发、一人站立，没有倒地过程。盒子规则状态为 `dynamic_low_position / dynamic_low_count=5 / fall_confirm_seconds=2.427`。根因是多人画面中左侧站立者的基线被错误继承给另一位坐着的目标，形成 `vertical_drop=0.2228`。云端 `Qwen/Qwen3.5-27B` 返回 `person_count=3 / posture=sitting / surface=sofa / emergency=false / confidence=0.95 / suggested_event_type=none`，所以 `rejected` 是正确兜底。

代码修正：

- `RuleEngine._normalized_target()` 保留姿态目标 `track_id`；多人动态低位判断优先同轨迹历史，没有同轨迹基线时返回 `track_identity_missing`，不使用旁人基线。
- `TemporalObservationEngine.evidence_bundle()` 支持有界最近时间窗；`EdgeWorker` 为安全事件按最高风险姿态选择轨迹，默认只取最近 10 秒最多三张关键帧。
- `EacpAcceptanceService` 增加确认路径、动作趋势耗时、低位确认耗时、动态锚点数、云端复核理由和风险历史状态；风险环形历史被淘汰时不再输出伪造的首风险延迟。

回归新增多人旁观者/坐姿目标串线负例、按轨迹取最近 10 秒关键帧、云端理由、动作耗时和 `history_truncated` 口径检查。原有单人动态低位、快速跌倒、沙发/椅子抑制、蹲姿抑制和恢复路径保持通过。本次云端驳回只证明复核兜底有效，不能替代下一次单人真实跌倒验收。

部署观察继续暴露两个同源边界：事件 `#2054` 是家具区域未写入目标时的普通沙发坐姿；事件 `#2056` 是跟踪器错误复用同一 ID，目标从画面左侧跳到最右侧，归一化水平位移约 `0.827`，旧下降确认仍被继承。最终增加两道安全门：动态 `sitting / upper_body` 要求 `bottom_y >= 0.88`；同 ID 相邻安全目标的归一化中心距离必须不超过 `0.38`。两条门只收紧宽松动态低位补充路径，不修改标准姿态跌倒、快速因子图、床/沙发排除、恢复和云端复核。

验收服务同时增加 `cloud_confirmed` 检查：当前会话 `f3933a23f16646d787ec16aa35f598bc` 因云端以 0.95 置信度返回 `rejected`，最终状态正确记录为 `failed`，而不是把“事件、三图和模型均有返回”误算为成功。修复后的本地 33 个逻辑/契约回归通过；树莓派规则、时序、验收和视觉运行时回归通过，腾讯云 App Server 闭环回归通过。

## 123. 2026-07-22 视觉算法闭环验收与可信恢复重构

本轮修复的是事件状态语义，不是针对现场样本增加阈值：

- 新增 `edge-agent/app/vision/posture_semantics.py`，集中定义物理恢复姿态和过渡低位姿态，避免 `worker.py`、规则引擎和云端各自维护不同恢复集合。
- `PoseFactorGraphEngine` 新增 `gohome-physical-recovery-v1` 证据。地面躺卧状态遇到 `squatting/bending` 时保持活动，不清除躺卧计时；只有同轨迹连续稳定 `standing/sitting` 才输出 `confirmed=true`、`sample_count`、`required_samples`、`identity_match=same_track` 和 `track_id`。
- `RuleEngine` 将跌倒生命周期明确为 `confirmed -> candidate_cleared -> recovered`。候选信号消失不会再直接生成恢复；历史跌倒目标身份保留到可信恢复或新事件替换。
- 长时间地面躺卧事件使用同一物理恢复语义，短暂漏检或过渡姿态不会重复创建事件；完成真实恢复后才允许同轨迹开启新的躺卧事件。
- `EdgeWorker` 删除第二套 `_credible_fall_recovery()` 原始姿态扫描，改为只消费规则引擎输出的 `fall_recovery`；日志关闭与事故恢复职责分离。
- `Storage.latest_unresolved_event()` 增加 `track_id` 精确匹配，避免同一摄像头多个人同时有开放事件时恢复错误事件。
- 云端 `/api/v1/device/events/{edge_event_id}/state` 只接受 `standing/sitting`、稳定样本、同轨迹身份和 `confirmed` 恢复证据；下蹲恢复请求返回 400。

回归与实机结果：

- 本地核心回归通过：跌倒规则、姿态因子图、长时间地面躺卧、时序观察、日志、上传代理和 App Server 闭环。
- 树莓派 OpenCV/NumPy 环境回归通过：自适应 worker、连续姿态跟踪、运动门、视觉管线和上述核心回归；`gohome-edge-agent.service=active`。
- 两路摄像头 `online/synced`，云中继 `8 FPS`，盒子温度约 `67°C`，近 5 分钟无 warning/error；腾讯云 `gohome-app.service=active`，健康检查返回 PostgreSQL store，部署后无 warning/error。
- 现场三分钟事件结论：`2098/2099` 为弯腰并被云端排除，`2100` 为下蹲并被排除，`2101` 为快速倒地并被确认；模型均为 `Qwen/Qwen3.5-27B`，置信度均为 `0.95`。
- 提交 `cc0ec5a` 已推送远端并部署边缘端与腾讯云。历史事件保留原始记录，不回写历史判断；新事件使用新的恢复契约。
