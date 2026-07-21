# AGENTS.md

## 角色

这是一个由单人维护的机器人工作区。Codex 应作为谨慎的工程搭档：先检查真实文件、日志和文档再下结论；保持改动范围收敛；明确区分“方案已写”“代码已实现”和“运行已验证”。

## 搜索与扫描规则

- 不要一开始就在整个仓库执行不受限制的 `rg` 搜索。
- 优先按目录和源文件类型缩小范围。仓库可能包含模型权重、图片、bag、构建产物、虚拟环境、缓存、生成文件及权限敏感路径。
- 遇到算法、Flask、ROS、Qt、Android 或脚本问题，先搜索最可能相关的源码、配置和文档：
  - `*.py`, `*.cpp`, `*.cc`, `*.c`, `*.h`, `*.hpp`
  - `*.launch`, `*.xml`, `*.yaml`, `*.yml`, `*.json`
  - `*.sh`, `*.bat`, `*.ps1`, `*.md`
- 除非任务明确需要，否则排除 `.git`、`.venv`、`venv`、`build`、`install`、`log`、`logs`、缓存、图片、模型文件、bag、APK 和其他生成产物。
- 若 `rg` 卡住、遇到权限错误，或受 Windows 引号影响而行为异常，改用带明确目录和扩展名的 PowerShell `Get-ChildItem -Recurse -File` 管道。

按范围搜索的 PowerShell 示例：

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.cpp,*.h,*.hpp,*.launch,*.xml,*.yaml,*.yml,*.json,*.sh,*.bat,*.md |
  Where-Object { $_.FullName -notmatch '\\(\.git|\.venv|venv|build|install|log|logs|__pycache__)\\' } |
  Select-String -Pattern 'keyword'
```

按范围搜索的 `rg` 示例：

```powershell
rg -n "keyword" `
  -g "*.py" -g "*.cpp" -g "*.h" -g "*.hpp" -g "*.launch" -g "*.xml" -g "*.yaml" -g "*.yml" -g "*.json" -g "*.sh" -g "*.bat" -g "*.md" `
  -g "!**/.git/**" -g "!**/.venv/**" -g "!**/venv/**" -g "!**/build/**" -g "!**/install/**" -g "!**/log/**" -g "!**/logs/**" `
  -g "!**/*.pt" -g "!**/*.pth" -g "!**/*.onnx" -g "!**/*.bag" -g "!**/*.db3" -g "!**/*.png" -g "!**/*.jpg" -g "!**/*.jpeg" -g "!**/*.apk"
```

## Windows 与编码

- 在 Windows 上，要留意 PowerShell 的引号、环境变量、重定向和分号分隔参数。
- 对复杂的 Android SDK、Gradle、rosjava 或环境依赖较重的命令，优先使用仓库现有脚本；必要时使用临时 `.bat` 脚本。
- 若中文 Markdown 在 PowerShell 输出中显示异常，先将其视为控制台乱码的可能性；报告损坏或修改本地化文本前，必须用 UTF-8 安全方式复读确认。

## 远程访问

- WSL 不是项目的运行、构建、DDS、RViz、部署或验收环境。不要引导用户在 WSL 中运行任一产品线。
- 当路径可用时，Codex 可选用 `Codex -> WSL -> SSH -> Jetson/VMware` 作为网络透传。WSL 透传成功不构成运行验收；证据必须来自真实 Jetson、xtark 小车或 VMware 目标机。
- 按目标机文档指定的入口，使用仓库提供的 Windows/Git Bash 辅助工具、原生 SSH 或 plink。不要另造基于 WSL 的日常工作流。
- 检查源码、脚本、文档和中文文本时，使用 Git Bash 或其他 UTF-8 安全读取器。不要用 PowerShell `Get-Content` 的输出判断中文文本是否损坏。
- 本地 Shell 脚本语法检查使用 Git Bash `bash -n`。本地语法检查不等于 Jetson/VMware 运行验收。

## 文档与架构

- 仅涉及文档的架构问题，先阅读文档集，不要一开始就重新翻代码。
- 优先就地更新已有权威文档，不要新建并行的说明笔记。
- 除非用户明确要求连接它们，否则保持 Android、Qt/PC、xtark 和 RK3568 的职责边界分离。

## Git 与审查

- 判断暂存功能是否完成前，同时检查 `git diff` 和 `git diff --cached`。
- 除非用户明确要求，否则不得回退或覆盖用户的修改。
- 对审查请求，先给出带文件/行号的具体发现。

## 安全

- 不得将密钥、密码、token、私钥或 Codex 凭据写入仓库。
- 对远程部署、设备控制、机器人运动、破坏性文件命令和 Git 历史改动保持谨慎；执行有风险的操作前先确认。
