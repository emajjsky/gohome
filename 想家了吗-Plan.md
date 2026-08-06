# 回家 Plan

更新时间：2026-08-03

## 1. 文档定位

这份 Plan 定义 `回家` 从当前本机验证走向商业化产品的实施路径。

### 1.1 对齐要求

`Plan` 不是自由发挥的任务清单，而是 `PRD` 的执行展开。

固定要求：

- `PRD` 没定义清楚的能力，不进入 `Plan`。
- `Plan` 没排到当前阶段的能力，不进入代码主线。
- `Implement` 只能回写 `Plan` 已经允许进入当前阶段的事项。

固定顺序：

1. 先改 `PRD`，确认产品方案和边界。
2. 再改 `Plan`，确认阶段、优先级和执行顺序。
3. 再做实现与验收。
4. 最后回写 `Implement`。

如果这四步顺序被打乱，默认视为方案尚未对齐，不进入正式实现。

当前已有的 `edge-agent`、管理台、Web 页面接入和 YOLO 检测，是阶段 0 的技术基线。Mac 继续作为开发对照和回退环境；当前主验证对象切到树莓派盒子，目标是证明它能独立完成联网、拉流、检测、事件、预览、日志和报警。

商业化目标系统包含：

- 原生 SwiftUI iOS 用户端 App
- 云端业务后端
- API 管理和设备通道
- 边缘硬件端 edge-agent
- YOLO 和视觉模型服务
- 管理台 / 运营后台
- 数据、事件、媒体和规则治理

## 2. 实施原则

### 2.1 产品先于阶段验证

每个阶段都必须回答：

- 这个能力未来商业化是否需要。
- 这个能力属于用户端、云端、边缘端、算法端还是硬件端。
- 当前实现是否只是验证，后续是否需要替换。
- 数据是否能从本机结构平滑迁移到云端结构。

### 2.2 数据和逻辑拆分

从现在开始避免把逻辑写死在页面或单个脚本里。

原则：

- 前端只展示和发起用户动作。
- 云端负责用户、设备、事件、通知和权限。
- 边缘端负责摄像头、抽帧、视觉检测和本地规则执行。
- 算法层输出检测事实，不直接输出业务结论。
- 规则层把检测事实转成产品事件。
- 事件层把候选事件转成用户可理解的提醒。

### 2.3 分阶段可替换

当前技术选型可以服务验证，但要保留替换空间：

- Mac 只作为开发对照和临时回退，不能继续承接正式产品主路径。
- 当前主验证设备切到树莓派盒子，必须尽快验证部署、自启、720p 拉流、算法负载、散热和 24 小时稳定性。
- SQLite 后续替换为云端 PostgreSQL / MySQL。
- 本地文件截图后续替换为对象存储。
- 临时通知后续替换为 APNs / 厂商推送。
- YOLOv8n 后续替换为更合适的检测或姿态模型。
- 家属端静态 Web 由原生 iOS App 替换；Web 最终只保留盒子安装管理、云端运维、隐私协议和帮助页面。

### 2.4 2026-07-21 原生 iOS 正式交付路线

本节覆盖后文仍以 `H5 / WebView App` 作为正式用户端的历史排期。历史记录保留用于说明已完成验证，不再作为当前实施指令。

正式交付目标：

- TestFlight 可安装的原生 SwiftUI App，最低 iOS 16。
- 家属端不加载远程 HTML；现有 SwiftUI + WKWebView 壳只作为迁移对照。
- 五个主导航固定为首页、守护、记忆、社区和我的；事件并入守护，关怀并入首页，资讯精选留在首页，适老产品推荐并入社区。
- 首页展示真实天气、日历、距离和有来源图文资讯；回家提醒进入消息中心，不做静态假卡片。
- 回家消息完成“规则触发 -> 站内/APNs 推送 -> 话题与可编辑文案 -> 原生分享 -> 已联系/稍后提醒/已回家记录”。
- 精选只做真实非医疗类适老生活用品推荐和外部链接，不做交易系统。
- 盒子视觉算法继续在原主线验收，本线只消费稳定摄像头、视频、事件和云端复核契约。

当前执行顺序：

1. 把云端账号、家庭权限和 PostgreSQL 持久化从内存整库覆盖改成实体级事务仓储。
2. 建立原生 App 基础层：Keychain、APIClient、账号级缓存、Session/Onboarding Coordinator 和五 Tab 导航。
3. 原生完成注册登录、家庭、老人资料、盒子绑定和摄像头配置。
4. 原生完成首页与守护，守护内部合并实时画面、活动轨迹和事件，确保切 Tab 不重新读取整页，视频只播放当前选中一路。
5. 完成关怀消息、话题生成、系统分享、消息动作记录，以及家庭私密记忆 MVP。
6. 完成社区服务入口、真实来源产品推荐、我的设置、活动日志开关和三种隐私画面模式。
7. 配置 APNs、定位、隐私清单、签名、真机回归和 TestFlight 上传。
8. 原生能力验收后停止家属端 Web 公开入口；盒子管理、云端运维和协议帮助 Web 保留。

## 3. 当前基线

仓库路径：

```text
/Users/tanyihua/trae比赛/gohome
```

当前边缘服务：

```text
/Users/tanyihua/trae比赛/gohome/edge-agent
```

当前默认端口：

```text
8711
```

当前启动命令：

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
GOHOME_AGENT_PORT=8711 GOHOME_DETECTOR_BACKEND=yolo ./run.sh
```

当前已完成：

- 本机 `edge-agent`
- FastAPI API
- SQLite 本地数据
- 本地 App API 替身 `local-app-server`，用于模拟云端用户、家庭、设备、摄像头、事件、媒体和实时流接口
- 本地 App API JSON 数据导出到云端表结构的迁移快照脚本
- 局域网 RTSP 摄像头 `192.168.1.11:554`
- 树莓派已同步两路 App 配置摄像头并可通过 App API 代理实时画面
- 摄像头测试和抓帧
- 后台定时抽帧
- 黑屏 / 画面变化检测
- YOLO 人形数量检测和检测结果保存
- 疑似跌倒候选启发式
- 本地事件记录
- 管理台
- 产品 Web 首页、守护页、事件页局部接入真实数据
- 管理台检测摘要和 YOLO 检测框叠加

当前明确状态：

- 开发对照设备：当前 M4 / 24GB Mac。
- 当前主验证设备：树莓派盒子。
- 主摄像头：局域网 RTSP 摄像头，不再以 `local:0` 为主线路；当前本地闭环已有两路摄像头。
- 当前服务端口：`8711`。
- `8711` 是 edge-agent 的开发/内部监听端口；产品化访问不让用户看到端口，使用 nginx/Caddy 在 `80` 端口反向代理到 `127.0.0.1:8711`，对外呈现 `http://gohome.local/admin`。树莓派可用 `sudo bash scripts/install-admin-proxy.sh` 安装该代理。
- 当前 App API 端口：本地 `8788`，由 `local-app-server` 模拟云端 API；这不是正式云服务。
- 当前阶段目标：树莓派盒子本地视觉闭环已经进入稳定验证，下一步把本地 App API 的 JSON 存储迁移到正式云端数据库结构，再部署 HTTPS 云服务。

## 4. 总体路线

```text
阶段 0：树莓派盒子本地闭环
-> 阶段 1：盒子安装与本地管理台产品化
-> 阶段 2：最小服务器和设备通道
-> 阶段 3：用户端 App / H5
-> 阶段 4：视觉模型产品化
-> 阶段 5：真实家庭试点
-> 阶段 6：商业化运营
```

每个阶段必须形成可验收产物，不能只停留在页面或想法。

### 4.1 工作线拆分

后续实施按工作线推进，不按单一页面或单一脚本推进。

| 工作线 | 当前状态 | 下一阶段交付物 | 商业化目标 |
| --- | --- | --- | --- |
| 产品与交互 | 已有静态 Web 原型；亲情关怀主线需要增强 | 用户端 H5 流程、安装调试流程、告警处理流程、每日关怀卡片 | 正式 App / H5 / 安装向导 |
| 前端工程 | 静态 HTML + JS 局部接 API | 首页、连接页、规则页、亲情关怀页接入真实数据 | 用户端、管理端、运营后台分离 |
| 云端后端 | 本地 App API 替身已跑通；PostgreSQL schema 和第一版可选 store 适配已起步；正式云端未完成 | API v1 数据库适配完善、亲情关怀消息、设备通道、对象存储、HTTPS 部署 | 多家庭、多设备、多端同步 |
| 边缘端 | `edge-agent` 本机服务 | 设备身份、配置、日志、断网缓存、RTSP 稳定性 | 可部署边缘运行时 |
| 视觉算法 | basic + YOLO 人形 | 检测框、模型版本、DetectionResult、规则链路 | 可灰度、可解释、可评估的算法系统 |
| 通知链路 | 测试接口 | Bark / 飞书真实通知 | APNs、短信、电话、升级通知 |
| 硬件端 | Mac 已完成开发基线，树莓派已到位 | 树莓派部署、自启、720p 拉流、散热、24 小时稳定性、安装模式 | 低功耗边缘盒 |
| 数据治理 | edge-agent SQLite + App API JSON；已新增 PostgreSQL 初始 schema、导出快照和可选 PostgresStore | 细粒度表级写入、对象存储、事件状态机、媒体留存策略 | 可审计、可迁移、可运营的数据平台 |
| 运营后台 | 管理台雏形 | 设备诊断、告警质量、日志查看 | 售后、运营、模型灰度和工单 |

### 4.2 关键依赖

依赖关系：

- 用户端 App 依赖云端用户、设备、事件 API。
- 云端事件 API 依赖 edge-agent 上报格式稳定。
- edge-agent 上报格式依赖检测结果和事件候选结构化。
- 视觉模型产品化依赖检测结果保存、检测框可视化和误报反馈。
- 硬件试点依赖 edge-agent 开机自启、watchdog、日志和断网恢复。
- 运营后台依赖设备心跳、事件状态、通知状态和日志上报。

因此当前最优先的不是马上写完整 App，而是在树莓派上把盒子本地闭环跑稳，并同步把 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 这条数据链路做清楚。

### 4.3 里程碑产物

| 里程碑 | 产物 | 完成后能证明什么 |
| --- | --- | --- |
| M0 技术基线 | Mac 上 RTSP 摄像头、YOLO、事件、Web、通知 | 基础链路可跑，作为开发对照 |
| M1 树莓派盒子闭环 | `edge-agent`、systemd、自启、720p 实时流、事件、截图、日志 | 盒子能独立运行 |
| M2 配网和本地管理台 | `/setup` 只做配网；`/admin` 承接摄像头接入、算法配置、算法预览、日志诊断、报警测试 | 盒子可配网、可管理、可演示、可诊断 |
| M3 最小云端事件平台 | 设备注册、绑定、心跳、事件上报、媒体上传、API v1 | App 不依赖局域网 |
| M4 用户端产品 | H5/App、告警详情、规则配置、推送、图文消息卡片 | 家属可以真实使用 |
| M5 家庭试点 | 边缘盒、真实家庭、7 天运行报告 | 商业化风险可评估 |
| M6 商业版本 | 运营后台、套餐、安装 SOP、售后流程 | 可以销售和交付 |

### 4.4 从现在开始的总执行顺序

后续开发必须严格按下面顺序推进，避免同时铺太多线导致每条都不闭环。

1. 固定 Mac 基线，只作为开发对照和回退。
2. 跑通树莓派上的 `edge-agent`、`systemd` 自启和单路 RTSP 摄像头。
3. 把实时画面默认压到 720p 档位，先解决延迟、花屏、码流和稳定性问题。
4. 做手机优先的 `/setup` 配网页，只覆盖热点连接、家庭 Wi-Fi 选择、密码输入、连接结果和回到 App / 管理端提示。
5. 重构本地 `/admin` 为盒子开发管理模式：首页、网络状态、摄像头配置、算法配置、算法预览、报警、日志诊断。
6. 跑通统一实时感知：选择摄像头后，在同一真实画面查看人物、姿态、场景、风险状态、规则解释和最近日志。
7. 跑通 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event` 数据链，并完成同类事件归并和频控。
8. 跑通跌倒、火灾候选等高优先级报警的测试渠道和应急处置动作。
9. 跑通真实手机通知或至少一个可验证报警通道。
10. 完成树莓派 24 小时稳定性记录和故障诊断记录。
11. 跑通最小云端：设备注册、绑定、心跳、事件、媒体、实时画面鉴权、规则下发。
12. 跑通正式 App/H5：安装模式、日常首页、事件、规则、实时画面、图文消息卡片。
13. 跑通视觉模型产品化、真实家庭试点和商业化交付。

阶段切换原则：

- 上一阶段没有达到验收标准，不进入下一阶段。
- 没有形成用户可见价值的能力，不优先做花哨界面。
- 没有形成可重复部署方式的能力，不视为真正完成。
- 没有把数据层、算法层、规则层、视频层、展示层拆开，不进入后续扩张阶段。

### 4.5 面向正式产品的最小闭环定义

围绕“树莓派盒子作为本地视觉载体，App 运行在云端并支持任意网络访问”的目标，后续实施必须按以下最小闭环判断是否真正前进：

1. 本地盒子闭环：
   - 盒子能启动 `edge-agent`
   - 盒子能连接家庭 Wi-Fi
   - 首次安装时有手机可操作的 `/setup` 配网流程，且该页面不混入摄像头、算法、事件和日志
   - 盒子入网后可通过 `gohome.local/admin` 或局域网 IP 进入开发管理模式
   - `/admin` 具备登录保护，并能接入局域网 RTSP 摄像头
   - 盒子能本地生成事件、截图和状态
   - 盒子能通过 `/admin` 的算法预览能力展示单算法实时效果
   - 盒子能通过本地诊断页查看拉流、检测、报警和系统日志
   - 跌倒、火灾候选等高优先级事件有测试报警和应急动作
2. 设备上云闭环：
   - 盒子具备设备 ID、设备密钥和绑定码
   - 盒子能主动连云、发送心跳、上报事件、上传媒体
   - 云端能追踪设备在线状态和最近事件
3. 远程使用闭环：
   - 用户手机退出配网页后，改走正式 App 登录
   - App 不依赖局域网地址
   - App 通过云端查看设备状态、实时画面、事件和规则
   - 用户在任意网络下都能继续使用

当前阶段只允许宣称“完成了本地盒子闭环”，不能把它表述成“已经完成远程家庭版产品”。

### 4.5.1 当前产品路径校正

当前第一版产品路径必须按“App 和盒子都连云端”理解，不能把局域网本地服务器当成最终形态。

正确路径：

1. 树莓派首次通电后进入 Wi-Fi 配网。
2. 手机连接 `GoHome-XXXX` 热点，打开盒子本地 `/setup`，只完成家庭 Wi-Fi 配网。
3. 配网成功后，手机回到家庭网络或任意网络，打开 `回家` App。
4. App 登录云端账号，创建家庭和老人资料。
5. App 通过云端生成绑定码或绑定凭证，把树莓派设备绑定到家庭。
6. App 内完成摄像头配置；云端保存摄像头配置版本。
7. 树莓派主动连接云端，拉取摄像头配置并在本地完成扫描、测试、拉流和检测。
8. 树莓派把摄像头状态、心跳、事件、截图和诊断摘要上传到云端。
9. App 在任意网络下只读云端数据，不直连树莓派局域网地址，也不直连摄像头 RTSP。

边界：

- `/setup` 可以是盒子本地 Web，不要求第一版放进 App。
- `/setup` 只做 Wi-Fi 配网，不做账号、家庭、设备绑定、摄像头配置、算法和事件。
- `/admin` 只给开发、安装和售后调试，不作为普通家属端入口。
- `local-app-server` 只允许作为云端 App API 的本地开发替身；正式产品路径必须部署到云端。

### 4.6 当前推荐执行步骤

基于当前项目状态，执行顺序明确为：

1. 先完成本地盒子闭环，不直接铺完整云端。
2. 本地盒子闭环通过后，只上最小云，不做大全套平台。
3. 最小云跑通后，再让正式 App/H5 改走云端。

原因：

- 当前最大风险仍在盒子稳定性、RTSP 兼容、检测链路和 24 小时运行。
- 如果本地链路不稳，提前铺云会把盒子问题、网络问题、云端问题和 App 问题叠在一起。
- 当前最优策略是先把“盒子能不能独立跑”做成硬结果，再补“用户能不能异地使用”。

对应执行动作：

第一段，先盒子侧跑通：

1. 在树莓派上启动 `edge-agent`。
2. 完成盒子初始化：生成设备身份、本地密钥、管理员初始凭证、hostname / mDNS 名称、数据目录和日志目录。
3. 完成盒子基础联网和运行检查；开发阶段可先用 Pi Imager，产品化必须补 Wi-Fi 热点配网。
4. 将 `/setup` 收口成手机配网页，只验证热点、选网、输密码、连接中断提示、成功后地址提示。
5. 将 `/admin` 收口成开发管理模式，验证登录、管理地址、设备状态、网络状态和服务状态。
6. 在 `/admin` 接入一路真实 RTSP 摄像头并完成扫描、测试、保存、启停和删除。
7. 将实时画面和抓帧固定到 H.264 / 720p 子码流优先，验证延迟、花屏和断流恢复。
8. 跑通统一实时感知：选择一个摄像头后同时查看全部视觉结果。
9. 做本地日志诊断，覆盖服务、拉流、检测、报警、CPU、温度、磁盘和上传队列。
10. 做事件归并、频控和高优先级报警测试。
11. 跑通至少一个真实通知或报警通道。
12. 验证重启恢复、自启和 24 小时稳定性。

第二段，再上最小云。这里的“最小云”必须是 App 和树莓派都能从外网访问的云端服务，本地局域网服务器只作为开发替身：

1. 先做 `identity / family / device / camera-config / event / media` 的最小子集。
2. 跑通 App 云端登录、家庭、老人资料和设备绑定。
3. 跑通树莓派主动连云、心跳、配置拉取和同步状态回传。
4. 跑通 App 摄像头配置 -> 云端保存版本 -> 树莓派拉取应用 -> App 展示同步结果。
5. 跑通事件上报、事件列表、事件详情、事件处理状态同步。
6. 跑通截图或短视频片段上传与授权访问。
7. 跑通实时画面的播放会话和播放鉴权。

第三段，最后切正式用户端：

1. App/H5 不再读取局域网地址。
2. App/H5 统一改走云端 API。
3. 用户在任意网络下查看设备状态、告警、媒体和实时画面。

## 5. 阶段 0：树莓派盒子本地闭环

目标：

- 用树莓派证明“家庭盒子上电 -> 联网 -> 局域网摄像头 -> 本地视觉检测 -> 规则判断 -> 事件 -> 本地预览 / 日志 -> 报警测试”的技术链路成立。
- Mac 已完成开发基线验证，后续只作为开发对照和问题排查环境。

### 5.1 要完成的能力

- 树莓派前台启动 `edge-agent` 并完成 `systemd` 自启。
- RTSP 摄像头接入验证，当前主摄像头为 `192.168.1.11:554`，优先使用 H.264 / 720p 子码流。
- 实时画面默认提供 720p 档位，先降低延迟和花屏风险。
- YOLO 模式下输出人形数量、检测框、置信度和模型信息。
- 黑屏、离线、无变化、无人、疑似跌倒候选事件。
- 页面端实时画面能力可跑通。
- `/setup` 支持手机优先的配网流程，不暴露摄像头、算法、事件和日志。
- `/admin` 支持登录、网络状态、摄像头配置、算法配置、事件和截图。
- `/admin` 支持选择摄像头并在一个真实画面查看全部视觉效果。
- `/admin` 支持查看服务、拉流、检测、报警和系统状态。
- 跌倒和火灾候选支持测试报警和应急动作展示。
- 临时通知或报警通道能真实推到手机或完成可验证触达。

### 5.2 当前下一步

按顺序做：

1. 树莓派前台启动 `edge-agent`，确认 `/health`、`/admin` 和 `/ui` 可打开。
2. 安装 `systemd` 并验证重启恢复。
3. 接入一路真实 RTSP 摄像头，优先 H.264 / 720p 子码流。
4. 跑通实时画面、抓帧、规则评估、事件列表和事件详情。
5. 做手机优先 `/setup` 配网页，只保留 Wi-Fi 配网和成功提示。
6. 做本地 `/admin` 开发管理模式，补齐登录、摄像头配置、算法预览和日志诊断。
7. 验证 `gohome.local/admin` 和局域网 IP 两种进入方式。
8. 补齐跌倒候选、火灾候选、用餐候选、久坐/静止、夜间活动等演示级算法预览。
9. 将检测链路拆成 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event`，并补事件归并和频控。
10. 配置一个真实通知或报警通道，完成至少一次送达或可验证触达。

### 5.2.1 树莓派到货后的执行顺序

树莓派到位后，阶段 0 按下面顺序执行：

1. 上电、散热、存储和网络检查。
2. 拉起 `edge-agent` 前台运行，确认页面和接口可打开。
3. 配置 `.env` 并确认端口、检测后端和数据目录正确。
4. 接入一路 RTSP 摄像头，完成测试、保存和启用。
5. 打开 `/setup` 验证配网流程不暴露摄像头、算法、事件和日志。
6. 打开 `/admin` 验证登录、设备状态、网络状态和管理入口。
7. 在 `/admin` 打开统一实时感知，并确认能看到服务、摄像头、人物、姿态、场景、风险状态和报警日志。
8. 触发至少一条真实事件，确认截图、事件详情和规则解释可读。
9. 触发一次跌倒或火灾候选的测试报警，确认应急动作可见。
10. 配置一个真实通知通道并完成送达。
11. 安装 `systemd`，验证重启恢复。
12. 开始 24 小时观察。

阶段 0 完成前，不进入正式云端开发。

### 5.2.2 树莓派逐条验收清单

明天实际执行时，按下面清单逐条打勾：

#### A0. 盒子初始化

1. 生成或读取唯一设备 ID。
2. 生成本地设备密钥。
3. 设置管理员账号：开发阶段固定为 `admin / 123456`。
4. 设置 hostname / mDNS 名称，如 `gohome.local` 或带序列号后缀的名称。
5. 创建数据目录、日志目录和初始化标记。
6. 确认恢复出厂入口的设计，不依赖树莓派本体按钮完成产品级初始化。

通过信号：

- 能看到设备 ID 和本地管理地址
- `/admin` 登录规则明确，开发阶段默认账号为 `admin / 123456`
- 当前开发演示盒子允许初始密码直接登录；正式交付时再开启首次改密要求。
- 重启后初始化状态不会丢失
- 清除初始化标记后能重新进入初始化流程

执行命令：

```bash
bash scripts/init-box.sh init
```

需要重置开发阶段管理密码时：

```bash
bash scripts/init-box.sh reset-admin
```

需要做白纸测试时，不新建第二个项目目录，只在原 `edge-agent` 目录内移动旧运行数据并重新初始化：

```bash
sudo bash scripts/reset-runtime-data.sh --preserve-admin
```

该命令保留代码、`.venv`、`.env`、systemd、设备 ID 和 admin 密码，只清空本地数据库、摄像头、事件、截图、对象上传和算法运行状态。完整出厂化开发测试才使用：

```bash
sudo bash scripts/reset-runtime-data.sh --factory
```

#### A. 硬件与系统

1. 电源稳定，散热方案已装好。
2. 系统已启动，网络可用。
3. `python3`、`ffmpeg`、`git`、`curl` 已安装。
4. 仓库已放到固定目录，`.venv` 已创建。
5. `.env` 已复制并按当前口径填写。

通过信号：

- `python3 --version`
- `ffmpeg -version`
- `curl http://127.0.0.1:8711/health`

#### B. 服务启动

1. `./run.sh` 能前台启动。
2. `admin/index.html` 可打开。
3. `ui/index.html` 可打开。
4. 数据目录和日志目录正常生成。

通过信号：

- `/health` 正常返回
- `data/agent.db` 已创建
- 页面无白屏、无启动即崩溃

#### C. 配网与管理入口

1. `/setup` 在手机视口可打开。
2. `/setup` 只展示 Wi-Fi 配网，不展示摄像头、算法、事件和日志。
3. 配网成功页能提示手机回到家庭 Wi-Fi 或打开 `回家` App。
4. `/admin` 作为开发者 / 安装人员模式单独访问，不从普通配网页引导。

通过信号：

- `http://10.42.0.1` 或开发环境等价入口可打开
- 页面只有选网、密码、连接、重新扫描和成功提示
- 切换 Wi-Fi 后页面把断连视为预期状态，不显示误导性失败

#### D. 开发管理模式

1. 家庭网络下可访问 `http://gohome.local/admin` 或局域网 IP。
2. 管理端具备登录保护，初始用户名和密码规则清楚。
3. 首页能看到网络、IP、服务、CPU、温度、磁盘和云连接状态。
4. 管理端不面向普通用户入口暴露。

通过信号：

- `/admin` 可登录
- 页面能显示当前 IP 和服务状态
- 退出登录或无凭证时不能直接进入管理功能

#### E. 摄像头接入

1. 接入一路真实 RTSP 摄像头。
2. 测试接口返回成功。
3. 保存后摄像头状态为启用。
4. 能抓到首帧截图。
5. 优先使用 H.264 / 720p 子码流，记录延迟、FPS 和花屏情况。

通过信号：

- `/admin` 可完成添加、测试、保存
- `POST /api/cameras/{camera_id}/test` 成功
- `POST /api/cameras/{camera_id}/capture` 成功

#### F. 视觉预览和产品主链

1. 管理端选择一个摄像头，在同一真实画面预览全部视觉结果。
2. 预览能显示实时画面、检测框或状态、置信度、阈值和最近日志。
3. `watch.html` 能打开实时画面。
4. `monitor.html` 能显示真实状态。
5. `events.html` 能显示真实事件列表。
6. `event_detail.html` 能看到截图和解释字段。

通过信号：

- 至少有一条真实截图
- 至少有一条真实事件
- 详情页能读到时间、房间、原因或规则解释
- 管理端至少一个算法预览可用

#### G. 通知闭环

1. 在生产云配置 APNs，不在盒子配置通知通道。
2. 盒子触发一次真实事件并通过持久队列上行。
3. 云端按事件幂等键生成一条消息和一次 APNs 投递，手机收到并回执。

通过信号：

- 盒子数据库和环境中没有 APNs 私钥、Push Token 或通知投递表
- 云端同一事件只有一条消息和一条投递记录
- 手机能看到通知并进入正确原生详情

#### H. 自启与恢复

1. 安装 `systemd` 服务。
2. 手动重启服务后恢复正常。
3. 机器重启后服务自动恢复。

通过信号：

- `systemctl status gohome-edge-agent` 正常
- 重启后页面仍能打开
- 摄像头无需手工重新添加

#### I. 24 小时观察

1. 无持续崩溃重启。
2. 摄像头持续在线。
3. 事件链路未中断。
4. 温度、磁盘、内存可接受。

通过信号：

- `journalctl` 无明显 crash loop
- `vcgencmd measure_temp` 在可接受范围
- `df -h`、`free -h` 正常

### 5.2.3 树莓派当天命令清单

下面这组命令按顺序执行，目标是当天把阶段 0 盒子闭环跑起来：

#### A. 系统准备

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git curl jq rsync
sudo apt install -y htop iotop
```

#### B. 拉取仓库与 Python 环境

```bash
cd /home/pi
git clone <your-repo-url> gohome
cd /home/pi/gohome/edge-agent
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

如果当天需要一起验证 YOLO，再补：

```bash
cd /home/pi/gohome/edge-agent
./.venv/bin/pip install -r requirements-yolo.txt
```

#### C. 配置与前台启动

```bash
cd /home/pi/gohome/edge-agent
cp .env.example .env
sed -n '1,120p' .env
./run.sh
```

前台启动后优先检查：

```bash
curl http://127.0.0.1:8711/health
curl -I http://127.0.0.1:8711/setup/network.html
curl -I http://127.0.0.1:8711/admin/index.html
```

#### D. 摄像头与主链验证

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/1/test
curl -X POST http://127.0.0.1:8711/api/cameras/1/capture
curl 'http://127.0.0.1:8711/api/events?limit=10'
```

这里的 `camera_id` 需要换成树莓派当天真实保存成功后的那一路摄像头。

#### E. 通知测试

盒子不执行测试通知。先确认事件进入本地上传队列，再在生产云使用受运维鉴权的通知测试或真实事件路径验收 APNs。

#### F. 安装 systemd

```bash
cd /home/pi/gohome/edge-agent
bash scripts/install-systemd-service.sh
sudo systemctl status gohome-edge-agent --no-pager
sudo systemctl restart gohome-edge-agent
sudo systemctl enable gohome-edge-agent
```

#### G. 24 小时观察命令

```bash
journalctl -u gohome-edge-agent -n 200 --no-pager
journalctl -u gohome-edge-agent -f
free -h
df -h
uptime
vcgencmd measure_temp
```

### 5.3 验收标准

- 运行 30 分钟无服务崩溃。
- RTSP 摄像头能稳定拉到首帧和周期截图。
- Web 页面能展示真实状态。
- Web 页面能打开实时画面。
- 管理台能完成基础配置。
- 手机能收到至少一条真实通知。
- Mac 重启后服务可恢复，日志能定位问题。

### 5.4 任务拆解顺序

阶段 0 不再按页面零散推进，而是按闭环顺序推进：

1. 运行固化：统一启动命令、配置入口、数据目录、日志目录。
2. 摄像头闭环：`connect.html` 添加、测试、保存、启用真实 RTSP 摄像头。
3. 规则闭环：`rules.html` 读取、修改、保存真实规则。
4. 事件闭环：旧测试事件清理，当前启用摄像头事件单独展示。
5. 算法解释闭环：检测框、置信度、模型版本、命中原因写入数据并展示。
6. 实时画面闭环：页面端通过后端视频能力查看实时画面。
7. 通知闭环：至少一个真实通知通道能触发到手机。
8. 守护闭环：开机自启、watchdog、状态诊断、日志轮转可复现。

### 5.5 阶段 0 出口物

只有以下产物全部具备，阶段 0 才算完成：

- 一条可复现的启动命令和默认运行配置。
- 一套真实摄像头接入流程，不依赖手工改数据库。
- 一套真实规则配置流程，不依赖 curl。
- 一条可解释事件，带截图、检测结果、规则命中原因。
- 一套页面端实时画面流程，不能只在后台调试页可用。
- 一条真实送达的手机通知记录。
- 一份本地运行问题排查方式。

## 6. 阶段 1：边缘端产品化

目标：

- 把现在的 `edge-agent` 从开发服务改造成可部署、可维护、可升级的边缘端运行时。

### 6.1 工程拆分

将 edge-agent 内部拆成：

- `device-agent`：设备身份、云端连接、心跳。
- `camera-agent`：摄像头配置、ONVIF、RTSP、断线恢复。
- `stream-agent`：拉流、抽帧、缓存、短视频切片。
- `live-agent`：实时画面转发、码流选择、会话限流。
- `vision-agent`：图像质量、YOLO、人形、姿态。
- `rule-agent`：规则计算、时间窗、区域和阈值。
- `event-agent`：事件生成、去重、节流、补传。
- `media-agent`：截图、短视频、本地留存和上传。
- `update-agent`：远程升级、模型升级、回滚。
- `watchdog`：进程保活、磁盘清理、异常恢复。

### 6.2 数据结构升级

边缘端需要保留本地 SQLite，但结构要向云端对象对齐：

- `devices`
- `cameras`
- `rules`
- `frames`
- `detection_results`
- `event_candidates`
- `events`
- `media_assets`
- `sync_queue`
- `agent_logs`

### 6.3 设备能力

要做：

- 设备唯一 ID。
- 设备密钥。
- 本地配置文件。
- 开机自启。
- 日志轮转。
- 磁盘占用限制。
- 网络恢复后补传。
- 服务崩溃自动重启。
- 模型文件版本管理。

### 6.3.1 盒子安装闭环

阶段 1 需要把“拿到盒子后如何落地到家庭”明确成可执行安装流程：

1. 盒子首次启动进入待配网状态。
2. 安装人员或家属通过 `/setup` 完成家庭 Wi-Fi 配网；`/setup` 不做摄像头、算法和日志。
3. 盒子联网后，安装人员通过 `gohome.local/admin` 或局域网 IP 登录开发管理模式。
4. `/admin` 完成 RTSP 摄像头扫描、接入、测试、保存和启用。
5. `/admin` 完成算法开关、统一实时感知、报警测试和日志诊断。
6. 盒子向云端完成设备注册或激活，并被绑定到某个家庭。
7. 盒子开始稳定心跳、抓帧、检测和事件上报。

这一步的交付物不是单个页面，而是一套可重复执行的安装 SOP。

### 6.3.2 设备注册 / 绑定 / 心跳状态机

设备状态必须明确，避免后续接口和页面各自理解。

```text
factory_new
-> wifi_config_pending
-> registered
-> activation_pending
-> bound
-> online
-> offline
```

状态说明：

- `factory_new`
  - 刚出厂或刚刷机
  - 还没有设备身份
- `wifi_config_pending`
  - 盒子等待配网
  - 还不能进入正式用户流程
- `registered`
  - 已向云端注册
  - 已拿到 `device_id`
  - 但还没有归属家庭
- `activation_pending`
  - 已经展示绑定码或等待激活
  - 等待某个家庭完成绑定
- `bound`
  - 设备已归属家庭
  - 已具备访问控制语义
- `online`
  - 最近心跳有效
  - 可以接收配置、上报事件和提供播放会话
- `offline`
  - 心跳超时或服务不可达
  - 仍保留绑定关系，但对用户显示离线

状态迁移规则：

1. 首次上电：`factory_new -> wifi_config_pending`
2. 配网成功并完成注册：`wifi_config_pending -> registered`
3. 生成绑定码后等待家庭激活：`registered -> activation_pending`
4. 家庭完成绑定：`activation_pending -> bound`
5. 首次成功心跳：`bound -> online`
6. 心跳超时：`online -> offline`
7. 离线恢复并重新心跳：`offline -> online`

异常约束：

- 未到 `registered`，不允许上报正式事件。
- 未到 `bound`，不允许暴露给家属端列表。
- `offline` 不等于解绑，不能自动丢失家庭关系。
- 解绑必须走显式用户动作，不能由心跳超时触发。

### 6.4 验收标准

- 断网后本地继续检测。
- 网络恢复后补传事件。
- 进程崩溃后自动恢复。
- 设备重启后自动启动。
- 本地日志能定位拉流、模型和通知问题。

### 6.5 阶段 1 出口物

- `edge-agent` 具备设备 ID、配置文件、日志目录和状态接口。
- 关键进程具备自动拉起能力。
- 事件和媒体具备本地缓存和补传队列。
- 设备已经不依赖 IDE 手工启动，能按设备方式运行。

## 7. 阶段 2：云端和 API 中台

目标：

- 建立商业化产品必需的云端业务平台，使 App 不直接访问家庭局域网设备。

### 7.1 云端服务拆分

优先实现：

- `identity-service`：用户、家庭、角色。
- `device-service`：设备注册、绑定、心跳、版本。
- `camera-service`：摄像头配置、状态、房间。
- `video-service`：实时画面会话、播放鉴权、码流控制。
- `rule-service`：规则模板、家庭规则、设备下发。
- `event-service`：事件入库、查询、状态机。
- `media-service`：截图、短视频、访问授权。
- `notification-service`：App 推送、短信、Webhook。
- `message-service`：回家消息、陪伴消息、解释消息生成。
- `log-service`：边缘端日志摘要、推送回执、审计日志接入。

后续补：

- `model-service`：模型版本、灰度、回滚。
- `ops-service`：运营后台、报表、审计。
- `billing-service`：套餐、订单、订阅。

### 7.2 设备通信

要做：

- 设备注册 API。
- 设备 token。
- 心跳上报。
- 配置拉取。
- 事件上报。
- 媒体上传。
- 日志上报。
- WebSocket 或 MQTT 设备通道。

原则：

- edge-agent 主动连云端。
- 不要求老人家有公网 IP。
- 不暴露 RTSP 到公网。
- 云端不直接拉家庭摄像头。

### 7.2.1 远程访问最小范围

阶段 2 只做支撑正式远程使用所必需的能力：

- 设备在线状态和最近心跳。
- 设备绑定后的家庭可见性控制。
- 事件上报、事件查询和事件状态同步。
- 截图或短视频片段上传与授权访问。
- 实时画面播放会话和播放鉴权。

不在这个阶段做的内容：

- 公网直暴露 RTSP。
- 复杂多端聊天或社交功能。
- 大而全的运营系统。

### 7.2.2 最小云第一批接口

最小云第一批只做能支撑“盒子上云 + 用户远程可用”的接口，不扩张。

#### 设备身份

- `POST /api/v1/devices/register`
  - 用途：盒子首次注册，获取 `device_id`
- `POST /api/v1/devices/activate`
  - 用途：用绑定码或激活码把设备挂到家庭
- `POST /api/v1/devices/heartbeat`
  - 用途：上报在线状态、版本、IP、最近时间
- `GET /api/v1/devices/{device_id}`
  - 用途：查询设备状态和绑定关系

#### 事件链路

- `POST /api/v1/devices/{device_id}/events`
  - 用途：盒子上报结构化事件
- `GET /api/v1/app/events`
  - 用途：家属端读取事件列表
- `GET /api/v1/app/events/{event_id}`
  - 用途：家属端读取事件详情
- `PATCH /api/v1/app/events/{event_id}`
  - 用途：确认、误报、已处理等状态回写

#### 媒体与播放

- `POST /api/v1/devices/{device_id}/media`
  - 用途：上传截图或短视频片段
- `GET /api/v1/app/media/{media_id}`
  - 用途：获取媒体元数据
- `POST /api/v1/app/playback-sessions`
  - 用途：签发短时播放票据
- `GET /api/v1/app/streams/{camera_id}`
  - 用途：基于播放票据拉取被授权实时流

#### 第一批接口的完成定义

只有满足下面四点，才算“最小云第一批完成”：

1. 盒子能注册、激活并稳定心跳。
2. 盒子能把真实事件和截图上报到云端。
3. 用户不在老人家局域网时，仍能通过云端读事件列表和详情。
4. 用户不暴露 RTSP 和局域网地址，也能拿到被授权的媒体和实时画面。

### 7.2.3 最小云接口字段草案

下面是第一批接口的最小字段口径，优先保证盒子和 App 可以对齐，不追求一次做全。

#### `POST /api/v1/devices/register`

请求体：

```json
{
  "device_name": "gohome-pi-001",
  "hardware_model": "raspberry-pi-5-8gb",
  "software_version": "0.1.0",
  "lan_ip": "192.168.1.20"
}
```

响应体：

```json
{
  "device_id": "dev_xxx",
  "device_secret": "sec_xxx",
  "status": "registered"
}
```

#### `POST /api/v1/devices/activate`

请求体：

```json
{
  "device_id": "dev_xxx",
  "binding_code": "FQ4SNX"
}
```

响应体：

```json
{
  "device_id": "dev_xxx",
  "family_id": "fam_xxx",
  "status": "bound"
}
```

#### `POST /api/v1/devices/heartbeat`

请求体：

```json
{
  "device_id": "dev_xxx",
  "status": "online",
  "lan_ip": "192.168.1.20",
  "software_version": "0.1.0",
  "camera_count": 1,
  "detector_backend": "basic"
}
```

响应体：

```json
{
  "ok": true,
  "server_time": "2026-07-01T10:00:00Z"
}
```

#### `POST /api/v1/devices/{device_id}/events`

请求体：

```json
{
  "camera_id": "cam_xxx",
  "event_type": "no_person",
  "occurred_at": "2026-07-01T10:00:00Z",
  "room": "客厅",
  "severity": "medium",
  "reason": "连续 300 秒未检测到人",
  "snapshot_id": "media_xxx"
}
```

响应体：

```json
{
  "event_id": "evt_xxx",
  "accepted": true
}
```

#### `POST /api/v1/devices/{device_id}/media`

请求体：

```json
{
  "media_type": "snapshot",
  "file_name": "snapshot-001.jpg",
  "content_type": "image/jpeg"
}
```

响应体：

```json
{
  "media_id": "media_xxx",
  "upload_url": "https://example.com/upload",
  "expires_in": 300
}
```

#### `GET /api/v1/app/events`

响应体：

```json
{
  "items": [
    {
      "event_id": "evt_xxx",
      "event_type": "no_person",
      "room": "客厅",
      "occurred_at": "2026-07-01T10:00:00Z",
      "severity": "medium",
      "status": "open"
    }
  ]
}
```

### 7.2.4 最小云核心对象 schema 草案

为了避免接口先写了、对象语义后面对不上，第一批先固定这些核心对象。

#### Device

```json
{
  "device_id": "dev_xxx",
  "family_id": "fam_xxx",
  "device_name": "gohome-pi-001",
  "hardware_model": "raspberry-pi-5-8gb",
  "software_version": "0.1.0",
  "status": "online",
  "lan_ip": "192.168.1.20",
  "camera_count": 1,
  "last_heartbeat_at": "2026-07-01T10:00:00Z",
  "created_at": "2026-07-01T09:00:00Z"
}
```

#### Event

```json
{
  "event_id": "evt_xxx",
  "device_id": "dev_xxx",
  "camera_id": "cam_xxx",
  "event_type": "no_person",
  "room": "客厅",
  "severity": "medium",
  "status": "open",
  "reason": "连续 300 秒未检测到人",
  "occurred_at": "2026-07-01T10:00:00Z",
  "snapshot_id": "media_xxx"
}
```

#### MediaAsset

```json
{
  "media_id": "media_xxx",
  "device_id": "dev_xxx",
  "camera_id": "cam_xxx",
  "media_type": "snapshot",
  "content_type": "image/jpeg",
  "file_name": "snapshot-001.jpg",
  "storage_key": "devices/dev_xxx/media/snapshot-001.jpg",
  "created_at": "2026-07-01T10:00:00Z"
}
```

#### PlaybackSession

```json
{
  "session_id": "play_xxx",
  "device_id": "dev_xxx",
  "camera_id": "cam_xxx",
  "viewer_user_id": "usr_xxx",
  "playback_ticket": "ticket_xxx",
  "expires_at": "2026-07-01T10:05:00Z"
}
```

#### 字段约束

- `device_id`、`event_id`、`media_id`、`session_id` 统一用服务端生成的稳定 ID。
- `status` 必须是枚举值，不能页面自己随便拼字符串。
- `occurred_at`、`created_at`、`last_heartbeat_at` 统一用 ISO8601 UTC 时间。
- `snapshot_id` 指向 `MediaAsset.media_id`，不直接在事件对象里塞文件路径。

### 7.2.5 第一批开发任务顺序

最小云第一批按下面顺序开发，不并行大扩张：

#### T1 设备身份

1. 建 `Device` 表和状态枚举。
2. 实现 `POST /api/v1/devices/register`。
3. 实现 `POST /api/v1/devices/activate`。
4. 实现 `POST /api/v1/devices/heartbeat`。
5. 实现 `GET /api/v1/devices/{device_id}`。

完成信号：

- 盒子能从 `registered` 进入 `bound`。
- 心跳能把设备状态推到 `online / offline`。

#### T2 事件对象

1. 建 `Event` 表和状态枚举。
2. 实现 `POST /api/v1/devices/{device_id}/events`。
3. 实现 `GET /api/v1/app/events`。
4. 实现 `GET /api/v1/app/events/{event_id}`。
5. 实现 `PATCH /api/v1/app/events/{event_id}`。

完成信号：

- 盒子能把真实事件送到云端。
- 家属端能读到事件列表、详情并修改状态。

#### T3 媒体对象

1. 建 `MediaAsset` 表。
2. 实现 `POST /api/v1/devices/{device_id}/media` 预签名或上传地址下发。
3. 实现 `GET /api/v1/app/media/{media_id}`。
4. 让 `Event.snapshot_id` 和 `MediaAsset` 打通。

完成信号：

- 事件详情能读到授权后的截图。

#### T4 播放会话

1. 建 `PlaybackSession` 表或短期票据服务。
2. 实现 `POST /api/v1/app/playback-sessions`。
3. 实现 `GET /api/v1/app/streams/{camera_id}` 的播放鉴权。

完成信号：

- 用户离开局域网后仍能通过云端打开被授权的实时流。

#### T5 边缘端接入改造

1. `edge-agent` 新增设备注册和心跳上报客户端。
2. `edge-agent` 新增事件上报客户端。
3. `edge-agent` 新增媒体上传客户端。
4. 当前本地 token 方案保持兼容，但逐步迁到云端设备身份体系。

完成信号：

- 本地模式仍可跑。
- 云端模式已经可以跑通最小远程闭环。

#### T6 日志与诊断链路

在最小云第一批主链稳定后，优先补日志链路：

1. 增加设备日志摘要上报接口。
2. 增加推送送达与失败回执记录。
3. 增加用户关键动作审计日志。
4. 在运营侧提供最小诊断查询能力。

完成信号：

- 能回答“设备为什么离线”“为什么没出事件”“为什么推送没送达”。

#### T7 亲情关怀、回家消息与陪伴消息

亲情关怀是当前产品主线，不再作为纯后置增强；但必须分批做，不能一开始就引入不可控的全网内容推荐。

第一批 P0：每日关怀主链，本地闭环阶段就要做：

1. 定义 `MessageCandidate / CareCard / CarePreference` 对象。
2. 基于设备在线、摄像头同步、今日事件、生活节律、天气、日历和家庭资料生成每日关怀卡片。
3. 区分 `alert / explain / accompany / gohome / daily / content` 六类消息。
4. App 首页或亲情页展示“今日安心 / 今日关怀 / 建议联系”卡片。
5. 提供联系入口：打电话、发问候、记录已联系。
6. 在“我的”里提供“关怀推送”设置：每日汇总卡时间、是否开启、推送内容类型、内容区域、异常即时提醒、节日提前天数、纪念日提前天数、关怀重点、老人兴趣、上次回家日期和回家间隔阈值。

第一批完成信号：

- App 不只看到硬事件，也能看到“今天家里平稳”“建议打个电话”“天气降温，提醒添衣”这类可解释卡片。
- 不配置模型 API 时，模板规则仍能生成基础卡片。
- 卡片能说明来源，不凭空编造老人状态。
- `CarePreference.metadata.care_card_schedule` 能保存定时、内容类型、内容区域、关怀重点、回家间隔、纪念日和 `delivery_rules`，并进入每日卡片生成、天气和内容搜索上下文。
- 本地闭环只验证保存、立即生成和 App 展示。每日到点推送、异常即时推送和 APNs 送达由云端 scheduler / notification-service 实现。

第二批 P0.5：文本模型 API：

1. 新增 `model-service` provider 配置。
2. 对每日关怀上下文调用文本模型生成更自然的标题、正文和问候建议。
3. 记录 `provider / model / prompt_version / input_hash / output_status`。
4. 模型失败、超时或未配置时回退模板文案。

第二批完成信号：

- 同一张关怀卡片既有结构化事实，也有更自然的表达。
- 模型调用失败不影响安全事件和基础关怀卡片。

第三批 P1：生图卡片：

1. 新增 `image-service` provider 配置。
2. 支持平台侧配置 `wan2.7-image` 或等价生图模型。
3. 只为 `daily / accompany / gohome / festival` 生成非证据型配图。
4. 生成失败时回退默认卡片视觉，不影响消息展示。

第三批完成信号：

- 可生成温暖的问候卡片图，但告警证据仍只来自真实媒体资产。

第四批 P1.5：合规内容链接推荐：

1. 先支持用户手动订阅或人工白名单来源。
2. 保存 `ContentSource / ContentRecommendation`。
3. 只展示标题、来源、链接、摘要和推荐理由。
4. 加入频率控制和一键关闭。

第四批完成信号：

- App 可以推荐少量老人感兴趣的合规内容链接，但不抓取全文、不搬运视频。

第五批 P2：自动搜索自媒体视频、公众号文章和跨平台内容：

1. 接入合规公开 API、RSS、用户授权来源或内容合作来源。
2. 做内容安全、去重、兴趣匹配和推荐理由生成。
3. 明确版权和平台规则。
4. 评估是否推给家属、老人端或仅作为 App 内卡片。

第五批不进入当前本地闭环优先级。

当前执行状态：

- P0 的模板版 `CareCard`、偏好接口、平台模型能力只读状态接口和亲情页展示已经进入本地闭环。
- P0 的数据库迁移层已经补齐到 PostgreSQL schema、seed bundle 导出和反向还原校验。
- 模型底层能力不是用户配置项，平台方通过服务器环境变量或云端 Secret Manager / KMS 配置。
- 当前本地 `local-app-server` 已从根目录 `.env / .env.local` 读取平台模型配置；真实 key 只填本机 `.env`，不提交 git。
- P0.5 的多模态语言模型关怀卡片生成已经接入本地闭环，成功时写入 `model_generation_jobs`，失败时回退模板。
- P1 的 DashScope `wan2.7-image` 1:1 生图卡片已经接入本地闭环：
  - 生图使用平台侧 env，不暴露给普通用户配置。
  - 生成图会下载成本地 `media_asset`，`CareCard.image_url` 只保存本地媒体路径，不保存供应商临时 URL。
  - 首页和陪伴页优先展示 1:1 今日关怀图片，图片失败时保留文字卡兜底。
- 当前后台页只做平台内部只读状态检查，不给普通用户填写 key、Base URL、模型名或 Prompt。
- 下一步先做云端化前的数据和任务边界：本地 PostgreSQL 跑通后，把 `care_card_schedule` 接到云端 scheduler / push 任务。
- 白名单内容链接和自动内容搜索仍排在文本模型与生图主链之后。

##### T7.1 场景化图文消息输入域

`T7` 不只生成抽象消息，还需要在第二批接入这些输入域：

1. `ElderProfile`
   - 展示称呼、关系、城市、手机号、家里电话、生日、喜好、作息、敏感备注
2. `CalendarEvent`
   - 生日、节日、体检、复诊、回家计划
3. `WeatherSignal`
   - 雷暴雨、降温、高温、大风、空气质量
4. `ContactRecord`
   - 最近一次通话、消息或手动联系记录
5. `VisitRecord`
   - 最近一次回家、探访计划、已完成陪伴

阶段约束：

- `阶段 0` 允许本地 mock 或手动录入验证卡片展示。
- `阶段 2` 才把这些对象正式收进云端接口和存储。
- 这些输入域不允许抢跑在最小云第一批之前。

#### T8 通知结果与审计

在消息生成链路稳定后，补通知结果追踪和审计闭环：

1. 建 `NotificationReceipt` 表。
2. 建 `AuditLog` 表。
3. 打通推送回执写入。
4. 打通查看事件、查看媒体、开始播放、确认处理等关键动作审计。

完成信号：

- 能回答“推送是否真的到达”和“谁查看并处理过该事件/消息”。

#### T9 表结构、错误码与 OpenAPI 固化

在对象 schema 稳定后，立刻补最小契约固化层：

1. 建第一批表结构迁移草案。
2. 固化业务错误码枚举。
3. 为第一批 `/api/v1` 接口输出 OpenAPI 草案。
4. 把表结构、错误码和 schema 名互相对齐。

完成信号：

- 后续进入代码实现时，不再出现“对象名、表名、返回结构、错误语义各写各的”。

### 7.2.6 日志接口最小范围

最小日志链路先不做全量日志平台，只做必要诊断接口：

- `POST /api/v1/devices/{device_id}/logs`
  - 上报边缘端运行摘要、拉流错误、检测错误、同步错误
- `GET /api/v1/ops/devices/{device_id}/logs`
  - 运营或售后查询最近日志摘要
- `POST /api/v1/notifications/receipts`
  - 记录推送送达、点击、失败回执
- `POST /api/v1/audit/events`
  - 记录关键查看、确认、误报、播放等用户动作

第一版日志字段必须包含：

- `device_id`
- `log_type`
- `level`
- `message`
- `occurred_at`
- `context`

### 7.2.7 回家消息接口最小范围

回家消息、陪伴消息和每日关怀第一版不单独起复杂新系统，先落成最小接口：

- `POST /api/v1/internal/messages/generate`
  - 内部根据事件、节奏和规则生成消息候选
- `GET /api/v1/app/messages`
  - 家属端读取消息列表
- `GET /api/v1/app/messages/{message_id}`
  - 家属端读取消息详情
- `PATCH /api/v1/app/messages/{message_id}`
  - 标记已读、忽略、已处理
- `GET /api/v1/app/care-cards/today`
  - 家属端读取今日亲情关怀卡片
- `POST /api/v1/internal/care-cards/generate`
  - 内部根据设备状态、事件、天气、日历、联系记录和偏好生成今日卡片
- `GET /api/v1/families/{family_id}/care-preferences`
  - 读取亲情关怀偏好
- `PUT /api/v1/families/{family_id}/care-preferences`
  - 更新卡片频率、兴趣标签、生图开关、内容推荐开关、`metadata.care_card_schedule` 和 `delivery_rules`

第一版本地闭环只负责保存关怀推送配置、立即生成今日卡片和验证模型上下文。真正“每天到点自动推送”、异常即时推送、节日提前推送和纪念日提前推送放到云端阶段，由 scheduler / notification-service / APNs 统一执行，避免依赖本地电脑或局域网服务常驻。

消息对象最小字段：

- `message_id`
- `family_id`
- `elder_id`
- `message_type`
- `priority`
- `title`
- `body`
- `source_event_ids`
- `source_media_ids`
- `source_summary`
- `render_payload`
- `created_at`
- `status`

亲情关怀卡片最小字段：

- `card_id`
- `card_date`
- `card_type`
- `title`
- `body`
- `facts`
- `source_message_ids`
- `image_mode`
- `image_url`
- `actions`
- `status`

模型能力第一版接口：

- `GET /api/v1/model-providers`
  - 平台内部只读兼容接口，读取模型能力配置状态，不返回 API key 明文
- `PUT /api/v1/model-providers/{provider_id}`
  - 不开放给用户配置；模型底层配置由平台方通过服务器环境变量或云端 Secret Manager 管理
- `GET /api/v1/ops/service-config`
  - 平台内部后台页读取服务状态、存储类型、两类模型能力和密钥策略

第一版平台模型能力必须支持：

- 多模态语言模型：用于日历、热点、天气、事件、设备状态和老人资料生成每日关怀卡片。
- 生图模型：用于非证据型 1:1 温馨可爱漫画图文卡片，可配置 `wan2.7` 或等价模型。
- 本地开发：通过服务器环境变量配置 `base_url / api_key / model / prompt`。
- 云端部署：接 Secret Manager / KMS，业务数据库不保存明文 API key。
- 家属用户：只能配置老人资料、兴趣、提醒偏好和内容来源偏好，不能配置模型底层参数。

明确不在第一版做：

- 自动搜索全网视频。
- 未授权抓取公众号文章。
- 保存外部平台全文或视频文件。
- 给老人端直接推送未经家属确认的内容。

### 7.2.7.1 场景化图文消息第二批输入域接口

这批接口属于 `message-service` 的第二批输入域，应晚于最小消息主链：

- `GET /api/v1/families/{family_id}/elders/{elder_id}/profile`
- `PUT /api/v1/families/{family_id}/elders/{elder_id}/profile`
- `GET /api/v1/families/{family_id}/calendar-events`
- `POST /api/v1/families/{family_id}/calendar-events`
- `GET /api/v1/families/{family_id}/weather-signals`
- `GET /api/v1/families/{family_id}/contact-records`
- `POST /api/v1/families/{family_id}/contact-records`
- `GET /api/v1/families/{family_id}/visit-records`
- `POST /api/v1/families/{family_id}/visit-records`
- `GET /api/v1/families/{family_id}/content-sources`
- `POST /api/v1/families/{family_id}/content-sources`
- `GET /api/v1/families/{family_id}/content-recommendations`
- `POST /api/v1/internal/content-recommendations/generate`
- `GET /api/v1/model-generation-jobs/{generation_id}`

约束：

- 这批接口服务于 `MessageCandidate` 生成，不另起新的顶层消息对象。
- 用户端正式读取消息仍统一通过 `/api/v1/app/messages`。
- 场景化图文卡片属于 `MessageCandidate` 的渲染结果，不再单独开 `/api/v1/.../reminder-cards` 主接口。
- 内容推荐接口第一版只处理白名单或用户订阅来源，自动搜索全网内容放到 P2。

### 7.2.8 日志与消息对象 schema 草案

为了让 `message-service`、`notification-service`、`log-service` 和 App 一开始就按同一套语义开发，先固定下面四个对象。

#### MessageCandidate

```json
{
  "message_id": "msg_xxx",
  "family_id": "fam_xxx",
  "device_id": "dev_xxx",
  "message_type": "gohome",
  "priority": "medium",
  "title": "这周可以回家看看",
  "body": "最近 12 天没有回去，客厅晚间活动明显减少。",
  "source_event_ids": ["evt_xxx"],
  "source_media_ids": ["media_xxx"],
  "generated_by": "rhythm_rule_v1",
  "subtitle": "她喜欢桂花糕，也喜欢你回家吃顿饭。",
  "facts": ["生日：7 月 2 日", "你上次回家：5 天前"],
  "image_mode": "generated",
  "image_url": "/cards/images/msg_xxx.png",
  "created_at": "2026-07-01T10:00:00Z",
  "status": "open"
}
```

补充说明：

- `subtitle`、`facts`、`image_mode`、`image_url` 属于卡片渲染辅助字段。
- 这些字段服务于“场景化图文消息卡片”，但不改变 `MessageCandidate` 作为正式主对象的定位。

#### DeviceLog

```json
{
  "log_id": "log_xxx",
  "device_id": "dev_xxx",
  "log_type": "stream_error",
  "level": "error",
  "message": "RTSP read timeout",
  "occurred_at": "2026-07-01T10:00:00Z",
  "context": {
    "camera_id": "cam_xxx",
    "retry_count": 3
  }
}
```

#### NotificationReceipt

```json
{
  "receipt_id": "rcp_xxx",
  "notification_id": "ntf_xxx",
  "channel": "apns",
  "receipt_type": "delivered",
  "provider_message_id": "apns_msg_xxx",
  "occurred_at": "2026-07-01T10:00:00Z",
  "detail": {
    "device_token_suffix": "9ab3"
  }
}
```

#### AuditLog

```json
{
  "audit_id": "adt_xxx",
  "actor_type": "user",
  "actor_id": "usr_xxx",
  "action": "view_event_detail",
  "target_type": "event",
  "target_id": "evt_xxx",
  "occurred_at": "2026-07-01T10:00:00Z",
  "context": {
    "device_id": "dev_xxx"
  }
}
```

字段约束：

- `message_type` 固定为 `alert / explain / accompany / gohome`。
- `receipt_type` 固定为 `accepted / delivered / clicked / failed`。
- `context` 和 `detail` 允许扩展，但必须是结构化 JSON。
- 所有时间字段统一 ISO8601 UTC。

### 7.2.9 第一批数据库表结构草案

第一批云端不追求复杂分库，先以最小可迁移表结构为目标。

当前 `local-app-server/migrations/001_initial_schema.sql` 已按本地闭环和上云迁移需要落了第一版表结构：

1. 账号和家庭：
   - `users`
   - `families`
   - `family_members`
   - `elder_profiles`
2. 设备绑定与设备鉴权：
   - `devices`
   - `device_bindings`
   - `binding_codes`
   - `device_tokens`
3. 摄像头与看护规则：
   - `cameras`
   - `camera_secrets`
   - `care_rules`
4. 事件、媒体和设备同步：
   - `media_assets`
   - `events`
   - `device_heartbeats`
   - `calendar_events`
   - `device_config_versions`
5. 亲情关怀、模型和内容推荐预留：
   - `care_preferences`
   - `care_cards`
   - `model_providers`，仅作为平台模型能力元数据和历史兼容预留，不存普通用户配置或明文密钥
   - `model_generation_jobs`
   - `content_sources`
   - `content_recommendations`
6. 审计：
   - `audit_logs`

暂缓进入第一版 schema 的表：

- `message_candidates / message_candidate_sources`：等 CareCard、本地消息列表和文本模型输出稳定后再拆独立消息候选表。
- `notifications / notification_receipts`：等 APNs、短信或电话通道进入真实联调后再落。
- `device_logs`：短期仍走边缘端日志和健康摘要，运营后台成型时再独立建表。

最小索引要求：

- `devices.family_id`
- `devices.status`
- `events.device_id, occurred_at`
- `events.status`
- `media_assets.device_id, created_at`
- `message_candidates.family_id, created_at`
- `notifications.message_id`
- `notification_receipts.notification_id, occurred_at`
- `device_logs.device_id, occurred_at`
- `audit_logs.target_type, target_id, occurred_at`

### 7.2.10 错误码规范

第一批接口统一用“HTTP 状态码 + 业务错误码”双层表达。

通用错误码：

- `AUTH_REQUIRED`
- `PERMISSION_DENIED`
- `INVALID_ARGUMENT`
- `RESOURCE_NOT_FOUND`
- `CONFLICT`
- `RATE_LIMITED`
- `INTERNAL_ERROR`

设备链路错误码：

- `DEVICE_NOT_REGISTERED`
- `DEVICE_ALREADY_BOUND`
- `DEVICE_BINDING_CODE_INVALID`
- `DEVICE_BINDING_CODE_EXPIRED`
- `DEVICE_OFFLINE`
- `DEVICE_HEARTBEAT_STALE`

事件与媒体错误码：

- `EVENT_NOT_FOUND`
- `EVENT_STATUS_INVALID`
- `MEDIA_NOT_FOUND`
- `MEDIA_ACCESS_DENIED`
- `PLAYBACK_SESSION_EXPIRED`

消息与通知错误码：

- `MESSAGE_NOT_FOUND`
- `MESSAGE_STATUS_INVALID`
- `NOTIFICATION_CHANNEL_UNAVAILABLE`
- `NOTIFICATION_RECEIPT_INVALID`

日志与审计错误码：

- `DEVICE_LOG_INVALID`
- `AUDIT_EVENT_INVALID`

约束：

- 任何 4xx/5xx 都必须返回稳定 `code`，不能只返回自然语言。
- 同一业务错误在不同接口必须复用同一个 `code`。
- 页面提示文案由前端映射，不让后端错误文案直接决定用户表达。

### 7.2.11 OpenAPI 契约口径

从第一批云端接口开始，OpenAPI 必须与对象和阶段边界一起维护。

固定要求：

1. 所有正式接口统一在 `/api/v1`。
2. schema 名与核心对象保持一致，如 `Device`, `Event`, `MediaAsset`, `MessageCandidate`。
3. 每个写接口必须声明：
   - 鉴权方式
   - 请求体 schema
   - 成功响应 schema
   - 错误码列表
4. 每个读接口必须声明：
   - 列表过滤条件
   - 排序字段
   - 分页方式
   - 可见性约束
5. 设备端接口和 App 端接口分组展示，不混写。

建议的 tags：

- `Device API`
- `Event API`
- `Media API`
- `Message API`
- `Notification API`
- `Audit API`
- `Ops API`

统一响应包裹：

```json
{
  "request_id": "req_xxx",
  "data": {},
  "error": null
}
```

错误响应示例：

```json
{
  "request_id": "req_xxx",
  "data": null,
  "error": {
    "code": "DEVICE_BINDING_CODE_INVALID",
    "message": "binding code is invalid"
  }
}
```

### 7.3 API 管理

要做：

- `/api/v1` 版本规范。
- OpenAPI 文档。
- 用户 JWT。
- 设备 token。
- 角色权限。
- 审计日志。
- 限流。
- 幂等。
- 事件去重键。
- 错误码规范。

### 7.4 验收标准

- App 可以通过云端查询设备状态。
- App 和页面都可以通过云端打开被授权的实时画面。
- edge-agent 可以向云端上报心跳和事件。
- 事件状态能在多端同步。
- 媒体文件通过授权 URL 访问。
- API 有基础鉴权和文档。

### 7.5 阶段 2 最小交付范围

第一版云端只做商业化闭环必须能力，不做大而全后台：

- 用户注册、登录和家庭空间。
- 设备注册、绑定、解绑。
- 设备心跳和在线状态。
- 实时画面会话和播放鉴权。
- 事件上报、列表、详情、处理。
- 媒体上传和授权访问。
- 最少一个正式推送通道。

不在这个阶段扩张的内容：

- 复杂结算系统。
- 完整 CRM。
- 多层组织架构。
- 大规模报表平台。

## 8. 阶段 3：用户端 App / H5

目标：

- 形成真正面向家属的用户端，而不是管理台或调试页。

### 8.1 技术路径

建议顺序：

1. 继续用 Web / H5 验证产品流程和页面结构。
2. 先完成最小用户后端：注册、登录、用户身份、家庭空间、设备绑定。
3. 再做 WebView App 或 React Native / Flutter 原型。
4. 产品方向稳定后再评估原生 Swift。

不建议现在直接重投入 Swift 原生，因为当前主要风险仍在设备、云端和算法链路。

补充原则：

- 没有注册、登录、家庭和设备绑定后端之前，不进入正式 App 开发。
- 在用户后端完成前，可以继续做 Web/H5 原型，但其定位是流程验证，不是正式交付端。

### 8.2 页面范围

P0 用户端：

- 登录 / 注册。
- 家庭空间。
- 设备绑定。
- 首页状态摘要。
- 实时画面查看。
- 摄像头列表。
- 看护规则。
- 告警列表。
- 告警详情。
- 告警处理。
- 通知设置。

P1 用户端：

- 邀请家属。
- 处理记录。
- 告警升级。
- 联系老人。
- 多路实时画面切换。
- 设备安装向导。

### 8.3 验收标准

- 家属无需知道 RTSP、YOLO、端口等技术概念。
- 页面端和 App 端都能打开实时画面。
- 告警详情能解释为什么提醒。
- 处理按钮能回写云端状态。
- 多家属能看到一致事件状态。
- 推送点击能打开正确告警详情。

- 用户手机离开老人家局域网后仍能正常查看设备状态和事件。
- App 或 H5 不出现要求用户填写 RTSP、端口、局域网 IP 的操作。

### 8.4 App 推进顺序

用户端按以下顺序实现，不能一上来做全量 App：

1. 先完成最小用户后端：注册、登录、用户身份、家庭、设备绑定。
2. H5 版本再跑通：登录、绑定、首页、事件、规则、实时画面。
3. H5 跑通后封装为 WebView App 或跨端原型。
4. 当推送、绑定、事件处理、状态同步稳定后，再决定是否转原生。

当前原则：

- 先解决功能闭环，再讨论原生体验。
- 先让家属能收到并处理提醒，再讨论复杂陪伴能力。

## 9. 阶段 4：视觉模型产品化

目标：

- 让视觉能力从“YOLO 能跑”升级为可运营的算法产品。

### 9.1 模型路线

第一层：图像质量

- 亮度。
- 对比度。
- 清晰度。
- 遮挡。
- 黑屏。

第二层：YOLO 目标检测

- 人形检测。
- 人数统计。
- 检测框。
- 置信度。
- 场景物体扩展。

第三层：跟踪和时序

- 多帧 person tracking。
- 长时间无人。
- 长时间静止。
- 活动量下降。
- 区域停留。

第四层：姿态和行为

- RTMLib + RTMPose 主线，MoveNet / Hailo 备用。
- 坐、躺、倒地候选。
- 夜间异常活动。
- 疑似跌倒。

当前模型路线纠偏：

- 不继续把刚才未验证的 YOLO Pose 实验推进到主线。
- 先做视频性能修正，避免管理台预览和算法分析分别打开 RTSP。
- 再做 RTMLib + RTMPose POC，用真实实时帧输出骨架关键点、姿态摘要和跌倒候选依据。
- 如果 Pi5 CPU 帧率不够，再切 MoveNet；如果要产品化实时效果，再评估 Hailo AI HAT+。
- 没有样本库、误报反馈和标注规范前，不进入自训练。

### 9.2 算法工程

要做：

- 一算法一文件的模块组织。
- 模型输入输出标准。
- 检测结果表。
- 检测框可视化。
- 姿态、跌倒、图像质量、区域停留、夜间活动等算法后台可见。
- 模型版本和能力下发。
- CPU / GPU / NPU 性能评估。
- ONNX 导出。
- 量化方案。
- 模型版本号。
- 灰度发布。
- 回滚。

### 9.3 数据闭环

要做：

- 用户误报反馈。
- 告警样本留存。
- 标注规范。
- 训练集 / 验证集分离。
- 场景分类：客厅、卧室、厨房、玄关。
- 模型效果报表。

### 9.4 验收标准

- 每个事件都能看到命中的检测框、规则和时间窗。
- 模型版本可追踪。
- 误报反馈可进入样本库。
- 同一模型在不同硬件上有性能数据。

### 9.5 模型工作流

算法推进顺序：

1. 先把当前 YOLO 结果标准化并存证。
2. 再把算法拆成一算法一文件并形成统一输入输出。
3. 再补多帧时序、区域和时间窗规则。
4. 再补 RTMPose 或等价轻量姿态模型，升级跌倒和动作候选。
5. 最后做灰度、回滚和多硬件性能对比。

没有数据闭环前，不进入大规模模型优化。

### 9.6 算法后台要求

管理后台必须满足：

- 能看到当前启用了哪些算法。
- 能看到每种算法的版本号和关键阈值。
- 能看到每种算法最近一次或最近一批输出摘要。
- 能区分“检测框结果”和“姿态/行为/规则解释结果”。
- 不能把所有算法逻辑堆在单个文件或单个巨大类里。

## 10. 阶段 5：真实家庭试点

目标：

- 在树莓派盒子本地闭环、最小服务器和 App/H5 主链完成后，进入真实家庭连续运行验证。
- 这一阶段不是第一次把代码跑到树莓派，而是验证“一个家庭拿回去通电后能长期使用”。

### 10.1 硬件候选

优先顺序：

1. Raspberry Pi 5：当前盒子验证主设备，优先跑通安装、720p 拉流、自启、预览、日志和报警。
2. Raspberry Pi 5 + AI HAT+：需要本地高频视觉推理时验证。
3. Mac mini / N100 小主机：小批量家庭试点候选。
4. 工控机：稳定性试点。
5. 带 NPU 的低功耗盒子：产品化候选。
6. 当前 M4 / 24GB Mac：开发对照和问题排查环境，不作为交付硬件。

树莓派使用边界：

- 适合验证开机自启、低功耗、散热、断网恢复和长期运行。
- 适合低频抽帧、黑屏/离线/运动检测和轻量 YOLO。
- 适合当前阶段作为盒子侧主验证设备，但不作为重型算法训练或大模型开发机。
- 不建议直接用 2880x1620 主码流跑高频 YOLO，应优先使用低分辨率子码流或抽帧降采样。
- 如需更高频推理，再评估 AI HAT+、ONNX、NCNN、TFLite 或其他量化路线。

### 10.2 试点要求

要验证：

- 24 小时连续运行。
- 有线网络和 Wi-Fi。
- 断网恢复。
- 断电恢复。
- 摄像头兼容性。
- 多路摄像头性能。
- 发热和噪音。
- 本地存储寿命。
- 远程升级。

### 10.3 验收标准

- 7 天连续运行无人工干预。
- 摄像头断线恢复率可接受。
- 告警延迟可接受。
- 硬件温度和磁盘占用可控。
- 安装人员可以按 SOP 完成部署。

### 10.4 试点进入条件

必须同时满足：

- 树莓派盒子本地闭环已通过：自启、720p 拉流、事件、截图、预览、日志和报警测试。
- `/setup` 纯配网页、`/admin` 开发管理模式、算法预览和日志诊断已可用。
- 云端事件、设备身份、绑定、心跳、配置下发和媒体链路已跑通。
- H5/App 至少有一个家属端可用版本，且不依赖局域网地址。
- 页面端和 App 端实时画面都已通过鉴权链路打通。
- 真实通知或报警通道已经可用。
- 安装 SOP 和回收/排障流程已经写清楚。

## 11. 阶段 6：商业化运营

目标：

- 形成能销售、交付、运维和售后的产品体系。

### 11.1 运营后台

要做：

- 用户管理。
- 家庭管理。
- 设备管理。
- 摄像头状态。
- 告警质量。
- 模型版本。
- 推送送达率。
- 误报反馈。
- 工单。
- 审计日志。

### 11.2 交付体系

要做：

- 设备出厂绑定。
- 安装 SOP。
- 摄像头兼容清单。
- 网络要求。
- 隐私授权流程。
- 售后诊断流程。
- 数据留存和删除策略。

### 11.3 商业指标

要跟踪：

- 设备激活率。
- 首次安装成功率。
- 7 日设备在线率。
- 30 日家庭留存。
- 告警处理率。
- 误报率。
- 单设备售后工单数。
- 订阅转化率。

### 11.4 商业化最小交付包

商业化第一版不追求大而全，至少包含：

- 一台可运行的本地盒子或等价边缘设备。
- 一套家属端 H5/App。
- 一套设备绑定和安装流程。
- 一条正式通知链路。
- 一套售后诊断和日志查看方式。
- 一份隐私授权文本和媒体留存规则。
- 一个清晰的试点套餐或报价模型。

## 12. 当前开发优先级

现在不是直接做完整 App，也不是马上铺完整云端。树莓派已经到位后，当前重点调整为：先把树莓派盒子侧做成可配网、可管理、可接摄像头、可演示、可诊断的本地视觉盒子。

当前最合理顺序：

1. 在树莓派上跑稳 `edge-agent` 前台启动、`systemd` 自启和单路 RTSP 摄像头。
2. 把本地管理台重构为盒子开发管理模式，不再只是开发调试页。
3. 新增手机优先的 `/setup` 纯配网页。
4. 在 `/admin` 补齐统一实时感知能力，一个真实画面同时展示全部检测结果。
5. 在 `/admin` 补齐日志诊断能力。
6. 将算法预览覆盖到图像质量、人形检测、长时间无人、久坐/静止、跌倒候选、用餐候选、夜间活动、火灾候选、摄像头异常。
7. 做高优先级报警测试和应急处置动作，至少覆盖跌倒候选和火灾候选。
8. 做事件归并和频控，避免同类事件刷屏。
9. 跑通一个真实通知或报警通道。
10. 盒子侧稳定后，再进入最小云端：设备绑定、心跳、配置下发、事件和媒体上云。
11. 最后调整正式 App/H5：安装模式和日常使用模式分开。

### 12.0 当前唯一主线

为了避免并行失控，从现在开始只保留一条主线：

- 先把树莓派盒子做成“可安装、可配网、可接摄像头、可看算法预览、可报警、可诊断、可自启”。
- 然后补最小服务器：设备绑定、心跳、配置下发、事件上云、媒体访问和通知。
- 最后做家属端 App/H5：安装模式和日常模式分离，普通用户只看到状态、事件、规则和图文消息卡片。

任何新需求如果不能直接推动这条主线，就延后。

### 12.0.1 最新纠偏：先盒子，再服务器，再 App

本轮根据树莓派到位、盒子配网、算法预览、动作识别和应急报警需求，执行顺序调整为：

1. 盒子侧优先：
   - 树莓派部署和自启
   - Wi-Fi 热点配网方案
   - 手机优先 `/setup` 纯配网页
   - 本地 `/admin`
   - 算法预览
   - 日志诊断
   - 高优先级报警和事件频控
2. 服务器侧第二：
   - 设备身份
   - 绑定
   - 心跳
   - 配置下发
   - 事件和媒体上云
   - 正式通知
3. App 前端最后：
   - 安装模式
   - 日常首页
   - 事件和应急处理
   - 简化规则开关
   - 场景化图文消息卡片

普通 App 不展示 RTSP 密码、底层模型阈值、算法原始输出和大段日志；这些能力留在盒子本地 `/admin` 或后续运维后台。

### 12.0.2 当前执行任务

当前正在执行的任务是：

- 树莓派盒子侧能力收口

本次任务目标：

- 基于树莓派真实环境，把盒子侧最短路径收成可反复安装和演示的闭环：`通电 -> 联网 -> 启动 edge-agent -> 接入摄像头 -> 算法预览 -> 事件报警 -> 日志诊断 -> 自启恢复`。
- 新增或调整本地盒子页面，优先服务安装人员和现场演示，不把复杂调试能力塞进普通 App。
- 明确动作识别、火灾候选和跌倒候选都先作为“候选检测 + 规则解释 + 应急动作”，不承诺医疗或消防级判断。
- 在盒子侧稳定前，不继续扩张完整云端和正式 App 页面。

本次任务不扩张到的范围：

- 不在本轮同时继续扩张 Android 原生壳、FCM、多 topic 推送证书托管和商店发布流程。
- 不在本轮做完整云端设备平台，只保留必要接口契约。
- 不在本轮把 App 改成完整正式产品，只保留安装和演示所需入口。
- 不在本轮承诺高精度动作识别或消防级火灾识别，只做演示级候选和报警流程。
- 不在本轮同时把所有陪伴、消息和纪念模式页面做完。

本次任务完成后，按顺序进入：

1. 做一轮树莓派盒子侧真实冒烟验收，并沉淀固定安装演示顺序。
2. 回到最小服务器：设备绑定、心跳、配置下发、事件和媒体上云。
3. 再回到 App：安装模式、日常首页、事件应急处理和图文消息卡片。

### 12.0.3 2026-07-03 算法路线纠偏

本轮对算法路线做一次强制纠偏：先退回未验证的 YOLO Pose 实验，不把它作为主线继续扩；接下来按“视频性能 -> 姿态 POC -> 事件上报”的顺序推进。

原因：

- 当前页面卡顿和视频冻结的根因更可能是 RTSP 被多处打开、模型分析阻塞和分辨率/频率过高，继续叠加姿态模型会把问题放大。
- 用户要的是实时演示命中，示意图和静态 GIF 只能辅助解释，不能替代当前摄像头画面上的检测结果。
- 只靠人框无法支撑坐姿、半身、躺倒和动作解释，必须补骨架关键点或等价姿态结果。
- Pi5 是当前主验证硬件，任何模型进入主线前必须通过 Pi5 上的帧率、延迟、温度和稳定性验证。

新的执行顺序：

1. 回退未验证的 YOLO Pose 代码实验，只保留已验证的 YOLO 人形检测和人体存在增强。
2. 新增单路帧源缓存，让视频预览、截图和算法分析共享同一摄像头最新帧，避免重复打开 RTSP。
3. 调整算法预览：预览流低频低码率，分析结果异步刷新，页面不能因为推理变慢而卡死。
4. 接入 RTMLib + RTMPose POC，先输出骨架关键点、姿态摘要、坐/躺/倒地候选和置信度。
5. 把跌倒、久坐/静止、用餐候选改成“人框 + 骨架 + 时间窗 + 场景规则”的组合判断。
6. 将命中日志拆成三类：预览结果只给管理台看；跌倒/火灾/离线/黑屏进入正式事件；长时间无人/无变化进入生活观察区间。
7. 打通 `DetectionResult -> RuleEvaluation -> EventCandidate -> Event -> UploadQueue` 和 `DetectionResult -> RuleEvaluation -> ObservationLog` 双链路，让后续 App 服务器能分别接收告警、截图 URL、结构化证据和老人日志。
8. 用真实摄像头在 Pi5 上完成一次演示验收：框、骨架、命中状态、最近日志、事件截帧和报警测试都能解释清楚。

模型和资料参考：

- RTMLib：`https://github.com/Tau-J/rtmlib`
- MMPose / RTMPose：`https://github.com/open-mmlab/mmpose`
- ONNX Runtime：`https://onnxruntime.ai/`
- Ultralytics Pose 备用：`https://docs.ultralytics.com/tasks/pose/`

### 12.1 近期两周建议排期

第 1 批任务：跑通树莓派盒子本地闭环

- 在树莓派上部署当前代码，前台启动 `edge-agent`。
- 安装 `systemd`，验证重启恢复。
- 接入一路 H.264 / 720p RTSP 子码流，验证实时画面、截图和事件列表。
- 新增单路帧源缓存，先解决实时画面卡顿、算法预览冻结和 RTSP 重复打开问题。
- 清理旧事件对盒子验证的干扰，并补同类事件归并和频控。
- 新增或补齐 `/setup` 手机配网页。
- 新增或补齐 `/admin` 统一实时感知页面。
- 新增或补齐 `/admin` 日志诊断。

第 2 批任务：建立产品化数据链

- 新增 `DetectionResult` 数据结构。
- 新增 `RuleEvaluation` 数据结构。
- 新增 `EventCandidate` 数据结构。
- 将 `Event` 从检测逻辑中拆出来，作为用户可见业务事件。
- 为 YOLO 和后续模型结果增加检测框、置信度、模型版本和规则解释字段。
- 接入 RTMLib + RTMPose POC，输出骨架关键点、姿态摘要和跌倒候选依据；如果 Pi5 CPU 帧率不够，再切 MoveNet 或 Hailo 加速路线。
- 补齐跌倒候选、火灾候选、用餐候选、久坐/静止、夜间活动、摄像头异常的演示级预览输出。
- 设计实时画面会话、事件媒体和设备上报接口草案。

第 3 批任务：准备最小服务器和 App 承接

- 选择一个临时通知通道并跑通手机接收。
- 补跌倒和火灾候选的测试报警、升级策略和应急动作。
- 规划算法模块一算法一文件的工程拆分。
- 写树莓派安装 SOP、Wi-Fi 热点配网方案和现场演示顺序。
- 先做最小设备后端、心跳、配置下发、事件和媒体上云，再进入正式 App。
- 设计设备绑定码、设备 token、心跳上报草案。

### 12.2 近期不做清单

近期先不做：

- 完整 Swift 原生 App。
- 高并发复杂直播平台。
- 复杂账号体系。
- 多家庭多角色完整协作。
- 真正收费系统。
- 大规模模型训练。

这些不是不重要，而是依赖边缘端、云端事件和设备通道先稳定。

### 12.3 后续逐项跑通清单

这份清单就是接下来实际开发的执行顺序：

1. 树莓派同步当前代码并跑通 `edge-agent` 前台启动。
2. 树莓派安装并验证 `systemd` 自启、重启恢复和日志查看。
3. 跑通单路 RTSP 摄像头接入，优先 H.264 / 720p 子码流。
4. 做手机优先 `/setup` 纯配网页，只保留家庭 Wi-Fi 选择、密码输入、连接结果和回到 App / 管理端提示。
5. 重构本地 `/admin` 为桌面 Web 开发管理台，主导航固定为：首页、摄像头配置、视觉算法。
6. 收口 `/admin/cameras` 摄像头配置，只保留局域网扫描、选择扫描结果、填写 IP / 端口 / 用户名 / 密码、选择频道和主副码流、测试不保存、保存启用、启停和删除；默认频道 `1`、码流 `2`，生成 RTSP 路径 `/1/2`。
7. 收口 `/admin/algorithms` 算法配置，只保留开关、阈值、模型版本和保存生效。
8. 新增 `/admin` 统一实时感知能力，选择摄像头后同时展示人物、姿态、场景和风险状态。
9. 第一批算法预览覆盖图像质量、人形检测、长时间无人、久坐/静止、疑似跌倒、用餐候选、夜间活动、火灾候选、摄像头异常。
10. 新增 `/admin/alerts` 或等价报警配置页，覆盖跌倒和火灾候选的报警渠道、升级策略和测试报警。
11. 新增 `/admin` 日志诊断能力，覆盖服务状态、拉流错误、检测错误、最近报警和诊断包导出。
12. 跑通 `DetectionResult / RuleEvaluation / EventCandidate / Event / ObservationLog` 数据链，并补事件归并、生活观察聚合、频控和误报反馈。
13. 跑通真实 Bark / 飞书 / Telegram / APNs relay 中至少一个报警通道。
14. 盒子侧完成后，再进入最小服务器 `api/v1`：设备身份、绑定、心跳、配置下发、事件、媒体、实时画面鉴权。
15. 最小服务器完成后，再调整 H5/App：安装模式、首页消息卡片、事件应急处理、简化规则页和实时查看。
16. 最后再推进算法模块化、模型版本、样本闭环、边缘盒试点和商业化交付。

## 13. 风险和应对

### 13.1 算法误报

风险：

- 家庭场景复杂，单帧 YOLO 很容易误判。

应对：

- 必须引入多帧时序、规则引擎、误报反馈和可解释证据。

### 13.2 摄像头兼容

风险：

- RTSP 地址、编码格式、网络环境差异大。

应对：

- 建立摄像头兼容清单、ONVIF 扫描、拉流诊断和安装 SOP。

### 13.3 隐私风险

风险：

- 老人家庭视频高度敏感。

应对：

- 原始视频默认不上传，只上传事件证据；提供留存和删除策略。

### 13.4 硬件稳定性

风险：

- 家庭设备需要长期无人值守。

应对：

- Watchdog、日志、断网补传、远程升级、磁盘清理必须产品化。

### 13.5 架构债务

风险：

- 如果继续把逻辑写在静态页面和本机脚本里，后续难以接 App 和云端。

应对：

- 从现在开始按数据层、规则层、算法层、事件层、展示层拆分。

## 14. 2026-07-05 下一阶段执行路线

### 14.1 先跑通本地云语义闭环，再部署最小云端

当前树莓派已经具备摄像头接入、视觉预览、规则引擎、事件证据包和上传队列。下一步不继续把功能堆在 `/admin`，也不让 App 直接连局域网盒子；先用 `local-app-server` 作为“云端 App API 的本地替身”跑通完整闭环，再把同一套接口部署到公网云端：

1. 本地启动 `local-app-server`，验证 App/H5 和树莓派都只通过 App API 交互。
2. 提供 App 端接口：
   - 注册 / 登录
   - 家庭空间
   - 老人资料
   - 设备绑定码或绑定凭证
   - 摄像头配置
   - 事件列表 / 详情 / 处理状态
   - 媒体访问票据
3. 提供设备端接口：
   - `POST /api/v1/device/heartbeat`
   - `POST /api/v1/device/events`
   - `POST /api/v1/device/media-assets/upload`
   - `GET /api/v1/device/config`
   - `POST /api/v1/device/sync`
4. 给边缘盒子配置：
   - `GOHOME_APP_SERVER_BASE_URL`
   - `GOHOME_DEVICE_API_TOKEN`
5. 验证树莓派从 App API 拉取摄像头配置、写入本地 SQLite，并回传 `sync_status / status / last_error`。
6. 验证树莓派上传队列从 `pending` 变成 `completed`。
7. App/H5 改为从 App API 读取设备状态、摄像头状态、事件列表和证据图，而不是直接读取边缘端数据库或局域网盒子接口。
8. 本地闭环稳定后，把 `local-app-server` 的接口语义迁移到云端服务和正式数据库。
9. 云端正式验收前必须清空演示用户、演示家庭、演示摄像头和演示关怀数据，只保留服务器 `.env`、第三方模型 / 天气 / 搜索 key、设备服务密钥以及必要的未绑定设备登记。

### 14.2 视频与算法解耦

为保证“画面流畅、算法实时、展示可信”，后续按两条链路推进：

- 视频链路：优先保持低延迟预览，短期继续优化 MJPEG/OpenCV 的队列和缓存；中期切到 go2rtc / MediaMTX / WebRTC。
- 算法链路：按固定抽帧频率运行 YOLO + RTMPose + 规则引擎，推理慢时丢弃旧帧，只处理最新帧，不阻塞视频预览。

验收口径：

- 视频预览不能因为算法推理耗时出现持续卡死。
- 算法页展示必须明确当前算法、当前状态、命中依据、连续帧、置信度、模型版本。
- 正式告警不能由单帧直接生成，必须经过规则引擎确认。

### 14.3 算法继续做准的顺序

优先级：

1. 跌倒：继续扩大 UR Fall 样本，补坐下、弯腰、躺沙发、多人遮挡、低光负样本；正式事件使用状态机确认。
2. 人体存在和骨架：保持 YOLO 人框 + RTMPose 骨架组合，预览页只展示当前算法相关证据，避免“所有算法看起来一样”。
3. 火灾：从暖色区域规则升级为“暖色纹理 + 动态变化 + 连续帧 + 排除灯光/屏幕/阳光”的事件逻辑。
4. 生活观察：用餐、久坐、长时间无变化优先作为观察日志，不默认升级高危告警。

### 14.4 云端服务验收清单

最小云端 App API 完成后，按以下顺序验收。`local-app-server` 仍可用于本机回归测试，但不作为产品验收口径：

1. 云端服务有公网可访问 HTTPS 地址。
2. App/H5 使用云端 base URL 完成注册 / 登录 / 家庭 / 老人资料。
3. 云端初始化为空业务数据：新手机号登录后没有默认家庭、默认老人、默认盒子、默认摄像头和默认关怀卡片。
4. App/H5 创建家庭并填写老人资料；未完成老人资料前，只能停留在配置向导。
5. App/H5 通过扫二维码或输入绑定码认领盒子。当前树莓派无实体二维码时，用云端临时绑定码替代。
6. 树莓派 `.env` 配置云端 `GOHOME_APP_SERVER_BASE_URL` 和设备服务密钥。
7. 重启 `gohome-edge-agent` 后，云端能看到未绑定设备在线，但普通用户未认领前不能读取设备数据。
8. 认领成功后，App/H5 提交摄像头配置，云端 `config_version` 变化。
9. 树莓派拉取新配置，应用到本地摄像头配置，并回传同步状态。
10. 触发一条真实事件，确认树莓派本地 `upload_jobs` 从 `pending` 变成 `completed`。
11. 手机离开老人家局域网后，App/H5 仍能通过云端看到事件列表、事件详情和证据图。

### 14.5 用户端信息架构收口规则（历史 H5 基线）

本节记录 2026-07-05 的 H5/App 原型职责，只用于解释历史实现；正式原生产品信息架构以第 15 节的五栏导航为准，不再按本节新增用户端页面。

1. `首页`：默认展示今日关怀完整图文卡，并向下沉淀历史关怀卡片流；下方只保留家庭状态摘要。
2. `守护`：只展示家庭盒子状态、实时画面和摄像头在线情况；配置动作只通过“设备”入口进入设备管理。
3. `事件`：只展示盒子、摄像头和规则生成的安全事件；检测依据进入事件详情，不再单独作为主流程入口。
4. `陪伴`：展示今日关怀完整内容和真实联系动作；不承接安全告警处理，也不重复承接关怀推送设置。
5. `我的`：承接家庭成员、关怀推送、设备管理、通知设置、规则设置、隐私与数据。
6. `关怀推送`：普通家属只配置推送时间、内容类型、关怀重点、老人兴趣、回家提醒和纪念日；模型 Base URL、Key、Prompt 只由服务提供方配置。
7. `规则设置`：只展示家庭盒子当前真实支持的离线、黑屏、静止、无人、跌倒候选和通知开关，不展示尚未实现的徘徊、响声等能力。

移动端页面必须统一处理 `viewport-fit=cover`、顶部刘海安全区、底部 Home Indicator 和底部导航遮挡。验收时用 `390 x 844` 手机视口检查横向溢出、最后一个可操作按钮是否被底栏遮挡、Material icon 是否退化成英文文本。

### 14.6 上云前的本地闭环缺口

当前 `local-app-server` 已经可以作为云端 App API 的本地替身跑通首页、守护、事件、陪伴、设备管理、规则和今日关怀卡片。下一步不继续堆页面入口，先补齐以下缺口，否则上云后仍会出现“页面能看、链路不可信”的问题：

1. 正式设备绑定记录
   - 本地演示不能只依赖设备同步状态判断“盒子已连接”。
   - 需要让用户、家庭、设备、绑定码和设备 token 形成清晰绑定记录。
   - 上云后 `device_bindings` 必须能回答“这个家庭是否真的拥有这台盒子”。
2. 盒子运行状态回传
   - 树莓派需要持续回传 `worker_running`、服务版本、最近同步时间和最近错误。
   - App 只能展示用户可理解的“家庭盒子运行中 / 等待同步 / 需要检查”，不能暴露工程状态。
3. 规则下发与应用确认
   - App 保存规则后，服务器生成 `desired_rule_version`。
   - 盒子拉取并应用后必须回传 `applied_rule_version`。
   - 只有两者一致，用户端才显示“已同步到家庭盒子”。
4. 老人联系信息
   - 老人资料必须保存手机号和家里电话。
   - “打电话”动作只在有号码时直接拨号；缺失时引导补全资料。
5. 本地数据库到云数据库
   - 继续用 `npm test` 保证本地 App API 行为不回归。
   - 继续用 `npm run verify:local-loop` 保证本地真实运行态可自检。
   - PostgreSQL store 跑通后，再把同一套接口部署到 HTTPS 云服务。

验收口径：

- `npm test` 通过。
- `npm run verify:local-loop` 通过，且上面 1 到 4 的 warning 被消除或明确标为云端阶段遗留。
- 手机离开老人家局域网前，先在本地确认 App/H5 不再依赖盒子局域网 IP 读取状态、事件和关怀卡片。

### 14.7 新用户配置向导和设备认领

从当前云端阶段开始，新用户路径必须按产品真实链路强制串联，不能让用户登录后直接进入空首页或读到历史演示数据。

强制顺序：

1. 手机号登录或注册。
2. 创建或加入家庭。
3. 填写老人资料，至少包括称呼关系、老人姓名或称呼、老人手机或家里电话、城市区域。
4. 绑定守护盒。
   - 正式产品：扫盒身 / 包装 / 说明卡二维码。
   - 当前树莓派验证：输入云端或 `/admin` 生成的临时绑定码。
   - 局域网搜索和 BLE 只做辅助发现，不能跳过云端认领。
   - 已绑定家庭可在 App 设备管理中解绑；仅家庭所有者可操作，并需要二次确认。
   - 解绑后盒子保持 Wi-Fi 和云连接，摄像头接入配置从旧家庭移除，设备恢复为可认领。
5. 配置至少一路摄像头。
6. 等待盒子拉取配置并回传 `synced / online`。
7. 进入首页、守护、记忆、社区和我的完整主功能。

未完成状态处理：

- 没有家庭：只显示“创建家庭 / 加入家庭 / 切换手机号”。
- 没有老人资料：只显示“填写老人资料 / 切换手机号”。
- 没有绑定盒子：只显示“扫码绑定 / 输入绑定码 / 盒子还没联网？”。
- 没有摄像头：只显示“添加摄像头 / 稍后退出”，不能展示正常守护首页。
- 底部主导航在配置完成前隐藏或禁用，避免用户进入空守护、空记忆或空社区。

云端数据策略：

- 云端环境变量和服务密钥由服务提供方配置，保留在服务器 `.env` 或后续 Secret Manager / KMS。
- 云端业务数据上线验收时应为空，不预置演示用户、默认家庭、默认摄像头或默认关怀卡片。
- 盒子可以作为未绑定设备上报心跳，但 `family_id` 必须为空；只有 App 完成认领后才写入家庭归属和设备绑定记录。
- 摄像头、规则、事件、媒体和关怀卡片必须全部按当前用户所属家庭过滤。

实现顺序：

1. 后端增加设备认领对象：`device_claims` 或等价字段，支持 `sn + claim_code` 校验、单次使用、过期和撤销。
2. 调整设备心跳 / 同步：未绑定设备不得自动落到默认家庭。
3. 调整首页和 App 壳：按家庭、老人资料、盒子绑定、摄像头同步四步展示配置向导。
4. 调整设备绑定页：从“绑定当前设备”改为“扫码绑定 / 输入绑定码”，当前阶段先做输入绑定码。
5. 调整云端初始化脚本：清空用户业务数据，保留 `.env` 和未绑定设备登记。
6. 用一个全新手机号从空云端跑通完整路径，再把盒子摄像头配置接回云端。

设备转移验收必须额外覆盖：`旧家庭解绑 -> 盒子继续在线 -> 旧家庭不再收到配置和事件 -> 新家庭输入盒身码认领 -> 重新配置摄像头 -> 盒子同步新家庭配置`。

云端实时画面和事件证据必须分开：`live_relay` 只维护实时预览，不进入永久媒体资产；只有规则事件关联的截图或用户明确保存的媒体才进入 `media_assets`。App 登录 session 必须持久化到 PostgreSQL，服务重启不得让用户退出登录。

当前状态：

- 设备绑定记录、盒子运行状态回传、规则下发与应用确认已在本地闭环中通过自检。
- 注册 / 登录已从“前端状态切换”收口为后端真实会话：登录返回 `app_...` token，新账号默认看不到旧家庭，家庭、设备、摄像头、事件、媒体和关怀卡片均按 `family_members` 做用户隔离。
- 登录页已明确分成“已有账号 / 首次创建”：已有账号走真实登录，首次创建走真实注册；旧“一键登录”、微信和 Apple 等未实现入口已移除，避免假跳转。
- 首次创建账号后的家庭路径已收口：新账号进入 `family.html?mode=setup`，必须显式创建家庭或用邀请码加入家庭；老人资料页不再隐式创建“我的家”。
- 本地闭环已支持家庭邀请码加入：当前为 `GH-{familyId}-{校验码}` 简化码，正式云端阶段再升级为邀请链接、二维码签名、过期和撤销机制。
- 手机号账号本地验证码已收紧为 `000000` 或账号保存验证码；不再允许“手机号存在 + 任意 4 位以上验证码”登录。
- 媒体播放 ticket 已绑定签发用户，使用播放票据访问截图 / 视频时仍按正确家庭权限校验。
- 用户端 HTML 已移除 Tailwind CDN 运行时依赖，统一改为本地 `assets/styles/tailwind.css`；`npm test` 已加入静态断言，防止再次引入 CDN 或 `tailwind.config` 运行时配置。
- 浏览器端已移除从 `/health` 自动写入本地演示 token 的逻辑；未登录打开首页不会读取默认家庭，已有手机号账号登录后才看到默认家庭、家庭盒子和 2 路摄像头。
- 旧 JSON 数据已做兼容迁移：当前家属账号缺少家庭成员关系时，会把现有默认家庭补给该账号，避免升级后丢失已接通盒子和摄像头。
- 当前 `npm run verify:local-loop` 为 `37 passed, 0 warnings, 0 failed`，已覆盖主账号闭环、新账号隔离、临时家庭创建、老人资料保存、主账号恢复和自检临时数据自动清理。
- 老人联系电话配置入口已补齐：“我的 -> 家人资料”可编辑称呼、城市、老人手机号和家里电话；陪伴页有电话才使用 `tel:`，无电话时显示“补电话”并进入资料页。
- 当前真实数据里的老人手机号已配置，陪伴页“打电话”闭环已通过本地自检。
- 天气 provider 已接入和风天气：`GET /api/v1/families/{family_id}/weather-signals` 返回真实 `qweather` 信号，首页天气卡显示 QWeather 实时数据；未配置或失败时明确降级，不再伪造天气。
- 内容搜索 provider 已接入 Tavily 接口和首页话题候选卡；换入有效 Tavily key 后，`GET /api/v1/families/{family_id}/content-recommendations` 已返回 3 条候选，自检 `content search - tavily 3 candidate(s)` 通过。
- “我的 -> 关怀推送”已成为内容偏好的唯一配置源：内容类型覆盖本地热点、健康养生、防诈骗、文娱兴趣、天气、节日纪念日、回家提醒和家庭状态；内容区域为空时回落到老人资料城市/区县；首页和每日关怀卡生成都从同一份 `care_card_schedule` 读取。
- 首页关怀信息架构已收口：今日关怀主视觉卡、最近关怀历史横滑卡、今日信号横滑卡分层展示；首页不再把同一关怀文案重复塞进多个模块，旧泛化标题在首页展示层会被清洗。
- 今日关怀模型输出已增加服务端后处理，模型若继续产出“家里一切平稳 / 聊聊家常”等占位句，会基于真实天气、回家间隔或老人兴趣改写；生图提示词已禁止品牌字样、logo、角标、水印和无关徽章。
- PostgreSQL schema、导出和反向恢复已补齐老人手机号、手机号码和家里电话字段，避免上云后拨号能力丢字段。
- PostgreSQL seed bundle 已导出真实 `family_members`，PostgresStore 反向恢复也会保留家庭成员关系，避免切库后账号隔离失效。
- 当前 JSON 运行态已能持久化默认老人资料，seed 导出包含 `elder_profiles=1`；剩余问题是联系电话字段值为空，不是资料对象缺失。
- 已新增 `npm run verify:postgres-loop`，拿到空 PostgreSQL 数据库连接串后可直接验证迁移、PostgresStore 启动和 App API 基础读取。
- 首页内容编排和卡片视觉已完成本轮收口：当前首页在手机宽度下展示今日关怀、天气、热点/养生/文娱/日历/位置与回家、家庭状态和最近关怀，且无横向溢出。
- 新注册用户路径已通过自动自检：临时账号不会继承旧家庭、旧盒子和旧摄像头；创建临时家庭后可保存老人资料；测试后会恢复主账号，并自动清理 `verify-*` 临时账号和 `流程自检-*` 临时家庭。
- 阿里云轻量服务器已完成最小云部署：
  - 公网 App/H5 地址：`http://139.196.223.58`
  - 云端 App API 运行在 `gohome-app.service`，由 nginx 反代公网 80。
  - 云端存储已切 PostgreSQL，本机 JSON 只作为开发和 seed 来源。
  - `/health` 不再暴露本地调试 token，服务日志只输出脱敏 token。
  - 云端登录态接口已验证：主账号能读取默认家庭、2 路摄像头、关怀推送配置和 3 张关怀卡片。
- 树莓派盒子已从本地 Mac 地址切到云端：
  - `GOHOME_APP_SERVER_BASE_URL=http://139.196.223.58`
  - 盒子配置同步、规则应用和心跳已通。
  - 云端能看到设备 `edge-042714be475b91da` 在线，2 路摄像头为 `online / synced`。
- 本轮已修复 Postgres 上云缺陷：
  - JSONB 数组/对象写入 PostgreSQL 的序列化问题。
  - 历史事件引用旧摄像头 ID 导致外键失败的问题。
  - `npm test` 已通过，`data/app-server/cloud-seed.json` 已重新导出。
- 当前边界：
  - 云端已承接账号、家庭、设备、规则、关怀卡片、配置同步和设备心跳。
  - 事件上传 agent 已 ready，但本轮没有强造假告警；真实画面未命中规则时不会生成新事件。
  - 外网实时直播还没有完成内网穿透/云中继。手机离开老人家局域网后，事件/截图/状态可走云端，但实时视频需要下一步做 WebRTC、反向 WebSocket/MJPEG 中继或其他 relay。
  - 当前公网是 HTTP；iOS 真机和正式推送前仍要补 HTTPS。

下一步不继续堆页面入口，按云端闭环推进：

1. 先按 14.7 做新用户配置向导、设备认领和空云端数据验收。
2. 用 `http://139.196.223.58` 从新手机号跑通：注册、家庭、老人资料、绑定盒子、配置摄像头、盒子同步、首页进入。
3. 做最小云端视频中继，让手机不在家庭局域网时也能看到实时画面。
4. 做云端 scheduler / notification-service：按关怀推送规则定时生成卡片，接天气、Tavily 和模型调用，准备 iOS 推送。
5. 补 HTTPS 后再进入 iOS WebView/原生壳打包。

### 14.8 2026-07-09 当前执行顺序更新

截至 2026-07-09，14.7 后续事项已经部分推进完成，执行顺序更新如下。

已跨过的阶段性事项：

- 云端 App/H5 已部署到阿里云轻量服务器，运行库为 PostgreSQL。
- 树莓派盒子已切到云端地址，并持续回传心跳、配置同步状态和实时帧。
- 当前家庭已绑定真实盒子，2 路摄像头为 `online / synced`。
- 关怀内容已接入天气、Tavily、多模态语言模型和生图模型。
- scheduler / notification-service 已建立，能生成 App 内消息、通知投递记录和 scheduler 运行记录。
- 通知设置页已改成真实通知状态页，读取 `app_messages`、`notification_deliveries` 和 `app_push_tokens`。

当前优先级：

1. 保持当前云端和盒子稳定，不做会破坏演示家庭的重置操作。
2. 完成 HTTPS。没有域名或证书时，先明确比赛演示是否接受公网 HTTP；若要 iOS 真机和 APNs，必须接 HTTPS。
3. 做一次“非破坏性公网验收”：
   - 使用当前已绑定家庭验证登录、首页、守护、摄像头、实时画面、关怀卡片、通知页和规则同步。
   - 不解绑当前盒子，不清空当前家庭。
4. 做一次“破坏性完整新用户验收”前必须先确认：
   - 是否允许备份后清空云端业务数据。
   - 是否允许把当前盒子恢复为 `claimable`。
   - 是否接受重新添加 2 路摄像头并等待盒子同步。
5. HTTPS 完成后进入 iOS 壳和 APNs：
   - iOS 登录后登记 push token。
   - 云端接 APNs provider。
   - 通知状态从 `app_message_only / simulated` 升级为 `queued / sent / delivered / failed`。
6. 再进入视频链路升级：
   - 短期继续压测当前盒子实时帧中继。
   - 如果延迟和流畅度仍不能满足演示，再切 WebRTC / TURN / MediaMTX。

当前不优先做：

- 不继续扩展无关页面入口。
- 不在没有 HTTPS 和 iOS token 前伪装正式手机推送。
- 不在没有用户确认前清空现有云端家庭或解绑当前盒子。
- 不把临时设备码当成正式出厂二维码体系。

### 14.9 2026-07-10 盒子视觉算法状态纠偏

本轮确认算法代码没有丢失，YOLO 和 RTMPose 此前都真实运行过。失效根因是旧 `.venv` 被 Mac Homebrew 路径和 macOS OpenCV 动态库污染；随后新建的 Pi 原生 `.venv-pi` 只安装了基础视频依赖，systemd 在 7 月 6 日重启后优先切到这个不完整环境，导致 YOLO 和 RTMPose 同时消失。之后切换 `basic` 只是为了避免页面假显示模型运行，不是根因。

已完成：

- Pi 现有 Python 3.13/aarch64 环境已安装并验证 `torch 2.10.0 + torchvision 0.25.0 + ultralytics 8.4.91`。
- 正式检测后端恢复为 `yolo`，使用 `yolo11n.pt`，推理尺寸为 416。
- 两路真实摄像头均已输出人形框、人数和置信度；后续单帧推理约 90-95ms。
- 盒子、云端 App API 和管理台均已同步显示 YOLO 能力，App 可继续配置人形和长时间无人规则。
- ARM64 依赖版本已锁定到 `requirements-yolo.txt`，避免重装时再次拉取未验证的大版本。
- 原 RTMPose 路线已恢复：`onnxruntime 1.27.0 + rtmlib 0.0.15`，沿用原 YOLOX tiny 与 RTMPose-S ONNX 模型缓存。
- worker 在跌倒或活动规则开启时继续按间隔采样姿态，管理台跌倒、用餐和久坐预览会实时启用姿态，不改成两路摄像头全时高频运行。
- 已增加 Pi 专用安装脚本、部署排除规则和 systemd 启动前检查，禁止再次把 Mac `.venv` 覆盖到盒子，并在依赖或模型缺失时直接阻止服务假启动。
- RTMPose 在 `tracking=0` 时改用无状态 `Body` 推理器，每个姿态采样帧独立完成人形检测，避免 RTMLib `PoseTracker` 跨两路摄像头复用上一帧框导致 `'NoneType' object is not subscriptable`。

当前边界与下一步：

1. 人形检测已恢复为真实模型结果，不再使用 basic 示意状态。
2. 长时间无人由连续人形结果和时间规则组合，可进入持续运行验证。
3. 跌倒候选已恢复为 `YOLO 人框 + RTMPose 骨架 + 低位/卧姿 + 连续帧和持续时间` 的组合判断；它仍是家属确认型候选，不宣称医疗级结论。
4. 下一项算法工作不再是重新做姿态 POC，而是补真实样本评估、误报反馈和连续运行指标，重点统计人形召回、姿态可见率、跌倒候选误报率和两路摄像头 CPU 占用。

### 14.10 2026-07-10 跌倒误报回归与启用边界

本轮没有更换 YOLO、RTMPose 或现有姿态数据路线。历史高分样本复跑确认，算法失效修复后仍有两类真实误报：空客厅中的沙发纹理被 RTMPose 组合成低置信横向骨架，以及正常正面坐姿因肩髋区域宽高比临界而被判成卧姿。

已完成：

- 姿态跌倒候选增加证据质量门控：最低骨架置信度、最少可见关键点和最少肩髋核心关键点。
- 原始关键点、姿态和 `raw_pose_fall_score` 继续保留；低质量骨架只失去告警资格，不删除姿态数据。
- 正面坐姿改为依据肩部中点到髋部中点的躯干方向判断，避免肩宽略大于肩髋高度时误判卧姿。
- RTMLib 偶发 `NoneType` 人体框错误增加一次受控同帧重试；连续失败仍保留为明确错误状态。
- systemd 服务退出上限改为 15 秒，避免浏览器保持 MJPEG 长连接时服务重启等待 90 秒。
- 在本地和 Pi 的 Git 忽略数据目录新增 6 张家庭场景私有负样本回归：空客厅、沙发遮挡、远处半身、正常坐姿和画面边缘站姿；实拍图不进入代码仓库。

当前验收结果：

- 家庭场景负样本：`TN=6 / FP=0 / errors=0`。
- UR Fall：`TP=8 / TN=12 / FP=0 / FN=0 / errors=0`。
- 两路真实摄像头并发跌倒预览 20 次：`20/20 ready`，模型错误 0，跌倒候选 0。
- 合成 smoke：人形、姿态、火焰视觉和火焰事件均通过；规则引擎和告警去重测试通过。

当前边界：

1. 跌倒正式通知继续保持关闭，不能仅凭 6 张家庭负样本和 20 张 UR Fall 样本宣称可直接上线告警。
2. 下一步先持续采集家庭正常活动负样本，并补至少一组当前真实摄像头视角下的安全模拟跌倒正样本。
3. 达到连续观察期内可接受误报率后，再由用户确认开启 `fall_detection_enabled`；开启后仍采用连续帧、持续时间和家属确认型事件，不宣称医疗级能力。

### 14.11 2026-07-10 人形候选纠偏与公开样本扩展

本轮继续使用原 YOLO + RTMPose 路线，没有删除姿态数据或更换算法。用户截图中空客厅出现 3 个 50%-71%“人体”的根因，是肤色区域和 Haar 上半身启发式候选被管理台包装成增强置信度，并错误计入人数，不是 YOLO 真正输出了 3 个人框。

已完成：

- 默认关闭肤色/Haar 经典人形增强；保留开关仅用于管理台候选复核和回归测试。
- YOLO 低置信候选保留真实 `model_confidence`，不再人为增加固定分数。
- 启发式候选只输出 `candidate_score` 和 `confidence_kind=heuristic`，不计入人数，不显示为模型置信度。
- 人形预览启用 RTMPose 复核；姿态开启但没有可信骨架时，经典启发式候选不能作为人体证据。
- 管理台只给可信姿态画骨架，并明确区分“模型置信度”“YOLO 低置信候选”和“候选分”。
- 新增 GMDCSA24 公开视频导入与评估脚本，覆盖跌倒、睡床、阅读、坐姿、走动和弯腰场景。
- 新增 Wikimedia Commons 空室内负样本导入与评估脚本，专门回归沙发、柜子、窗户等家具误检。
- UR Fall 从早期 20 帧小样本扩大到 88 帧；公开视频、抽帧和家庭私有样本均保存在 Git 忽略目录，不进入仓库。

当前真实评测：

- 空客厅真实摄像头连续 5 次：`person_count=0`、`pose_count=0`，原 3 个假框消失。
- 有人摄像头连续 5 次：保持 `person_count=1`，可由 YOLO 或可信骨架确认。
- Wikimedia 空室内负样本：`TN=5 / FP=0 / errors=0`。
- GMDCSA24 22 帧：`TP=6 / FP=4 / TN=10 / FN=2`，`precision=0.60 / recall=0.75 / FPR=0.2857`；4 个误报均为正常睡床，2 个漏报均为跌倒后人体大部分出画。
- UR Fall 扩展 88 帧：按盒子当前生产参数 `yolo11n / conf=0.20 / imgsz=416 / pose threshold=0.78` 复跑为 `TP=29 / FP=0 / TN=56 / FN=3`，`precision=1.00 / recall=0.90625 / FPR=0`。3 个漏报中 1 个有人框但无可用骨架，2 个倒地人体大部分出画且人形、骨架均未检出。14.10 的 `8/8` 只代表早期小样本，不再作为整体准确率结论。

下一阶段顺序：

1. 实现视频序列评估器，验证“活动/站坐 -> 快速下降 -> 低位持续 -> 是否恢复”的完整过程，不再用独立抽帧代替跌倒判断。
2. 增加每路摄像头的床、沙发和非地面区域配置；正常卧床默认排除高危跌倒事件，但仍可保留生活观察状态。
3. 补人体出画、遮挡、低光、轮椅、正常躺沙发和当前家庭视角下安全模拟跌倒样本，分别统计候选召回和正式事件误报。
4. 在视频时序、区域排除和连续观察指标达到可接受范围前，继续保持 `fall_detection_enabled=0`。

### 14.12 2026-07-10 自动场景识别与跌倒时序状态机

根据产品路径纠偏，床、沙发区域不由普通用户手动画。用户仍只选择摄像头所在房间；盒子在同一轮 YOLO 推理中同时识别人和固定家具，连续多帧稳定后自动形成卧躺区域，管理台只负责展示调试证据。

已完成：

- YOLO 同一帧增加 `bed / couch / chair / dining_table` 场景对象输出，不额外加载第二个模型。
- `SceneContextTracker` 按摄像头跟踪场景对象；同类包含框自动合并，默认连续 2 帧稳定后生成场景区域。
- 床和沙发标为 `normal_lying_surface`；人体 `lying / low_body` 姿态与稳定区域重合时标为正常卧躺，但原始骨架、分数和视觉候选继续保留。
- 场景学习会过滤大部分面积被当前人框或骨架覆盖的家具候选，避免蜷缩倒地人体被 YOLO 错分成沙发后反向抑制真实跌倒。
- 跌倒状态机增加近期站坐基线、水平目标匹配、垂直下降、运动变化和转变继承；只有同一目标完成“站坐 -> 下降 -> 低位持续”才可进入确认。
- 单帧高分卧姿没有先前站坐过程时进入 `awaiting_transition`；床/沙发重合进入 `normal_lying_zone`，两者都不生成正式事件。
- 正式跌倒开启时，worker 每轮都运行姿态采样，不再按普通活动观察的 5 帧间隔跳过关键下降过程。
- 管理台跌倒页显示自动床/沙发框、场景状态、时序状态、复核帧数和持续时间；普通 App 没有手动画区域入口。
- 新增序列评测器，按同一视频的时间顺序把抽帧送入同一个规则状态机，不再用单帧 TP/FP 代替正式事件指标。

真实验证：

- 当前客厅三人实拍帧中，一人横躺沙发：第一帧为 `awaiting_transition`；第二帧沙发稳定后，卧姿与沙发重合 `88.8%`，状态变为 `normal_lying_zone`，连续 3 帧正式事件为 0。
- 两路真实摄像头空画面均在第二帧稳定识别沙发；空客厅保持 `person_count=0`，未产生跌倒事件。
- GMDCSA24 序列级 9 段：`TP=2 / FP=0 / TN=5 / FN=2`，正常睡床误报由单帧 4 个降为 0；2 个漏报来自人体出画或稀疏抽帧未形成有效下降证据。
- UR Fall 序列级 18 段：`TP=8 / FP=0 / TN=10 / FN=0`，`precision=1.0 / recall=1.0 / FPR=0`。该结果只代表当前抽取的 8 段跌倒和 10 段 ADL 回归，不代表产品级准确率。
- Playwright 实测管理台显示 1 个自动沙发框、无横向溢出，场景和时序文案正常。

后续边界：

1. 场景图当前在服务进程内按两帧自动重建，不要求用户配置；后续产品化可把稳定结果持久化，缩短重启后的学习窗口。
2. 继续补当前家庭视角的安全模拟跌倒、夜间低光、遮挡、轮椅和多人交叉轨迹样本。
3. 在真实家庭长期观察没有达到可接受误报率前，继续保持 `fall_detection_enabled=0`。

### 14.13 2026-07-10 默认全开启决策

用户已确认产品交付状态应为全部守护能力默认开启。本节取代 14.10-14.12 中测试阶段“继续保持 `fall_detection_enabled=0`”的临时执行口径。

执行顺序：

1. App 服务新建规则默认开启离线、黑屏、无活动、人形、跌倒、活动状态、烟火和通知。
2. 把当前云端运行规则和真实树莓派本地规则迁移为同样的全开启状态，确认配置版本同步完成。
3. 跌倒检测继续使用自动床/沙发区域和时序状态机，禁止退回单帧姿态高分直接告警。
4. 增加默认值回归测试，防止后续版本再次把活动、烟火或跌倒默认关闭。
5. 后续实现按家庭、盒子和摄像头持久化规则时，仍以全开启作为新记录默认值，并保留用户主动关闭能力。

当前完成状态：

- 步骤 1-4 已完成并通过本地、云端、App 页面和树莓派实机验证。
- PostgreSQL 已按家庭持久化 `edge_rules`；当前粒度是家庭级，后续只有在确有需求时再细分到单摄像头阈值。

### 14.14 2026-07-10 家庭规则、真实事件闭环和公网新用户验收

本轮已一次性完成进入 HTTPS / iOS 前的剩余核心闭环。因比赛时间限制，不等待 24 小时稳定性报告，但保留现有自动回归和运行状态检查。

已完成：

1. 守护规则由全局对象升级为按家庭持久化，盒子按绑定家庭拉取对应规则。
2. 家庭创建者可以修改规则，受邀成员只读；App 页面同步禁用成员端输入和保存按钮。
3. 删除“服务重启时把无家庭活跃账号自动加入现有家庭”的旧兼容逻辑，家庭关系只能通过创建或邀请加入产生。
4. 解绑盒子会撤销旧设备 token；修复无家庭 token 被 PostgreSQL 导出层错误归到默认家庭并自动恢复绑定的问题。
5. 盒子使用 UR Fall 公开序列经过生产 YOLO、RTMPose、自动场景和时序状态机，按 `clear -> awaiting_transition -> suspect -> confirming -> confirmed` 真实生成一条测试跌倒事件。
6. 该事件已完成截图上传、云端事件入库、App 告警消息、通知投递记录和事件页展示。
7. 新增非破坏性公网验收脚本，覆盖注册、数据隔离、家庭、老人资料、成员权限、盒子绑定、摄像头下发、同步、规则隔离、解绑和测试数据清理，共 13 项通过。

下一阶段固定顺序：

1. 配置 HTTPS 域名、证书和 nginx。
2. 在 HTTPS 环境复跑登录、实时视频、事件证据和新用户验收。
3. 制作 iOS 壳，优先处理登录态、安全区、相机/定位权限、系统拨号和深链。
4. 登记 iOS push token 并接 APNs；没有 Apple 真机和开发者配置前不伪装正式推送。

### 14.15 2026-07-11 边缘存储稳定性修复

十几个小时运行观察确认云端、双路视频、规则同步和事件链正常，但盒子历史数据达到约 15GB，SQLite 连接依赖垃圾回收关闭，存在数据库锁和长期容量风险。

已完成：

1. SQLite 连接改为事务结束后显式关闭，启用 WAL、`busy_timeout=30s` 和清理查询索引。
2. 普通运行历史默认保留 24 小时；事件证据、最新画面和未完成上传永久保留。
3. worker 增加异常兜底，单次数据库异常不再直接结束视觉工作线程。
4. 云端新增家庭创建者清理命令，盒子通过配置同步分批执行并回传结果。
5. App“设备管理”展示盒子磁盘、数据库、剩余容量、保留规则和“立即清理”。
6. 实机安全删除约 13.8 万张过期快照及对应分析链，保留 1870 条事件；数据库完整性检查通过。

后续顺序：

1. 不再等待完整 24 小时观察，保留运行日志检查作为上线前回归。
2. 直接进入 HTTPS 配置和 HTTPS 环境闭环复验。
3. HTTPS 通过后制作 iOS 壳和 APNs。

### 14.16 2026-07-11 腾讯云单云迁移

已完成：

1. 在不影响现有 Next.js 项目的前提下，以独立目录、PostgreSQL 数据库、systemd 服务和 Nginx 站点部署 GoHome。
2. 新增 `gohome.ai2shx.club` A 记录并签发独立 Let’s Encrypt 证书，HTTP 自动跳转 HTTPS。
3. 生产环境关闭默认管理员和默认家庭种子数据，数据库确认用户、家庭、摄像头、事件和关怀卡均为空。
4. 树莓派已切换到腾讯云 HTTPS，真实设备 `edge-042714be475b91da` 在线且处于待认领状态。
5. 腾讯云完成 13 项非破坏性新用户验收，测试数据已自动清理。

待完成：

1. 用户在真实 App 页面走一遍注册、家庭、老人资料、认领盒子和摄像头配置。
2. 验证两路视频、守护规则、事件证据、关怀卡和存储清理。
3. 验收后停止阿里云旧服务并进入 iOS 壳。

执行状态：腾讯云真实账号已完成盒子绑定、两路摄像头同步和公开样本事件闭环；阿里云 `gohome-app.service` 已停止并禁用。下一阶段直接进入 iOS 壳与 APNs。

### 14.17 2026-07-11 局域网发现与安全绑定

执行方案：

1. 生产环境关闭 `/api/device-claims/available` 的全局设备列表和 `/api/device-claims/claim` 的直接认领能力。
2. 绑定页只保留家庭选择、备注和“搜索并绑定盒子”，不要求用户输入设备码。
3. App 创建 5 分钟高熵一次性凭证，并顶层跳转到 `http://gohome.local:8711/pair`，规避 HTTPS 页面主动读取 HTTP 局域网接口的混合内容限制。
4. 盒子校验云端回跳域名和启动后 15 分钟配对窗口，再由盒子服务端向腾讯云兑换设备 token。
5. 新签发的本地设备 token 优先于出厂 bootstrap token，供配置同步、视频中继和事件上传使用。
6. 云端校验设备不能仍绑定其他家庭；解绑会撤销旧 token，重新配对成功后盒子覆盖本地旧 token。
7. H5 实机闭环通过后，在 iOS 壳使用 Bonjour 真正枚举多台盒子，并配置 Local Network 权限说明。

验收标准：

- 生产环境全局设备列表为空，直接云端认领返回 403。
- 一次性凭证为 16 位随机十六进制值、只能消费一次。
- 已绑定其他家庭的设备兑换返回 409。
- 手机不在同一局域网或盒子配对窗口关闭时不能绑定。
- 成功绑定后自动进入摄像头配置，盒子规则、视频和事件继续走 HTTPS 云端。

### 14.18 2026-07-11 iOS 壳第一阶段

1. 复用现有 SwiftUI + WKWebView 工程，默认入口切换到腾讯云 HTTPS 首页。
2. WebView 由原生安全区约束，适配 Dynamic Island、刘海和 Home Indicator，不再全屏覆盖系统区域。
3. 使用持久化 `WKWebsiteDataStore` 保留登录态，支持侧滑返回、内联视频和 Web 内容进程恢复。
4. 原生桥接电话、微信、通知深链；只允许腾讯云域名、`gohome.local` 和受控外部 scheme。
5. 增加本地网络、Bonjour 和定位权限说明；树莓派广播 `_gohome._tcp` 服务，为后续多盒子枚举准备。
6. 增加正式 App 图标和模拟器视觉验收。
7. 下一步使用真机完成签名、局域网绑定、双路视频、电话/微信和定位测试，再接 APNs。

### 14.19 统一视觉感知与云端复核实施计划（执行中）

本节仅完成代码审计、架构设计和验证，尚未开始算法实现。用户确认前不修改生产算法、数据库或页面。

#### A. 现状审计

可直接复用：

- `CameraAgent` 已把实时视频流和算法抽帧解耦，并有最新帧缓存。
- `VisionPipeline` 已统一调用画面质量、YOLO 人形与家具、RTMPose、活动、跌倒、火灾和自动场景跟踪。
- `RuleEngine` 已实现站坐基线、下降、低位持续、恢复、床/沙发排除和事件确认状态机。
- `EventAgent + UploadAgent` 已具备事件去重、截图优先上传、事件幂等上传和失败重试。
- 云端已有事件、媒体、App 消息、通知投递、确认和误报反馈闭环。

必须重构：

- 当前 worker 默认每 5 秒处理每路摄像头，每次都保存 JPEG、snapshot、detection_result 和 rule_evaluation，不适合作为长期姿态日志架构。
- 当前姿态只粗分 `lying / standing_or_sitting / seated_or_half_body / upper_body / low_body`，无法满足站、坐、蹲、弯腰独立持续时间统计。
- 当前没有稳定人体 track ID，姿态缓存按摄像头而非同一人体轨迹组织。
- `no_person` 当前是单摄像头边缘候选，不能表达家庭级跨摄像头 12 小时未见老人。
- 当前云端 Qwen 只用于关怀卡文字，事件图片复核调用、结果表和事件复核状态尚未实现。
- 当前通知幂等键固定到事件和目标，同一事件不会每分钟形成新的提醒投递。
- 旧摄像头删除后仍可能残留开放 observation log，必须增加摄像头生命周期清理。

#### B. 目标内部架构

代码保持可维护的三层，不对应多个页面：

1. `PerceptionEngine`：YOLO、骨架、姿态分类、火灾和场景。
2. `TemporalDecisionEngine`：人体跟踪、姿态片段、因子图、跌倒、长时间地面躺卧和恢复。
3. `CloudVerificationService`：证据上传、Qwen 图片复核、家庭存在汇总、提醒与每日摘要。

#### C. 新数据对象

边缘端：

- `PersonTrack`：camera_id、track_id、首末出现时间、最近人体框、置信度和状态。
- `PresenceSession`：某路摄像头的有人片段、样本数、覆盖率和代表截图。
- `PostureEpisode`：track_id、姿态、开始/结束时间、持续秒数、置信度、场景区域和代表证据。
- `EvidenceBundle`：候选前、中、后代表帧或短片、结构化时序摘要和校验和。

云端：

- `FamilyPresenceState`：家庭级最后见人时间、摄像头覆盖、暂停/外出状态和长时间未见计时。
- `VisionVerificationJob`：事件或姿态片段、模型请求、严格 JSON 结果、延迟、费用、重试和状态。
- `SafetyIncident`：在现有 Event 上增加 candidate/verifying/confirmed/rejected/acknowledged/resolved 生命周期。
- `IncidentReminder`：event_id、提醒序号、分钟时间桶、渠道、状态和停止原因。
- `ActivitySummary`：家庭、时段、结构化统计、来源片段和模型生成解释。

#### D. 第一版时序规则

- 人体确认：空闲约 1 FPS；首个可信人物命中立即进入观察模式，稳定 `person_present` 再由近期多次命中确认。
- 姿态检测：观察模式目标约 2 FPS，快速下降等风险期间短时目标 3-5 FPS；连续 3 秒多数一致后形成普通姿态片段。
- 姿态集合：standing、sitting、squatting、bending、lying、upper_body、unknown。
- 快速跌倒：保留现有站坐基线、下降、低位持续和床/沙发排除，动作触发后约 1.5-3 秒内形成边缘临时候选；云端复核异步更新结论，不阻塞 App 首次提醒。
- 长时间地面躺卧：非床/沙发地面 lying 连续 180 秒且未恢复。
- 火灾：连续约 1-2 秒多帧强命中，边缘先创建临时紧急事件。
- 长时间未见：云端跨摄像头 12 小时，无外出/暂停状态，且有效摄像头在线和覆盖率达标。

以上是首版默认值，必须通过数据集和真实家庭样本校准，不作为医疗安全承诺。

#### E. 云端视觉复核协议

输入：

- 1-3 张代表帧或 3-5 秒短证据。
- person track、姿态序列、持续时间、场景区域、边缘分数和规则原因。
- 只发送当前事件所需信息，不发送持续录像。

输出 JSON：

```json
{
  "person_count": 1,
  "posture": "lying",
  "surface": "floor",
  "emergency": true,
  "confidence": 0.88,
  "suggested_event_type": "prolonged_floor_lying",
  "reason": "人物位于非床沙发区域并持续低位未恢复"
}
```

执行原则：

- 快速跌倒和强火灾不等待云端才入 App，先标记 `verifying`。
- 云端超时或失败时保留边缘事件并显示“云端复核暂不可用”。
- 云端拒绝后不删除事件，改为 rejected/downgraded 并保留用户误报反馈。
- 统计时长和次数由程序计算，模型只负责画面语义与解释。

#### F. 分阶段实施

阶段 1：数据降噪与人体轨迹

- 已完成：新增 `TemporalObservationEngine`，统一管理每路摄像头的稳定 track ID 和 48 条紧凑环形历史。
- 已完成：新增 `presence_sessions`，按有人片段合并样本、最大人数、轨迹和代表快照。
- 已完成：`no_person / no_motion` 直接更新 observation log，不再产生每采样候选。
- 已完成：摄像头停用、删除、云端同步移除或历史孤儿状态均会关闭观察片段，并清理 worker、规则引擎和轨迹内存。
- 已完成：实时预览只接受 `live` 或 `live_preview`，公开数据集和事件证据不再作为画面回退。

阶段 1 状态：已完成并部署到真实树莓派和腾讯云。下一步进入阶段 2，不提前实施云端紧急复核。

阶段 2：姿态细分类和片段状态机

- 已完成：新增 `PostureClassifier`，使用躯干方向、人体宽高比、膝关节角度、髋膝高度、腿部紧凑度和膝髋展开比建立可解释 baseline。
- 已完成：输出 `standing / sitting / squatting / bending / lying / upper_body / unknown`，同时保留旧标签映射，保证现有跌倒和活动逻辑平滑过渡。
- 已完成：轨迹层会把重叠骨架姿态合并进 person track，不再只记录人框的 `unknown`。
- 已完成：最少 2 个样本且持续 3 秒后开启 `PostureEpisode`；新姿态稳定前保留原片段，track 过期或摄像头生命周期结束时关闭。
- 已完成：SQLite 持久化 `posture_episodes`，保存时间、置信度、样本数、场景区域、正常卧躺区域和代表快照。

阶段 2 状态：已完成并部署到真实树莓派。下一步进入阶段 3，将空间骨架、姿态片段、下降轨迹、场景和恢复状态合并为姿态因子图。

阶段 3：姿态因子图和安全事件

- 已完成：新增 `PoseFactorGraphEngine`，按稳定 track 输出近期直立、下降位移、水平一致性、低位/横卧、运动、场景排除、持续时长和恢复因子。
- 已完成：快速跌倒因子接入原 `RuleEngine`，保留原 YOLO、RTMPose、下降转变、多帧确认、恢复和事件去重，不增加平行告警状态机。
- 已完成：同一 track 在非床/沙发区域连续 `lying >= 180s` 时生成 `prolonged_floor_lying`，普通卧床和卧沙发继续抑制。
- 已完成：从 48 条时序历史选择开始、转折、当前最多 3 张代表快照，并保存 track、姿态序列和因子图作为事件证据。
- 已完成：工作线程重启会以 `worker_restart` 关闭旧进程遗留的开放 observation、presence 和 posture 状态。
- 已完成：树莓派与公开数据集回归保持原基线，UR Fall 序列 `TP=8 / FP=0 / FN=0`，GMDCSA24 序列 `TP=2 / FP=0 / FN=2`。

阶段 3 状态：已完成并部署到真实树莓派。下一步进入阶段 4，将事件证据包提交给云端多模态模型进行严格 JSON 复核；当前不得把边缘候选描述成已由云端确认。

阶段 4：云端图片复核

- 已完成：复用 `model_generation_jobs` 持久化 `purpose=vision_event_verification` 的独立复核任务，事件 payload 保存用户可见复核状态。
- 已完成：边缘事件先入库和通知，再异步调用 Qwen；模型失败不撤销、不阻塞边缘告警。
- 已完成：输入包含一张事件证据图、边缘规则、指标、姿态因子图和时序摘要；API Key 不进入任务请求或事件数据。
- 已完成：严格校验 `person_count / posture / surface / emergency / confidence / reason / suggested_event_type`，额外字段、缺字段、非法枚举和越界数值均拒绝。
- 已完成：视觉复核生产超时统一为 120 秒、最多 3 次重试、`5s / 30s / 120s` 退避、响应和错误审计。
- 已完成：App 事件列表和详情显示待复核、已确认、未确认、证据不足、重试中和复核失败状态；用户仍需人工确认事件。
- 已完成：真实 `Qwen/Qwen3.5-27B` 使用 UR Fall 公开图片返回 `lying / floor / emergency=true / confidence=0.92`，生产验证任务一次成功。

阶段 4 状态：已完成并部署腾讯云。当前为单张事件证据图 + 多帧结构化摘要复核；另外两张代表快照尚未上传。下一步进入阶段 5，建立家庭级长期未见状态和 SafetyIncident 持续提醒。

阶段 5：家庭级长期未见和持续提醒

- 已完成：盒子按摄像头上报 `last_observed_at / last_person_seen_at / observed_samples / person_samples / observation_coverage`。
- 已完成：云端将存在状态持久化到摄像头和家庭 metadata，只有全部启用摄像头在线、同步、报告新鲜且覆盖率至少 50% 时进入有效观察。
- 已完成：默认 12 小时未见生成家庭级 `long_absence`；任一路见人自动解决，摄像头离线和覆盖不足暂停计时。
- 已完成：支持 `away / travel / hospital / paused / paused_until` 抑制，不把已知外出状态当异常。
- 已完成：新安全事件统一带 `incident_id / status / started_at / reminder_count`，不把历史事件批量迁移为持续提醒。
- 已完成：首次事件通知后满 1 分钟开始按分钟时间桶生成提醒，App 确认后 incident 进入 acknowledged 并停止后续提醒。
- 已完成：真实双摄像头覆盖率均为 `0.8194`，家庭状态为 observing，最近见人后未误触发 long_absence；部署后历史 incident reminder 为 0。

阶段 5 状态：已完成并部署树莓派与腾讯云。APNs 未接入前，每分钟提醒形成 App 消息和模拟投递记录；真正系统推送待 iOS/APNs 阶段完成。

阶段 6：统一视觉感知页面与家庭存在交互（已完成本地闭环）

- 已新增家庭存在状态读取接口，统一返回家庭状态、每路观察有效性、覆盖率、最后见人时间和家庭创建者权限。
- 已新增家庭创建者专用的外出与暂停守护接口；临时外出、旅行、住院和定时暂停均持久化到家庭关怀配置，普通成员不能绕过通用配置接口修改。
- 已重构普通 App 守护页，只保留家庭状态、双路实时画面、每路姿态/覆盖摘要和 active SafetyIncident；数据轮询不重建视频节点。
- 已在“我的”增加唯一的“外出与暂停守护”入口，不在守护、陪伴或事件模块重复放置。
- 已把研发侧检测页合并为“视觉感知”，同页展示人形、姿态因子图、区域、姿态持续、烟火指标、规则证据和云端复核状态。
- 已移除视觉页的数据集占位图；无真实视频或真实抓拍时显示空画面，不得回退到公开样本或历史事件证据。
- 已完成 390px 移动端宽度、刘海安全区、横向溢出、模式选中态和历史候选标识验证。

阶段 6 云端同步已完成：腾讯云服务重启后保持 active，PostgreSQL 和 HTTPS 正常；家庭创建者账号完成 `away -> active` 持久化验证并恢复正常守护；家庭状态为 `observing`、有效摄像头 `2/2`，两路云中继均返回真实 `640x360` 视频帧。下一步进入阶段 7。

阶段 7：数据集与学习模型

- 已完成数据就绪审计：现有 `27` 个唯一跌倒/ADL 序列满足当前跌倒规则回归门槛，但家庭困难负样本、姿态类别序列、火灾时序和 train/validation/test 序列隔离均不足以训练新模型。
- 已把 GMDCSA24 从每段 2-3 帧扩展为复用原视频的每段 12 帧密集时序回归，不增加新数据来源；单帧评测仍保留原稀疏样本用于横向对比。
- 已增强失败报告，逐帧记录人形数、骨架数、跌倒分、姿态分、目标框、下降距离、状态迁移和候选类型。
- 已修复跌倒过程中弯腰/半坐帧覆盖最近站立/坐姿基线的问题；20 秒窗口保留最多 24 个有界基线目标，从空间匹配历史中选择可解释本次下降的基线。
- GMDCSA24 密集序列从 `TP=2 / FP=0 / TN=5 / FN=2` 提升为 `TP=3 / FP=0 / TN=5 / FN=1`；UR Fall 保持 `TP=8 / FP=0 / TN=10 / FN=0`，家庭负样本保持 `TN=6 / FP=0`。
- 剩余 GMDCSA24 漏报只有一帧强躺倒证据，随后人体连续出画；不通过降低阈值或单帧直接报警追求数据集满分。
- 当前比赛阶段冻结现有回归集，不启动 ST-GCN 训练。后续真实运行出现无法覆盖的困难场景时，再定向补样本和人工标签。
- 已部署真实树莓派：Pi `.venv-pi`、YOLO、RTMPose 和新跌倒基线回归均通过；双摄 `online/synced`、覆盖率约 `0.836`、云中继 `8 FPS`，云端家庭状态保持 `observing / 2 of 2 valid`。

#### G. 验收指标

- 人体存在：召回率、每摄像头小时假人次数、5 秒确认延迟。
- 姿态：按类别 macro F1、片段持续时间误差、姿态切换边界误差。
- 跌倒：序列级召回、每摄像头日误报数、告警延迟、床/沙发误报。
- 长时间地面躺卧：事件召回、恢复后误提醒、云端复核一致率。
- 长时间未见：每家庭日误报数、离线误判数、外出状态抑制正确率。
- 火灾：每摄像头日误报数、强候选延迟和云端复核延迟。
- 系统：双路视频流畅度、边缘 CPU/温度、上传量、云端模型耗时与费用。

#### H. 硬件加速边界

- 当前真实盒子 4 核 8GB，审计时进程约 38% CPU、温度约 56℃、可用内存约 6.3GB；先完成算法状态与数据架构。
- AI HAT+ 作为可插拔 inference backend，不进入业务规则。只有达不到目标 FPS/延迟时再采购和适配。
- Hailo 接入需要模型转换与回归；可优先评估单模型人体+骨架方案，但不得在未验证 RTMPose/YOLO 兼容性前承诺“插上即用”。

#### I. 阶段 8：统一实时感知研发页（已完成）

- 已取消算法预览下拉框和独立算法演示素材，研发页只保留一个真实摄像头画面。
- 已新增 `unified` 实时分析模式，同时启用人体、姿态、场景家具、画面质量、活动、跌倒和火灾结果。
- 已在同一画面叠加人物框、人物编号、RTMPose 骨架、中文姿势，以及沙发、床、椅子、餐桌和电视等场景目标。
- 已把跌倒、火灾和摄像头异常改为同画面状态，侧栏开关只负责配置能力启停，不再切换预览模块。
- 已把当前目标、运行指标、安全记录和生活观察收口到紧凑侧栏，历史列表在固定高度内滚动。
- 已通过本地视觉 smoke 回归、Pi 部署、服务重启和 Playwright 实机验收；`algorithm=unified` 请求成功，页面无脚本错误和横向溢出。

阶段 8 状态：已完成并部署真实树莓派。下一步不继续扩管理台模块，转入真实家庭样本观察与事件准确性校准；只有出现现有回归集无法覆盖的误报或漏报，才定向补样本和规则。

#### J. 阶段 9：屏幕内容抑制、跌倒语义和视频恢复（已完成）

- 已增加稳定电视区域的屏幕内容抑制，电视节目中的人物不计入家中人数、姿态、活动或跌倒趋势。
- 已明确姿态与事件边界：站、坐、躺是单帧/片段事实；跌倒必须由同一人物的站坐基线、快速下降、空间一致、非床/沙发低位持续和连续帧状态机共同确认。
- 已修复人物框与骨架合并时丢失沙发/床区域的问题，正常卧躺区域不得被姿态空值覆盖。
- 已增加 MJPEG 内部重连、近黑解码帧抑制和页面指数退避重连；后续 GH-029 明确禁止用上一画面保持实时输出，持续真实黑屏仍由独立质量状态审计。
- 已将已确认的本地误报事件 `#1877` 标记为 `false_positive`，活跃安全记录查询自动排除误报事件。
- 已保持 UR Fall `8/0/10/0` 和 GMDCSA24 密集序列 `3/0/5/1` 基线，Pi 连续页面采样画面亮度稳定、黑屏 false、跌倒阶段 clear、控制台无错误。

阶段 9 状态：已完成并部署真实树莓派。下一步观察真实人物进入、坐下、躺沙发、站起和离开画面的完整片段，重点统计 track 稳定性、姿态切换边界和每摄像头小时误报数。

#### K. 阶段 10：姿态人体一致性、云端复核日志和黑屏恢复（已完成）

- 已把 RTMPose 输出拆成可信 `poses` 与诊断 `rejected_poses`；拒绝骨架不进入人物、缓存、活动时序、跌倒和前端绘制。
- 已新增家具假骨架一致性门：无 YOLO 人框、低置信、超宽横向骨架且与稳定沙发/床/椅子/餐桌明显重叠时拒绝；真实躺姿和高置信遮挡坐姿有独立保留回归。
- 已新增云端设备级复核查询接口和盒子代理接口；管理页展示模型连接状态、事件结论、模型、原因、置信度、尝试次数和失败日志。
- 已把视觉复核超时从独立默认 30 秒调整为生产 120 秒，并使用真实空沙发画面验证 Qwen 返回 `person_count=0 / surface=sofa / emergency=false / confidence=0.95 / suggested_event_type=none`，事件被降级为 rejected。
- 已增强 MJPEG：连续近黑解码帧永不覆盖最后有效预览，达到确认帧数后主动重开 RTSP；启动时无有效帧则不发布黑图。
- 已完成本地服务、上传代理、视频恢复、视觉 smoke、UR Fall、GMDCSA24、树莓派部署和 Chrome 实机验收。

阶段 10 状态：已完成并部署树莓派与腾讯云。下一步不再继续堆管理台功能，进入真实人物动作片段采集和误报统计；重点验收人物进入、坐下、正常躺沙发、起身、快速跌倒和离开画面的完整时序。

#### L. 阶段 11：云端 SafetyIncident 事件编排（已完成）

- 已把安全事故状态扩展为 `verifying / confirmed / rejected / uncertain / acknowledged / resolved`，同时兼容历史 `active` 数据。
- 已增加 incident 状态迁移审计，记录来源、时间、触发事件和模型复核状态，最多保留最近 24 条迁移。
- 已实现模型复核后续消息：confirmed 生成高优先告警，rejected 归档原告警并生成排除说明，uncertain 生成需要人工确认的高优先消息。
- 已实现同家庭、同事件类型、45 秒窗口内的跨摄像头关联；多个摄像头保留各自事件证据，但 App 列表、初始消息和持续提醒只使用主事件。
- 已实现复核聚合优先级：任一路 confirmed 即确认；没有确认但存在 uncertain、failed 或 unavailable 时需要人工确认；仍有任务处理中时保持 verifying；全部 rejected 才排除。
- 已实现用户确认联动：处理任一关联事件会确认整个 incident、归档关联消息并停止后续分钟提醒。
- 已通过服务端回归、PostgreSQL 数据导出恢复回归和腾讯云真实空沙发验证；验证事件从 verifying 自动转 rejected，状态迁移与任务编排日志均已保存，且测试事件不会生成用户消息。

阶段 11 状态：云端事件编排核心已部署。下一步进入 iOS/APNs 前置工作：把 notification delivery 的 queued 记录接入真实 APNs provider，并在 App 事件详情中把 incident 时间线和多摄像头证据作为统一对象展示。

#### M. 阶段 12：猫狗独立识别与安全隔离（已完成）

- 已使用现有 YOLO11 COCO `cat / dog` 类别输出独立 `pets / pet_count / pet_types`，未引入新模型和额外推理进程。
- 已保证猫狗不进入 `people`、RTMPose、活动时序、跌倒状态机、PresenceSession 或家庭 `last_person_seen_at`。
- 已增加电视宠物画面抑制和稳定家具场景关联；统一管理页显示宠物框、中文类型、置信度和场景，不把宠物显示为人物。
- 已把宠物写入 DetectionResult、事件 evidence 和云端视觉复核结构化上下文；默认模型提示明确区分人物和猫狗。
- 已增加回归：单猫画面必须得到 `pet_count=1 / person_count=0 / fall_candidate=false`，事件证据保留宠物，电视中的宠物被过滤。
- 已通过视觉 smoke、跌倒规则、服务端测试、UR Fall `8/0/10/0` 和 GMDCSA24 密集序列 `3/0/5/1`，并部署树莓派与腾讯云。

阶段 12 状态：核心链路完成。下一步先做真实猫狗画面校准和双摄运行观察；确认误检与性能后，扩展盒子状态上报，在 App 守护页显示“未见老人 / 有宠物活动”，随后再进入 iOS/APNs 与 incident 详情适配。

#### N. 阶段 13：盒子事件日志与云端事件对账（已完成）

- 已新增云端设备令牌接口 `/api/v1/device/event-log`，只返回当前盒子所属事件的 edge ID、云端 ID、incident、模型复核、处理状态和时间。
- 已新增盒子 `/api/event-log` 聚合接口，按本地 Event ID 合并事件上传、证据上传和云端 `edge_event_id`，不会把观察片段或实时算法候选当成正式事件。
- 已新增 `/admin/events.html`，固定展示“盒子触发 -> 证据上传 -> 云端接收 -> 最终状态”四段链路，并提供状态、类型筛选和证据查看。
- 已明确交互权限：App 用户确认是事故处理的唯一入口；盒子后台只允许提交算法误报，不提供本地“已处理”按钮。
- 已新增受设备令牌保护的误报反馈接口。盒子先等待云端成功，再更新本地；云端将关联 incident 转为 rejected、归档提醒并保存 `edge_admin` 反馈来源。
- 已通过服务端、上传代理、视觉和跌倒回归；桌面 1440x1000 与移动 390x844 渲染检查通过，移动端导航压缩后首屏可看到事件内容。
- 已使用真实数据验证本地 `#1877 -> 云端 #7` 对账，并把历史误报状态修正为 rejected。

阶段 13 状态：已完成。下一步回到阶段 12 的真实猫狗画面校准与 App 宠物活动摘要；随后在 App 事件详情中复用同一 incident 时间线，而不是再开发另一套事件状态组件。

#### O. 阶段 14：宠物活动家庭状态与 App 展示（已完成）

- 已在盒子 cameras 表持久化 `last_pet_seen_at / last_pet_count / pet_types`，只在真实 snapshot `pet_count > 0` 时更新。
- 已把宠物字段加入每路摄像头 presence report；人物样本数和最后见人时间不受宠物快照影响。
- 已在云端家庭 presence 聚合最近宠物时间和类型，默认 6 小时内标记 `pet_activity_recent=true`，但 absence 仍只读取 `last_person_seen_at`。
- 已在 App 守护首页增加家庭宠物活动和每路摄像头宠物活动；宠物比人物更新时展示“暂未看到老人，检测到宠物活动”。
- 已修复待确认提醒仍只识别旧 `active` incident 的问题，兼容 `verifying / confirmed / uncertain`。
- 已增加回归，验证单猫快照为 `person_count=0` 时上报宠物活动，但云端 `absence_seconds` 继续按上一次人物时间增长。
- 已部署树莓派和腾讯云并提升静态资源版本号；双路当前无宠物数据，线上不会出现虚构宠物状态。

阶段 14 状态：数据闭环已完成。下一步需要真实猫狗入镜，校准 YOLO 置信度、遮挡、电视画面与双摄重复命中；确认后再评估是否把宠物活动加入首页关怀卡事实，不新增宠物健康或宠物告警需求。

#### P. 阶段 15：App 事件详情统一事故时间线（已完成）

- 已复用事件 `payload.incident`，在 App 详情中展示边缘发现、跨摄像头佐证、云端复核和最终处置。
- 已按 `source_camera_ids` 合并多摄像头事实，不为同一事故增加第二条用户事件。
- 已映射 `vision_verification / app_user / edge_admin / presence_recovery` 状态来源，页面不暴露模型任务和设备上传的工程字段。
- 已修复云端 rejected 或系统 resolved 后页面仍显示“需要确认”、仍可重复操作的问题。
- 已给公共事件对象补充 `updated_at`，供终态和用户操作时间展示。
- `npm test`、JavaScript 语法、390x844 Chrome 检查通过；本地与腾讯云服务均已部署并验证。

阶段 15 状态：已完成。下一步优先完成真实猫狗现场校准；无真实宠物条件时，继续加强 App 事件详情的多图证据，但不得用公开数据集画面替代实时摄像头内容。

#### Q. 阶段 16：关键帧多图复核与验证隔离（已完成）

- 已从 `temporal_evidence_bundle` 选择去重后的事发前、转折、当前关键帧，并在事件上传前完成媒体上传。
- 已把多张媒体资产随事件绑定到同一 edge event；上传任务保持幂等，旧单图事件兼容。
- 已把视觉复核任务从单个 `asset_id` 扩展为最多 3 个 `asset_ids`，模型上下文包含帧角色、时间和姿态摘要。
- 已在 App 事件详情增加横滑关键帧，390x844 实测 3 张图片正常加载、无横向页面溢出。
- 已升级公开跌倒探针脚本，可生成隐藏的三关键帧复核任务。
- 已用腾讯云真实 Qwen 完成一次三图验证，一次请求成功，结果为 fallen/floor/emergency=true/confidence=0.92。
- 已修复验证事件仍被定时器持续提醒的问题，并增加回归确保测试事件不产生用户消息。
- 已将宠物默认置信度从 0.25 提升到 0.40，清理现场固定物体造成的单帧 dog=0.2819 错误状态。

阶段 16 状态：已完成并部署。下一步应加强正式事件的证据保留和事故恢复闭环，优先核对跌倒报警每分钟提醒、App 确认停止提醒、恢复后自动结束三者在真实事件中的一致性；宠物现场校准等待真实猫狗条件。

#### R. 阶段 17：可信姿态恢复与提醒归档（已完成）

- 已确认原缺口：盒子 RuleEngine 会进入 recovered，但此前没有把恢复状态上传云端。
- 已增加本地最近未解决事故查询、edge recovery 持久化和 `event_state_upload` 幂等任务。
- 已限定只有 recovered + person visible + standing/sitting/squatting + confidence>=0.45 才能提交恢复。
- 已增加云端设备事件 state 接口，校验设备归属、事件类型、状态、resolution 和姿态证据。
- 已把同 incident 关联事件统一置为 resolved/acknowledged，归档开放消息，追加 edge_recovery transition。
- 已验证人物消失、无姿态、0.44 低置信站姿均不会恢复；0.82 站姿只创建一个恢复任务。
- 已完成真实腾讯云状态契约探针：弱证据 400，强证据 200，incident=resolved；重启后测试事件未进入 PostgreSQL。

阶段 17 状态：已完成。后端提醒闭环已具备，但 iOS 真机 APNs 到达、通知点击进入正确事件、App 前后台确认同步仍需在 iOS 壳阶段验收。

#### S. 阶段 18：iOS 真机壳、页面性能与生产代码清理（进行中）

- iOS 真机已完成开发签名、安装、信任和启动，当前使用 `com.gohome.family` 加载腾讯云 HTTPS App。
- 原生启动白屏已替换为品牌加载页；首次网页加载完成后平滑进入登录页，加载失败可重试。
- 云端 App API 已改为同源连接，不再逐页探测手机 `127.0.0.1:8711`；静态资源已增加分类缓存、ETag 和 304。
- 公共 API 客户端已增加会话级分层缓存：家庭与关怀资料使用分钟级缓存，设备与摄像头使用秒级缓存，事件短缓存，实时快照不缓存；任何写操作自动失效缓存。
- 已删除 3 份零引用旧前端脚本、29 张零引用图片和 16 页重复内联导航；完整本地闭环保持 37/37 通过。
- 树莓派启动已解除算法演示视频强制依赖；环境备份、旧源码、测试日志和 PID 已清理。QA/数据集脚本保留在 Git，但不再部署到正式盒子和云端。
- `app-shell.html` 仍被盒子 public pilot 通知入口引用，`detection.html` 仍被实时画面页引用，纪念模式页面仍互相引用；这些页面必须先迁移入口再删除，本阶段不做破坏性清理。

阶段 18 当前状态：基础真机运行和第一轮性能清理已完成。下一步先在真机复测主导航、首页卡片状态复用和视频流；确认稳定后再迁移旧 `app-shell / detection` 产品路径，最后进入 APNs 能力配置。

#### T. 阶段 19：双摄实时视频统一 8 FPS（已完成）

- 已确认两路摄像头原始子码流均为 15 FPS，实际解码约 14.4 FPS。
- 已定位低帧率根因是 `drop_stale_frames` 固定吞帧和解码后再次完整休眠，不是树莓派算力或腾讯云负载不足。
- 已把盒子后台、算法页、设备视频档位和云端回退档位统一为 8 FPS、`drop=1`。
- 已将视频生成器改为 deadline 节拍，盒子双路实测约 7.68 到 7.69 FPS，云端每路稳定接收约 8 帧/秒。
- 已验证双路运行时 CPU、内存、温度和系统负载正常，断流重连和黑屏抑制回归通过。
- 播放 FPS 与算法采样保持独立；跌倒视频数据用于动作趋势和持续时间验证，不要求 YOLO、姿态和云端模型逐播放帧运行。

阶段 19 状态：已完成并部署树莓派与腾讯云。下一步在 iPhone 真机复测守护页双摄切换、持续播放和前后台恢复；若 8 FPS 体验稳定，不再继续提高 MJPEG 帧率，后续流畅度升级应转向 H.264/WebRTC，而不是继续增加 JPEG 上传带宽。

#### U. 阶段 20：路由器重启恢复与摄像头稳定身份（进行中）

- 已确认盒子重启后地址仍为 `.12`，当前两台摄像头地址为 `.3` 和 `.11`。
- 已定位实时流长期中断根因：每个观看者重复打开 RTSP，且 15 FPS 源帧没有被持续排空，TCP 队列积压后触发 HEVC 解码错误和 30 秒读取超时。
- 已实现每摄像头单连接共享读取器，源帧持续读取、订阅者只消费最新帧；双摄 RTSP Receive-Q 持续为 0。
- 已把 OpenCV 打开/读取超时改为创建时参数，并把读取超时收紧到 5 秒。
- 已通过正常云端配置链路恢复 `.11` 书房摄像头；双摄均为 online/synced，云端每路收帧 8 FPS，公网 HTTPS 实测约 7.2 到 7.3 FPS。
- 已确认当前正式配置仍以 RTSP IP 为主要身份，尚不能在下一次 DHCP 地址变化后自动确认同一物理摄像头。

阶段 20 当前状态：实时流单连接和当前双摄恢复已完成。DHCP 地址保留、ONVIF UUID/MAC 持久化和地址变更回传继续作为并行网络稳定性任务，不再阻塞阶段 23 的 EACP 安全检测重构。

#### V. 阶段 21：云端摄像头配置唯一真相（已完成）

- 已确认当前云端和盒子配置版本一致，cloud camera 2/3 分别映射 local camera 24/25。
- 已修复同步器只删除 camera_map 内旧记录的问题；完整云端 cameras 快照会清理所有未被当前版本引用的本地旁路摄像头。
- 已新增云端配置 authority。云端签发设备令牌或本地绑定任一成立时，正式盒子进入 cloud_managed。
- 已禁止 cloud_managed 盒子的本地摄像头 POST/PATCH/DELETE；扫描、连接测试和诊断保留。
- 已把盒子摄像头后台改为只读同步视图，正式增删、启停和配置统一回到 App。
- 已用真实管理员会话验证本地 PATCH 返回 409，并通过配置同步、权限判定、Python 编译和 JavaScript 语法回归。

阶段 21 状态：已完成。后续摄像头配置功能只在 App/云端继续开发，盒子后台不得重新加入正式写入口；DHCP 稳定身份自动恢复与 EACP 分别推进，不以网络身份增强延后跌倒检测高频采样。

#### W. 阶段 22：算法帧结果同步与低置信假骨架抑制（已完成）

- 已确认旧管理页是 8 FPS MJPEG 视频与 5.2–9 秒固定轮询结果异步叠加，人移动后旧框和骨架仍停在原位，造成延迟和假识别。
- 已为每个摄像头缓存帧生成 `frame_id / captured_at`，实时分析接口原子返回本次分析 JPEG 与结果。
- 已把管理页改为串行快速分析，丢弃旧摄像头、旧模式和旧采集时间响应；每 6 秒的日志刷新不再覆盖分析画面。
- 已禁用管理预览的 8 秒旧骨架沿用，并对共享 DetectAgent 增加推理锁，防止 worker 与预览并发进入模型。
- 已对无 YOLO 人形佐证的 pose-only 候选增加 0.42 最低置信门，修复空沙发靠垫被拼成 0.36 “躺姿”的现场误报；有 YOLO 佐证的真实躺姿和高置信遮挡坐姿保持通过。
- 已增加帧标识、前端过期响应、推理串行和低置信 pose-only 回归，并在真实树莓派双摄页面验证。

阶段 22 状态：已完成并部署树莓派。管理页分析约 0.5–0.7 秒更新，单次推理约 0.30–0.50 秒，帧龄通常 0.0–0.3 秒。下一步进入阶段 23 EACP；管理预览频率不代替正式事件采样策略，DHCP 稳定身份作为并行网络任务。

#### X. 阶段 23：EACP 事件自适应连续姿态感知（P0/P1/P2/P3a/P3a.1/P3a.2 已完成，P3b-P6 待实施）

目标：在不阻塞双路 8 FPS 视频的前提下，消除正式 worker 当前每路约 6 秒一次的固定低频采样，使人物出现后进入约 2 FPS 模型锚点、快速下降等风险期间短时达到目标 3-5 FPS，并通过可信短时跟踪把研发骨架展示提升到 6-8 FPS。

架构约束：

- 保留现有 YOLO、RTMPose、场景区域、PoseFactorGraph、RuleEngine、三图上传和云端 Qwen 复核，不建立第二套事件状态机。
- 每路摄像头使用独立最新帧、轨迹、模式和 deadline；模型执行可以共享，但不得共享跨摄像头跟踪状态。
- 调度优先级为 `risk > active > idle`，同优先级公平轮转；处理落后时丢弃旧 deadline，只分析最新帧。
- 视频、轻量连续观察、模型锚点和云端复核是四条不同频率链路，不能再由页面轮询驱动正式算法。
- `observed / tracked / expired` 必须贯穿模型输出、前端绘制和事件安全门；跟踪帧只能触发升频，不能单独报警或恢复事故。

实施批次：

1. **P0 只读基线与契约测试（已完成）**：已记录每路帧龄、推理耗时、模型锚点 FPS、调度模式、CPU、温度和持久化增量；失败回归证明旧 worker 的固定休眠和双摄串行问题。
2. **P1 最新帧独立调度（已完成）**：已把整轮双摄加固定 sleep 改为每摄像头 deadline 和统一优先队列；空闲约 1 FPS、活跃目标约 2 FPS、风险目标 3-5 FPS，吞吐不足时处理最新帧而不补跑历史帧。常态分析只按原 5 秒间隔持久化，人物出现/消失、风险和事件候选立即落盘，避免高频推理放大磁盘写入。
3. **P2 推理链去重（已完成）**：外层 YOLO 人框直接送入共享 RTMPose 姿态头；没有可用外部人框时才懒加载 RTMLib YOLOX 回退检测器，回退检测为空时直接返回无骨架，不再默认对整张画面做姿态推理。外部框与回退路径共用同一 RTMPose 实例，分析结果记录来源和框数量；原姿态分类、跌倒、时序、因子图、事件和持久化回归保持通过。
4. **P3a 连续关键点**：接入 KLT 关键点短时传播，增加前后向误差、骨骼几何、置信度衰减和约 600ms 正式新鲜度门；光流短暂失败时在最多 1.2s 的展示窗口进入 `coasting`，以低透明度虚线承接最后可信叠加层，随后才 `expired`。所有 `tracked / coasting` 均不得进入正式证据。**已完成并部署。** P3a.1 展示解耦也已部署并完成浏览器实机验收：管理页保持一条连续 MJPEG 底图，只轮询无 JPEG 的姿态元数据并叠加骨架；同帧 JPEG 仅用于研发精确帧复核。
5. **P3a.2 多摄推理预算与热保护（已完成）**：树莓派资源监控按 `normal / warm / hot / critical` 分级；调度优先风险路、同级公平轮转，任一路超过 3 秒未获预算时强制获得基础巡检。温度升高只增加推理冷却，不停止双路 8 FPS 视频、KLT、事件和云端链路；worker runtime 公开温度、当前降级状态和最近状态切换。
6. **P3b 多人轨迹**：已接入内嵌的 observation-centric 人框跟踪器。它使用速度预测、全局分配、短遮挡恢复和 2 秒重识别时限，覆盖多人交叉、快速位移、轨迹替换和摄像头隔离；这是面向当前树莓派的 OC-SORT 思路实现，不依赖 boxmot，也不宣称安装了上游 OC-SORT。轨迹结果仍不能绕过模型锚点成为正式安全证据。
7. **P4 风险升频与事件整合**：代码已由廉价运动门、KLT 的快速向下提示、人体中心下降、人体框变化和姿态因子触发短时 `risk` 升频；床/沙发内正常躺卧只保持 `active`。KLT 提示只唤醒下一次正式 YOLO/RTMPose 锚点，不进入 RuleEngine、恢复判断或事件证据；边缘临时候选与云端三图复核继续更新同一 SafetyIncident。真人跌倒端到端仍需现场动作完成最终验收。
8. **P5 数据驱动增强**：仅在真实回归确认具体误报/漏报缺口后按需补样本并评估轻量 TCN/Continual ST-GCN，输出下降、倒地和恢复趋势，与 PoseFactorGraph 并行；公开数据集是备选，不直接部署 SkateFormer、CoTracker 或 TAPIR。
9. **P6 加速后端评估**：只有 CPU 路线未达到双摄延迟和温度目标时，才对 RTMO、Hailo YOLO 或兼容姿态模型做同帧 A/B；业务规则不得绑定 AI HAT+。

验收门：

- 双路视频持续不低于 7.5 FPS；算法页开关不改变正式守护频率。
- 人物进入 1.5 秒内开始姿态观察，风险升频触发目标不超过 300ms，边缘临时候选约 1.5-3 秒形成。
- 活跃锚点约 2 FPS、风险目标 3-5 FPS、连续骨架展示 6-8 FPS，并在研发页明确锚点和跟踪来源。
- 跟踪结果过期、漂移或缺少新鲜模型锚点时不得报警；正常坐下、蹲下、弯腰、躺床/沙发和宠物画面不得因升频被放大为事件。
- 双摄同级公平、无历史帧积压，持续温度目标低于 75 摄氏度且没有热降频。

阶段 23 当前状态：P0-P3a.2 已完成并部署；P3b 跟踪与 P4 风险升频代码已完成并通过本地回归，正在进行真实人物端到端验收。P3b 回归覆盖多人交叉、短遮挡、快速站立到低位位移、长时间消失后的轨迹替换和跨摄像头隔离。P4 的 KLT 快速向下提示已经能够唤醒 `risk` 频率，但不生成事件。2026-07-20 部署后单服务进程、双摄在线、云同步/视频中继无错误，CPU 约 131-150%、温度约 61.5-65.3 摄氏度、`throttled=0x0`。这些数字不能替代真人跌倒的现场动作、边缘候选时延和云端三图闭环验收。

P3a.3 展示连续性修复（2026-07-19）已完成并部署：光流在正式 600ms 新鲜度门内失败时进入最多 1.2s 的 `coasting`，沿用最后可信姿态坐标并在管理页使用低透明度虚线；状态、人物框、骨架和 API 都明确这是 display-only。`coasting` 不更新任何正式人物、姿态、跌倒、恢复、长期未见或云端事件数据，窗口耗尽后正常 `expired`。Pi 合成回归、API 回归、页面契约回归和真实运行计数均通过；当前 `continual_pose_error` 与 worker `last_error` 为空。该补丁不代表 P3b 多人遮挡恢复或 P4 风险升频已经完成。

P3a.3 运行稳定性补丁已于 2026-07-19 完成：盒子重启时配置同步可能执行运行记录清理，曾与上传线程争抢 SQLite 写锁。现将 SQLite 等待窗口延长至 120 秒，并让上传线程将 transient `database is locked` 转为退避重试，任何存储/网络异常都不能杀死上传 daemon。重启后的真实验证中两路重新 `online/synced`、上传线程 `running=true`、事件成功上传，新增日志无锁异常。该补丁不改变事件、配置或算法语义。

P4.1 非侵入式现场验收工具（2026-07-20）：

1. 在盒子内建立单会话验收服务，只读取正式 worker runtime、事件、候选、上传任务和云端复核，不写入算法配置，也不创建测试事件。
2. 为调度器和连续跟踪器补充有界诊断计数，记录风险信号来源和单调时间戳；诊断字段不得改变调度、证据或告警分支。
3. 增加受盒子管理员会话保护的开始、状态、结束和清理 API；无安全事件时不访问云端复核，避免管理轮询增加服务器负载。
4. 先完成正常动作负样本，再在用户可安全配合时做低风险模拟跌倒；每次只验收一路摄像头，另一摄像头继续按正式多摄调度运行，不改成单摄产品。
5. 通过门槛为：风险提示时延、风险锚点频率、正式事件时延、三帧证据、上传完成和云端多模态结论全部可追溯。未完成真人动作时阶段状态保持“工具已部署、现场验收待完成”。

P4.2 多人身份与证据链修正（2026-07-20）：

1. 保留站立基线的 `track_id`；多人目标有轨迹时只允许同轨迹历史参与下降计算，找不到同轨迹基线则不确认动态低位跌倒。
2. 动态事件证据优先选择最高风险姿态轨迹，并从该轨迹最近 10 秒历史取最多三帧。
3. 验收报告新增动作到事件、低位确认持续时间、确认路径、动态低位锚点数和云端复核理由；风险历史不足时显式报告 `history_truncated`。
4. 多人正常坐/站不得生成正式跌倒事件；单人真实跌倒仍需现场复验，不能用事件 `#2047` 的云端驳回替代真实跌倒通过。
5. 修复部署后重新执行边缘回归、盒子健康检查和一次负样本观察，再进行下一次真人动作验收。
6. 将普通沙发高度但家具漏标、同 ID 跨画面极端跳变加入固定负样本；动态坐姿要求 `bottom_y >= 0.88`，同 ID 目标状态继承要求中心距离不超过 `0.38`。
7. `simulated_fall` 的最终通过条件增加云端 `confirmed`；三帧上传完成但云端 `rejected` 的会话必须失败，避免把“链路跑通”误写成“跌倒识别通过”。

## 15. 2026-07-23 产品完善持续推进计划

### 15.1 当前基线

- 原生 iOS 已完成登录、引导、首页、守护、事件、产品推荐和我的第一版，并在真机通过云端访问。
- 腾讯云 PostgreSQL、盒子双摄同步、实时帧上传、事件、媒体、云端复核和 MJPEG 移动端播放已跑通。
- 现状仍是“初步跑通”。关怀行动、活动轨迹和家庭记忆已有独立闭环增量，但活动报告、隐私画面、APNs、社区服务履约和完整真机验收尚未完成。

### 15.2 有序实施批次

1. **P0 文档与契约冻结**：统一五栏导航、数据开关、活动区间、记忆权限、社区服务和 Hailo 后端边界。
2. **P1 首页关怀闭环**：把消息转成话题与可编辑文案，接入系统分享，并持久化已联系、稍后提醒和忽略动作。
3. **P2 守护合并**：合并实时画面、今日轨迹和事件；保留单路播放、摄像头切换、云端复核和统一 SafetyIncident。
4. **P3 活动日志与报告**：盒子聚合普通活动，断网排队，云端按小时、每日、每周分析；完成开关、留存和删除策略。
5. **P4 记忆 MVP**：完成家庭私密发布、最多 9 张照片或 1 个 60 秒内视频、可选当前位置、评论、喜欢、编辑、删除和由真实记忆生成联系话题；发布时间由服务端生成，不提供人物/时间手填项。
6. **P5 隐私与身份**：完成原画、人像模糊、骨架隐私切换；评估本地人脸特征和家庭成员 ID，不让身份识别阻塞安全算法。
7. **P6 社区服务**：先实现真实电话、导航、外链和需求登记；只有取得真实接口后才实现派单和状态同步。
8. **P7 Hailo 加速**：AI HAT+ 到货后完成驱动、HEF 转换、同帧 A/B、双摄 FPS、温度和稳定性验收。
9. **P8 发布验收**：完成 APNs、异常恢复、数据权限、真机回归、TestFlight 和比赛演示脚本。

P2 当前状态：原生页面已完成“实时 / 轨迹 / 事件”单页合并，事件复用统一数据与详情动作，非实时分段会停止视频流。轨迹分段暂不生成模拟数据；待 P3 完成普通活动区间上传和云端聚合后再接入真实今日轨迹。

P3 当前状态：云端 `ActivityInterval` 表、设备幂等批量接收、家庭今日轨迹查询和原生缓存时间轴已完成并部署。树莓派生产端、断网队列、家庭开关、留存删除以及小时/日/周汇总尚未接入，继续在视觉主线实施。

P4 当前状态：家庭私密时间流、最多 9 张照片或 1 个 60 秒内视频、可选当前位置、评论、喜欢、编辑和删除已完成；发布页只保留正文、媒体和地点，时间流显示服务端真实发布时间。系统照片选择器在进入发布页前限制数量，原生端完成图片收敛和视频自适应压缩后，通过持久化上传意图直传私有 COS；PostgreSQL 只保存结构化元数据，视频通过短时签名 URL 流式播放。iPhone 真机已通过照片选择、单视频限制、位置、发布回显、编辑、删除、此前因体积失败的视频重试、冷启动首次选择立即显示预览、上传中强制退出回收，以及重启后视频封面恢复和播放。腾讯云已部署 `009_media_upload_intents.sql`，真实过期对象探针和 App 中断上传均验证自动回收。P4 进入完成状态，后续不再改造媒体结构；事件证据迁移到 `event-evidence/*` 不属于本 P4 分支。

### 15.3 活动数据调度

- 跌倒、长时间倒地、火灾和设备离线继续实时上传。
- 普通人物出现、房间活动和姿态区间默认每 5 到 15 分钟批量上传；盒子离线时本地有界缓存，恢复网络后幂等补传。
- 云端每小时更新今日轨迹，每日固定时间生成摘要，每周生成趋势。日报失败不得阻塞紧急事件链路。
- 用户关闭活动轨迹后停止新的普通活动上传；紧急安全事件由独立开关和授权决定，不与普通日志共用一个总开关。

### 15.4 Hailo 实施门

- 购买前确认 Raspberry Pi 5、26 TOPS Hailo-8、PCIe 排线、主动散热和稳定电源。
- 驱动识别和 `hailortcli` 健康检查通过后，才进入模型转换。
- HEF 输出必须与现有 CPU 同帧结果做准确率比较；未通过困难负样本和事件回归时不能替换生产模型。
- 目标是提高正式模型锚点频率并降低 CPU/温度，不以管理页面骨架看起来更快作为唯一验收标准。

### 15.5 进度更新规则

- 每完成一个批次，先运行对应测试和真机/盒子验收，再回写 `Implement`。
- `Plan` 中的待办不等于已完成；硬件到货、页面出现或接口返回都不能单独视为产品闭环完成。
- ESP32 保留为门磁、求助按钮、环境传感器和配网的备选研究项，不阻塞 P1-P6。

### 15.6 已完成视觉主线基线

- 阶段 24 已完成“跌倒候选信号消失”和“人物物理恢复”的拆分；`PoseFactorGraphEngine` 生成同轨迹稳定恢复证据，`RuleEngine` 管理跌倒生命周期，`EdgeWorker` 只负责持久化和上传，云端只接受经过契约校验的恢复状态。
- 恢复必须为同一 `track_id` 连续稳定 `standing/sitting`；`squatting/bending`、遮挡、人物离开画面和旁人均不能恢复事故。多人事件按轨迹匹配，不按摄像头最新事件误关闭。
- 主线已完成下蹲、弯腰、旁人站立、同人站起/坐起、长时间倒地、临时信号间隙、上传幂等和云端恢复拒绝回归；真实现场 `2098/2099/2100` 被正确排除，`2101` 快速倒地被云端确认。
- 主线提交截至 `ec5dc9a` 已合入本原生 App 支线。后续 App/COS 开发不得修改视觉架构，也不得部署缺少主线事故契约的旧 `server.js`。

### 15.7 私有媒体异常上传回收

- 已新增持久化 `media_upload_intents`，在服务端签发 COS PUT 地址前先记录家庭、用户、对象键、媒体规格和过期时间；记录不包含 SecretId、SecretKey、临时签名 URL 或上传令牌。
- App 正常完成或主动中止上传时立即释放对应意图。App 被系统终止、网络中断或 PUT 后未确认时，服务端在签名过期后回收未登记 COS 对象；COS 删除失败保留意图并在下一轮重试。
- 回收任务默认随启用 COS 的服务启动，并每 5 分钟执行一次。已进入 `media_assets` 的对象只释放过期意图，不删除正式媒体；健康检查公开待处理数量，不公开对象地址或授权信息。
- PostgreSQL 媒体删除已改为显式参数化行删除，避免只修改进程内快照而残留数据库记录。JSON 本地仓储继续使用同一业务入口。
- 本批服务端 32 项测试中 31 项通过、1 项因本机没有 PostgreSQL URL 跳过；缓存/API 校验通过；iOS 70 个单元测试和 12 个 UI 测试全部通过。
- 腾讯云已应用 `008_activity_intervals.sql` 的迁移登记和 `009_media_upload_intents.sql`，并部署包含视觉事故契约、原生 App API、私有 COS 和过期回收的组合服务。远端服务、PostgreSQL、HTTPS、盒子在线状态和现有数据均正常。
- 真实 COS 过期对象探针已完成：服务启动后约 28 秒删除测试对象与 PostgreSQL 意图，`pending_media_uploads` 回到 0，正式记忆、媒体和事件计数不变。周期清理默认每 5 分钟运行，删除失败保留意图等待下一轮。
- iPhone 真机照片/视频发布、重启封面和上传中强制退出回收均已完成。下一顺序固定为：推送原生 App 分支 -> 接入 APNs 真推送 -> 完成发布签名与 TestFlight；不再重复改造记忆上传结构。

### 15.8 首次媒体选择一致性收口

- 真机部署后发现冷启动首次选择照片或视频时，发布页可能先以空种子创建；退出后第二次选择才显示。该问题属于 SwiftUI 表示状态竞争，不是 COS、压缩或系统相册读取失败。
- 修复计划已按单一请求状态执行：选择结果先形成拥有临时文件的待发布请求，选择器完全关闭后将同一请求提升为活动发布页，并通过 item-based sheet 直接传递不可变媒体种子。
- 待发布请求被替换或取消时立即清理其临时文件；编辑请求固定为空种子。禁止以固定延时作为主要修复，也不再保留发布布尔值、编辑对象、媒体种子和会话 ID 四套并行状态。
- 自动验收已覆盖首次提升、替换清理、取消和编辑四条路径。完整 iOS 回归通过后覆盖安装真机，最后以冷启动后第一次选择立即出现预览作为完成门槛。
- 冷启动首次选择已在 iPhone 15 Pro Max 通过，发布页第一次即显示预览；该项已完成。

### 15.9 APNs 与 TestFlight 激活计划

当前已完成但保持关闭的基础：

1. 服务端 APNs HTTP/2 provider、ES256 provider token、sandbox/production 分流、AES-256-GCM token 密文、计划时间门、三次有界重试和失效 token 撤销。
2. PostgreSQL 迁移 `010_apns_delivery.sql`，统一 JSON/PostgreSQL 导出与恢复字段；明文 device token 不进入业务数据库或云端 seed。
3. 原生 `PushNotificationCoordinator` 统一安装 ID、权限申请、token 登记、退出撤销和通知点击路由；事件通知进入“守护 / 事件 / 详情”。旧 `GoHomeShellRuntime`、`GoHomeShellWebView` 和 `GoHomeWebAppURL` 已删除。
4. 发送状态固定为 `queued -> sent/failed`。`sent` 仅表示 APNs 接收，不设置 `delivered_at`，不伪造终端送达。

付费账号到位后的执行顺序：

1. 以个人身份加入 Apple Developer Program，在正式 Team 下为 `com.gohome.family` 开启 Push Notifications，创建 APNs Auth Key 并只下载一次 `.p8`。
2. Debug 使用 sandbox，Release/TestFlight 使用 production；为目标加入 `aps-environment`，将 `GoHomePushEnabled` 按构建配置开启，不在源码中硬编码生产密钥。
3. 腾讯云以受限文件权限保存 `.p8`，注入 `GOHOME_PUSH_PROVIDER / GOHOME_APNS_TEAM_ID / GOHOME_APNS_KEY_ID / GOHOME_APNS_AUTH_KEY_PATH / GOHOME_APNS_TOPIC / GOHOME_PUSH_TOKEN_ENCRYPTION_KEY`，先执行迁移 010，再重启组合服务。
4. 真机重新安装或登录以登记新 token，分别验证前台、后台、App 被终止、事件通知、普通关怀通知、点击详情、退出撤销、无效 token 和 sandbox/production 隔离。
5. 上述通过后再 Archive、上传 App Store Connect、配置 TestFlight 内测；免费 Personal Team 构建不能作为 TestFlight 交付。

当前阻塞仅是付费 Apple Team 与 `.p8` 尚未提供。代码未部署到腾讯云，现有真机版本继续以推送关闭状态运行。

### 15.10 P8 发布元数据与隐私预检

当前已完成且不依赖付费账号的部分：

1. 新增并打包 `PrivacyInfo.xcprivacy`，按原生 App 当前真实数据路径声明收集类型、App 功能用途、无跟踪，以及 `UserDefaults` 的 `CA92.1` required reason。
2. Xcode 工程新增正式 Resources phase；`Assets.xcassets` 和隐私清单不再只是仓库文件，而是由构建系统编译或复制进入 App 包。
3. App Icon 保持原视觉内容，转换为 App Store 接受的 1024x1024 RGB PNG；发布版本设为 `1.0.0 (1)`。
4. 推送登记不再上传用户自定义的设备名称，只上传通用设备型号；稳定安装 ID 仍作为撤销单台安装实例的必要标识。
5. 新增 `npm run verify:ios-release` 并纳入全量 `npm test`，固定检查 HTTPS、系统权限说明、隐私类型、无跟踪、图标尺寸/alpha、资源阶段、版本号和免费签名不得声明 APNs。

剩余顺序不变：取得付费个人 Apple Team -> 开启 Push capability -> 创建 `.p8` -> 部署迁移 010 和 APNs provider -> 真机推送回归 -> Archive 与 TestFlight。发布元数据通过不能越过上述真实签名和投递验收。

### 15.11 活动数据 P2 收口与 P3 边界

本批已经完成：

1. 云端 `activity-overview` 按需生成今日事实摘要与七日趋势，多摄像头重叠区间合并计时，房间统计独立保留。
2. 时间线、概览、JSON 仓储和 PostgreSQL 仓储统一使用上海自然日的区间相交查询；跨午夜活动在每天边界裁剪，避免漏记下一天或重复整段计时。
3. 活动轨迹开关、7 至 365 天留存和家庭创建者清空普通活动记录已经进入原生设置与服务端权限模型；安全事件和证据不随普通轨迹删除。
4. 原生轨迹页采用缓存优先、后台刷新，展示今日分钟数、主要区域和七日趋势；无论冷启动数据是否已返回，都保持稳定页面容器，切换分段不重新挂载实时视频。
5. 用户端暂时隐藏未闭环的每日摘要、每周报告、规律异常提醒和多模态复核开关，避免无效配置制造产品承诺。

P3 后续按以下顺序执行：

1. 在视觉主线增加盒子侧活动区间生产器和持久化离线队列，按 `source_interval_id` 幂等补传；原生 App 分支只消费稳定契约，不修改 EACP 和跌倒状态机。
2. 完成云端日终/周度调度、基线比较、异常候选、审计和消息投递，再开放对应设置；任何状态或健康结论必须有可追溯事实与必要的多模态复核。
3. 先完成活动批次全量服务端、iOS 单元/UI 和发布预检，再提交原生分支；本批不部署腾讯云。随后进入原生设备/摄像头管理、隐私模式、数据导出与账号删除。

Apple 付费开发者审核、APNs capability、`.p8` 和 TestFlight 仍是独立阻塞项；活动 P2 收口不改变推送关闭状态，也不代表 P3 已完成。

### 15.12 原生设备与摄像头管理收口

本批实现范围：

1. 复用现有云端 `device_bindings / cameras` 和盒子 `/api/cameras/discover`，不新增平行设备系统。首次引导和“我的”管理页共用同一摄像头表单、请求模型和服务端权限。
2. 家庭创建者可继续添加或解绑盒子，并可添加、编辑、暂停和删除摄像头；普通成员保持只读。服务端对设备认领、盒子绑定、摄像头创建/编辑/删除/重新验证全部执行创建者鉴权。
3. 摄像头添加采用“局域网发现候选 -> 选择安装位置 -> 填写账号 -> 保存并等待盒子同步”，只在发现失败时展开地址、端口和路径；原生页面不显示完整 RTSP 输入，也不再执行会伪造成功的手机侧测试。
4. 摄像头必须绑定当前家庭的有效盒子，编辑请求不能迁移 `family_id / device_id`。公开列表剔除地址、用户名和密码；创建、编辑、删除、解绑成功后同步更新唯一的 `ProfileViewModel` 状态与受家庭隔离的磁盘缓存。
5. 解绑级联删除该盒子的摄像头配置并保留历史安全事件；绑定列表只返回未撤销记录，避免刷新后恢复已解绑盒子。摄像头同步中状态显示“配置中”，不能误报在线或离线。
6. 首次引导完成后在家庭元数据持久化 `onboarding_completed_at`。后续删除最后一路摄像头或解绑盒子只改变设备空状态，不得把成熟家庭重新路由到不可返回的首次配置页；真正未完成第一路摄像头的新家庭继续保持强制引导。

验收顺序：

1. 已完成服务端创建者/成员权限、跨盒迁移拒绝、敏感字段隐藏、无盒创建拒绝和解绑后列表为空的专项回归。
2. 已完成 iOS 模型兼容、请求字段白名单、成员不可调用设备 mutation、创建者状态与缓存一致性，以及创建者/成员管理页专项 UI 回归。
3. 提交前继续执行完整 App Server、iOS 单元/UI、Release 构建和发布包预检；随后在真实 iPhone 与树莓派同一 Wi-Fi 下验收盒子发现、摄像头候选、凭证保存、盒子同步回传、编辑、暂停、删除和解绑后重新认领。
4. 本批验证通过后提交并推送原生分支，不在提交动作中自动部署腾讯云。2026-07-25 已在提交后单独完成设备管理最小服务差异部署和真机覆盖安装；仍须由家庭创建者在真机验收新增、编辑、暂停/恢复、删除、解绑和重新认领，验收前不标记闭环完成。
5. 已补充“完成引导 -> 删除最后一路摄像头 -> 冷启动仍进入主界面”的 JSON/PostgreSQL 回归；现有历史家庭通过保留事件安全补全完成标记，新家庭无历史时仍返回 `camera` 步骤。

后续顺序保持为：原生设备管理真机闭环 -> 隐私画面模式 -> 数据导出与账号删除 -> 付费 Apple Team 下的 APNs 和 TestFlight。视觉算法继续由原主线维护，本批不调整 EACP 或事件阈值。

### 15.13 安全配对与归属展示收口

本批按一个闭环实施，不增加第二套设备系统：

1. 盒子端以独立 `PairingWindow` 管理启动时 15 分钟和管理端重新开放的 10 分钟窗口；绑定成功后立即关闭。局域网发现继续公开最小设备信息，`/api/device` 和重新开窗接口必须经过盒子管理会话。
2. 云端绑定成功和设备配置同步只下发脱敏 `binding_summary`，包含家庭名称、家庭创建者展示名、脱敏账号和绑定时间。盒子使用独立持久状态保存该摘要，不保存完整账号或云端凭证副本。
3. 云端解绑撤销设备 token。盒子配置同步收到 401 后清除本地摘要，管理端恢复未绑定状态并允许重新开窗；家庭转移继续只在 App 创建者权限下完成。
4. 管理端首页增加紧凑归属栏和“开启配对 10 分钟”动作。已绑定时隐藏开窗动作，并显示云端同步状态；App 的过期提示改为前往盒子管理端，不再把重启作为产品主路径。
5. 自动验收覆盖窗口开启/过期/关闭、摘要字段白名单、完整手机号与 token 不落盘、未认证开窗 401、配对摘要下发和解绑后旧 token 401。实机验收覆盖盒子服务重启、局域网发现、管理会话开窗和管理页组件存在。

摄像头候选扫描单独保留局域网只读例外：`GET /api/cameras/discover` 仅对私有源地址开放，摄像头配置 mutation 和管理端其他 API 继续要求认证，避免 App 添加摄像头时被盒子管理会话错误拦截。

摄像头配置完成后的产品状态必须跨页面即时一致：个人页设备操作发布配置变更 revision，首页/守护页基于现有缓存静默刷新，并在盒子同步窗口内做有限对账；禁止依赖杀掉 App、重新登录或页面级常驻轮询。绑定摘要只能以真实认领时间参与配置版本，普通设备心跳不得触发配置版本变化。

同一局域网内的配置操作采用“云端先保存、App 只唤醒、盒子主动拉取”的低延迟路径：唤醒接口不得携带 RTSP 凭证或配置参数，盒子端必须合并高频唤醒；不在局域网时由原有轮询保证最终一致性。

量产后续门槛：增加盒身实体配对键和每机唯一初始管理凭证，实体键开放 10 分钟窗口；在此之前当前 Raspberry Pi 方案只作为受控网络原型验收，不宣称达到量产防抢绑标准。

### 15.14 家庭实时画面隐私模式

本批冻结以下产品与技术边界：

1. 实时观看只提供 `原画 / 人像模糊 / 骨架隐私` 三种家庭级模式。模式不是单个页面的临时滤镜，唯一状态保存在云端家庭关怀配置中；App、盒子管理端、播放票据和盒子上传流必须读取同一状态。
2. 只有家庭创建者可以修改；普通成员可查看当前模式但不能操作。App 与管理端在实时画面可见时每 1 秒静默对齐；盒子同时保留实时帧上传回执通知和每 1 秒一次的轻量隐私策略读取，完整摄像头配置仍按 10 秒同步，不用高频重型配置拉取换取低延迟。
3. 隐私渲染只位于实时视频输出层。EACP、人物/姿态/跌倒/火灾检测、事件状态机和正式证据链继续读取原始帧；不得为了隐私预览降低安全算法输入质量，也不得把模糊图替代正式安全证据。
4. 人像模糊与骨架隐私合并连续感知锚点中的 YOLO 人框和姿态跟踪框，只替换可信人体区域并保留原始环境。有人框但无可信关键点时只模糊人物；有可信姿态时遮蔽人物后绘制骨架；当前无人或没有可信人体区域时保留正常环境画面，不允许整帧压暗。渲染异常时非原画流仍丢弃该帧，不以原始 JPEG 作为异常兜底。
5. 盒子只上传当前家庭模式的一路实时帧，不同时编码和上传三套视频。云端按摄像头与模式隔离缓存，隐私流不回退旧原画；播放票据绑定摄像头和家庭模式，URL 参数不能降低家庭当前隐私等级。
6. App 模式切换保留上一帧，待新模式首帧到达后替换，不能显示黑屏或整页读取态。离开守护页或进入后台后停止视频和模式同步任务，恢复时只启动一条流和一条同步任务。

完成门槛：

1. 自动化必须覆盖创建者修改、成员拒绝、播放票据约束、设备配置同步、实时上传回执和管理端/App 状态一致性。
2. 树莓派视觉虚拟环境运行三模式像素级脚本；真实双摄分别验证原画、人像模糊和骨架，不出现原画泄露、黑屏、闪烁或三倍上传负载。
3. 实机双向验收：管理端修改后 App 2 秒内显示同一模式，App 修改后管理端 2 秒内显示同一模式；策略状态与新模式首帧分别计时，切换期间保留旧帧且不得回退错误模式；持续观察视频 FPS、CPU、温度和断流恢复。
4. 上述实机验收通过后才部署腾讯云和真机版本并标记 P5 隐私画面完成。人脸身份识别仍为后续独立评估项，不与本批混入。

2026-07-27 人物区域修正已完成：盒子管理端四个页面由共享脚本生成唯一一套 `原画 / 模糊 / 骨架` 控件，并每秒对齐家庭状态；像素级回归固定检查框外背景保持、人物区域变化、骨架模式不全局变暗、无人画面保持正常，以及仅有人框无关键点时仍遮蔽人物。该模式是检测驱动的观看隐私，漏检风险必须如实披露，不能包装成绝对匿名化。

### 15.15 原生个人数据导出与账号注销收口

本批已完成：

1. 服务端新增账户导出、注销影响计划和确认注销接口；JSON 与 PostgreSQL 仓储使用同一产品契约，导出按用户可访问家庭隔离并剔除密码、摄像头凭证、绑定码、token、会话和 COS 存储秘密。
2. 注销计划由服务端计算家庭角色、有效成员数、需删除家庭、需退出成员关系和本人记忆数量。创建者仍有其他成员时返回 `ownership_transfer_required`，客户端只展示阻断原因，不能绕过。
3. PostgreSQL 注销在一个事务内锁定用户、成员关系和家庭后执行；普通成员数据与唯一创建者家庭数据采用不同删除范围。共享媒体在仍被保留记忆引用时不清理，唯一家庭删除后设备 `family_id` 释放，旧 bearer token 立即失效。
4. 原生“隐私与数据”支持生成 JSON、系统分享、删除影响摘要和破坏性二次确认。删除成功后清理 Keychain、全部磁盘缓存、会话上下文和推送状态并回到登录页；导出临时文件在分享关闭或重新导出前删除。
5. 自动验证已覆盖导出秘密排除、创建者阻断、普通成员注销、独立创建者注销、共享媒体保留、PostgreSQL 事务、COS 清理调用、token 即时失效、iOS ViewModel 和原生删除确认 UI。

提交与部署结果：

1. 已完成 `62` 项原生服务端回归（`61` 通过、`1` 项因未配置 PostgreSQL 集成地址跳过）、`97` 项 iOS 单元测试（`96` 通过、`1` 项模拟器 Keychain 跳过）、`16/16` UI 测试、Release 真机架构构建和全仓发布预检。
2. 已以提交 `e216017` 推送 `feature/native-ios-app`。腾讯云通过 `b63c329..e216017` 三方合并生产定制，只部署五个服务端文件；没有修改盒子视觉、EACP、跌倒、火灾、隐私流或生产数据库结构。
3. 已在 PostgreSQL 事务中创建一次性临时创建者、成员、家庭和随机哈希会话，重启加载后完成未认证 401、导出秘密排除、创建者阻断、普通成员注销、独立创建者注销和旧 token 401。两个临时账号与家庭均由正式注销接口删除，内部清理复查全 0；现有真实账号和家庭未参与。
4. 家庭创建者转移 API 与原生入口是多人家庭注销的下一项依赖。本批只提供正确阻断，不把“请先转交”描述成已经可完成的闭环。

云端部署后 `gohome-app.service=active`，内外网 `/health` 均为 PostgreSQL，业务计数保持 `events=256 / assets=496 / pending_media_uploads=0`，近 15 分钟无 warning。后续顺序更新为：真机覆盖安装验证系统分享和注销回登录 -> 家庭创建者转移闭环 -> 付费 Apple Team 下的 APNs、Archive 和 TestFlight。视觉算法继续由原主线维护。
## 15.16 登录安全与家庭角色闭环（2026-07-27）

- [x] 删除 PostgreSQL 水合后“无密码凭证 + 任意非空密码”降级分支；新增独立 `scrypt` 凭证模块和缺失/畸形哈希回归。
- [x] 新邮箱注册只保存带盐哈希；旧 JSON 明文凭证仅在正确登录后升级，手机号 OTP 注册登录路径保持不变。
- [x] 新增家庭成员列表、移除成员、退出家庭和创建者转让的统一 v2 API，JSON 与 PostgreSQL 使用同一权限语义。
- [x] PostgreSQL 创建者转让在事务内锁定家庭和全部有效成员，保证唯一创建者；转让结果同步组合服务内存快照，避免旧角色被后台保存覆盖。
- [x] 原生家庭页先显示当前账号再静默刷新；创建者使用成员菜单转让/移除，普通成员使用底部退出动作，全部带系统破坏性确认。
- [x] 转让或退出成功后重新读取 bootstrap 并重建家庭上下文，角色、设备管理、规则管理、活动清理和注销阻断同步生效。
- [x] 服务端单元、HTTP 双账号闭环、iOS 权限动作和模拟器构建通过。
- [x] 通过生产差异三方合并部署腾讯云；公网临时家庭完成越权阻断、注销阻断、唯一 owner 转让、旧创建者退出、账号注销、token 撤销和零残留验收，缺失密码哈希账号在服务重启后明确返回 401。
- [x] 将既有兼容邀请码替换为创建者主动生成、默认 10 分钟、一次性、可撤销且只保存 SHA-256 哈希的邀请；移除 bootstrap 永久邀请码和历史确定性邀请码消费路径。
- [ ] 真机在家时补做家庭页菜单、系统确认框、转让后角色刷新和旧创建者退出的人工交互验收；禁止使用现有真实家庭执行账号注销。

## 15.17 安全家庭邀请与发布签名收口（2026-07-27）

本批执行顺序：

1. [x] 新增 `family_invitations` 独立数据表与 JSON/PostgreSQL 同构仓储；邀请码明文只返回一次，持久层只保存哈希、末四位、状态、创建者、使用者和有效期。
2. [x] 新增创建、列表、撤销和消费四个 v2 API；创建者权限由服务端校验，消费使用 PostgreSQL 事务和行锁保证并发只有一次成功。
3. [x] 原生家庭页只对创建者展示“邀请家人”，支持生成、系统分享、重新生成和撤销；普通成员不显示入口。App 内只临时保留本次生成的明文，重新进入后仅展示末四位并要求重新生成。
4. [x] 首次家庭引导改用安全邀请消费接口；bootstrap 和家庭创建响应不再返回永久 `join_code`，旧 `/api/families/join` 仅委托新安全消费逻辑。
5. [x] 自动化覆盖错误、过期、撤销、已用、历史格式、创建者权限、已有成员不消耗邀请码、JSON 并发消费、PostgreSQL 约束和 iOS 创建者/成员界面边界。
6. [x] 腾讯云已执行 `011_family_invitations.sql` 并按生产共同基线三方合并部署；公网 PostgreSQL 已完成创建者权限、并发唯一消费、撤销、旧码拒绝和零残留清理，真实业务计数保持 `events=261 / assets=501 / pending_media_uploads=0`。
7. [x] Apple 正式团队 `yihua tan / X4M4T6Z4CJ` 已生效；App Store Connect App 记录、Push Notifications capability、Sandbox + Production APNs Auth Key、腾讯云 Provider、生产 entitlement 和签名 IPA 均已配置并校验。Archive 已上传，TestFlight 构建 `1.0.0 (1)` 为准备提交，内测组与当前测试员已启用。

本批继续不修改 Raspberry Pi、EACP、姿态、跌倒、火灾、多模态复核、隐私流和盒子配置。

## 15.18 APNs 与 TestFlight 交付收口（2026-07-27）

1. [x] 创建 App Store Connect App「想家了吗」，固定 Bundle ID `com.gohome.family` 和 Apple App ID `6795126675`。
2. [x] 为 App ID 启用 Push Notifications，创建支持 Sandbox 和 Production 的 APNs Auth Key；私钥不进入仓库。
3. [x] 腾讯云安装受限私钥、随机 Token 加密密钥和 APNs 环境变量，应用迁移 `010_apns_delivery.sql`，校验 Provider 为 configured。
4. [x] iOS 开启 `GoHomePushEnabled`，Debug 使用 sandbox token，Release/TestFlight 使用 production token；保留类型化消息/事件深链路由。
5. [x] 通过 APNs 加密、JWT、sandbox/production、重试、失效 token、事件路由专项，iOS `100/100` 单元测试和发布元数据检查。
6. [x] 生成 App Store IPA 并校验 `aps-environment=production / get-task-allow=false / GoHomePushEnabled=true`；上传成功，TestFlight 已显示 `1.0.0 (1)` 为准备提交，出口合规已完成。
7. [ ] 内部组「比赛内测」已启用自动分发，当前开发者账号已加入。在目标 iPhone 从 TestFlight 安装 `1.0.0 (1)` 后，完成通知授权、production token 登记、站内消息 + 系统通知双通道、前台提示、点击事件/消息深链和退出撤销验收。
8. [ ] 比赛交付前补齐 TestFlight 测试说明、内部测试人员与必要合规问题；App Store 审核图、描述和审核账号不与首包内测试混做。

## 15.19 活动区间、规律候选与关怀闭环（2026-07-28）

1. [x] 盒子以人物出现、姿态变化、10 分钟心跳和人物离开生成结构化活动区间；普通区间不带图片、不写 COS，断网进入 SQLite outbox，恢复后按来源区间 ID 幂等补传。
2. [x] 观察覆盖率改为 worker 内存滚动窗口，不再依赖高频 JPEG 或 `snapshots` 数量；历史最后见人时间从结构化 presence session 合并，摄像头离线、禁用和重启时活动区间截止到最后可信观察。
3. [x] 云端七日概览增加数据质量、活动减少、夜间活动和首次活动时间偏移候选；规律比较至少需要 3 个历史活动日，今日无活动不直接触发活动减少，夜间活动在 05:00 窗口结束后评估，当天总活动量减少只在上海时间 20:00 后判断。
4. [x] 候选进入现有 scheduler / App 消息 / APNs / 关怀编辑和系统分享链路，同一家庭同一天最多生成一条，重复调度不重复推送；用户关闭“活动变化提醒”后停止生成。
5. [x] 原生守护轨迹页展示真实趋势、基线建立状态、候选事实和联系话题；缓存优先与后台静默刷新不变，未新增整页读取态。
6. [x] 通过盒子 outbox、HTTP 401 退避保留、观察覆盖率、云端活动报告、早晚确定时钟、消息幂等、原生 `100/100` 单元测试和 `17/17` UI 自动化。
7. [ ] 腾讯云部署本批服务端差异；恢复盒子设备绑定令牌后完成真实活动区间上传、断网补传、云端报告、APNs 和真机消息动作验收。
8. [ ] 每日定时摘要、正式周报和多模态活动复核继续保持隐藏；时序风险模型等待真实困难样本和标签规范满足后再启动训练。

## 15.20 主线统一与 TestFlight Build 5（2026-07-31）

1. [x] 将原生 SwiftUI App、云端契约和最新 Hailo/EACP 边缘管线统一合入 `main`；删除旧 WebView iOS 运行入口，只保留 `ios-shell/GoHomeShell.xcodeproj` 一个发布工程。
2. [x] 发布身份统一为显示名 `GoHome`、Bundle ID `com.gohome.family`、版本 `1.0.0 (5)`、团队 `X4M4T6Z4CJ`；Release 保留生产 APNs 和隐私清单。
3. [x] 清理临时工作树和 7.7 GB 历史构建缓存；保留 Hailo 文档、研究资料、比赛素材和证据图片，不将其误删或混入发布包。
4. [x] 自动化通过：云端 90 项中 89 项通过、1 项因本机未配置 PostgreSQL 集成 URL 跳过；边缘端 45/45；iOS 单元 123/123；iOS UI 22/22；发布元数据校验通过。
5. [x] App Store Connect 已接受 Build 5 上传，Delivery UUID 为 `8eb7df01-0089-4f57-a319-850a907a5499`；Apple 已处理完成并将其提供给“比赛内测”内部测试组。
6. [ ] 从 TestFlight 安装 Build 5；实机验收登录、盒子与摄像头同步、实时画面、三种隐私模式、定位、事件去重和自动业务推送后，才关闭本阶段。

## 15.21 Build 5 首轮真机验收与骨架帧率修复（2026-07-31）

1. [x] Build 5 已从 TestFlight 安装并冷启动到已恢复的家庭首页；首页、守护、记忆、社区、我的五个原生页面可正常浏览，实时摄像头画面可打开。
2. [x] 定位骨架模式不显示 FPS 的根因：App 将整个速率标签错误绑定到“包含人物的安全姿态包”，无人或暂时丢失人物时会清零并隐藏，不代表 Hailo 停止工作。
3. [x] 主线改为所有隐私模式只显示手机实际解码 FPS；骨架不再追加 Pose Hz，也不再由 App 消费独立姿态流。
4. [ ] 下一 TestFlight 构建实机确认骨架单路 MJPEG、真实 FPS、长时间停留、切页返回、蜂窝网络、家庭与手机双位置、自动业务推送、跌倒事件和单次通知。

## 15.22 历史家庭固定位置恢复闭环（2026-07-31）

1. [x] 明确位置边界：盒子不自行伪造 GPS；家庭创建者在家时用手机确认一次固定家庭位置，首页只用手机当前位置计算回家距离，社区只使用家庭固定位置。
2. [x] 首页“回家距离”和社区页右上角共用同一原生设置页，不增加第二套位置数据；历史家庭无需解绑盒子、重建摄像头或重新注册。
3. [x] 保存位置前读取现有照护资料，只更新城市、区域、家庭坐标和位置标签，保留长者姓名、关系及联系电话；成功后同步刷新首页和个人资料状态。
4. [x] 只有家庭创建者可修改固定位置，普通成员只看到缺失提示；社区在位置缺失时禁用非紧急附近服务，不回退到手机当前位置。
5. [x] 云端家庭位置契约专项测试、资料字段保留单元测试、创建者/成员权限 UI 测试通过；完整 iOS 回归 `152/152` 与发布预检通过。
6. [ ] 下一 TestFlight 构建在真机保存家庭位置，验收首页距离、社区位置、杀进程重启后的持久化、普通成员只读和拒绝定位后的可恢复提示。

发布记录：`GoHome 1.0.0 (6)` 已从主线唯一原生工程归档并上传，Delivery UUID 为 `7a905a03-83ba-4e02-bd95-4a8457e6f8d4`。Apple 已处理完成并自动加入“比赛内测”组；下一步只按 TestFlight 真机验收，不使用 Xcode 直装代替交付验收。

## 15.23 Build 6 家庭位置缺陷与 Build 7 修复（2026-07-31）

1. [x] 真机发现 Build 6 会接受 Core Location 返回的历史缓存样本，导致家庭位置被设为用户此前在外地的位置；该构建的位置验收判定为失败，不能作为交付基线。
2. [x] 将定位样本新鲜度与精度抽成唯一共享策略：只接受本次请求开始后、15 秒内且水平误差不超过 200 米的坐标；家庭位置和首页手机距离均使用该策略。
3. [x] 一次性定位改为 12 秒有界连续定位，忽略临时 `locationUnknown`；地址名称解析失败仍允许保存可信坐标，并使用中性“家庭位置”标签，不沿用旧地点名称。
4. [x] 家庭创建者可从首页和社区明确进入“更改家庭位置”，不解绑盒子、不删除摄像头；普通成员继续只读。
5. [x] 绑定后首次确认与后续纠错复用同一资料更新构造器，只更新位置字段并保留照护资料；连续请求的回调按请求 ID 隔离。
6. [x] Build 7 完整自动化、发布预检、归档并上传；`GoHome 1.0.0 (7)` Delivery UUID 为 `7555c324-63d1-4657-8d44-d7c3e86a7d21`，Apple 当前状态为 `PROCESSING`。
7. [ ] Apple 处理完成后从 TestFlight 安装 Build 7，在家重新确认家庭位置，验收首页距离、社区位置、重启持久化和成员只读。

## 15.24 骨架隐私实时链路收口（2026-07-31）

1. [x] 定位 `1 FPS` 根因为骨架安全背景固定 1 秒限速和单连接同步上传，确认 Hailo Pose 约 14-18ms 且零推理失败，不错误归因于 26 TOPS 算力。
2. [x] 骨架安全背景改为只替换人物区域，人物外环境保留当前画面；不绘制第二套服务端骨架，不以原画作为异常兜底。
3. [x] 复用有界上传槽并按流批次和帧序号排序；忙时丢弃过期输入，云端拒绝晚到旧帧，不能形成持续增长的延迟队列。
4. [x] 云端骨架 MJPEG 使用播放档位频率，并在 `/health.stream_metrics.scene_cameras` 独立报告有效 FPS、帧间隔、传输延迟和乱序拒绝。
5. [x] 双摄实测边缘安全背景约 11-14 FPS、云端完整窗口约 10-14 FPS，有人姿态包约 10.8 Hz，温度约 70.5-74.3 摄氏度，Hailo 失败和摄像头重连均为 0。
6. [ ] 在 TestFlight Build 7 守护页完成 10-20 分钟真人移动、前后台、切页返回和隐私像素验收；App 解码 FPS 和 POSE Hz 达标后再关闭该项。

## 15.25 双摄隐私隔离与宠物稳定（2026-07-31）

1. [x] 根据真机截图确认客厅人物区域嵌入冰箱摄像头画面，按高优先级隐私隔离故障处理。
2. [x] 删除历史安全背景和所有跨帧像素缓存；骨架人物区只使用当前摄像头当前帧的局部 inpaint，状态明确报告 `retained_pixel_state=false`。
3. [x] 摄像头 ID、基于实际流配置生成的 `source_key` 和帧 ID 从采集贯穿到 KLT 锚点、同步包、隐私渲染和云端上传；任一不一致时拒绝该帧并输出中性安全画面。
4. [x] 新增“底图 A、仅人体区域注入摄像头 B 像素”的精确回归；同时在 Hailo Pose 解码层增加包含框去重，阻止同一人叠加全身与上半身两套骨架。
5. [x] 宠物稳定器升级为衰减分数与权重同步的置信度计算；候选至少两次命中、最终平均置信度不低于 0.40 才输出猫狗类别，连续 0.31 的错误狗类别不得被时序累计放大。
6. [x] 树莓派已部署 `privacy-frame-renderer-v9 / privacy-background-reconstructor-v3 / pet-temporal-stabilizer-v2`；当前像素状态为 0，局部工作区最长边 192，稳定后实机有人路 inpaint P50/P95 约 7.6/11.8ms，Hailo Pose 中位/P95 约 14/23ms且零失败。
7. [ ] 真机刷新后确认两路骨架模式不再串画面、无包含骨架重叠和旧帧残影；让家庭猫在近、中、远距离和部分遮挡下通过两路摄像头，保留原始候选分数后再决定是否训练宠物专项分类器。

## 15.26 空场景人物证据收口（2026-07-31）

1. [x] 删除 Pose 框转人物框再验证 Pose 的循环证据；Object 人框、Pose 检测分数、关键点和场景区域保留独立来源。
2. [x] 场景建图不再被未验证 Pose 排除；电视、家具和画面边缘候选在进入人物、活动和跌倒状态前统一过滤。
3. [x] 新增摄像头隔离的 `HumanEvidenceGate`，以候选区域局部运动/位移激活人物轨迹，连续检测期间保持已确认静止目标，超时自动过期；其它区域运动不能替静态候选激活。
4. [x] 修复姿态为空时 Object 孤立人框仍保留的问题；被拒候选不能进入连续骨架、人物计数、进食、活动、跌倒、事件或通知。
5. [x] 树莓派完整视觉回归通过；双摄服务重启后的空场景均为 `empty / pose_count=0`，Hailo Pose/Object 零失败，临时测试文件已清理。
6. [ ] 现场依次完成真人进入、行走、停止 30 秒、坐下、沙发躺卧、离开和快速跌倒；记录首次建立时间、静止保持、清空时间、误报、漏报和通知结果后再冻结门控参数。
7. [ ] 宠物猫狗准确率仍按 15.25 单独验收，不能用本次人体门控结果宣称宠物识别完成。

## 15.27 骨架隐私 v4 与连续追踪验收（2026-08-01）

1. [x] 删除 Telea 人物区拉伸修复，改为同摄像头、同源配置、同流代际、同分辨率的三帧确认干净背景；换源、场景不一致和身份不一致立即失效。
2. [x] 连续骨架改为姿态轮廓内 Shi-Tomasi 特征、前后向 LK 校验和 RANSAC 局部仿射传播，不再直接跟踪低纹理关节点。
3. [x] 增加 `untracked` 人物状态；骨架不足仍执行隐私替换，不作为无人背景，不进入正式跌倒、恢复或通知证据。
4. [x] 管理端明确显示唯一同步内容 FPS、源流 FPS 与 Hailo 模型锚点 Hz；同一缓存帧重复读取不计数，部署版本统一为 `eacp-continual-pose-v2 / privacy-frame-renderer-v12 / privacy-background-reconstructor-v4`。
5. [x] 自动回归、Hailo 运行检查和双摄空场实机观察通过；当前源流约 15/12 FPS，Hailo Pose 中位约 14-15ms且零失败，无断流和重连。
6. [x] 为 Uvicorn 长时 MJPEG 连接设置 6 秒有界关闭，后台服务按 7 秒共享截止时间并行停止，视频 HTTP 先关闭再等待线程；保持真实骨架流重启约 9 秒，已验证正常退出、无 systemd timeout 和 SIGKILL。
7. [ ] 在新进程上依次完成电视柜与冰箱两路真人行走 20 秒，核对人物阶段输出接近各自源流、骨架连续、无画面扭曲、无旧矩形和无跨摄像头像素。
8. [ ] 继续完成静止 30 秒、坐下、沙发躺卧、快速下降、离开和 TestFlight 前后台/切页 10-20 分钟验收；同时核对正式事件、云端复核和通知只产生一次。

## 15.28 单一骨架合成与真实新帧调度（2026-08-01）

1. [x] 管理端骨架模式改为安全背景 MJPEG + 独立 Pose 元数据，浏览器为唯一骨架绘制方；原画由服务端同帧标注，模糊模式不允许叠加骨架。
2. [x] 管理端与 iOS 统一青色骨架、黑色底线和白色关节点；删除黄蓝两套视觉语义，缓存资源版本在四个主管理页面统一更新。
3. [x] 元数据刷新由 500ms 调整为 80ms，并增加 401 登录跳转和异常退避，避免服务重启后无效高频请求。
4. [x] 摄像头缓存新增新帧条件通知，连续跟踪改为真实新帧驱动和唯一 `frame_id` 去重；KLT 最小间隔改为 50ms，消除双摄固定轮询相位错帧。
5. [x] 空场当前帧进入同步显示通道但保持 `empty / no_anchor`；显示 FPS 只统计唯一帧，状态原因不再残留。
6. [x] 树莓派回归与运行检查通过：双路源约 15.1 FPS、真人活动路连续姿态约 14.9 FPS、Hailo Pose 中位约 14.3ms/P95 约 24.3ms、失败和摄像头重连均为 0。
7. [ ] 重新登录管理端后完成两路真人行走和离开验收：只能看到一套青色骨架，人物离开后 1.2 秒内清空，无旧黄色像素、无矩形残留、无跨摄像头画面。
8. [ ] 验收模糊模式只模糊人物且绝不绘制骨架；TestFlight 守护页继续完成 10-20 分钟前后台、切页、蜂窝网络和云端安全场景 9-15 FPS 稳定性测试。
9. [ ] 若云端安全场景长期低于 12 FPS，下一阶段将 JPEG 帧上传替换为持久 H.264/H.265/WebRTC 传输；不得用增加请求计数、重复帧或插值刷新率冒充真实视频 FPS。

## 15.29 源帧单调性与隐私合成去重（2026-08-01）

1. [x] 摄像头真实解码帧增加 `captured_monotonic`，连续姿态、隐私输出 FPS 和帧龄统一使用源帧时间，不使用处理完成时间。
2. [x] 连续姿态增加展示单调性：旧帧、重复帧和乱序空模型结果不得覆盖当前展示；晚到可信人物结果仅作为下一新帧的跟踪锚点。
3. [x] worker 校验当前活动流代次，摄像头重连后拒绝旧 `stream_generation` 的推理结果，保持摄像头、流源和帧身份全链一致。
4. [x] 安全场景按摄像头、源代次、真实帧、尺寸和质量有界缓存；同一帧被多个消费者读取时只做一次背景重建和 JPEG 编码。
5. [x] 树莓派回归通过；稳定窗口 camera 31 源/显示/隐私约 `15.07/14.77/13.96 FPS`，camera 32 约 `15.10/15.10/14.65 FPS`，显示不再高于源流，Hailo 与中继错误为空。
6. [x] 盒子运行进程统一由 `gohome-edge-agent.service` 管理，确认单一 MainPID、`NRestarts=0`，不保留手工 Uvicorn 副本。
7. [ ] 两路真人动作验收晚到锚点召回、单骨架、离场清空和无残影；同时观察 10-20 分钟帧龄、CPU、温度、云端有效 FPS 和 TestFlight 切页返回。
8. [ ] 家庭猫在近、中、远距离及遮挡条件下采集原始猫/狗候选与最终时序类别；未达到真实样本准确率门槛前，不宣称通用 COCO 模型完成宠物专项识别。

## 15.30 管理端视频流生命周期恢复（2026-08-01）

1. [x] 确认盒子重启后旧 MJPEG 连接可能不触发 `img.onerror`，导致姿态接口已恢复但视频仍停在黑场或旧帧。
2. [x] 由连续姿态元数据统一监督当前视频流；摄像头源代际变化、帧序号回退和持续无有效图像均触发有冷却的单流重连。
3. [x] 回归锁定恢复逻辑不刷新整页、不重启服务、不复制视频元素，也不改变单一骨架合成责任方。
4. [x] 重启后盒子单一 systemd 进程、Hailo、双摄、隐私渲染和云端中继运行正常，六项树莓派核心回归通过，临时验证副本已清理。
5. [x] 保持管理页面打开执行 systemd 服务重启，页面未刷新，视频请求自动换新并在 12 秒观察点恢复为 `640x360 / 骨架 14.6 FPS / 源流 15.0 FPS / 帧龄 50ms`。
6. [ ] 分别在两路摄像头完成人物行走、离开和 10-20 分钟页面停留，确认单青色骨架、无残影、无跨路像素和无递增延迟。

## 15.31 骨架残影与真实帧抖动收口（2026-08-01）

1. [x] 禁止干净背景在已建立后被连续“无人”结果反复替换；同摄像头、同源代际连续 8 帧稳定无人后只确认一次背景。
2. [x] 对短时人物漏检保留 1.4 秒最近遮罩，禁止单帧漏检直接泄露原画或污染背景。
3. [x] 只在人物扩展 ROI 内做当前帧与干净背景差分，将真实人物前景并入漂移遮罩；删除高成本全帧形态学路径。
4. [x] 连续跟踪最小间隔调整为 20ms，适配平均 15 FPS、帧间隔不均匀的真实 HEVC 输入，同时继续按源时间和唯一帧 ID 去重。
5. [x] 树莓派六项回归、Python 编译和差异检查通过；局部合成约 7.1ms，单一 systemd 进程、Hailo 失败 0、摄像头重连 0、服务 warning 为空。
6. [x] 直接使用正式 RTSP 凭证探测双路子流：HEVC 640x360，`r_frame_rate=20/1`、`avg_frame_rate=15/1`，8 秒内容各 121 帧。产品指标按真实平均输入与唯一输出报告，不承诺不存在的 30 FPS。
7. [ ] 两路分别行走 15-20 秒后离开画面，确认无人物原像素残留、遮罩不滞后、离场 1.2-1.4 秒清空、输出稳定接近源流且帧龄不持续增长。
8. [ ] 单独复核电视柜路持续 3 个人物候选的来源；若空场仍存在，修正人物证据/电视内容抑制并补固定场景回归，不能把误检帧写入背景。
9. [ ] TestFlight 长时仍低于 12 FPS 或明显卡顿时，启动持久 H.264/H.265/WebRTC 传输改造；MJPEG 保留为降级方案，不通过重复帧、插帧或提高请求频率伪造流畅度。

## 15.32 当前帧隐私与时序分割加速（2026-08-01）

1. [x] 隐私渲染从姿态线程缓存帧改为直播线程当前采集帧，完整传递摄像头、来源代次、帧号和源单调时间；旧姿态只作有界元数据，不再替换当前像素。
2. [x] YOLOv11s 人体分割改为逐摄像头低频 Hailo 锚点和当前帧光流传播；来源、分辨率、场景、时间、人物证据不满足或空遮罩遇到新前景时强制重新锚定，不直接复用旧遮罩。
3. [x] 背景像素学习的保守膨胀仅在真实学习周期执行，保持人物覆盖边界；正式隐私回归合成约 11.46ms。
4. [x] 八项盒子回归通过，新增同帧去重、跨帧传播和来源切换测试；双路源约 15 FPS，骨架隐私输出约 14.2/13.9 FPS，推理与摄像头失败均为 0。
5. [x] 六槽与动态上传窗口对照因乱序使有效 FPS 下降，删除无收益调度代码并恢复固定四槽有界上传，保留忙时丢弃和云端旧序号拒绝。
6. [ ] 运行 10-20 分钟双路真人窗口，记录源流、隐私输出、分割锚点、光流、云端有效 FPS、帧龄、CPU、温度、重连、残影和遮罩清空时间。
7. [ ] TestFlight 完成真人移动、前后台、切页返回、蜂窝网络和通知幂等验收；逐帧 JPEG 在动态窗口后仍长期低于 12 FPS 时进入持久 H.264/H.265/WebRTC 改造。

## 15.33 纯骨架隐私架构重做（2026-08-01，重新开启）

Build 8 的“人物强模糊 + 骨架”方向违反正式产品定义，相关完成标记全部作废。Build 8 只保留历史构建记录，不进入最终交付验收。

1. [x] 固化三种隐私模式的唯一产品契约，并建立 `issue.md` 交付问题台账。
2. [ ] 删除骨架渲染对人物模糊输出的调用；建立保留当前场景、完全移除人物、只绘制一套骨架的独立合成器。
3. [ ] 建立按摄像头、来源、流代次和分辨率隔离的显式空房校准；近期人物区域禁止学习，场景变化立即失效。
4. [ ] 将视频、Pose、分割掩码和背景校准绑定到同一个完成帧身份；禁止晚到结果、旧代次结果和跨摄像头状态进入成品帧。
5. [ ] 盒子成为成品帧唯一合成方；生产云端删除 Pose SSE、safe-scene 和客户端合成的正式路径，管理端与 iOS 只解码显示。
6. [ ] 每路视频改为一个在途上传和一个可覆盖的最新待发送帧，消除并发乱序和持续积压。
7. [ ] 每种 HEF 只保留一个共享 runtime，使用跨摄像头有界最新帧调度；评估 GStreamer 解码和持久 H.264/H.265/WebRTC 链路。
8. [ ] 完成自动回归、双摄真人动作、30 分钟长时、断线恢复、通知幂等和存储生命周期验收。
9. [ ] 只从正式 `ios-shell` 工程生成下一 TestFlight 构建；显示名保持 `GoHome`，Bundle ID 保持 `com.gohome.family`。

## 15.34 纯骨架隐私单帧架构本地收口（2026-08-02）

本节取代 15.27 至 15.33 中关于浏览器/iOS 二次绘制、`safe-scene`、Pose SSE、四路并发上传以及“人物模糊 + 骨架”的方案结论。历史章节仅用于说明故障演进，不再代表当前架构或交付标准。

1. [x] 纯骨架模式改为显式空房校准：按 `camera_id + source_key + stream_generation + resolution` 隔离持久状态；校准和流代次复验未完成时返回明确状态，不输出模糊、黑场、中性色块或当前人物帧。
2. [x] 盒子成为唯一画面合成方。`original`、`person_blur`、`skeleton` 均由盒子生成完整 JPEG；云端、管理端和 iOS 不再接收独立 Pose 或场景底图，也不绘制第二套骨架。
3. [x] 唯一正式协议收敛为 `edge-composed-mjpeg-v1`，会话与实际 MJPEG 响应同时声明 `composition-owner=edge`；iOS 在接收首帧前校验协议版本和合成所有者。
4. [x] 视频、Pose、分割、背景和成品帧统一校验摄像头、来源、流代次及精确 `frame_id`；相邻帧、旧代次和跨摄像头结果不得进入成品帧。
5. [x] 每路云端上传调度收敛为一个在途请求和一个可覆盖的最新待发送帧；不再维护四槽并发、过期积压或 `safe-scene` 第二上传通道。
6. [x] 同一人体分割 HEF 只创建一个共享 Hailo runtime，双摄设备推理串行占有，各摄像头时序遮罩状态独立；单路重置不销毁共享 runtime。
7. [x] 本地回归通过：相邻 Pose 拒绝、流代次复验、最大上传并发 1、最终新帧送达、校准等待不重启采集、双摄分割 runtime 数量 1；云端移除协议返回 404；iOS 协议测试 12 项 0 失败并完成 Simulator 编译。
8. [ ] 清理旧上传 worker、场景上传指标、部署变量和管理端消费者，建立解码、分割、合成、JPEG、上传、云中继、iOS 解码各阶段真实性能指标。
9. [ ] 部署树莓派与生产云端，从正式 `ios-shell` 生成下一 TestFlight；完成双摄 30 分钟、三隐私模式、断线恢复、前后台、跌倒单次通知和存储生命周期验收后，才能关闭 `issue.md` 中 GH-002 至 GH-020。

## 15.35 直播性能口径与帧所有权收口（2026-08-02）

1. [x] 删除盒子共享读取器中的第二份 BGR 帧；唯一中央最新帧缓存保存源帧，读取器只发布新序号，订阅者不再先复制后丢弃。
2. [x] 共享读取器不再保留第二份 BGR 帧；GH-029 进一步删除订阅者旧画面保持，近黑帧不得进入中央缓存或实时输出。共享采集、持续拉流、近黑重连和双订阅回归通过。
3. [x] 复核正式云中继：每张输出帧只执行一次 RTSP 解码、按需一次缩放、一次隐私合成和一次 JPEG 编码；云端与 iOS 不重复合成或重编码。
4. [x] 将云端滚动直播指标提取为独立 `RollingStreamMetrics`，FPS 按真实接收帧间隔计算；新增样本数、帧间隔、传输延迟、最后帧龄和陈旧拒绝指标。
5. [x] 新增确定性云端指标测试，并重跑隐私协议、MJPEG 背压、盒子上传、共享采集、黑帧恢复、显式校准和共享 Hailo runtime 回归；云端 `93/94` 通过（PostgreSQL 环境项跳过），正式 iOS 单元测试 `127/127`、UI 测试 `25/25` 通过。
6. [ ] 部署到树莓派和生产云端，连续记录两路源解码、Pose 等待、分割、背景替换、骨架绘制、JPEG、上传、云端接收和 TestFlight 解码 P50/P95/最大值。
7. [ ] 根据实测瓶颈完成持久 H.264/H.265/WebRTC 正式链路；逐帧 MJPEG 只保留明确降级用途，不通过重复帧或 UI 刷新伪造 FPS。

## 15.36 边缘视频服务所有权收口（2026-08-02）

1. [x] 完整核对盒子启动、systemd、部署脚本、管理端、生产云端和正式 iOS 调用关系；确认正式 iOS 的 `/api/app/*`、`/api/v1/video/*` 归生产云端，云端通过 `/api/v1/device/cameras/*` 读取盒子成品帧。
2. [x] 删除未被部署或客户端使用的边缘 `video_app.py`、`video_service.py`、`video_distribution_service.py`、`video_profiles.py`，以及边缘 `/api/app/*`、`/api/v1/video/*` 路由，消除可直接输出原始 MJPEG 的隐私旁路。
3. [x] 保留盒子管理端 `/api/cameras/*` 和设备令牌 `/api/v1/device/cameras/*`；两者共用 `camera_mjpeg_stream -> PrivacyMjpegStream`，不建立第二个解码、合成或编码服务。
4. [x] 将事件快照提升、媒体鉴权读取和媒体 URL 归并到 `ObjectStorageService`；受鉴权资产路径统一为 `/api/v1/media/assets/{id}`，不再挂在视频命名空间。
5. [x] 删除废弃播放/节点 Schema、视频节点数据库方法和配置项；初始化迁移清除 `video_service_nodes`，Bootstrap 清除历史视频节点、旧 Pose relay 和旧并发上传环境变量。
6. [x] 部署脚本显式删除树莓派残留旧模块并排除验证脚本；新增跨端 AST 契约检查和运行时路由检查。本地共享采集、重连、隐私、上传、Hailo runtime、管理端和关停回归全部通过。
7. [ ] 部署到树莓派并核对旧文件、旧表和旧环境变量均已消失；管理端、生产云端和 TestFlight 分别打开两路三模式，确认画面、鉴权、事件证据与恢复行为无回归后关闭 GH-012。
8. [ ] GH-012 实机通过后继续 GH-013：统一 SQLite、快照、上传队列和 COS 清单、保留期、循环删除、失败重试与孤儿对账。

## 15.37 盒子、云端与 COS 统一存储生命周期（2026-08-02）

1. [x] 盒子建立持久 `media_lifecycle_jobs` 队列；快照、对象资产和过期上传会话统一先删除受管字节，再提交 SQLite 引用清理。失败保留业务行和任务，以有界指数退避重试。
2. [x] 清理候选在 `BEGIN IMMEDIATE` 中重新检查事件、检测、规则、活动摘要、上传任务和媒体引用；被重新引用时取消删除。每路摄像头最新快照始终受保护，达到临界水位时按最老未保护数据循环回收。
3. [x] 容量统计统一包含 SQLite、WAL/SHM、快照、对象存储和运行日志；高/临界水位清理后仅在可复用页和临时空间达标时执行 WAL checkpoint 与 VACUUM，目录由 worker 显式传入。
4. [x] 删除清理事务关闭外键检查的历史路径；现由真实外键约束阻止悬空引用，失败进入可重试生命周期，不再静默制造不一致。
5. [x] 云端资产按家庭记忆、用户上传、严重事件、普通事件、验证证据和临时上传分类；家庭记忆、用户上传及未解决严重事件自动保护，其余按可配置期限进入对象先删和删除墓碑。
6. [x] 新增 COS 全分页清单、`event-evidence/` 与 `memory-media/` 孤儿对账、本地媒体孤儿对账；COS 与本地分别建立权威 key 集，禁止同名 key 跨存储后端互相误保护。
7. [x] 新增受运维 token 保护的生命周期接口和 `dry_run`；盘点定时器默认启用，但真实删除由独立 `GOHOME_MEDIA_LIFECYCLE_DELETE_ENABLED=1` 显式解锁。未解锁时接口默认 dry-run 且拒绝强制删除。调度器只保留一个生命周期定时器。
8. [x] PostgreSQL 迁移、导出、水合和差量持久化统一保留生命周期字段；验证事件和证据可持久化用于质量审计，但验证消息继续隔离，不进入用户通知。
9. [x] 自动验证完成：云端 `100/101` 通过、`1` 项仅因无 PostgreSQL 集成地址跳过；边缘失败重试、最新帧保护、事件证据、家庭记忆、容量统计、外键、环形留存和有界关停通过。
10. [ ] 生产云先保持自动生命周期关闭，应用迁移 `013_media_lifecycle.sql`，执行真实 COS dry-run 并人工核对清单；确认后启用删除，验证对象、墓碑、失败重试、指标和服务重启。
11. [ ] 树莓派保留现有数据部署，制造高水位并验证循环删除、每路最新帧保护、数据库压缩耗时、服务连续性和重启恢复；通过后关闭 GH-013。

## 15.38 盒子真实数据库完整性迁移（2026-08-02）

1. [x] 保留 `/home/gohome/gohome/edge-agent/data` 部署并审计真实 SQLite；确认历史摄像头物理删除导致 `10,476` 条外键违规，活动摄像头为 31、32。
2. [x] 所有 `Storage.connect()` 连接强制 `foreign_keys=ON`；摄像头删除改为软归档，清除流地址和账号密码并保留历史主键锚点，活动读取和状态更新统一排除归档行。
3. [x] 初始化迁移恢复 1-30 的历史摄像头锚点；生命周期任务引用改为 `ON DELETE SET NULL`，旧约束通过幂等重建升级，保留任务审计和目标编号。
4. [x] 本地旧约束升级、软归档、历史恢复、生命周期、运行留存、环形留存、配置同步、Python 编译、脚本语法和差异检查全部通过。
5. [x] 盒子迁移后 `foreign_key_check=0`、`integrity_check=ok`、30 条归档摄像头无凭据、2 路活动摄像头保持原编号；数据库从约 `735 MB` 压缩到约 `159 MB`，服务重启后 active 且 `NRestarts=0`。
6. [ ] 完成生产 PostgreSQL/COS 首次 dry-run、删除解锁和失败重试验收；盒子完成持续高水位、断电恢复和长时循环测试后关闭 GH-013。

## 15.39 单一 RTSP 所有者与骨架同帧历史（2026-08-02）

1. [x] 树莓派实测两路状态与 RTSP：31 在线，32 的 `192.168.1.3:554` 拒绝连接；在线子码流 `640x360@15`，主码流 `2880x1620@15`，均不具备 30 FPS 输入。
2. [x] 共享读取器增加 `0.5/1/2/4/8` 秒有界指数退避、连接尝试数、连续失败数和下次重试指标；收到真实帧才重置失败状态。
3. [x] 删除 `capture_frame()` 在托管读取器失败时自行创建第二连接的旁路；离线分析立即返回统一状态，不再等待 2 秒拖慢其它摄像头。
4. [x] Continual Pose 为每路保留 64 帧轻量元数据历史；隐私渲染按摄像头、源流代和帧号读取同帧 Pose，缓存不含图像，重置摄像头时清空。
5. [x] 共享采集、断线恢复、节拍、adaptive worker、Pose、隐私、同帧同步和单在途上传回归通过；盒子在线解码约 `14.98 FPS`，隐私输出约 `14.92 FPS`，服务 active、`NRestarts=0`。
6. [ ] 恢复或停用第二路摄像头；逐路完成空房校准后进行纯骨架真人走动、遮挡、出入画和 30 分钟长时 TestFlight 验收，记录输出 FPS、残影、错帧和重连指标。
7. [ ] 以持久 H.264/H.265/WebRTC 替换当前公网逐帧 JPEG，MJPEG 仅保留局域网管理和明确降级用途。

## 15.40 摄像头 DHCP 地址原位更新（2026-08-02）

1. [x] 定位正式 iOS 编辑模式隐藏连接区、更新请求缺少连接参数，以及云端连接变化后不进入重新同步状态三个根因。
2. [x] 云端公开结构增加不含密码的 RTSP 连接摘要；PATCH 校验 `rtsp/rtsps` 地址，连接变化后统一写入 `pending_edge_sync` 并保留原摄像头、密码和历史关系。
3. [x] 正式 `ios-shell` 编辑页展示地址、端口、路径及可选新凭证；使用 `URLComponents` 生成地址，空用户名和密码不进入请求。
4. [x] 生产云摄像头 `29` 原位更新到 `192.168.1.7`，盒子本地摄像头 `32` 自动同步并恢复在线；云端恢复 `online / synced` 和约 `12.5 FPS` 接收。
5. [x] 云端设备专项 `2/2`、iOS 摄像头模型 `6/6`、权限与状态 `11/11` 通过，只使用正式 `GoHomeShell` 工程。
6. [ ] 下一 TestFlight 实机验证编辑地址、空密码保留、同步等待和守护页自动恢复；随后在路由器为 MAC `a8:b5:8e:a8:ef:cc` 设置 `192.168.1.7` DHCP 地址保留。

## 15.41 应用与模型升级供应链（2026-08-03）

1. [x] 删除无校验复制、`extractall()`、版本目录覆盖和任意入口执行路径；旧无签名发布不能进入新安装流程。
2. [x] 建立 Ed25519 版本化清单，签名覆盖包类型、版本、家庭/设备范围、大小、SHA-256、公钥标识、文件名、入口类型、入口路径和安装策略。
3. [x] 安装统一经过私有暂存、包体复验、逐成员安全解包、入口与文件树校验、不可变版本目录和原子移动；ZIP/TAR 穿越、链接、设备节点、重复成员和资源越界全部拒绝。
4. [x] 运行守护每次启动前复验签名、原始包、安装文件索引和入口位置；启动方式只读取签名 `entry_type`，不再根据后缀或执行位猜测。
5. [x] 新 App 先通过启动健康检查，再原子切换当前清单；失败只允许回滚到上一份已验证清单。包类型级跨进程锁阻止并发升级互相覆盖。
6. [x] 增加不部署到盒子的签名工具、发布契约文档、独立安全依赖和确定性攻击回归；边缘完整回归 `51/51` 通过。
7. [ ] 在正式发布环境保管私钥并向盒子配置对应公钥；树莓派实测合法升级、篡改拒绝、启动崩溃回滚、升级中断电和重启恢复后关闭 GH-038。

## 15.42 事件证据与升级包存储域拆分（2026-08-03）

1. [x] 删除盒子通用 `ObjectStorageService`、家庭媒体上传、公开媒体下载和设备媒体接收路由，停止事件接收后的快照二次复制。
2. [x] 事件证据只由本地持久上传队列发送生产云；上传端改为文件流，禁止 `read_bytes()` 整包载入。
3. [x] 生产云按 `Content-Length` 和上限校验后直接将请求流写入 COS；本地存储模式使用临时文件、大小复核和原子替换。
4. [x] 签名升级包独立为 `PackageArtifactService` 与 `/api/v1/package-artifacts/*`，使用 `package_artifact` 留存类别和流式上传，不复用家庭媒体语义。
5. [x] 新增边缘媒体所有权、升级包流式上传、超限清理和 COS 流式接收回归；边缘 `53/53`、云端 `100/101` 通过，PostgreSQL 集成项因未配置地址跳过。
6. [ ] 部署树莓派和生产云，验证断网重试、COS 故障、接近上限文件、事件幂等、唯一对象、鉴权读取和生命周期对账。
7. [ ] 由 GH-034/GH-038 继续把升级发布与目标控制面迁至生产云，迁移完成前不得恢复 `/api/v1/media/*` 通用接口。

## 15.43 盒子运行时与通知所有权收敛（2026-08-03）

1. [x] 完整核对盒子入口、设置、Schema、事件代理、SQLite、配网页、管理端和部署脚本，确认 LaunchAgent、旧 Web 试点和直发通知仍进入生产运行时。
2. [x] 删除 `EdgeBootstrapService`、`PublicPilotService`、通用通知器、App push、APNs relay 及全部盒子通知/运行时安装/旧公网试点路由；移除 `/ui` 静态挂载。
3. [x] 盒子事件代理和设备事件接收只负责持久化、去重与上行，不读取通知开关、不直接发送任何用户通知。
4. [x] 删除盒子 APNs/通知环境变量、DTO、规则字段、Push Token 与投递表；旧数据库启动迁移幂等删表删列，并验证保留规则值和事件清理可继续执行。
5. [x] 配网与管理登录图标改为自身 CSS 的 `data-icon`，移除已删除 `/ui` 字体资源依赖；删除失效测试通知脚本并让部署清单清理旧模块。
6. [x] 新增 `verify-production-runtime-boundary.py`，锁定盒子通知路由/模块/Web 入口为 0、systemd 为唯一生产运行时、APNs 仍由云端独占。边缘 `54/54`、云端 `100/101` 通过，PostgreSQL 集成项因未配置地址跳过。
7. [ ] 部署到树莓派，确认旧文件、旧表和 APNs 环境变量均已消失；验证 systemd 重启、断网上行补传和生产云单事件单通知后关闭 GH-040。
## 15.44 骨架证据资格解耦（2026-08-03）

状态：本地实现与专项回归完成，等待树莓派双摄真人验收。

1. [x] 冻结唯一 Pose 对象流，禁止新增 `display_poses`、`risk_poses` 或客户端二次骨架实现。
2. [x] 在模型输出层分别计算显示质量和跌倒质量；显示合格但跌倒质量不足的 Pose 保留骨架、清除跌倒候选并将正式风险分数归零。
3. [x] 人物一致性继续在场景和独立人物证据之后执行，不能因显示门槛降低而放过电视、家具、边缘和静态误检。
4. [x] 场景跌倒聚合与 Pose 因子图显式只消费 `fall_evidence_eligible=true` 的当前模型 Pose；缓存、KLT 和 coasting 维持 display-only。
5. [x] 输出显示骨架数、风险合格骨架数和仅显示骨架数，供算法页和验收日志区分显示质量与风险质量。
6. [x] 自动验收覆盖半身遮挡、完整骨架、无效几何、场景聚合和因子图隔离；边缘完整回归 `55/55` 通过。
7. [ ] 树莓派双摄实机覆盖进餐、侧身、桌面遮挡、站立到倒地和 30 分钟持续运行，确认显示召回改善且风险准确率不回退。

## 15.45 EACP 可复现质量评估（2026-08-03）

状态：评估基础设施本地完成；现有数据只达到规则回归门槛，未达到产品声明或模型训练门槛。

1. [x] 帧评估与跌倒序列评估统一到同一指标实现，输出完整混淆矩阵、F1、Specificity、Balanced Accuracy、FPR/FNR 和 95% Wilson 区间。
2. [x] 报告升级为 v2，绑定 Git/source/model/config/dataset 指纹、执行命令、平台、显式 split、分层结果及误报漏报清单。
3. [x] 增加严格产品声明门禁：独立 test、完整标签和文件、三 split 齐全、序列与受试者不泄漏、正负支持量达标；否则固定降级为工程回归证据。
4. [x] 数据审计增加帧顺序、元数据一致性、重复内容、序列泄漏、受试者泄漏和内容泄漏检查；稀疏/密集抽帧不重复计为独立数据来源。
5. [x] 从验收和数据目录移除退役火灾质量门禁；删除能从公开样本制造正式生产事件的注入脚本，运行闭环验收与统计评估保持隔离。
6. [x] 新增永久评估完整性和数据审计回归；真实 person 帧和 GMDCSA24 序列报告可生成且正确标记 `quality_claim_ready=false`。
7. [ ] 采集并标注不少于 50 个真实家庭困难负样本，覆盖两路固定视角和昼夜变化，先完成真实家庭误报 pilot。
8. [ ] 按受试者和序列建立 train/validation/test，不交叉使用同一人或同一视频；独立 test 至少 30 个跌倒正序列、50 个 ADL 负序列和 3 个来源。
9. [ ] 达到数据门槛后再训练轻量骨架时序模型，与现有规则基线做消融、延迟和 Hailo/Pi 资源对比；未优于基线不得替换生产规则。
10. [ ] 双摄完成 30 分钟、8 小时和多日长时实机采集，对齐离线失败清单、线上事件、云端复核与单次通知后，才形成有边界的产品质量报告。

## 15.46 持久空房基线与场景复核事务（2026-08-03）

状态：本地实现和自动回归完成，等待树莓派双摄实机验收。

1. [x] 删除运行场景不匹配时清空内存并删除持久基线的路径；强变化只阻断该路骨架并保留资产。
2. [x] 重校准改为候选事务，旧基线保留到新背景完成连续空房确认、压缩、fsync 和原子替换；成功后才切换内存。
3. [x] 同一路并发校准明确拒绝；人物进入、超时、分割不可用、磁盘失败和未知异常取消候选并退出 active，不产生半写临时文件。
4. [x] 新流代和服务重启必须使用无人帧复验持久基线；复验失败不删除文件，恢复原场景后可重新变为 ready。
5. [x] 场景判断抵消整体 BGR 色偏并允许有限局部变化；可见区域不足时不把人物遮挡误判为摄像头移动。
6. [x] 管理端和云中继区分 calibrating、revalidating、scene_review_required 和 calibration_required；管理端显示“场景变化，需重校准”。
7. [x] 新增校准 API 事务回归；扩展纯骨架专项覆盖电视、灯光、重启、移动、并发、持久化失败和成功基线替换。
8. [ ] 树莓派两路分别完成电视变化、开关灯、局部物品变化、服务重启、断流重连和真实移动；记录基线哈希、状态变化、输出 FPS、残影和恢复时间。
9. [ ] TestFlight 在场景复核期间保持原画/模糊可用，骨架显示明确状态；重校准成功后无需退出 App 即恢复画面。

## 15.47 重复像素与冻结源失效（2026-08-03）

状态：本地实现和自动回归完成，等待真实摄像头冻结/恢复验收。

1. [x] 共享读取器区分 decoded arrival 与 unique frame arrival；effective/source FPS 只使用唯一帧样本跨度。
2. [x] 相同内容不写中央缓存、不推进 `frame_id`、不刷新有效帧时间，也不会唤醒 Tracker。
3. [x] 连续冻结超过 3 秒释放捕获、清空缓存和 FPS 窗口、提升流代并通知统一视觉状态重置。
4. [x] 内容指纹覆盖提升到每 8 像素并绑定分辨率，回归覆盖旧 16 像素采样会漏掉的局部移动。
5. [x] 自动回归确认冻结时 decoded 增长、unique 固定、effective FPS 为 0、旧 Pose 清除、缓存为空和流代提升。
6. [ ] 树莓派两路分别制造摄像头 App 冻结、RTSP 重复帧、断网和恢复，确认管理端、云端和 TestFlight 的有效 FPS、帧龄、人物状态与重连时间一致。

## 15.48 近黑帧身份与实时缓存收口（2026-08-03）

状态：本地实现和自动回归完成，等待树莓派双摄与 TestFlight 实机验收。

1. [x] 将近黑判定从每个 `raw_frames()` 订阅者收回到每路唯一共享读取器，删除订阅者独立黑帧状态。
2. [x] 删除 `last_good_frame` 及旧像素替换；预览像素、`frame_id`、采集时间、源键和流代始终来自同一中央有效帧。
3. [x] 近黑帧只增加 decoded 和 near-black 诊断，不写中央缓存、不推进 unique/effective FPS、不唤醒算法订阅者。
4. [x] 首个近黑帧立即撤下中央实时缓存、清空有效 FPS/内容连续性并进入 stale；连续至少 5 帧且 0.75 秒后提升流代、通知下游重置并按现有有界退避重连。
5. [x] 专项回归审计中央每一次缓存写入，确认连续 5 张近黑帧为零写入、旧像素为零重发、恢复帧流代提升；共享采集、冻结源、同帧分析和同步骨架测试通过。
6. [ ] 两路分别制造解码启动黑帧、镜头遮挡、夜间低照、RTSP 断流和恢复，核对 decoded/effective/near-black、流代、帧龄、Pose 清理和重连耗时。
7. [ ] 管理端、生产云和 TestFlight 同时观察：异常期间不得停留旧人物画面或显示非零有效 FPS；恢复后无需退出页面，并从第一张真实新帧继续。

## 15.49 Hailo idle Pose 激活闭环（2026-08-03）

状态：首个调度根因已修复，GH-030 继续处理中。

1. [x] 读取 Pi 现场 `/health` 累计指标并做 15 秒差分：空房 Pose 总计 4.0 Hz、Object 1.6 Hz、分割 9.33 Hz，两路 KLT 展示约 11-13 FPS。
2. [x] 确认 Pose HEF 中位 22.86 ms、P95 35.24 ms，整管线中位 28.76 ms、P95 71.62 ms，Hailo 推理失败 0；当前硬件不存在温度或模型不可用瓶颈。
3. [x] 修复 idle Hailo Pose 结果被配置层丢弃：后端已确认 accelerated 时启用当前预计算 Pose 解析，直接承担人物出现和风险首帧门禁，不增加一次 Hailo 调用。
4. [x] 保持 CPU/未知后端 idle 时不加载 RTMPose；只有已有 Hailo 结果可复用，避免第二模型、第二 runtime 或额外设备负载。
5. [x] Worker 回归覆盖 Hailo idle Pose 复用、CPU motion-only、人物 active、风险唤醒、流代身份和 KLT 锚点；调度器与视觉管线专项通过。
6. [ ] 部署 Pi 后两路分别执行空房、单人进入、遮挡、快速移动、离开，记录从 2 Hz 切到 active 的时间、每路模型 Pose Hz、deadline miss 和恢复 idle 时间。
7. [ ] 启用正式 Hailo 监控并记录 Pose/Object/Seg 各网络组利用率和队列；只有设备存在空闲且全局锁造成吞吐损失时，才拆分模型级并行，不能凭宣传 FPS 增加线程。

## 15.50 管理凭据迁移与登录缓存（2026-08-03）

状态：已完成并通过盒子实机验收。

1. [x] 核对盒子真实认证文件、权限、限流和安全审计，确认旧默认密码已被逐设备一次性凭据替换，认证数据未损坏。
2. [x] 使用盒子保存的一次性凭据调用真实登录接口，确认返回成功且 `must_change_password=true`。
3. [x] 受保护页面重定向加入当前认证静态版本，登录 HTML、脚本、样式与认证 API 统一设置 `no-store`。
4. [x] 保持未认证状态不泄露凭据或待改密细节；成功登录后才进入强制改密流程。
5. [x] 部署树莓派并单次重启，验证 `no-store` 响应头、`auth-5` 登录跳转、一次性凭据真实登录和盒子实际脚本；修复 8 位密码校验错误被显示成 `[object Object]`，增加 10-128 位前端校验和结构化错误格式化。
6. [x] 用户完成首次改密并以新凭据进入管理端；认证元数据为用户自定义凭据、无需再次改密，一次性凭据文件已删除。

## 15.51 诊断画面与纯骨架成品流收口（2026-08-03）

状态：代码、自动回归和盒子部署完成，等待两路空房校准和重启验收。

1. [x] 现场确认视觉算法页连接诊断 Pose 流，黄色骨架为盒子诊断合成，不是用户隐私成品流。
2. [x] 现场确认云端期望模式为 `skeleton`，但两路状态均为 `calibration_required`、基线目录为空、云端成品接收 FPS 为 0。
3. [x] 算法页改为固定诊断状态，移除可操作隐私模式；管理首页和摄像头页改为“App / 首页画面”模式控制。
4. [x] 首页纯骨架未校准时停止建立视频连接；盒子 MJPEG 在响应建立前以结构化 409 拒绝，禁止空 200 和隐私降级。
5. [x] 管理端 API 错误处理支持结构化 `detail.message` 和非 JSON 响应，校准失败显示明确中文。
6. [x] 完整边缘回归 `58/58` 通过并部署树莓派；服务 `active`、`NRestarts=0`、无 warning，实际静态资源和两路未校准阻断状态符合契约。
7. [ ] 画面无人时分别完成两路空房校准，核对 `.npz`、SHA-256、蓝色纯骨架成品流和云端接收 FPS。
8. [ ] 服务重启后确认基线恢复与自动复验，管理首页和 App 无需重新校准且显示同一纯骨架画面。

## 15.52 未校准隐私计算短路（2026-08-03）

状态：已完成并通过 Pi 实机差分验收。

1. [x] Pi 现场确认两路纯骨架均为 `calibration_required`、成品提交为 0，但 Hailo 人物分割和掩码传播仍持续增长。
2. [x] 记录现场资源基线：两路源流约 15 FPS，Pose 锚点约 `2.25 / 3.20 Hz`，CPU 温度约 `72-74°C`，进程约 270% CPU。
3. [x] 背景重建器增加持久基线前置门禁，按摄像头、配置源身份和分辨率判定；缺失基线和校准中状态立即阻断。
4. [x] 纯骨架在 Pose 同步、人物分割、背景重建和 JPEG 编码前执行门禁；持久基线的流代复验路径保持不变。
5. [x] 自动回归锁定未校准渲染的分割调用次数为 0；隐私、校准、上传专项和完整边缘回归 `58/58` 通过。
6. [x] 部署 Pi 并单次重启；两路未校准期间分割成功、分割锚点和传播均保持 0，无隐私帧编码/上传，服务 `active`、`NRestarts=0`、无 warning。
7. [x] 差分确认温度约 `74°C -> 65°C`、进程 CPU 约 `270% -> 90%`；有人画面 Pose 锚点约 `14 Hz`，无人画面约 `2 Hz`，展示约 `13-15 FPS`。当前无需为宣传吞吐盲目拆出第二套 Pose 管线。

## 15.53 双摄空房校准与管理流身份（2026-08-03）

状态：管理流会话隔离与连接终止已通过 20 次真实切换；摄像头 32 已完成真实空房校准并进入 `ready`，摄像头 31 已恢复持久资产发现，当前因真实人物在场保持 `revalidating / person_present / 0/3`。

1. [x] 分别直连两路 RTSP 抓取真实当前帧，确认摄像头 31 为电视柜/沙发视角、摄像头 32 为冰箱/电视墙视角，配置源和内容指纹彼此独立。
2. [x] 摄像头 31 在无人画面完成 8 帧空房确认和持久提交，状态 `ready`、`baseline_revision=1`；`.npz` 文件 SHA-256 为 `291639114ffe4064d3e11e503a150ccb7b8b4f5dbd56bc992bf070a970256bd8`，基线像素 SHA-256 为 `cc8ff649c3611f51ae063ba1c089758140415c48c56d12d4566750ffcab5f969`。
3. [x] 摄像头 32 首次真实校准请求因当前画面存在人物被后端拒绝，状态保持 `calibration_required`、错误为 `person_present`；不绕过人物门禁、不写污染基线。
4. [x] 定位管理端切换假串流根因：复用同一 MJPEG 图像节点且用 900 毫秒定时器隐藏加载层，新首帧前继续展示旧像素。
5. [x] 每次切换和重连使用全新图像节点，按摄像头与 `streamGeneration` 接受首帧和错误事件；删除定时揭示，未收到新首帧时只显示加载状态。
6. [x] 校准请求改为按摄像头唯一 pending 所有权，轮询重绘期间按钮不可重复提交；过期 toast 文本在提示结束后清空。
7. [x] Node 语法、静态资源版本契约和完整边缘回归 `57/57` 通过；CSS/JS 使用同一原子缓存版本，不发布混合静态资产。
8. [x] 首轮部署后实测切换立即隐藏旧像素并显示加载状态，但快速循环使共享源订阅由每路约 2 个累积到 `4 / 5`，新首帧最终超时；确认仅替换 DOM 节点不足以终止旧 MJPEG HTTP 会话。
9. [x] 生命周期调整为先提升代次，再隐藏旧节点、解除旧事件处理器并移除旧 `src`，最后替换节点；静态契约锁定该顺序，四页资源原子升级为 `stream-lifecycle-2`。
10. [x] 第二轮 Node 语法、静态契约和完整边缘回归 `57/57` 通过。
11. [x] 第二轮提交 `a59e1ef` 已推送并仅部署静态资产；真实 20 次交替切换全部先隐藏旧画面，首帧 `494-1312 ms`、中位 `751 ms`，标签和 URL 全部匹配。
12. [x] 切换前后共享源订阅稳定为 `31:2 / 32:4`，没有连接增长；两路源流约 `15 FPS`、重连为 0、Hailo Pose/Object 失败为 0。
13. [ ] 制造一路流不可用，确认页面显示不可用且不保留旧摄像头像素，完成 GH-050 最后一项验收。
14. [x] 修复摄像头 31 持久 `.npz` 在服务重启后被管理页显示为“未校准”的状态语义；启动发现后明确显示 `calibrated=true / baseline_retained=true / ready=false / revalidating`，不得要求无意义重校准。
15. [x] 复验门禁改为每次强制当前帧 Hailo 人物分割锚点；Pose 或分割任一有人证据都清零进度，修复有人画面曾被背景局部变化错误接受的问题。
16. [x] 重验证锚点按摄像头、源代和分辨率限制为每秒最多一次；保持三次独立锚点，不使用传播掩码。确定性专项和完整边缘回归 `58/58` 通过，提交 `5642c9d` 已部署。
17. [x] 部署后服务 `active`、`NRestarts=0`，校准文件哈希未变化，两路源流约 `15 FPS`、重连和 Hailo 失败为 0；`/health` 公开 1 秒调度状态。20:51 摄像头 31 当前帧可见两个人，安全门禁正确保持 `person_present / 0/3`，不得写成空房复验失败。
18. [x] 摄像头 32 真实空房画面完成 `8/8` 校准与 `3/3` 独立 Hailo 复验，人物拒绝数为 0、`ready=true`、`baseline_revision=1`；持久文件大小 `369281` 字节，文件 SHA-256 为 `8a2cda89ea9412841142193ef7ea9114c4ccb8c9ca51d7ec271ddd2a4fd63344`，基线像素 SHA-256 为 `05eae00d1c0faa0fc818d05e68a70a707130d91e9e3647e1e63e456918a49aab`。
19. [x] 摄像头 31 在真实空房后由现有基线自动完成 `3/3` 复验；文件 SHA-256 保持 `291639114ffe4064d3e11e503a150ccb7b8b4f5dbd56bc992bf070a970256bd8`，复验调度活动流清零，没有重复校准或绕过人物门禁。
20. [ ] 两路均 `ready` 后已切换纯骨架；摄像头 32 管理首页实帧确认单一蓝色骨架、无人物原像、无双骨架，端侧约 `12.8-13.6 FPS`、云端约 `10.5-11.4 FPS`、失败为 0。切换后人物重新进入摄像头 31，该路正确阻断并回到 `person_present / 0/3`，因此算法页、生产云、TestFlight 双路真人同帧、单次重启恢复、遮挡/离开/宠物和 30 分钟稳定性仍待完成。

## 15.54 TestFlight Build 9 骨架协议收口（2026-08-03）

状态：根因确认、正式实现、自动测试、双摄长时门禁和 Build 9 上传已完成；等待 Apple 处理和 TestFlight 真机验收。

1. [x] 核对手机当前安装版本与历史归档，确认故障版本为 2026-08-01 归档的 `1.0.0 (8)`。
2. [x] 还原 Build 8 对应源码，确认骨架模式要求 `safe-scene-pose-v1`、scene MJPEG 和 Pose SSE，协议不符时主动抛出 `APIError.invalidResponse`。
3. [x] 核对 2026-08-03 `2678233` 后正式架构：盒子是唯一隐私合成方，云端和 App 只传输、显示 `edge-composed-mjpeg-v1` 成品流。
4. [x] 确认生产会话与实际 MJPEG 响应声明新版协议；不恢复废弃路由、不降低客户端契约校验、不增加双轨兼容。
5. [x] 将唯一正式 iOS 工程的版本源和生成工程同步提升为 `1.0.0 (9)`。
6. [x] iOS 全量单元测试 `128/128`、UI 测试 `25/25` 通过，`xcodebuild` 返回 `TEST SUCCEEDED`。
7. [x] 完成纯骨架双摄 `1804.6` 秒、`360` 次稳定性采样：读取错误、模式不一致、服务故障、重连和上传失败均为 0；31/32 路云端帧龄 P95 为 `217.5 / 180.3 ms`，最终均为 `ready`。
8. [x] 从 `ios-shell/GoHomeShell.xcodeproj` 归档 Build 9；验证 `com.gohome.family / 1.0.0 (9)`、签名和二进制协议后完成 App Store Connect 上传，Apple 接收且无错误或警告。
9. [x] 安装 TestFlight Build 9 并进入生产骨架流；画面可见、约 `7-13 FPS`，不再出现“服务器返回无法识别的响应”，云端只存在正式 video 客户端而无 Pose/scene 客户端。
10. [x] 关闭 GH-005 协议故障；双路无人物像素、无双骨架、无残影、无串画面继续属于 GH-008，FPS 与持久传输继续属于 GH-010、GH-011、GH-033。

## 阶段 28：持久编码实时视频链路

状态：进行中。正式公网链路已迁移为持久 H.264 + WHEP/WebRTC；当前只剩三模式、网络切换和端到端 TestFlight 长时交付验收。

1. [x] 根据双摄、生产云和 TestFlight 同时段指标定位瓶颈：源流和端侧合成基本达到 `12-15 FPS`，云端/手机下降到 `7-13 FPS`，待发送帧覆盖约 `19%-20%`，最大间隔约 `1.1-1.5s`。
2. [x] 验证 Pi 5 当前系统没有可用 V4L2 H.264 编码设备；验证 `libx264 ultrafast/zerolatency` 对 `640x360@15 FPS` 达到约 `36.1x` 实时，双路软件编码可行。
3. [x] 定稿唯一正式链路：共享 RTSP 采集 -> 盒子一次隐私合成 -> 每路常驻 FFmpeg/libx264 -> RTSP/TCP 发布 -> MediaMTX -> WHEP/WebRTC -> iOS 原生渲染。
4. [x] `PrivacyFrameRenderer` 输出未经传输编码的 BGR 成品帧；JPEG 只由局域网管理诊断消费者按需编码，缓存不再绑定 JPEG 质量。
5. [x] 实现并部署每路一个有界 H.264 发布进程，绑定摄像头源代次、隐私模式和关停生命周期；进程异常时重建当前流，不排队补发旧帧。专项和完整边缘回归 `58/58` 通过。
6. [x] 生产云部署固定版本 MediaMTX、TLS、RTSP/TCP 发布、WHEP、ICE/TURN、外部鉴权、路径隔离、指标和 systemd/nginx；真实双摄已通过 RTSPS/H.264 持续发布。
7. [x] Node 播放会话已统一调用 `MediaAccessService` 签发短时 WHEP 权限，绑定家庭、盒子、摄像头、动作、路径、隐私模式和有效期；云端不解码、不合成、不保存直播像素。
8. [x] iOS 已使用 WebRTC M137 和原生 Metal 视频渲染器消费 WHEP；显示 FPS 只统计当前渲染器实际收到的新视频帧，换路、换模式和生命周期变化会关闭旧 PeerConnection 与 WHEP 资源。
9. [x] 删除正式 `_LatestFrameUploader`、逐帧上传 API、云端 JPEG 缓存/MJPEG 产品路由、播放票据和 iOS `MJPEGStreamClient`；盒子 LAN 管理 MJPEG 保持独立且正式 App 无自动降级。
10. [ ] 双摄执行 30 分钟原画/模糊/骨架、前后台、蜂窝网络、断网重连和模式切换验收；记录源、合成、编码、发布、云接收、WebRTC 接收/渲染 FPS，端到端延迟、丢包、CPU、温度、内存和重连次数。

## 15.55 云端媒体鉴权与部署契约（2026-08-04）

状态：生产媒体服务、盒子双路发布、WHEP 会话、iOS 原生 WebRTC 和旧正式 MJPEG 删除均已完成；TestFlight 全网络与三模式联合验收尚未完成。

1. [x] 建立唯一 `live/{device}/{camera}` 路径规则，设备 ID 和摄像头 ID 仅允许有界安全字符。
2. [x] 发布鉴权使用已签发设备令牌哈希，每次核对活跃令牌、设备、家庭、摄像头归属和启用状态。
3. [x] 读取令牌绑定用户、家庭、设备、摄像头、路径、动作、隐私模式和 30-300 秒有效期；令牌独立放入 Bearer 头，不进入 URL。
4. [x] 会话签发前与每次媒体连接时均重新核对当前成员资格、摄像头归属和隐私模式；撤销或切模式后旧会话拒绝。
5. [x] MediaMTX 鉴权路由限制为本机回环 + 32 字节以上独立共享密钥，成功只返回 204，健康状态不暴露任何密钥。
6. [x] 新增 MediaMTX `v1.19.3` 最小生产配置、systemd 单元、nginx WHEP 代理、加密环境模板、ICE/TURN 参数和防火墙/证书验收契约。
7. [x] 鉴权专项 `3/3`、完整云端 `103/104` 通过，唯一跳过为未配 PostgreSQL 连接的集成项；YAML 独立解析和差异检查通过。
8. [x] 生产机已加载官方 MediaMTX `v1.19.3`，配置 TLS、Coturn、防火墙和 nginx，完成匿名拒绝、路径鉴权与真实盒子双路发布。
9. [x] 正式播放会话已接入 `MediaAccessService`；iOS 已完成受鉴权 WHEP `OPTIONS/POST/DELETE`、完整 ICE 收集、SDP 应答、原生渲染和严格生命周期管理。
10. [x] 删除云端播放票据、逐帧直播上传、JPEG 缓存、产品 MJPEG 路由和 iOS MJPEG 客户端；云端回归 `98/99`、iOS 单元 `122/122`、UI `25/25` 通过，其中 WHEP 信令 `6/6`、守护页 ViewModel `13/13`，唯一云端跳过项为未配置 PostgreSQL 集成地址。
11. [x] 生产机稳定运行 MediaMTX `v1.19.3` 和 Coturn `4.6.1`；三组独立生产密钥、分离配置边界、TLS、nginx、匿名拒绝、证书钩子、Certbot dry-run、腾讯云安全组端口和真实盒子发布均已完成。
12. [ ] 从唯一正式工程生成下一 TestFlight，执行双摄三模式、前后台、切路、切模式、Wi-Fi/蜂窝、断网恢复和 30 分钟长时验收，再关闭 GH-033/GH-051。

## 15.56 H.264 发布稳定性与配置映射原子化（2026-08-05）

状态：根因修复、完整回归、Pi 精确版本部署和 30 分钟稳定性验收完成，GH-059 已关闭。

1. [x] 删除直播线程每三秒从磁盘重读摄像头映射的运行时通信路径；映射由 `ConfigSyncAgent` 的锁保护内存快照唯一持有，上传与直播共用同一解析器。
2. [x] 配置与隐私状态使用同一重入锁；状态文件经同目录临时文件、文件 `fsync`、`os.replace` 和目录 `fsync` 原子提交，禁止截断写入窗口。
3. [x] Relay 跨发布器对象保留逐路线程启动/停止次数、原因和时间；源变化、签名变化、停用、线程退出与服务停止可区分，旧停止请求不能污染新线程。
4. [x] 相同配置、摄像头映射、隐私模式、规则版本和维护结果不再写状态文件或 SQLite；`last_sync_at` 仅作为内存运行指标推进。
5. [x] 分割传播从逐帧 Farneback 改为每路复用 DIS UltraFast，并复用坐标网格和形态学核；Pi 中位约 `2.26 ms`、P95 `4.63 ms`，隐私分辨率和门禁保持不变。
6. [x] 当前主线与 Pi 四个关键文件 SHA-256 完全一致；本地完整边缘回归 `58/58`，状态文件超过 30 分钟哈希和 mtime 不变且无临时文件。
7. [x] 精确最新版完成 61 次、30 分钟采样：服务零重启，两路线程和 FFmpeg 进程均 `starts=1 / stops=0`，发布失败、半帧中止、stderr 和 journal warning 均为 0。
8. [x] 摄像头 31 编码输入 `12.44-14.78 FPS`，摄像头 32 `9.75-14.97 FPS`；进程约 `63.7% CPU / 349472 KiB RSS`，温度 `59.5-63.4°C`。
9. [x] 完成 GH-030 第一结构步骤：`DetectAgent` 与 `VisionPipeline` 共用一个 `PoseInferenceService`，唯一拥有 Hailo Pose runtime 和结果解释器；运行状态报告 `runtime_count=1`，原推理行为和串行边界不变，完整边缘回归 `58/58` 通过。Pi 部署后服务零重启，Hailo ready、双路 streaming、发布器单次启动且无错误，四个源码哈希与主线一致。
10. [x] 本地实现有界、最新帧优先的 Pose 协调器：每路单最新槽、全局单在途、双路持续进展、display/formal 同帧合并、完整源身份和 reset revision；完整 Pipeline 复用同帧 Hailo 结果，不复制 runtime。新目标只唤醒正式分析，只有已验证同源连续骨架可被高频刷新。完整边缘回归 `59/59` 通过。
11. [x] 精确部署 Pi 并完成 cadence 反证修复：`runtime_count=1`，每路一个最新槽、全局队列峰值 2，正式超时和 Hailo 失败为 0；活跃路协调器由约 `8.62 Hz` 提升至 `10.04 Hz`，Tracker 模型锚点 `9.85 Hz`，空闲路保持约 `2.26 Hz`。双路 H.264/隐私成品与各自源唯一帧同步，发布器均单次启动且 ready，服务零重启、journal 无 warning；`/health` 继续补齐唯一 Scheduler 状态源，用于解释后续真实场景升频原因。
12. [x] 完成双摄真人、遮挡、快速移动和离开同步实测：90.3 秒内 173/173 次采样成功，31/32 路 active 模型锚点峰值 `11.11 / 10.46 Hz`、协调器 Pose `14.43 / 12.70 Hz`，两路显示接近 15 FPS；31 路最后非空骨架后 `0.54` 秒清空，两路最终 empty/idle，超时、推理失败、事件和通知均为 0。温度峰值 `72.15°C` 后回落 normal。因入画早于采样进程建立，本轮不宣称精确进入延迟。
13. [x] 宠物时序状态改为线程安全的唯一状态源；健康接口按摄像头公开确认类别、猫狗证据命中数、时序平均置信度和最近命中年龄，不暴露图像或框坐标。完整边缘回归 `59/59` 通过；提交 `a109eef` 部署后两路当前轨迹均为 0，确认旧猫狗值只是历史观察，不是当前轨迹泄漏。
14. [x] 通过当日结构化记录确认类别冲突来自 Hailo Object 原始输出：31 路连续 4 帧为 `cat / 0.4628-0.5827`，32 路连续 8 帧为 `dog / 0.5277-0.6564`；时序层、App 和跨路缓存不是错误来源。随后 6 分钟采样中 Object 约 600 次成功、0 失败、无新宠物候选。
15. [ ] 执行 30 分钟有人/空房混合负载，覆盖两路同时 active、温控 warm 往返、宠物经过和持续电视内容；确认无 Hailo 饿死、无错误增长、无残留骨架且 H.264 帧率不持续下降。
16. [ ] 取得明确图像使用授权后，建立版本化宠物裁剪标注集和困难负样本；专用轻量分类器或类别不确定产品态必须通过独立混淆矩阵，禁止用统一阈值掩盖基础模型类别混淆。
17. [x] 完成宠物产品字段隔离：CPU 与 Hailo 均只向正式界面输出“宠物活动”，原始猫狗类别只进入受控诊断字段；时序、管理端和家庭首页契约测试及完整边缘回归 `59/59` 通过。提交 `f965f7f` 已部署 Pi 和生产云不可变版本 `20260805165225-f965f7f66a18`，双端文件哈希、服务健康和公网资源均已核对。
18. [x] 完成 61 次、30 分钟混合负载基础链路采样：服务、双路采集、Hailo、发布和温控无故障增长。模式只覆盖模糊与原画，未进入纯骨架，因此第 15 项保留未完成，下一轮必须显式核对每个样本的 `privacy_mode=skeleton` 后再做残影和清除验收。
19. [x] 在实时长测结束后完成盒子 SQLite 受控压缩：源库与压缩库完整性校验、原子切换和健康恢复均通过，`agent.db` 从 `693,161,984` 降至 `110,723,072` 字节；双路发布恢复、数据继续写入且无临时文件残留。持续高水位与断电环形留存仍按 GH-013 单独验收。

## 15.57 持久基线重启复验三态化（2026-08-06）

状态：根因修复与完整自动回归完成，等待 Pi 现有双路基线重启恢复和纯骨架长时实机验收。

1. [x] 记录 GH-060 现场反证：两路基线均存在，但几何结果只是 `unverifiable`，旧状态机却立即进入永久 `scene_review_required`。
2. [x] 场景判断从 `accepted` 布尔值改为 `same_view / camera_view_changed / unverifiable` 三态，禁止把证据不足当作摄像头移动。
3. [x] 几何验证在中等可用匹配上继续计算实际视角位移并公开 `strong / moderate / none` 置信度；弱移动证据保持不可验证，不能升级为正式机位变化。
4. [x] 每路独立记录连续同视角、连续可靠移动和不可验证次数；不可验证保留基线并继续有界复验，可靠同视角可恢复，只有连续 3 帧可靠移动才阻断。
5. [x] 已就绪骨架流短暂不可验证时继续执行同帧分割与持久背景合成，不回退原画、人物模糊、旧帧或第二套合成路径。
6. [x] 确定性专项覆盖连续不可验证、可靠恢复、双路隔离和连续移动确认；原有电视、家具、灯光、重启、校准事务与摄像头移动用例继续通过。完整边缘回归 `59/59`。
7. [x] 第一轮 Pi 部署保持两份基线哈希、服务零重启，但单应矩阵仍将局部特征外推为约 4.8%-8.9% 的全画面位移；不重校准、不调整位移阈值，继续回溯几何证据质量。
8. [x] 增加独立部分仿射 RANSAC、双模型一致性、双端内点空间覆盖和网格覆盖；局部特征簇、模型冲突和弱覆盖固定为不可验证，缓存结果不得重复累计移动次数。
9. [x] 部署双模型判定后 32 路以仿射约 0.5% 位移、单应约 5%-6%、覆盖不足的冲突证据正确恢复 ready；31 路保持 unverifiable，不再误封，但 ORB 只有约 6 个匹配。
10. [x] 31 路低纹理路径增加全局梯度相位对齐；只允许高响应、近零全局位移作为中等同视角证据，绝不单独确认机位移动。亮度变化同视角和全局平移反例均已回归。
11. [x] 精确部署相位复验；31 路响应约 `0.212`、位移约 `0.0011`，无需重校准完成 `3/3` 并恢复 ready；32 路保持 ready。基线哈希不变、复验调度清零、服务零重启且无 warning，GH-060 关闭。
12. [ ] 两路切换 `skeleton` 后执行逐样本模式断言的真人进入、行走、遮挡、离开和 30 分钟验收；任何样本不是骨架模式都必须判定本轮无效。

## 15.58 TestFlight Build 10 WHEP 发布一致性（2026-08-06）

状态：Build 10 已完成旧会话契约到 WHEP 契约的一致性修复；真机继续暴露 Trickle ICE 状态机错误，后续收口转入 15.59。

1. [x] 以生产访问日志、MediaMTX reader 和盒子发布状态定位故障边界：两路 H.264 持续 ready、会话签发持续 `200`，但 WHEP reader 始终为 0，证明 App 在协商前失败。
2. [x] 核对归档与提交时间，确认 TestFlight Build 9 早于 WHEP 迁移，仍要求旧 `ticket / stream_url / stream_path / edge-composed-mjpeg-v1`，无法解码生产 `whep-h264-v1` 契约。
3. [x] 保持正式视频链路唯一为 H.264 + WHEP/WebRTC；不恢复 MJPEG、不增加双协议兼容层、不把服务器回退到旧契约。
4. [x] 将正式版本提升为 `1.0.0 (10)`，补充生产形状响应缺省可选 `minimum_privacy_mode` 的解码回归。
5. [x] 发布门禁新增 `project.yml` 与生成工程版本一致性、iOS 与云端传输标识一致性、WHEP 会话字段和客户端实现存在性，并拒绝正式客户端重新出现旧 MJPEG 标识。
6. [x] 使用校验和匹配官方发布的本地 WebRTC XCFramework 完成构建验证；本地依赖只用于规避 Xcode 二进制下载钥匙串阻塞，不进入仓库或产品配置。
7. [x] iOS 定向 WHEP 测试 `7/7`、完整单元与 UI 测试 `148/148`、云端回归 `118` 通过且 `1` 个真实 PostgreSQL 用例按环境跳过，发布校验通过。
8. [x] 从唯一正式工程归档并上传 Build 10；归档核对为 `1.0.0 (10)`、`com.gohome.family`、arm64、生产 API，并包含 WHEP 会话端点和 WebRTC.framework。App Store Connect 于 2026-08-06 08:35 接受上传并进入处理。
9. [x] Build 10 真机确认生产 WHEP 会话可解码并成功完成 `OPTIONS`，不再出现旧 JSON 数据格式错误；但三模式均在 SDP `POST` 前约 8 秒超时，作为 GH-062 独立处理。
10. [ ] Build 11 完成端到端播放后再关闭 GH-061，并清理本机构建使用的 `/tmp` WebRTC 包、下载文件和诊断样本。

## 15.59 TestFlight Build 11 Trickle ICE 状态机（2026-08-06）

状态：根因修复、代码收口、自动验证、正式工程恢复、Build 11 归档上传均已完成；等待 Apple 处理和 TestFlight 真机验收。

1. [x] 以生产日志确定 Build 10 每次均为会话 `POST 200 -> WHEP OPTIONS 204`，没有 SDP `POST`，MediaMTX session/reader 为 0；故障严格限定在 iPhone 本地 offer 阶段。
2. [x] 对照 MediaMTX `v1.19.3` 正式 reader，确认旧客户端错误等待 `iceGatheringState == complete`；iPhone 未在固定 8 秒内完成收集，触发 `NSURLErrorDomain -1001`。
3. [x] `NativeWebRTCPeer` 设置本地描述后立即返回原始 offer，不轮询 ICE complete；本地候选由 delegate 实时交给单一有序队列。
4. [x] 候选严格按 `sdpMLineIndex` 分组生成 `application/trickle-ice-sdpfrag`，以同一 Bearer 权限和 `If-Match: *` 串行 PATCH 当前 WHEP resource；实现与 MediaMTX 正式 reader 的数字 `mid` 契约一致。
5. [x] 队列在资源创建和 answer 应用前保留早到候选，Actor 只批量排空队列，不为每个候选维护可乱序的独立发送任务；切路、切模式、停止或连接失败后关闭队列并拒绝旧代次。
6. [x] 连接建立期间的早期 PeerConnection 失败纳入同一连接状态，不能在 active peer 尚未赋值时丢失；候选 PATCH 失败会结束画面、关闭 peer 并删除 WHEP resource。
7. [x] 定向 WHEP/Peer 测试 `13/13`、完整 iOS 单元与 UI 测试 `154/154`，失败和跳过均为 0；云端回归 `118/119`，唯一跳过为未配置真实 PostgreSQL URL；发布门禁通过，版本提升为 `1.0.0 (11)`。
8. [x] 提交 `e023531` 已推送主线；使用唯一正式源码和 SHA-256 匹配的官方 WebRTC `137.0.0` 二进制完成 Build 11 归档并于 2026-08-06 09:39 上传。上传后工程已恢复远程 package 与精确锁文件，发布门禁确认不存在本地 `/tmp` 引用。
9. [ ] 真机观察生产请求顺序包含会话 `POST 200 -> OPTIONS 204 -> SDP POST 201 -> candidate PATCH 204`，MediaMTX reader 大于 0且 outbound bytes 持续增长。
10. [ ] 完成两路三模式、连续切换、前后台、Wi-Fi/蜂窝和断网恢复；全部通过后关闭 GH-061/GH-062并清理临时依赖与诊断源码。

## 15.60 生产 WHEP 网络族权限修复（2026-08-06）

状态：根因已由生产 HTTP 与 MediaMTX 日志确认，等待正式配置部署和 Build 11 真机复验。

1. [x] 确认 Build 11 已越过本地 ICE 等待：会话 `POST 200`、WHEP `OPTIONS 204`、SDP `POST 400`，故障位于媒体服务器 answer 生成阶段。
2. [x] 确认两路 H.264 path 均 ready/online，输入持续增长；三种隐私模式共用同一协商失败，排除摄像头、Hailo、隐私合成与发布链路。
3. [x] 从 MediaMTX 日志取得唯一根因：systemd 拒绝 route netlink，Pion 无法读取本机接口并创建 ICE answer。
4. [x] 正式 MediaMTX unit 的最小网络族增加 `AF_NETLINK`；不修改 Coturn/API 权限，不恢复 MJPEG或增加第二传输链路。
5. [x] 新增云媒体部署契约门禁，锁定精确地址族、安全限制、回环 WHEP 和 8189 UDP/TCP 配置。
6. [ ] 部署并单次重启生产 MediaMTX，验证 SDP `POST 201`、candidate `PATCH 204`、reader/outbound bytes 和无本机接口错误。
7. [ ] 用 Build 11 完成双路三模式、前后台、Wi-Fi/蜂窝、切路切模式和断网恢复验收，再关闭 GH-061/GH-062/GH-063。

## 15.61 WHEP 生产协商根因关闭（2026-08-06）

状态：GH-061、GH-062、GH-063 的协议、ICE 和生产 systemd 根因均已修复并取得 Build 11 真实证据；产品长时交付验收继续进行。

1. [x] 生产 MediaMTX unit 增加 `AF_NETLINK`，保留其余最小权限边界；部署提交 `efc7977`。
2. [x] 两路 H.264 发布在 MediaMTX 单次重启后自动恢复，服务 `active`、`NRestarts=0`。
3. [x] Build 11 两路真实会话均完成 `session 200 -> OPTIONS 204 -> SDP POST 201 -> candidate PATCH 204`。
4. [x] MediaMTX 两路均报告 peer connection established 和 H.264 reader，出站字节持续增长，接口读取错误为 0。
5. [x] 关闭 GH-061/GH-062/GH-063；不新增 MJPEG、双传输或宽松解析。
6. [ ] 继续双路三模式长时验收：每个采样强制记录 `privacy_mode`、视频接收/渲染 FPS、端到端延迟、断线恢复、前后台和切路代次。

## 15.62 本地闭环校验边界收口（2026-08-06）

状态：校验器已修复并通过；产品交付仍以生产 PostgreSQL、真实盒子和 TestFlight 实机证据为准。

1. [x] 新家庭老人资料为空时，校验器接受正式 API 的结构化 `404` 并记为 warning，不伪造默认资料。
2. [x] 干净回环 JSON 环境没有预置盒子/摄像头时，校验器记录明确 warning；云端 onboarding 独立验证绑定闭环。
3. [x] 当前主线临时实例闭环 `24 passed / 0 failed`，测试账号、家庭、设备和事件通过清理接口删除。
4. [x] 根门禁 `npm test`、云端 Node `119` 项（`118` 通过、1 项 PostgreSQL 环境跳过）继续通过。
5. [ ] 不把本地 JSON warning 当作生产验收；下一步继续真实双摄三模式和网络长测。

## 15.63 内容帧与直播投递帧解耦（2026-08-06）

状态：根因实现与完整自动回归完成，等待用户回家后精确部署 Pi 并执行双路实机验收。

1. [x] 确认两路摄像头解码约 `15 FPS`，H.264 输入下降不是 Hailo、编码器或 WHEP 故障，而是共享读取器提前丢弃重复内容帧。
2. [x] 内容帧只在像素内容真实变化时推进，继续作为 Motion、Pose、风险、活动日志和有效内容 FPS 的唯一输入。
3. [x] 新增逐路有界直播投递槽和独立单调投递身份；未冻结的有效重复帧可维持直播节奏，但不推进分析身份。
4. [x] 隐私合成继续使用内容 `frame_id/source_key/stream_generation`，H.264 发布改用 `delivery_frame_id` 和投递时间，不跨摄像头、不跨流代、不重复执行 Hailo。
5. [x] 近黑帧继续全部抑制；连续冻结仍清除内容与直播两个槽位、提升流代、清除旧 Pose 并重连。
6. [x] 专项覆盖内容/投递身份隔离、分析消费者不被重复帧唤醒、缓存超前、近黑恢复、冻结失效和发布器投递身份；完整边缘回归 `59/59`。
7. [ ] 用户回家后精确部署两个运行文件，先验证两路原画、模糊、骨架可播放，再同步采集四类 FPS 与冻结恢复指标。
8. [ ] 执行双路有人进入、静止、行走、遮挡、离开和 30 分钟三模式验收；没有真实证据前 GH-065 保持待实机验收。

## 15.64 内容帧与直播投递帧首轮 Pi 实机验收（2026-08-06）

状态：首轮实机指标通过，用户端画面与长时验收继续进行，GH-065 保持待实机验收。

1. [x] 只部署 `edge-agent/app/camera_agent.py` 和 `edge-agent/app/live_relay_agent.py`，不运行会清理历史文件的全量部署脚本；盒子服务只重启一次，远端哈希与主线完全一致。
2. [x] 重启后两路重新完成持久基线复验并恢复 `ready`，没有重校准、删除摄像头或修改设备数据。
3. [x] 两路解码约 `15.01/15.05 FPS`，直播投递约 `15.01/15.05 FPS`，内容帧约 `13.61/14.75 FPS`；重复内容只影响内容帧统计，不影响有效直播投递。
4. [x] 两路 H.264 编码输入约 `14.48/14.23 FPS`，发布器均 ready，读取失败、重连、编码失败和连续失败为 `0`；纯骨架端侧成品输出约 `13.1/13.9 FPS`。
5. [ ] 登录盒子管理端确认两路画面、右上角真实 FPS 和骨架无残影；在正式 GoHome App 确认两路 WHEP 播放与管理端同步。
6. [ ] 完成静止、行走、遮挡、离开、冻结输入、断流重连和 30 分钟原画/模糊/纯骨架长测，并把每次采样的模式、帧龄、输出 FPS、错误和重连写入交付报告。
