"""
零速撞种自动换种
参考 leG09/MoviePilot-Plugins 的 qboptimizer：
- get_torrents() 取全部任务（含 stalledDL）
- 状态 downloading / stalledDL
- 删种优先 qbc.torrents_delete
- onlyonce 用 BackgroundScheduler date 触发（与 qboptimizer 一致）
- 周期任务用 get_service + CronTrigger
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType, ServiceInfo


class ZeroSpeedReplace(_PluginBase):
    plugin_name = "零速撞种换种"
    plugin_desc = "下载速度长期为0时自动删种，并按下载历史tmdbid精确搜索换种"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/download.png"
    plugin_version = "0.2.2"
    plugin_author = "community"
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    plugin_config_prefix = "zerospeedreplace_"
    plugin_order = 25
    auth_level = 1

    _enabled = False
    _notify = False
    _onlyonce = False
    _only_mp_tag = True
    _mp_tag = "MOVIEPILOT"
    _min_runtime_min = 10
    _zero_speed_kb = 5
    _delete_files = False
    _auto_replace = True
    _cron = "*/5 * * * *"
    _max_per_run = 3
    _downloader = None
    _blacklist_hours = 24  # 已删 hash 在此小时内不再选中

    _scheduler = None
    _downloadhis = None
    _downloader_helper = None

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._downloadhis = DownloadHistoryOper()
        self._downloader_helper = DownloaderHelper()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._notify = bool(config.get("notify"))
            self._onlyonce = bool(config.get("onlyonce"))
            self._only_mp_tag = bool(config.get("only_mp_tag", True))
            self._mp_tag = (config.get("mp_tag") or "MOVIEPILOT").strip()
            self._min_runtime_min = int(config.get("min_runtime_min") or 10)
            self._zero_speed_kb = float(config.get("zero_speed_kb") or 5)
            self._delete_files = bool(config.get("delete_files"))
            self._auto_replace = bool(config.get("auto_replace", True))
            self._cron = (config.get("cron") or "*/5 * * * *").strip()
            self._max_per_run = int(config.get("max_per_run") or 3)
            self._downloader = (config.get("downloader") or "").strip() or None

        if self._onlyonce:
            logger.info(f"{self.plugin_name}: 准备立即运行一次...")
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            run_time = datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3)
            self._scheduler.add_job(
                func=self.run_once,
                trigger="date",
                run_date=run_time,
                name=f"{self.plugin_name}-once",
            )
            self._onlyonce = False
            cfg = dict(config or {})
            cfg.update({
                "enabled": self._enabled,
                "notify": self._notify,
                "onlyonce": False,
                "only_mp_tag": self._only_mp_tag,
                "mp_tag": self._mp_tag,
                "min_runtime_min": self._min_runtime_min,
                "zero_speed_kb": self._zero_speed_kb,
                "delete_files": self._delete_files,
                "auto_replace": self._auto_replace,
                "cron": self._cron,
                "max_per_run": self._max_per_run,
                "downloader": self._downloader or "",
            })
            self.update_config(cfg)
            if self._scheduler.get_jobs():
                self._scheduler.start()
                logger.info(f"{self.plugin_name}: 立即任务已调度，约3秒后执行")
            else:
                logger.warning(f"{self.plugin_name}: 立即任务调度失败")
        elif self._enabled:
            logger.info(
                f"{self.plugin_name}: 已启用，周期 {self._cron}，"
                f"等待系统定时服务；也可勾选「立即运行一次」后保存"
            )

    def get_state(self) -> bool:
        return bool(self._enabled and self._cron)

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
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "onlyonce", "label": "立即运行一次"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "notify", "label": "发送通知"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "auto_replace", "label": "自动换种"}}]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VSwitch", "props": {"model": "only_mp_tag", "label": "仅处理指定标签"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VTextField", "props": {"model": "mp_tag", "label": "标签名", "placeholder": "MOVIEPILOT"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VSwitch", "props": {"model": "delete_files", "label": "删除文件"}}]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VTextField", "props": {"model": "min_runtime_min", "label": "最少运行分钟", "type": "number"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VTextField", "props": {"model": "zero_speed_kb", "label": "零速阈值KB/s", "type": "number"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VTextField", "props": {"model": "max_per_run", "label": "每轮最多处理", "type": "number"}}]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VTextField", "props": {"model": "cron", "label": "Cron", "placeholder": "*/5 * * * *"}}]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12}, "content": [
                                {"component": "VTextField", "props": {"model": "downloader", "label": "下载器名称(空=默认)", "placeholder": "留空使用默认下载器"}}]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12}, "content": [
                                {"component": "VAlert", "props": {
                                    "type": "info", "variant": "tonal",
                                    "text": "测试：勾选「立即运行一次」后保存，约3秒应出现「开始检查」。逻辑对齐QB种子优化：含stalledDL，get_torrents拉全量。建议先关删除文件。",
                                }}]},
                        ],
                    },
                ],
            }
        ], {
            "enabled": False, "onlyonce": False, "notify": True, "auto_replace": True,
            "only_mp_tag": True, "mp_tag": "MOVIEPILOT", "delete_files": False,
            "min_runtime_min": 10, "zero_speed_kb": 5, "max_per_run": 3,
            "cron": "*/5 * * * *", "downloader": "",
        }

    def get_page(self) -> List[dict]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if self.get_state():
            try:
                trigger = CronTrigger.from_crontab(self._cron)
            except Exception as e:
                logger.error(f"{self.plugin_name}: Cron无效 {self._cron}: {e}")
                trigger = CronTrigger.from_crontab("*/5 * * * *")
            return [{
                "id": "ZeroSpeedReplace",
                "name": "零速撞种换种服务",
                "trigger": trigger,
                "func": self.run_once,
                "kwargs": {},
            }]
        return []

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception as e:
            logger.error(f"{self.plugin_name}: 停止调度器失败: {e}")

    def _get_downloader_service(self) -> Optional[ServiceInfo]:
        if not self._downloader_helper:
            self._downloader_helper = DownloaderHelper()
        if self._downloader:
            return self._downloader_helper.get_service(name=self._downloader)
        if hasattr(self._downloader_helper, "get_default_downloader"):
            return self._downloader_helper.get_default_downloader()
        return None

    def _fetch_torrents(self, downloader_obj) -> List[Any]:
        torrents = []
        try:
            result = downloader_obj.get_torrents()
            if isinstance(result, tuple):
                torrents, error = result
                if error:
                    logger.warning(f"{self.plugin_name}: get_torrents 错误: {error}")
            elif isinstance(result, list):
                torrents = result
            else:
                torrents = result or []
        except Exception as e:
            logger.error(f"{self.plugin_name}: get_torrents 失败: {e}")
            try:
                torrents = downloader_obj.get_downloading_torrents() or []
            except Exception as e2:
                logger.error(f"{self.plugin_name}: get_downloading_torrents 失败: {e2}")
        return list(torrents or [])

    def _torrent_state(self, torrent) -> str:
        state = getattr(torrent, "state", None) or getattr(torrent, "status", None) or ""
        if hasattr(state, "value"):
            state = state.value
        return str(state or "").lower()

    def _torrent_speed_kb(self, torrent) -> float:
        dlspeed = getattr(torrent, "dlspeed", None)
        if dlspeed is None:
            dlspeed = getattr(torrent, "download_speed", None) or 0
        try:
            return float(dlspeed) / 1024.0
        except Exception:
            return 0.0

    def _torrent_progress(self, torrent) -> float:
        progress = getattr(torrent, "progress", None)
        if progress is None:
            progress = getattr(torrent, "percentDone", 0) or 0
        try:
            p = float(progress)
            return p / 100.0 if p > 1 else p
        except Exception:
            return 0.0

    def _torrent_added_on(self, torrent) -> Optional[datetime]:
        added = getattr(torrent, "added_on", None) or getattr(torrent, "added_date", None)
        if added is None:
            return None
        try:
            if isinstance(added, datetime):
                return added
            added = float(added)
            if added > 1e12:
                added /= 1000.0
            return datetime.fromtimestamp(added)
        except Exception:
            return None

    def _torrent_tags(self, torrent) -> str:
        tags = getattr(torrent, "tags", None) or getattr(torrent, "labels", None) or ""
        if isinstance(tags, list):
            return ",".join(str(t) for t in tags)
        return str(tags)

    def _delete_torrent(self, downloader_obj, torrent_hash: str, name: str) -> bool:
        try:
            if hasattr(downloader_obj, "qbc") and downloader_obj.qbc:
                downloader_obj.qbc.torrents_delete(
                    delete_files=bool(self._delete_files),
                    torrent_hashes=torrent_hash,
                )
                logger.info(f"{self.plugin_name}: 经 qB API 删除成功: {name}")
                return True
        except Exception as e:
            logger.warning(f"{self.plugin_name}: qB API 删除失败，回退: {e}")
        try:
            downloader_obj.delete_torrents(delete_file=self._delete_files, ids=[torrent_hash])
            logger.info(f"{self.plugin_name}: 经封装方法删除: {name}")
            return True
        except Exception as e:
            logger.error(f"{self.plugin_name}: 删除失败 {name}: {e}")
            return False

    def run_once(self):
        logger.info(f"{self.plugin_name}: ====== 开始检查 ======")
        service = self._get_downloader_service()
        if not service or not getattr(service, "instance", None):
            logger.warning(f"{self.plugin_name}: 未找到可用下载器")
            return

        downloader_obj = service.instance
        downloader_name = getattr(service, "name", "unknown")
        logger.info(f"{self.plugin_name}: 使用下载器 [{downloader_name}]")

        torrents = self._fetch_torrents(downloader_obj)
        logger.info(f"{self.plugin_name}: 获取到任务数 {len(torrents)}")
        if not torrents:
            logger.info(f"{self.plugin_name}: 无任务可检查")
            return

        handled = 0
        for torrent in torrents:
            if handled >= self._max_per_run:
                break
            try:
                if self._process_one(downloader_obj, torrent):
                    handled += 1
            except Exception as e:
                logger.error(f"{self.plugin_name}: 处理异常: {e}")

        logger.info(f"{self.plugin_name}: ====== 结束，处理 {handled} 个 ======")

    def _process_one(self, downloader_obj, torrent) -> bool:
        name = getattr(torrent, "name", "") or ""
        torrent_hash = getattr(torrent, "hash", None) or getattr(torrent, "hashString", None)
        if not torrent_hash:
            return False

        state = self._torrent_state(torrent)
        if state not in ("downloading", "stalleddl", "stalled_downloading", "metadl"):
            return False

        if self._torrent_progress(torrent) >= 0.99:
            return False

        speed_kb = self._torrent_speed_kb(torrent)
        if speed_kb > self._zero_speed_kb:
            return False

        if self._only_mp_tag and self._mp_tag:
            tags = self._torrent_tags(torrent)
            tag_list = [t.strip() for t in tags.replace(";", ",").split(",") if t.strip()]
            if self._mp_tag not in tag_list:
                return False

        added_on = self._torrent_added_on(torrent)
        if added_on:
            runtime_min = (datetime.now() - added_on.replace(tzinfo=None)).total_seconds() / 60
        else:
            runtime_min = float(self._min_runtime_min)

        if runtime_min < self._min_runtime_min:
            return False

        logger.info(
            f"{self.plugin_name}: 候选零速 | {name} | state={state} | "
            f"{speed_kb:.1f}KB/s | 运行{runtime_min:.0f}分 | {torrent_hash}"
        )

        history = None
        try:
            history = self._downloadhis.get_by_hash(torrent_hash)
        except Exception as e:
            logger.warning(f"{self.plugin_name}: 查历史失败: {e}")

        tmdbid = getattr(history, "tmdbid", None) if history else None
        media_title = (getattr(history, "title", None) if history else None) or name

        if not self._delete_torrent(downloader_obj, str(torrent_hash), name):
            return False

        # 防止下次换种又选回这个 hash
        self._add_blacklist(str(torrent_hash))

        msg = (
            f"已删除零速任务：{media_title}\n"
            f"状态:{state} 速度:{speed_kb:.1f}KB/s 运行:{runtime_min:.0f}分钟\n"
            f"Hash:{torrent_hash}"
        )

        if not self._auto_replace:
            if self._notify:
                self.post_message(mtype=NotificationType.Download, title=f"【{self.plugin_name}】", text=msg)
            return True

        if not tmdbid:
            logger.warning(f"{self.plugin_name}: 无 tmdbid，将回退标题搜索换种")

        ok, detail = self._replace_by_tmdbid(tmdbid, media_title, str(torrent_hash), torrent_name=name)
        logger.info(f"{self.plugin_name}: 换种结果 ok={ok} | {detail}")
        if self._notify:
            self.post_message(
                mtype=NotificationType.Download,
                title=f"【{self.plugin_name}】换种{'成功' if ok else '失败'}",
                text=f"{msg}\ntmdbid={tmdbid}\n{detail}",
            )
        return True

    def _blacklist_path(self):
        return self.get_data_path() / "deleted_hashes.json"

    def _load_blacklist(self) -> dict:
        """hash -> expire_ts"""
        import json, time
        path = self._blacklist_path()
        try:
            if path.exists():
                data = json.loads(path.read_text() or "{}")
                now = time.time()
                # 清理过期
                data = {k: v for k, v in data.items() if float(v) > now}
                return data
        except Exception as e:
            logger.debug(f"{self.plugin_name}: 读黑名单失败: {e}")
        return {}

    def _save_blacklist(self, data: dict):
        import json
        try:
            path = self._blacklist_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"{self.plugin_name}: 写黑名单失败: {e}")

    def _add_blacklist(self, torrent_hash: str):
        import time
        if not torrent_hash:
            return
        data = self._load_blacklist()
        expire = time.time() + float(self._blacklist_hours) * 3600
        data[torrent_hash.lower()] = expire
        self._save_blacklist(data)
        logger.info(f"{self.plugin_name}: 已加入黑名单 {torrent_hash} ({self._blacklist_hours}h)")

    def _is_blacklisted(self, torrent_hash: str) -> bool:
        if not torrent_hash:
            return False
        data = self._load_blacklist()
        return torrent_hash.lower() in data

    def _extract_keyword(self, torrent_name: str) -> str:

        """从种子名提取搜索关键词（对齐 qboptimizer）"""
        import re
        name = torrent_name or ""
        patterns = [
            r"\b(1080p|720p|480p|2160p|4K|UHD)\b",
            r"\b(BluRay|BDRip|DVDRip|WEBRip|WEB-DL|HDTV)\b",
            r"\b(x264|x265|H\.?264|H\.?265|HEVC)\b",
            r"\b(AAC|AC3|DTS|FLAC|DDP5\.?1|Atmos)\b",
            r"\[.*?\]",
            r"\(.*?\)",
            r"-\w+$",
        ]
        for p in patterns:
            name = re.sub(p, " ", name, flags=re.IGNORECASE)
        name = re.sub(r"[.\-_]+", " ", name)
        name = " ".join(name.split())
        return name.strip() or torrent_name

    def _replace_by_tmdbid(self, tmdbid, title: str, old_hash: str, torrent_name: str = "") -> Tuple[bool, str]:
        """
        换种策略（对齐 qboptimizer）：
        1) 有 tmdbid 则尽量用媒体识别后精确搜
        2) 失败则用种子标题关键词 search_by_title
        3) 排除原 hash，按做种数选最佳，download_single
        """
        try:
            from app.chain.download import DownloadChain
            from app.chain.search import SearchChain
            from app.chain.media import MediaChain
            from app.core.context import MediaInfo, Context
            from app.core.metainfo import MetaInfo
        except Exception as e:
            return False, f"导入链路失败: {e}"

        search_chain = SearchChain()
        download_chain = DownloadChain()
        media_chain = MediaChain()
        contexts = []
        mediainfo = None

        # --- 路径1：tmdbid ---
        if tmdbid:
            try:
                try:
                    mediainfo = media_chain.get_tmdb_info(mtype=None, tmdbid=int(tmdbid))
                except TypeError:
                    # 部分版本签名不同
                    mediainfo = media_chain.get_tmdb_info(tmdbid=int(tmdbid))
                except Exception as e:
                    logger.warning(f"{self.plugin_name}: get_tmdb_info 失败: {e}")
                if mediainfo:
                    logger.info(f"{self.plugin_name}: 已用 tmdbid={tmdbid} 识别媒体")
                    try:
                        contexts = search_chain.process(mediainfo=mediainfo) or []
                    except Exception as e:
                        logger.warning(f"{self.plugin_name}: SearchChain.process 失败: {e}")
            except Exception as e:
                logger.warning(f"{self.plugin_name}: tmdbid 路径失败: {e}")

        # --- 路径2：MetaInfo 识别 ---
        if not contexts:
            try:
                meta = MetaInfo(title or torrent_name)
                mediainfo = media_chain.recognize_by_meta(meta)
                if mediainfo:
                    logger.info(f"{self.plugin_name}: MetaInfo 识别成功: {getattr(mediainfo, 'title', '')}")
                    contexts = search_chain.process(mediainfo=mediainfo) or []
            except Exception as e:
                logger.warning(f"{self.plugin_name}: MetaInfo 路径失败: {e}")

        # --- 路径3：标题关键词搜索（qboptimizer 主路径）---
        if not contexts:
            keyword = self._extract_keyword(torrent_name or title)
            logger.info(f"{self.plugin_name}: 回退标题搜索关键词: {keyword}")
            try:
                for page in range(2):
                    page_results = search_chain.search_by_title(title=keyword, page=page) or []
                    if not page_results:
                        break
                    contexts.extend(page_results)
            except Exception as e:
                logger.error(f"{self.plugin_name}: search_by_title 失败: {e}")

        if not contexts:
            return False, "搜索无结果（tmdbid/标题均无）"

        # 排除原 hash，按 seeders 选最佳
        def _seeders(ctx) -> int:
            ti = getattr(ctx, "torrent_info", None)
            if not ti:
                return 0
            try:
                return int(getattr(ti, "seeders", 0) or 0)
            except Exception:
                return 0

        blacklist = self._load_blacklist()
        candidates = []
        for ctx in contexts:
            ti = getattr(ctx, "torrent_info", None)
            if not ti:
                continue
            th = getattr(ti, "info_hash", None) or getattr(ti, "hash", None) or ""
            th_l = str(th).lower() if th else ""
            if th_l and th_l == (old_hash or "").lower():
                logger.info(f"{self.plugin_name}: 跳过原 hash: {th_l}")
                continue
            if th_l and th_l in blacklist:
                logger.info(f"{self.plugin_name}: 跳过黑名单 hash: {th_l}")
                continue
            candidates.append(ctx)

        if not candidates:
            return False, f"共{len(contexts)}条结果但均被排除（同hash或无torrent_info）"

        candidates.sort(key=_seeders, reverse=True)
        chosen = candidates[0]
        ti = chosen.torrent_info
        logger.info(
            f"{self.plugin_name}: 选中替代种 seeders={getattr(ti, 'seeders', 0)} "
            f"site={getattr(ti, 'site_name', '')} title={getattr(ti, 'title', '')}"
        )

        # 补齐 media_info
        media_info = getattr(chosen, "media_info", None) or mediainfo
        meta_info = getattr(chosen, "meta_info", None)
        if not media_info:
            media_info = MediaInfo()
            media_info.title = getattr(ti, "title", None) or title

        if not meta_info:
            try:
                meta_info = MetaInfo(getattr(ti, "title", None) or title)
            except Exception:
                meta_info = None

        context = Context(meta_info=meta_info, media_info=media_info, torrent_info=ti)
        try:
            download_id = download_chain.download_single(context=context, username="admin")
        except TypeError:
            # 兼容不同签名
            download_id = download_chain.download_single(context=context)

        if download_id:
            return True, f"已添加下载: {getattr(ti, 'title', title)} (id={download_id})"
        return False, f"download_single 返回空: {getattr(ti, 'title', title)}"
