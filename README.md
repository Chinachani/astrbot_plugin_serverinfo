# astrbot_plugin_serverinfo

用于查看服务器状态与插件启用情况。

当前服务器信息包含：
- CPU 占用率
- 系统内存占用
- AstrBot 进程内存占用
- 主机/平台/Python/PID/负载/磁盘等

## 指令
- `/serverinfo` 或 `/serverinfo info`：服务器信息
- `/serverinfo plugins`：插件状态（启用/未启用）
- `/serverinfo all`：全部信息
- `服务器信息`：中文免前缀命令（也兼容 `/服务器信息`）
- `插件状态`：中文免前缀命令（也兼容 `/插件状态`）

## 说明
- 服务器运行时长为**本插件启动后**的时长。
- 磁盘信息为当前工作目录所在分区。
