# AGENTS.md

## Role

This repository is maintained as a single-developer robotics workspace. Codex should act as a careful engineering partner: inspect real files, logs, and docs before making claims; keep changes scoped; distinguish written plans, implemented code, and runtime verification.

## Search And Scan Policy

- Do not start with unrestricted full-tree `rg` searches in this repository.
- Prefer scoped searches by directory and source-like file type. This repo may contain model weights, images, bags, build outputs, virtualenvs, caches, generated files, and permission-sensitive paths.
- For algorithm, Flask, ROS, Qt, Android, or script questions, search likely source/config/doc files first:
  - `*.py`, `*.cpp`, `*.cc`, `*.c`, `*.h`, `*.hpp`
  - `*.launch`, `*.xml`, `*.yaml`, `*.yml`, `*.json`
  - `*.sh`, `*.bat`, `*.ps1`, `*.md`
- Exclude `.git`, `.venv`, `venv`, `build`, `install`, `log`, `logs`, caches, image files, model files, bag files, APKs, and other generated artifacts unless the task explicitly needs them.
- If `rg` hangs, hits permissions, or behaves badly under Windows quoting, switch to a PowerShell `Get-ChildItem -Recurse -File` pipeline with explicit extensions and directories.

Example scoped PowerShell search:

```powershell
Get-ChildItem -Recurse -File -Include *.py,*.cpp,*.h,*.hpp,*.launch,*.xml,*.yaml,*.yml,*.json,*.sh,*.bat,*.md |
  Where-Object { $_.FullName -notmatch '\\(\.git|\.venv|venv|build|install|log|logs|__pycache__)\\' } |
  Select-String -Pattern 'keyword'
```

Example scoped `rg` search:

```powershell
rg -n "keyword" `
  -g "*.py" -g "*.cpp" -g "*.h" -g "*.hpp" -g "*.launch" -g "*.xml" -g "*.yaml" -g "*.yml" -g "*.json" -g "*.sh" -g "*.bat" -g "*.md" `
  -g "!**/.git/**" -g "!**/.venv/**" -g "!**/venv/**" -g "!**/build/**" -g "!**/install/**" -g "!**/log/**" -g "!**/logs/**" `
  -g "!**/*.pt" -g "!**/*.pth" -g "!**/*.onnx" -g "!**/*.bag" -g "!**/*.db3" -g "!**/*.png" -g "!**/*.jpg" -g "!**/*.jpeg" -g "!**/*.apk"
```

## Windows And Encoding

- On Windows, be careful with PowerShell quoting, environment variables, redirection, and semicolon-separated arguments.
- For complex Android SDK, Gradle, rosjava, or environment-heavy commands, prefer checked-in scripts or temporary `.bat` scripts when appropriate.
- If Chinese Markdown appears corrupted in PowerShell output, treat it as possible console mojibake first. Confirm with a UTF-8-safe read before reporting corruption or patching localized text.

## Documentation And Architecture

- For docs-only architecture questions, start with the documentation set before reopening code.
- Prefer updating existing canonical docs in place over creating new parallel notes.
- Keep Android, Qt/PC, xtark, and RK3568 responsibilities separate unless the user explicitly asks to connect them.
- Do not treat old `PROJECT_MEMORY.md` content as authoritative. Use it only as a legacy index.

## Git And Review

- Before judging a staged feature complete, inspect both `git diff` and `git diff --cached`.
- Do not revert or overwrite user changes unless explicitly requested.
- For review requests, lead with concrete findings and file/line references.

## Safety

- Do not write secrets, passwords, tokens, private keys, or Codex credentials into the repository.
- Be cautious with remote deployment, device control, robot motion, destructive filesystem commands, and Git history changes. Ask before risky actions.
