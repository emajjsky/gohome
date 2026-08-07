# GoHome 仓库清理清单

盘点日期：2026-08-07
适用分支：`main`
目的：区分生产源码、运行时生成物、用户资料和仍需产品决策的历史入口，避免误删或把副本重新带入交付包。

## 已确认的生产边界

- 正式盒子代码：`edge-agent/`。生产部署只取版本化源码、配置模板、systemd 单元和必要模型，不取本机虚拟环境、数据、日志、缓存或临时验证脚本。
- 正式 iOS 代码：`ios-shell/`。正式工程是 `ios-shell/GoHomeShell.xcodeproj`，Bundle ID 为 `com.gohome.family`。
- 正式云端代码：`local-app-server/` 及其部署目录。生产发布由云端部署清单决定，不从仓库根目录旧 Web 页面推断入口。
- 产品契约和问题记录：根目录 PRD、Plan、Implement、`issue.md` 与 `docs/`。

## 本机生成物

以下目录已经由 `.gitignore` 排除，不应提交；清理时只能在确认没有正在运行的任务后按目录删除：

| 路径 | 性质 | 处理规则 |
| --- | --- | --- |
| `node_modules/` | Node 依赖 | 由 lockfile 重建，不提交 |
| `edge-agent/.venv/`、`edge-agent/.venv-pi/` | Python 依赖环境 | 由部署脚本重建，不提交 |
| `edge-agent/data/`、`edge-agent/logs/` | 盒子运行数据和日志 | 不能当垃圾删除，按留存策略和审计流程处理 |
| `edge-agent/**/__pycache__/`、`*.pyc` | Python 缓存 | 可在停止相关进程后删除 |
| `ios-shell/build/`、根目录 `build/` | Xcode/工具构建产物 | 可在没有归档或验收任务运行时删除；不能作为源码依据 |
| `ios-shell/**/xcuserdata/`、`*.xcuserstate` | 本机 Xcode 状态 | 可删除，不影响工程 |

当前盘点没有发现上述构建目录被 Git 跟踪。删除 `edge-agent/data/`、日志或 COS 对象不属于本清单，必须走 `GH-013` 的容量、留存和对象对账流程。

## 必须保留的未跟踪资料

当前工作区中的 `hailo8/`、`research/`、`image_assets/`、`report-evidence/` 以及根目录产品文档副本是用户提供的参考资料、研究证据或设计资产。它们没有进入本次提交，也不能因为“未跟踪”被自动删除。是否纳入正式资料库，另行建立来源、授权、哈希和版本记录。

## 待产品收口的历史入口

根目录的 `app-shell.html`、`watch.html`、`monitor.html`、`detection.html`、`rules.html` 等旧 Web 试点页面仍属于 Git 历史内容。它们不是正式 iOS 工程，也不能在未经部署引用审计、云端路由审计和用户验收的情况下直接删除；按 `GH-040`、`GH-044` 的唯一入口收口计划处理。

## 清理门槛

1. 先生成本地、盒子和云端文件清单及 SHA-256，确认目标没有独有源码、用户资料、运行数据或正式归档。
2. 只删除已确认的构建产物、缓存和本机状态文件；不删除运行数据、媒体证据、模型或用户资料。
3. 删除后重新生成工程、运行静态入口契约、Python/Swift/Node 测试，并确认部署包不含副本和旧入口。
4. 任何生产数据回收必须同时记录留存状态、引用关系、失败重试和审计墓碑，不能用文件名匹配直接删除。

## 发布输入门禁

- 云端 `build-release.sh` 只从当前已提交树生成归档，并同时输出归档 SHA-256
  和逐文件 SHA-256 清单；清单中的测试、iOS、盒子、研究和备份路径会在构建时拒绝。
- 盒子 `deploy/edge-agent/build-production-payload.sh` 是唯一设备包生成入口，
  `deploy-to-pi.sh` 只负责传输和健康检查。它只从当前提交生成设备代码包。`yolo11n.pt` 和
  `yolov8n.pt` 是唯一允许从本机运行时输入复制的模型文件；`.env`、数据库、日志、
  `data/`、`logs/` 和虚拟环境始终不进入代码包。
- 盒子同步对生产代码使用 `rsync --delete-delay` 收敛旧文件，但明确排除运行数据和
  配置；设备包在同步前写入提交号与逐文件 SHA-256 清单，便于从设备反查实际代码版本。
- 不能只凭本地脚本通过就视为交付完成；Pi、生产云和 TestFlight 仍需分别记录版本、
  清单哈希和健康检查结果。
