# 构建 BuckyOS PIKG

File Browser 使用新版 `buckyos-tool` 的本地 PIKG 工作流。构建过程会把本地 Docker
镜像完整写入 `.pikg`，不需要先把镜像发布到 Docker Hub 或其它镜像仓库。

## 准备依赖

- Go 1.25
- Node.js 24 和 pnpm 10
- 可用的 Docker daemon
- Deno 2.2 或更高版本
- 新版 `buckyos` 命令（`buckyos-tool`）

如果 `buckyos` 不在 `PATH`，通过 `BUCKYOS_TOOL_PATH` 指向仓库中的启动脚本：

```bash
export BUCKYOS_TOOL_PATH=/path/to/buckyos/src/tools/buckyos-tool/buckyos
```

在本仓库根目录执行：

```bash
python3 build_dapp.py
```

脚本依次构建前端、Linux/amd64 后端和本地镜像
`local/buckyos-filebrowser:0.7.0-amd64`，然后执行：

```bash
buckyos pikg build ./dapp_meta
buckyos pikg pack ./dapp_dist
buckyos pikg info ./dapp_dist/filebrowser-0.7.0.pikg
```

最终产物是 `dapp_dist/filebrowser-0.7.0.pikg`。`dapp_dist` 是由工具管理的构建目录，
不提交到 Git；需要清理时执行：

```bash
buckyos --non-interactive --yes pikg clean ./dapp_meta
```

版本升级时同步修改 `dapp_meta/app.json` 中的 `version`，以及
`dapp_meta/pikg.json` 中的 `pikg_file` 和本地镜像 tag。
