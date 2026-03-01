# -*- coding: utf-8 -*-
import os
import platform
import socket
import sys
import time
import asyncio
from datetime import timedelta
from typing import Optional, Tuple

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:
    import psutil
except Exception:
    psutil = None


def _format_bytes(n: int) -> str:
    size = float(max(0, n))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    return f"{size:.1f}{units[idx]}"


class ServerInfoPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._started_at = time.time()
        self._last_cpu_stat: Optional[Tuple[int, int]] = None

    def _uptime_text(self) -> str:
        sec = int(max(0, time.time() - self._started_at))
        return str(timedelta(seconds=sec))

    async def _server_info_text(self) -> str:
        lines = []
        lines.append("服务器信息：")
        lines.append(f"- 主机名：{socket.gethostname()}")
        lines.append(f"- 平台：{platform.platform()}")
        lines.append(f"- Python：{sys.version.split()[0]}")
        lines.append(f"- 进程 PID：{os.getpid()}")
        lines.append(f"- 运行时长（本插件）：{self._uptime_text()}")
        lines.append(f"- CPU 核心数：{os.cpu_count() or 0}")
        cpu_percent = await self._get_cpu_percent()
        if cpu_percent is not None:
            lines.append(f"- CPU 占用：{cpu_percent:.1f}%")
        mem_used, mem_total = self._get_system_memory_bytes()
        if mem_used is not None and mem_total:
            lines.append(
                f"- 内存占用：{_format_bytes(mem_used)} / {_format_bytes(mem_total)} ({(mem_used / mem_total) * 100:.1f}%)"
            )
        proc_rss = self._get_process_rss_bytes()
        if proc_rss is not None:
            lines.append(f"- AstrBot 进程内存：{_format_bytes(proc_rss)}")
        if hasattr(os, "getloadavg"):
            try:
                l1, l5, l15 = os.getloadavg()
                lines.append(f"- 系统负载：{l1:.2f} / {l5:.2f} / {l15:.2f}")
            except Exception:
                pass
        try:
            st = os.statvfs(".")
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            used = max(0, total - free)
            lines.append(f"- 磁盘(当前目录)：已用 {_format_bytes(used)} / 总计 {_format_bytes(total)}")
        except Exception:
            pass
        return "\n".join(lines)

    async def _get_cpu_percent(self) -> Optional[float]:
        if psutil is not None:
            try:
                return float(psutil.cpu_percent(interval=0.1))
            except Exception:
                pass
        # Linux fallback: read /proc/stat and compute delta with previous sample.
        def _read_cpu_stat() -> Optional[Tuple[int, int]]:
            with open("/proc/stat", "r", encoding="utf-8") as f:
                first = f.readline().strip()
            parts = first.split()
            if len(parts) < 5 or parts[0] != "cpu":
                return None
            values = [int(x) for x in parts[1:]]
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return total, idle

        try:
            curr = _read_cpu_stat()
            if curr is None:
                return None
            if self._last_cpu_stat is None:
                # 首次调用给一个即时值
                await asyncio.sleep(0.1)
                next_stat = _read_cpu_stat()
                if next_stat is None:
                    return None
                prev_total, prev_idle = curr
                total, idle = next_stat
                self._last_cpu_stat = next_stat
            else:
                prev_total, prev_idle = self._last_cpu_stat
                total, idle = curr
                self._last_cpu_stat = curr
            d_total = total - prev_total
            d_idle = idle - prev_idle
            if d_total <= 0:
                return None
            used = max(0, d_total - d_idle)
            return (used / d_total) * 100.0
        except Exception:
            return None

    def _get_system_memory_bytes(self) -> Tuple[Optional[int], Optional[int]]:
        if psutil is not None:
            try:
                vm = psutil.virtual_memory()
                return int(vm.used), int(vm.total)
            except Exception:
                pass
        # Linux fallback: parse /proc/meminfo.
        try:
            mem_total_kb = None
            mem_avail_kb = None
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail_kb = int(line.split()[1])
            if mem_total_kb is None or mem_avail_kb is None:
                return None, None
            total = mem_total_kb * 1024
            used = max(0, (mem_total_kb - mem_avail_kb) * 1024)
            return used, total
        except Exception:
            return None, None

    def _get_process_rss_bytes(self) -> Optional[int]:
        if psutil is not None:
            try:
                return int(psutil.Process(os.getpid()).memory_info().rss)
            except Exception:
                pass
        # Linux fallback: parse /proc/self/status VmRSS.
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except Exception:
            return None
        return None

    def _plugins_info_text(self) -> str:
        stars = list(self.context.get_all_stars())
        enabled = [s for s in stars if getattr(s, "activated", False)]
        disabled = [s for s in stars if not getattr(s, "activated", False)]
        lines = []
        lines.append(f"插件状态：启用 {len(enabled)} / 总计 {len(stars)}")
        lines.append("已启用插件：")
        if enabled:
            for s in sorted(enabled, key=lambda x: str(getattr(x, "name", "")).lower()):
                lines.append(f"- {s.name} ({s.version})")
        else:
            lines.append("- 无")
        if disabled:
            lines.append("未启用插件：")
            for s in sorted(disabled, key=lambda x: str(getattr(x, "name", "")).lower()):
                lines.append(f"- {s.name} ({s.version})")
        return "\n".join(lines)

    def _get_event_text(self, event: AstrMessageEvent) -> str:
        text = getattr(event, "message_str", "") or ""
        if isinstance(text, str):
            return text.strip()
        try:
            msg = event.get_message_str()
            return str(msg or "").strip()
        except Exception:
            return ""

    @filter.command("serverinfo")
    async def serverinfo(self, event: AstrMessageEvent, args: str = ""):
        """查看服务器信息与插件状态。"""
        sub = (args or "").strip().lower()
        if sub in {"", "info", "server", "服务器"}:
            yield event.plain_result(await self._server_info_text())
            return
        if sub in {"plugins", "plugin", "pl", "插件"}:
            yield event.plain_result(self._plugins_info_text())
            return
        if sub in {"all", "full"}:
            yield event.plain_result((await self._server_info_text()) + "\n\n" + self._plugins_info_text())
            return
        yield event.plain_result("用法：/serverinfo [info|plugins|all]")

    @filter.command("服务器信息")
    async def serverinfo_cn(self, event: AstrMessageEvent):
        """中文快捷命令：查看服务器信息。"""
        yield event.plain_result(await self._server_info_text())

    @filter.command("插件状态")
    async def plugins_cn(self, event: AstrMessageEvent):
        """中文快捷命令：查看插件启用状态。"""
        yield event.plain_result(self._plugins_info_text())

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def plain_cn_commands(self, event: AstrMessageEvent):
        """中文免前缀命令：支持直接发送“服务器信息/插件状态”"""
        text = self._get_event_text(event)
        if not text:
            return
        if text.startswith("/"):
            text = text[1:].strip()
        if text == "服务器信息":
            yield event.plain_result(await self._server_info_text())
            return
        if text == "插件状态":
            yield event.plain_result(self._plugins_info_text())
            return
