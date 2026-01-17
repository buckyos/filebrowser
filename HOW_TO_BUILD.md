以下说明适用于linux机器

## 准备依赖
- go task: https://taskfile.dev/docs/installation
- nodejs and pnpm: https://nodejs.org/zh-cn/download
- go: https://go.dev/doc/install
- 正确安装官方docker，需要buildx-plugin
- 执行`docker buildx create --use`
- `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`启用多平台支持
- 准备正确版本的buckycli程序和身份信息，打包环节需要用到

## 修改appdoc文件
修改`./publish/app.doc.json`文件：
- pkg_name: app包名，同一owner的包名必须不同
- version：版本号。推荐使用符合semver规则的三位数字版本号

## 编译-打包-发布流程
1. 在根目录下执行python3 build_dapp.py进行全平台编译
   > 可以配置环境变量BUCKYOS_BUILD_ROOT，指定编译结果的输出目录。默认为`/opt/buckyosci`
   
   > 编译结果输出到`${BUCKYOS_BUILD_ROOT}/app_build/${pkg_name}${version}`
2. 在根目录执行python3 pack_dapp.py进行打包操作
   > 可以通过环境变量BUCKYCLI_PATH指定buckycli程序的位置，默认为`/opt/buckyos/bin/buckycli/buckycli`
   > 正确的身份文件必须放置在~/.buckycli目录下

   > 打包结果输出到`${BUCKYOS_BUILD_ROOT}/app/${pkg_name}${version}`
