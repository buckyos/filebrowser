# 构建 BuckyOS PIKG

File Browser 是纯 Docker 类型的 BuckyOS DApp，使用新版 `buckyos-tool` 的本地 PIKG
工作流。`image/Dockerfile` 在容器内完成前端和 Go 后端编译，构建过程会把本地 Docker
镜像完整写入 `.pikg`，不需要生成 system native App 分包，也不需要先把镜像发布到
Docker Hub 或其它镜像仓库。

## 准备依赖

- 可用的 Docker daemon
- Python 3.10 或更高版本
- Deno 2.2 或更高版本
- 新版 `buckyos` 命令（`buckyos-tool`）

如果 `buckyos` 不在 `PATH`，通过 `BUCKYOS_TOOL_PATH` 指向仓库中的启动脚本：

```bash
export BUCKYOS_TOOL_PATH=/path/to/buckyos/src/tools/buckyos-tool/buckyos
```

在本仓库根目录执行：

```bash
python3 build_pikg.py
```

脚本通过 `image/Dockerfile` 构造 Linux/amd64 本地镜像
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

## GitHub Release

在 GitHub 仓库的 **Actions → Release File Browser PIKG → Run workflow** 手工触发发布。
工作流会从 `dapp_meta` 读取版本和产物名，构造并校验 PIKG，上传 workflow artifact，
再以 DApp 版本创建 Git tag/Release 并附加 `.pikg` 文件。该流程不需要身份文件、
Docker Registry 凭据或旧版 `buckycli`。
