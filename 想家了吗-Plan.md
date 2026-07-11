# 回家 Plan

更新时间：2026-07-08

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

- 用户端 App / H5
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
- 静态 Web 后续替换为 App / H5 / 管理后台。

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
6. 跑通算法预览：每次选择一个摄像头和一个算法，看实时效果、阈值、置信度、规则解释和最近日志。
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
8. 跑通算法预览：每次只选择一个摄像头和一个算法。
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
- `/admin` 支持一次选择一个摄像头和一个算法查看实时效果。
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
7. 在 `/admin` 选择一个算法查看实时效果，并确认能看到服务、摄像头、检测和报警日志。
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

1. 管理端一次只选择一个摄像头和一个算法预览。
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

1. 配置至少一个真实通知通道。
2. 触发一次真实事件。
3. 手机收到至少一条通知。

通过信号：

- `scripts/send-test-notification.sh` 可跑通
- 手机能看到通知送达

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
curl -I http://127.0.0.1:8711/ui/index.html
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

```bash
cd /home/pi/gohome/edge-agent
bash scripts/send-test-notification.sh
```

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
5. `/admin` 完成算法开关、单算法预览、报警测试和日志诊断。
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
4. 在 `/admin` 补齐算法预览能力，每次只选择一个算法看实时效果。
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
- 新增或补齐 `/admin` 单算法预览。
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
8. 新增 `/admin` 算法预览能力，每次选择一个摄像头和一个算法。
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

### 14.5 用户端信息架构收口规则

当前 H5/App 原型按以下页面职责继续推进，后续不再为了补功能强行增加重复入口：

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
7. 进入首页、守护、事件、陪伴和我的完整主功能。

未完成状态处理：

- 没有家庭：只显示“创建家庭 / 加入家庭 / 切换手机号”。
- 没有老人资料：只显示“填写老人资料 / 切换手机号”。
- 没有绑定盒子：只显示“扫码绑定 / 输入绑定码 / 盒子还没联网？”。
- 没有摄像头：只显示“添加摄像头 / 稍后退出”，不能展示正常守护首页。
- 底部主导航在配置完成前隐藏或禁用，避免用户进入空守护、空事件、空陪伴。

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

- 人体确认：1 FPS，5 秒窗口至少 4 次可信命中。
- 姿态检测：确认有人后 2-4 FPS；连续 3 秒多数一致后形成姿态片段。
- 姿态集合：standing、sitting、squatting、bending、lying、upper_body、unknown。
- 快速跌倒：保留现有站坐基线、下降、低位持续和床/沙发排除，目标告警延迟约 4-8 秒。
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
- 已完成：30 秒默认超时、最多 3 次重试、`5s / 30s / 120s` 退避、响应和错误审计。
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

阶段 5 状态：已完成并部署树莓派与腾讯云。APNs 未接入前，每分钟提醒形成 App 消息和模拟投递记录；真正系统推送待 iOS/APNs 阶段完成。下一步进入阶段 6，合并统一视觉感知管理页面和家庭存在状态展示。

阶段 6：统一视觉感知页面

- 合并现有人形、姿态、跌倒和火灾研发页面。
- 普通 App 只保留守护状态、实时画面、事件和处理动作。

阶段 7：数据集与学习模型

- 在现有 UR Fall、GMDCSA24、Wikimedia 空室内和家庭负样本基础上增加姿态序列数据。
- 先用规则 baseline 生成候选，再由云端模型和人工确认标注困难样本。
- 数据成熟后评估 ST-GCN 或等价骨架时序模型，不在第一阶段直接替换可解释状态机。

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
