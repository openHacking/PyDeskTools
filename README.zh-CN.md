<p align="center">
  <img src="src/pydesktools/assets/logo.png" width="128" alt="PyDeskTools 图标">
</p>

<h1 align="center">PyDeskTools</h1>

<p align="center"><strong>把常用图片和 JSON 工具装进一个私密、离线的桌面应用。</strong></p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="https://github.com/openHacking/PyDeskTools/releases">下载</a> ·
  <a href="docs/plugin-sdk.md">开发插件</a>
</p>

<p align="center">
  <a href="https://github.com/openHacking/PyDeskTools/releases"><img alt="GitHub Release" src="https://img.shields.io/github/v/release/openHacking/PyDeskTools?include_prereleases&sort=semver"></a>
  <a href="https://github.com/openHacking/PyDeskTools/actions/workflows/ci.yml"><img alt="CI 状态" src="https://github.com/openHacking/PyDeskTools/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/github/license/openHacking/PyDeskTools"></a>
  <img alt="macOS arm64、Windows x64、Linux x64" src="https://img.shields.io/badge/platform-macOS%20arm64%20%7C%20Windows%20x64%20%7C%20Linux%20x64-2f81f7">
  <img alt="离线运行" src="https://img.shields.io/badge/runtime-offline-238636">
</p>

![PyDeskTools 主界面](docs/assets/pydesktools-home.png)

PyDeskTools 让高频、琐碎的文件处理变得快速而安静：无需账号，运行时不发起网络请求，
文件始终留在你的设备上。0.1.0 包含两个完整工具，以及可继续扩展的隔离插件架构。

如果它帮你节省了时间，欢迎点一个 Star，让更多人看到它。

## 现在可以做什么

| 工具 | 能力 |
| --- | --- |
| **图片压缩** | 批量压缩 JPEG、PNG、WebP；预览结果、调整尺寸、保留元数据，并只重试失败项目。 |
| **JSON 工具** | 格式化和压缩 JSON，不丢失大整数或小数精度；支持 UTF-8 导入、复制和完整导出。 |

你可以从侧边栏、搜索、命令面板、文件选择器或拖放开始。应用内置中英文、明暗主题、
插件生命周期管理，以及独立的本地数据目录。

## 下载 v0.1.0

PyDeskTools 0.1.0 是实验性 Pre-release。请只从
[官方 GitHub Releases 页面](https://github.com/openHacking/PyDeskTools/releases)下载。

| 平台 | 文件 | 支持与可信状态 |
| --- | --- | --- |
| Apple 芯片 Mac，macOS 14+ | `PyDeskTools-0.1.0-macos-arm64.dmg` | Developer ID 签名的测试版，未做 Apple 公证。拖入“应用程序”后，首次启动可能需要在“隐私与安全性”中选择“仍要打开”。 |
| Windows 10/11 x64 | `PyDeskTools-0.1.0-windows-x64-unsigned.exe` | **未签名 Beta。** SmartScreen 可能提示风险，请先核对 SHA-256 和构建来源。 |
| Linux x64 | `PyDeskTools-0.1.0-linux-x86_64.AppImage` | 首轮支持与 Ubuntu 22.04 兼容的 X11/XWayland 桌面，尚未认证原生 Wayland。 |

Linux 下载后需要添加执行权限：

```sh
chmod +x PyDeskTools-0.1.0-linux-x86_64.AppImage
./PyDeskTools-0.1.0-linux-x86_64.AppImage
```

每个 Release 都包含 `SHA256SUMS.txt`、各平台构建清单、第三方许可证和 GitHub
artifact attestation。验证构建来源：

```sh
gh attestation verify PyDeskTools-0.1.0-平台文件名 -R openHacking/PyDeskTools
```

## 为什么值得信赖

- **离线优先：** 内置工具及其 Python 依赖均随安装包提供，图片和文档不会离开设备。
- **清晰的插件边界：** 插件在独立 Python 进程和环境中运行，实现依赖与生命周期隔离；
  但这不是操作系统安全沙箱，第三方插件仍拥有当前用户权限，安装前必须明确同意。
- **可审计发布：** 各平台在对应原生系统上构建，固定依赖来源和哈希，使用不可变标签、
  最小 CI 权限和公开构建证明。
- **许可证透明：** 应用使用 MIT 许可证，每个安装包同时携带依赖许可证和 notices。
- **不夸大范围：** 0.1.0 尚无在线插件市场、自动更新、截图工具、Intel Mac 或 ARM
  Windows/Linux 安装包。

更精确的边界请查看[安全策略](SECURITY.md)、[架构文档](docs/architecture.md)和
[已实现 API](docs/implemented-api.md)。

## 从源码开发

开发环境要求 Python 3.13+、Tcl/Tk 9 和 PyDeskUI 0.2.x；安装包中的插件工作进程
使用另一套固定的 CPython 3.13。环境配置见[开发指南](docs/development.md)，构建与签名
见[发布指南](docs/build-release.md)。

```sh
python -m pip install -e ../PyDeskUI \
  -e packages/pydesktools-sdk \
  -e packages/pydesktools-runtime \
  -e plugins/json-tools \
  -e plugins/image-compressor \
  -e '.[dev]'
python scripts/build_bundles.py --target macos-arm64
python -m pytest
python -m pydesktools
```

欢迎贡献。提交改动前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[行为准则](CODE_OF_CONDUCT.md)。
