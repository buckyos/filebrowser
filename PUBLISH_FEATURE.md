# 发布功能说明

## 功能描述
在文件/文件夹的右键菜单中添加了一个新的 "publish" 项。点击后会打开一个指定的发布页面，并将当前文件的路径和类型作为参数传递。

## 配置方式

### 方式1: 使用CLI命令配置
```bash
filebrowser config set --branding.publishURL "https://sys.\$current_hostname/publish/pub.html"
```

### 方式2: 在初始化时配置
```bash
filebrowser config init --branding.publishURL "https://sys.\$current_hostname/publish/pub.html"
```

### 方式3: 导出/导入配置文件
在 `config.json` 中设置：
```json
{
  "branding": {
    "publishURL": "https://sys.$current_hostname/publish/pub.html"
  }
}
```

## URL模板说明
- `$current_hostname`: 会被替换为当前的主机名
- 最终URL示例: `https://sys.example.com/publish/pub.html?path=/path/to/file&type=file`

## URL参数说明
- `path`: 选中文件/文件夹的完整路径
- `type`: 项目类型，值为 `file` 或 `folder`

## 前端实现细节
1. **constants.ts**: 添加了 `publishURL` 常量，从后端 `window.FileBrowser.PublishURL` 获取
2. **FileListing.vue**: 
   - 在 `headerButtons` 中添加 `publish` 权限检查（单选时可用）
   - 在右键菜单中添加 "Publish" 项
   - 实现 `publish()` 函数处理发布逻辑
3. **i18n**: 使用现有的 "publish" 翻译

## 后端实现细节
1. **settings/branding.go**: 在 `Branding` 结构体中添加 `PublishURL` 字段
2. **http/static.go**: 在 `handleWithStaticData` 函数中将 `PublishURL` 注入到前端
3. **cmd/config.go**: 添加 `branding.publishURL` 配置选项，支持设置和显示

## 权限检查
发布功能在以下条件下可用：
- 有且仅有一个文件/文件夹被选中

## 使用示例

### 示例1：配置简单URL
```bash
filebrowser config set --branding.publishURL "https://publish.example.com/pub.html"
```
结果：点击文件 `/documents/report.pdf` 会打开
`https://publish.example.com/pub.html?path=/documents/report.pdf&type=file`

### 示例2：配置带主机名的URL
```bash
filebrowser config set --branding.publishURL "https://sys.\$current_hostname/publish/pub.html"
```
如果访问地址是 `file.example.com`，点击文件会打开：
`https://sys.example.com/publish/pub.html?path=/documents/report.pdf&type=file`
