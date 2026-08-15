# 零速撞种换种（ZeroSpeedReplace）

MoviePilot **V2** 最小可安装插件。

## 功能

- 定时检查下载中任务
- 条件：速度低于阈值（默认 5KB/s）且已运行超过 N 分钟（默认 10）
- 可选：仅处理带指定标签的种子（默认 `MOVIEPILOT`）
- 删除该种子（可选是否删文件）
- 通过**下载历史**取 `tmdbid`，做**精确搜索**后换种（避免标题识别失败）
- 支持通知、每轮处理数量上限

## 安装

### 方式一：第三方插件仓库（推荐）

1. 将本仓库推送到你的 GitHub（保留 `plugins.v2/` 与 `package.v2.json`）
2. MoviePilot → 插件 → 插件市场 → 添加仓库地址：  
   `https://github.com/你的用户名/你的仓库名`
3. 刷新后搜索「零速撞种换种」安装并启用

### 方式二：本地挂载（开发/自用）

Docker 示例：

```yaml
volumes:
  - /path/to/zerospeedreplace-plugin/plugins.v2/zerospeedreplace:/app/app/plugins/zerospeedreplace
environment:
  - PLUGIN_AUTO_RELOAD=true
```

重启或热加载后，在插件列表中启用。

## 配置建议

| 项 | 建议 |
|----|------|
| 启用 | 先开 |
| 自动换种 | 先关，只观察删除候选 |
| 删除文件 | 先关 |
| 最少运行分钟 | 10 |
| 零速阈值 | 5 KB/s |
| 仅处理指定标签 | 开，标签 `MOVIEPILOT` |
| Cron | `*/5 * * * *`（每 5 分钟） |

确认日志里候选正确后，再打开「自动换种」。

## 注意

1. **无下载历史 / 无 tmdbid** 的任务只能删种，无法精确换种。
2. 搜索仍受全局**过滤规则 / 优先级**影响，结果为空时请检查规则。
3. 不同 MoviePilot 小版本中 `SearchChain` / `DownloadChain` / 下载器接口可能略有差异；若换种报错，把日志贴出再改 `_replace_by_tmdbid`。
4. 本插件为社区最小骨架，生产使用前请充分试运行。

## 版本

- `0.1.0` 最小可安装版
