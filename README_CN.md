# 磁盘清理工具

这是一个安全的磁盘清理工具，可以帮助您清理磁盘上的旧文件，同时确保系统文件的安全。

## 功能特点

- 安全扫描：自动跳过系统关键目录
- 智能识别：基于文件访问时间识别长期未使用的文件
- 空间统计：显示可释放空间大小
- 安全确认：在执行清理前需要用户确认
- 详细日志：记录所有清理操作

## 使用要求

- Python 3.6 或更高版本
- Windows 操作系统
- 管理员权限（用于访问某些受保护的目录）

## 安装步骤

1. 克隆或下载此仓库
2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

## 使用方法

1. 以管理员身份运行程序：
   ```
   python disk_cleaner.py
   ```
2. 输入要清理的目录路径（例如 `C:\`）
3. 输入要清理的文件年龄（多少天未访问的文件）
4. 确认清理操作

## 安全说明

- 程序会自动跳过系统关键目录
- 清理前会显示详细的文件列表和大小信息
- 所有操作都需要用户确认
- 建议在清理前备份重要数据

## 注意事项

- 请勿在系统运行关键任务时执行清理
- 建议先在非系统盘测试使用
- 如果遇到权限问题，请确保以管理员身份运行 