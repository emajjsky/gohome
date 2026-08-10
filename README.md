# 回家 GoHome

GoHome 是一套由家庭边缘守护盒、云端服务和 iOS App 组成的家庭关系与安全辅助产品。它的目标不是让家属长期盯着摄像头，而是把家庭状态转成联系理由、回家计划和必要的异常处置证据。

## 当前基线

- 正式 iOS 工程：`ios-shell/GoHomeShell.xcodeproj`
- Bundle ID：`com.gohome.family`
- 当前发布候选：`1.0.0 (16)`，事件证据链改动已部署盒子和云端，待 TestFlight 上传与真机验收
- 硬件：树莓派 5 + Hailo-8 HAT+
- 云端：Node API、PostgreSQL、COS、MediaMTX、Coturn、nginx
- 视频主链路：RTSP 共享采集 -> 盒子一次隐私合成 -> H.264 -> WHEP/WebRTC -> iOS 原生渲染
- 自动验证：iOS 单元 `196` 项通过、UI `22` 项通过；Node 服务门禁、Python 编译和 `git diff --check` 已通过

Build 15 是发布候选，不等于所有产品质量门禁已经完成。真实家庭误报/漏报、APNs 生产到达率、宠物猫狗混淆矩阵、跨品牌摄像头兼容、双摄纯骨架长时稳定性和 20-50 户家庭试点仍需独立验收。

## 产品边界

### 三种用户隐私模式

| 模式 | 正式行为 |
| --- | --- |
| 原画 | 显示当前摄像头原始画面，不绘制骨架 |
| 模糊 | 保留当前场景，只模糊当前帧人物，不绘制骨架 |
| 骨架 | 保留非人物场景像素，移除人物像素，只绘制与当前帧同步的一套骨架 |

盒子是用户隐私成品帧的唯一合成方。管理端视觉算法页的黄色骨架是工程诊断输出；管理首页和 App 守护页显示盒子成品流，客户端不得二次绘制骨架、复用旧帧或跨摄像头混帧。

### 定位边界

- 家庭固定位置由家庭创建者在家中使用手机确认一次，保存为家庭事实。
- 手机当前位置只用于计算手机到家庭固定位置的距离。
- 社区服务只使用家庭固定位置，不使用手机当前位置附近的社区数据替代老人所在社区。
- 盒子或摄像头 DHCP/RTSP 地址变化应通过配置同步和自动重连处理，不要求删除摄像头或重新绑定盒子。

### 算法边界

EACP 当前是“边缘检测 + 骨架时序状态机 + 可解释因子图 + 云端多模态复核”的工程框架，不是已训练完成的 ST-GCN 或其他时序深度模型。公开数据回归和现场闭环只能证明当前工程链路，不能直接写成真实家庭准确率、医疗诊断能力或救援保证。

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `edge-agent/` | 树莓派守护盒：摄像头共享采集、Hailo 推理、EACP、隐私合成、事件和离线队列 |
| `local-app-server/` | 云端/本地 API：账号、家庭、设备、摄像头、事件、消息、媒体和 COS |
| `ios-shell/` | 正式 GoHome iOS App、WHEP/WebRTC 播放、原生导航和系统能力 |
| `deploy/cloud-app/` | 云端 API 的不可变版本发布和 PostgreSQL 迁移 |
| `deploy/cloud-media/` | MediaMTX、Coturn、TLS、nginx 和实时媒体部署契约 |
| `docs/` | TestFlight 清单、控制面矩阵、清理清单和实施规格 |
| `research/` | 论文与算法研究资料，不代表产品指标 |

## 文档关系

四份主线文档各自只有一个职责：

1. [`想家了吗-PRD.md`](想家了吗-PRD.md)：产品目标、用户流程、系统边界、数据模型和验收标准。
2. [`想家了吗-Plan.md`](想家了吗-Plan.md)：按 PRD 排列阶段、依赖、优先级和实施顺序。
3. [`想家了吗-Implement.md`](想家了吗-Implement.md)：记录真实实现、部署证据、测试结果和未关闭条件。
4. [`README.md`](README.md)：开发者入口、当前版本基线、目录和最小运行说明。

执行顺序固定为：先改 PRD，再改 Plan，再实现和验收，最后回写 Implement。历史章节保留追溯信息；当前状态以四份文档末尾或最新日期的基线章节为准。

## 开发与验证

安装 Node 依赖后，可运行服务端和发布门禁：

```sh
npm install
npm run test
npm run test:native-server
```

常用专项：

```sh
npm run verify:local-loop
npm run verify:cloud-onboarding
npm run verify:postgres-loop
npm run verify:ios-release
npm run verify:cloud-media
```

盒子部署入口位于 `edge-agent/run.sh` 和 `deploy/edge-agent/`，正式云端部署说明位于 `deploy/cloud-app/README.md` 与 `deploy/cloud-media/README.md`。不要把 `edge-agent/data/`、`edge-agent/logs/`、Xcode `build/`、虚拟环境、模型缓存或 COS 密钥加入代码包。

## 发布前必须补齐

- TestFlight Build 15 的 Apple processing、内测分组和真机安装验收；
- 双摄三模式、前后台、Wi-Fi/蜂窝、断线恢复和 30 分钟长测；
- APNs 生产通知的一次性去重、回执、深链和到达率；
- 真实家庭数据集、猫狗混淆矩阵和分家庭 train/validation/test 隔离；
- 跨品牌 RTSP/ONVIF 兼容清单、安装 SOP、恢复出厂和数据留存演练；
- 参赛队伍、学校、指导教师、联系方式、官方模板和演示视频信息。

## 安全与数据

不要提交或公开家庭视频、老人个人资料、摄像头账号密码、生产数据库、COS 密钥、APNs 私钥、设备令牌或局域网真实地址。盒子本地媒体按环形留存和事件引用保护管理，COS 通过生命周期和孤儿对象对账回收；任何删除必须保留可审计的失败重试记录。
