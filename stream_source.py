#!/usr/bin/env python3
"""stream_source.py —— 按网址直接抓直播音频（不经过扬声器，所以不会把你听的别的声音一起抓进来）

目前支持：
  · B 站直播间（房间号或 live.bilibili.com 链接）——走官方 getRoomPlayInfo 拿 FLV/HLS 地址
  · 任何 ffmpeg 能打开的媒体地址（m3u8 / flv / http 直链…）

对外接口和 live_translate.LoopbackCapture 一致：rate / channels / q / start() / stop() / dead
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SR = 16000
CHUNK_BYTES = 3200           # 0.1 s 的 16k 单声道 int16
LIVE_API = "https://api.live.bilibili.com"

HERE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent


def _find_up(name: str) -> Path | None:
    for base in (HERE, *list(HERE.parents)[:3]):
        p = base / name
        if p.is_file():
            return p
    return None


def ffmpeg_path() -> str:
    """优先用随身带的 ffmpeg.exe（便携包就靠它），找不到才用 PATH 里的"""
    env = os.environ.get("LIVE_TRANSLATE_FFMPEG", "").strip()
    cands = [Path(env)] if env else []
    cands += [_find_up("ffmpeg.exe"), HERE / "tools" / "ffmpeg.exe"]
    for c in cands:
        if c and c.is_file():
            return str(c)
    return "ffmpeg"


def _api(url: str, referer: str | None = None, timeout: int = 25) -> dict:
    h = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def bilibili_room_id(text: str) -> str | None:
    """从链接或纯数字里取出房间号"""
    text = text.strip()
    if re.fullmatch(r"\d{2,10}", text):
        return text
    m = re.search(r"live\.bilibili\.com/(?:blanc/|h5/)?(\d+)", text)
    return m.group(1) if m else None


def resolve_bilibili_audio(text: str) -> tuple[str, dict]:
    """房间号/链接 → (可直接给 ffmpeg 的音频流地址, 需要的 headers)"""
    rid_in = bilibili_room_id(text)
    if not rid_in:
        raise RuntimeError(f"看不出是哪个直播间：{text}")
    init = _api(f"{LIVE_API}/room/v1/Room/room_init?id={rid_in}",
                referer="https://live.bilibili.com/")
    d = init.get("data") or {}
    rid = d.get("room_id", rid_in)
    if d.get("live_status") != 1:
        raise RuntimeError(f"房间 {rid} 现在没有开播")
    ref = f"https://live.bilibili.com/{rid}"
    info = _api(f"{LIVE_API}/xlive/web-room/v2/index/getRoomPlayInfo?room_id={rid}"
                f"&protocol=0,1&format=0,1,2&codec=0,1&qn=10000&platform=web&ptype=8"
                f"&dolby=5&panorama=1", referer=ref)
    pi = (info.get("data") or {}).get("playurl_info") or {}
    if not pi:
        raise RuntimeError("拿不到播放地址（可能要登录、或该房间不允许第三方拉流）")
    # 优先级：FLV+avc（最省事） > HLS+ts > HLS+fmp4
    want = [("http_stream", "flv", "avc"), ("http_hls", "ts", "avc"), ("http_hls", "fmp4", "avc")]
    cands: list[tuple[int, str]] = []
    for st in pi["playurl"]["stream"]:
        for f in st["format"]:
            for c in f["codec"]:
                key = (st["protocol_name"], f["format_name"], c["codec_name"])
                if key in want:
                    for u in c["url_info"]:
                        cands.append((want.index(key), u["host"] + c["base_url"] + u["extra"]))
    if not cands:
        raise RuntimeError("没有可用的 avc 流（也许只有 hevc）")
    cands.sort(key=lambda x: x[0])
    return cands[0][1], {"Referer": ref, "User-Agent": UA}


def resolve(url: str) -> tuple[str, dict]:
    """任意地址 → (ffmpeg 地址, headers)"""
    if bilibili_room_id(url) and ("bilibili" in url or re.fullmatch(r"\d{2,10}", url.strip())):
        return resolve_bilibili_audio(url)
    return url, {"User-Agent": UA}


class StreamCapture:
    """ffmpeg 拉流 → 16k 单声道 int16 塞进 self.q；断了会自动重解析地址重连"""

    def __init__(self, url: str, verbose: bool = True, retries: int = 10):
        self.url_arg = url
        self.rate, self.channels = SR, 1
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self.dead = False
        self.info = {"name": url}
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._retries = retries
        self.url, self.headers = resolve(url)      # 先解析一次：房间没开播之类的问题立刻报出来
        if verbose:
            print(f"[stream] {url}\n[stream] 实际地址 {self.url[:90]}…")

    # ── 拉流进程 ──
    def _spawn(self):
        hdr = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-headers", hdr,
               "-fflags", "nobuffer", "-flags", "low_delay",
               "-analyzeduration", "500000", "-probesize", "500000",
               "-i", self.url, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      bufsize=0, creationflags=flags)   # 别弹黑色控制台

    def _read_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            try:
                piece = self._proc.stdout.read(n - len(buf))
            except Exception:
                break
            if not piece:
                break
            buf += piece
        return buf

    def _reader(self):
        fails = 0
        while not self._stop.is_set():
            data = self._read_exact(CHUNK_BYTES)
            if self._stop.is_set():
                break
            if data:
                fails = 0
                if len(data) % 2:                     # 16bit 对齐
                    data = data[:-1]
                arr = np.frombuffer(data, dtype=np.int16).reshape(-1, 1)
                try:
                    self.q.put_nowait(arr)
                except queue.Full:
                    pass
                continue
            # 没数据了：要么直播断了，要么地址过期
            err = ""
            try:
                err = (self._proc.stderr.read() or b"").decode("utf-8", "ignore")[-200:]
            except Exception:
                pass
            try:
                self._proc.kill()
            except Exception:
                pass
            if self._stop.is_set():
                break
            fails += 1
            if fails > self._retries:
                print(f"[stream] 连续 {self._retries} 次都拉不到流，放弃。最后错误：{err.strip()[:120]}")
                self.dead = True
                return
            print(f"[stream] 流断了，1.5 s 后重连（第 {fails} 次）… {err.strip()[:100]}")
            time.sleep(1.5)
            try:                                      # 重新解析（B 站地址会过期）
                self.url, self.headers = resolve(self.url_arg)
            except Exception as e:
                print(f"[stream] 重解析失败：{e}")
            try:
                self._spawn()
            except Exception as e:
                self.dead = True
                print(f"[stream] 重启 ffmpeg 失败：{e}")
                return

    def start(self):
        self._spawn()
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()
        self._thread = t

    def stop(self):
        self._stop.set()
        try:
            if self._proc:
                self._proc.kill()
        except Exception:
            pass
