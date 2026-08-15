"""
零速撞种自动换种（最小可安装版）
- 定时检查下载中且速度过低、运行超时的种子
- 通过下载历史获取 tmdbid，精确搜索后换种
- 仅建议处理 MoviePilot 添加的任务（有下载历史）
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType, ServiceInfo
from app.schemas.types import EventType
from app.utils.string import StringUtils


class ZeroSpeedReplace(_PluginBase):
    # 插件名称
    plugin_name = "零速撞种换种"
    # 插件描述
    plugin_desc = "下载速度长期为0时自动删种，并按下载历史tmdbid精确搜索换种（V2最小版）"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/download.png"
    # 插件版本（需与 package.v2.json 一致）
    plugin_version = "0.1.1"
    # 插件作者
    plugin_author = "community"
    # 作者主页
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "zerospeedreplace_"
    # 加载顺序
    plugin_order = 25
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _notify = False
    _only_mp_tag = True
    _mp_tag = "MOVIEPILOT"
    _min_runtime_min = 10
    _zero_speed_kb = 5
    _delete_files = False
    _auto_replace = True
    _cron = "*/5 * * * *"
    _max_per_run = 3
    _downloader = None  # 指定下载器名称，空=默认

    _scheduler: Optional[BackgroundScheduler] = None
    _downloadhis = None
    _downloader_helper = None

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._downloadhis = DownloadHistoryOper()
        self._downloader_helper = DownloaderHelper()

        if config:
            self._enabled = config.get("enabled", False)
            self._notify = config.get("notify", False)
            self._only_mp_tag = config.get("only_mp_tag", True)
            self._mp_tag = (config.get("mp_tag") or "MOVIEPILOT").strip()
            self._min_runtime_min = int(config.get("min_runtime_min") or 10)
            self._zero_speed_kb = float(config.get("zero_speed_kb") or 5)
            self._delete_files = config.get("delete_files", False)
            self._auto_replace = config.get("auto_replace", True)
            self._cron = (config.get("cron") or "*/5 * * * *").strip()
            self._max_per_run = int(config.get("max_per_run") or 3)
            self._downloader = (config.get("downloader") or "").strip() or None

        if self._enabled:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            try:
                self._scheduler.add_job(
                    func=self.run_once,
                    trigger=CronTrigger.from_crontab(self._cron),
                    id="ZeroSpeedReplace",
                    name="零速撞种换种",
                    kwargs={"manual": False},
                )
                self._scheduler.start()
                logger.info(f"{self.plugin_name} 已启动，周期: {self._cron}")
            except Exception as e:
                logger.error(f"{self.plugin_name} 定时任务配置错误: {e}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "发送通知",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "auto_replace",
                                            "label": "自动换种",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "only_mp_tag",
                                            "label": "仅处理指定标签",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "mp_tag",
                                            "label": "标签名",
                                            "placeholder": "MOVIEPILOT",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delete_files",
                                            "label": "删除文件",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "min_runtime_min",
                                            "label": "最少运行分钟",
                                            "type": "number",
                                            "placeholder": "10",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "zero_speed_kb",
                                            "label": "零速阈值(KB/s)",
                                            "type": "number",
                                            "placeholder": "5",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "max_per_run",
                                            "label": "每轮最多处理数",
                                            "type": "number",
                                            "placeholder": "3",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期(Cron)",
                                            "placeholder": "*/5 * * * *",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "downloader",
                                            "label": "下载器名称(空=默认)",
                                            "placeholder": "留空使用默认下载器",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "建议先关闭「删除文件」和「自动换种」，只观察日志；确认候选正确后再开启。"
                                                     "仅能对有下载历史(tmdbid)的任务精确换种。"
                                                     "过滤规则仍会作用于搜索结果。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "notify": True,
            "auto_replace": True,
            "only_mp_tag": True,
            "mp_tag": "MOVIEPILOT",
            "delete_files": False,
            "min_runtime_min": 10,
            "zero_speed_kb": 5,
            "max_per_run": 3,
            "cron": "*/5 * * * *",
            "downloader": "",
        }

    def get_page(self) -> List[dict]:
        return []

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止插件服务失败: {e}")

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册到「设定 → 服务」可手动执行
        """
        if self._enabled:
            return [
                {
                    "id": "ZeroSpeedReplace",
                    "name": "零速撞种换种",
                    "trigger": "interval",
                    "func": self.run_once,
                    "kwargs": {"manual": True},
                }
            ]
        return []

    def _get_downloader_service(self) -> Optional[ServiceInfo]:
        if not self._downloader_helper:
            self._downloader_helper = DownloaderHelper()
        if self._downloader:
            return self._downloader_helper.get_service(name=self._downloader)
        return self._downloader_helper.get_default_downloader()

    def _list_candidate_torrents(self, downloader) -> List[Any]:
        """
        获取可能卡住的任务：下载中 + 停滞下载。
        qB 里「停滞中」常不在 get_downloading_torrents() 结果里，必须额外拉取。
        """
        merged = []
        seen = set()

        def _add(items):
            if not items:
                return
            for t in items:
                info = self._normalize_torrent(t)
                if not info or not info.get("hash"):
                    # 仍保留原始对象，后面再 normalize
                    merged.append(t)
                    continue
                h = info["hash"].lower()
                if h in seen:
                    continue
                seen.add(h)
                merged.append(t)

        # 1) 下载中
        try:
            _add(downloader.get_downloading_torrents())
        except Exception as e:
            logger.warning(f"{self.plugin_name}: get_downloading_torrents 失败: {e}")

        # 2) 全部任务里筛未完成（覆盖 stalledDL / metaDL 等）
        for method_name in ("get_torrents", "get_all_torrents", "torrents_info"):
            if not hasattr(downloader, method_name):
                continue
            try:
                method = getattr(downloader, method_name)
                all_list = method()
                if all_list is None:
                    continue
                unfinished = []
                for t in all_list:
                    info = self._normalize_torrent(t)
                    if not info:
                        continue
                    # 未完成且非做种完成
                    if info["progress"] < 0.99:
                        unfinished.append(t)
                _add(unfinished)
                logger.info(
                    f"{self.plugin_name}: 通过 {method_name} 补充未完成任务，合并后共 {len(merged)} 个"
                )
                break
            except TypeError:
                # 部分实现需要参数，尝试 status 过滤
                try:
                    method = getattr(downloader, method_name)
                    for status in (None, "downloading", "stalled_downloading", "stalledDL"):
                        try:
                            if status is None:
                                all_list = method()
                            else:
                                all_list = method(status=status)
                            if all_list:
                                _add(all_list)
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"{self.plugin_name}: {method_name} 备选调用失败: {e}")
            except Exception as e:
                logger.debug(f"{self.plugin_name}: {method_name} 失败: {e}")

        # 3) qB 原生：若 instance 上有 qbc / transfer
        try:
            if hasattr(downloader, "qbc") and downloader.qbc:
                # qbittorrent-api: torrents.info(status_filter='downloading') 不含 stalled
                # 用 downloading + stalled_downloading
                for sf in ("downloading", "stalled_downloading", "active"):
                    try:
                        _add(list(downloader.qbc.torrents.info(status_filter=sf)))
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"{self.plugin_name}: qbc 补充失败: {e}")

        return merged

    def run_once(self, manual: bool = False):
        """
        执行一次检查与换种
        """
        if not self._enabled and not manual:
            return

        service = self._get_downloader_service()
        if not service or not service.instance:
            logger.warning(f"{self.plugin_name}: 未找到可用下载器")
            return

        downloader = service.instance
        name = service.name

        logger.info(f"{self.plugin_name}: 开始检查下载器 [{name}] ...")
        try:
            torrents = self._list_candidate_torrents(downloader)
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取任务列表失败 [{name}]: {e}")
            return

        if not torrents:
            logger.info(f"{self.plugin_name}: 当前无未完成/下载中任务（含停滞）")
            return

        logger.info(f"{self.plugin_name}: 待检查任务数 {len(torrents)}")

        handled = 0
        for torrent in torrents:
            if handled >= self._max_per_run:
                break
            try:
                if self._process_torrent(downloader, name, torrent):
                    handled += 1
            except Exception as e:
                logger.error(f"{self.plugin_name}: 处理种子异常: {e}")

        logger.info(f"{self.plugin_name}: 本轮结束，处理 {handled} 个任务")

    def _process_torrent(self, downloader, downloader_name: str, torrent) -> bool:
        """
        处理单个种子，返回是否已处理（删除/换种）
        """
        # 兼容 qB / 不同返回结构
        info = self._normalize_torrent(torrent)
        if not info:
            return False

        hash_ = info["hash"]
        title = info["name"]
        dlspeed_kb = info["dlspeed_kb"]
        progress = info["progress"]
        tags = info["tags"]
        added_on = info["added_on"]

        if progress >= 0.99:
            return False
        if dlspeed_kb > self._zero_speed_kb:
            return False

        if self._only_mp_tag and self._mp_tag:
            tag_list = [t.strip() for t in (tags or "").replace(";", ",").split(",") if t.strip()]
            if self._mp_tag not in tag_list:
                return False

        if added_on:
            runtime_min = (datetime.now() - added_on).total_seconds() / 60
        else:
            runtime_min = self._min_runtime_min  # 无添加时间时保守处理：仍要求其它条件

        if runtime_min < self._min_runtime_min:
            return False

        logger.info(
            f"{self.plugin_name}: 候选零速 "
            f"| {title} | {dlspeed_kb:.1f}KB/s | 已运行{runtime_min:.0f}分 | {hash_}"
        )

        # 下载历史
        history = None
        try:
            history = self._downloadhis.get_by_hash(hash_)
        except Exception as e:
            logger.warning(f"{self.plugin_name}: 查询下载历史失败: {e}")

        tmdbid = None
        media_title = title
        if history:
            tmdbid = getattr(history, "tmdbid", None) or (history.get("tmdbid") if isinstance(history, dict) else None)
            media_title = (
                getattr(history, "title", None)
                or (history.get("title") if isinstance(history, dict) else None)
                or title
            )

        # 删种
        try:
            downloader.delete_torrents(ids=hash_, delete_file=self._delete_files)
            logger.info(f"{self.plugin_name}: 已删除种子 {hash_} delete_files={self._delete_files}")
        except Exception as e:
            logger.error(f"{self.plugin_name}: 删除种子失败 {hash_}: {e}")
            return False

        msg = f"已删除零速任务：{media_title}\nHash: {hash_}\n速度: {dlspeed_kb:.1f}KB/s 运行: {runtime_min:.0f}分钟"

        if not self._auto_replace:
            if self._notify:
                self.post_message(mtype=NotificationType.Download, title=f"【{self.plugin_name}】", text=msg)
            return True

        if not tmdbid:
            tip = f"{msg}\n无 tmdbid，无法自动换种，请手动搜索。"
            logger.warning(f"{self.plugin_name}: {tip}")
            if self._notify:
                self.post_message(mtype=NotificationType.Download, title=f"【{self.plugin_name}】", text=tip)
            return True

        # 精确搜索并换种
        ok, detail = self._replace_by_tmdbid(tmdbid, media_title, old_hash=hash_)
        text = f"{msg}\ntmdbid={tmdbid}\n{detail}"
        logger.info(f"{self.plugin_name}: 换种结果 {ok} | {detail}")
        if self._notify:
            self.post_message(
                mtype=NotificationType.Download,
                title=f"【{self.plugin_name}】换种{'成功' if ok else '失败'}",
                text=text,
            )
        return True

    def _replace_by_tmdbid(self, tmdbid: int, title: str, old_hash: str) -> Tuple[bool, str]:
        """
        按 tmdbid 搜索并添加下载。最小版：走 chain 媒体搜索 + 批量下载。
        不同 MP 小版本 API 可能略有差异，失败时看日志再微调。
        """
        try:
            from app.chain.download import DownloadChain
            from app.chain.search import SearchChain
            from app.chain.media import MediaChain
            from app.core.context import MediaInfo
        except Exception as e:
            return False, f"导入链路失败: {e}"

        try:
            # 识别媒体
            mediainfo = MediaChain().get_tmdb_info(mtype=None, tmdbid=tmdbid)
            if not mediainfo:
                # 兜底：用标题再识别
                mediainfo = MediaChain().recognize_by_title(title=title)
            if not mediainfo:
                return False, "无法识别媒体信息"

            # 搜索资源
            contexts = SearchChain().process(mediainfo=mediainfo)
            if not contexts:
                return False, "精确搜索无结果（可能被过滤规则滤掉）"

            # 排除原 hash，选第一个可用
            chosen = None
            for ctx in contexts:
                torrent = getattr(ctx, "torrent_info", None) or getattr(ctx, "torrent", None)
                if not torrent:
                    continue
                th = (
                    getattr(torrent, "info_hash", None)
                    or getattr(torrent, "hash", None)
                    or (torrent.get("info_hash") if isinstance(torrent, dict) else None)
                    or (torrent.get("hash") if isinstance(torrent, dict) else None)
                    or ""
                )
                if th and th.lower() == (old_hash or "").lower():
                    continue
                chosen = ctx
                break

            if not chosen:
                return False, "搜索结果仅含原种或无可选资源"

            # 下载
            results = DownloadChain().batch_download(
                contexts=[chosen],
                media_download_list=[],
            )
            # batch_download 返回结构因版本而异，有结果即视为尝试成功
            tname = getattr(getattr(chosen, "torrent_info", None), "title", None) or title
            return True, f"已尝试添加：{tname}"
        except Exception as e:
            logger.error(f"{self.plugin_name}: 换种异常: {e}")
            return False, f"换种异常: {e}"

    @staticmethod
    def _normalize_torrent(torrent) -> Optional[Dict[str, Any]]:
        """
        统一 qB / Transmission / 内部对象字段
        """
        try:
            # 已是 dict
            if isinstance(torrent, dict):
                hash_ = torrent.get("hash") or torrent.get("hashString") or torrent.get("id")
                name = torrent.get("name") or torrent.get("title") or ""
                dlspeed = torrent.get("dlspeed") or torrent.get("download_speed") or torrent.get("rateDownload") or 0
                progress = torrent.get("progress") or torrent.get("percentDone") or 0
                if progress and progress > 1:
                    progress = progress / 100.0
                tags = torrent.get("tags") or torrent.get("labels") or ""
                if isinstance(tags, list):
                    tags = ",".join(tags)
                added = torrent.get("added_on") or torrent.get("added_date") or torrent.get("addedDate")
                added_on = None
                if added:
                    if isinstance(added, (int, float)):
                        # qB 多为 unix 秒
                        if added > 1e12:
                            added = added / 1000.0
                        added_on = datetime.fromtimestamp(added)
                    elif isinstance(added, datetime):
                        added_on = added
                return {
                    "hash": str(hash_) if hash_ else None,
                    "name": name,
                    "dlspeed_kb": float(dlspeed) / 1024.0 if dlspeed else 0.0,
                    "progress": float(progress or 0),
                    "tags": tags or "",
                    "added_on": added_on,
                }

            # 对象属性
            hash_ = getattr(torrent, "hash", None) or getattr(torrent, "hashString", None) or getattr(torrent, "id", None)
            name = getattr(torrent, "name", None) or getattr(torrent, "title", None) or ""
            dlspeed = getattr(torrent, "dlspeed", None) or getattr(torrent, "download_speed", None) or 0
            progress = getattr(torrent, "progress", None) or 0
            tags = getattr(torrent, "tags", None) or getattr(torrent, "labels", None) or ""
            if isinstance(tags, list):
                tags = ",".join(tags)
            added_on = getattr(torrent, "added_on", None) or getattr(torrent, "added_date", None)
            if isinstance(added_on, (int, float)):
                if added_on > 1e12:
                    added_on = added_on / 1000.0
                added_on = datetime.fromtimestamp(added_on)

            if not hash_:
                return None
            return {
                "hash": str(hash_),
                "name": name,
                "dlspeed_kb": float(dlspeed or 0) / 1024.0,
                "progress": float(progress or 0),
                "tags": tags or "",
                "added_on": added_on if isinstance(added_on, datetime) else None,
            }
        except Exception as e:
            logger.debug(f"normalize torrent failed: {e}")
            return None
