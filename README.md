# 巨潮公告批量下载器

基于 Tkinter 的桌面程序，用于按股票代码、时间范围、公告分类等条件批量检索并下载巨潮资讯公告。

## 环境要求

- Windows 10/11
- Python 3.11+

## 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 运行程序

```powershell
.\.venv\Scripts\python.exe -m app.main
```

## 主要功能

- 代码/简称/拼音联想与多选
- 板块、行业、公告分类多条件筛选
- 开始/结束日期日历选择
- 快捷区间下拉（1个月、半年、1年、2年）
- 检索结果勾选下载，单次最多 50 份
- 独立的 PDF 表格提取工具（提取后导出同名 Excel）

## PDF表格提取工具（第二功能）

在主界面点击“PDF表格提取”打开独立窗口。

支持能力：

- 源目录默认 downloads
- 目标目录默认与源目录一致
- 递归处理源目录全部子目录中的 PDF
- 进度日志滚动显示（成功/失败/跳过）
- 导出文件与 PDF 同名（.xlsx）
- 同名冲突自动加后缀避免覆盖

说明：

- 当前版本仅支持文字型 PDF（非扫描图片 PDF）
- 每个识别到的表格会按标题写入独立工作表

## 打包为 Windows 可执行文件

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name cninfo_downloader --distpath . --workpath build --specpath . app/main.py
```

打包完成后，启动文件为：

- cninfo_downloader/cninfo_downloader.exe

## 目录说明

- app: 源代码
- app/storage: 主数据缓存
- downloads: 下载结果目录（程序运行后自动创建）
- scripts: 运行与打包辅助脚本
