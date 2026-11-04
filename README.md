# Telegram 投稿机器人

私聊里接收投稿，管理员审核后发到频道。支持文字和多媒体、实名或匿名、标签、拒绝理由、封禁和按通过数升级。

机器人只处理私聊中的命令、消息和按钮。需要 Python >= 3.10。

## 功能

- 投稿：文字、图片、视频、音频、文件；一次最多 10 个媒体。
- 审核：通过后选择标签并发布；用预设理由或自定义理由拒绝。结果会通知投稿者。
- 用户：封禁和解封、投稿统计、按通过数划分等级。
- 标签：启动时写入默认标签，管理员可再添加；发布时统计使用次数。

## 安装

```bash
pip install -r requirements.txt
```

运行依赖是 `python-telegram-bot ~=22.0` 和 `SQLAlchemy ~=2.0`。

## 配置

复制示例后再填写。`config.json` 已在 `.gitignore` 中，不要把真实 Token 提交到仓库。

```bash
cp config.example.json config.json
```

`config.example.json` 包含导航、客服、页脚、默认标签和默认拒绝理由。最小可用配置如下，这是合法 JSON，不能写注释：

```json
{
  "bot_token": "123456:replace-with-the-token-from-botfather",
  "admin_ids": [123456789],
  "channel_id": "@your_channel",
  "channel_name": "示例频道",
  "database_path": "bot.db",
  "bot_info": {"name": "投稿机器人"},
  "submission_rules": "请确保内容真实、合法，并与频道主题相关。",
  "default_tags": [{"name": "分享", "emoji": "📢"}],
  "default_reject_reasons": ["内容与频道主题不符"]
}
```

环境变量优先于文件：

- `BOT_TOKEN` 覆盖 `bot_token`。文件里可以保留 `YOUR_BOT_TOKEN_HERE`。
- `DATABASE_PATH` 覆盖 `database_path`。

相对路径按配置文件所在目录解析，启动时转成绝对路径。未设置时使用项目目录下的 `bot.db`，不随当前工作目录变化。只设置 `BOT_TOKEN`、不创建 `config.json` 也可以启动，此时没有管理员和频道，审核与发布不会工作。

启动时检查 Token：形如 `数字:至少30位字母数字或_-`。占位符和非法格式会直接退出，日志里不会打印 Token。

| 配置项 | 说明 |
|--------|------|
| `bot_token` | BotFather 发放的 Token |
| `admin_ids` | 管理员 Telegram 用户 ID。数据库里 `role` 为 `admin` 或 `reviewer` 的用户也有审核权限 |
| `channel_id` | 发布频道，如 `@your_channel`。机器人必须是该频道管理员 |
| `channel_name` | 通知投稿者时显示的频道名称 |
| `database_path` | SQLite 文件路径 |
| `max_pending_submissions` | 每人待审核上限，默认 3，`0` 为不限制 |
| `submission_cooldown_seconds` | 两次投稿的最短间隔，默认 60 秒，`0` 为不限制 |
| `backup_enabled` | 是否每天自动备份，默认开启。环境变量 `BACKUP_ENABLED` |
| `backup_keep` | 保留最近几份备份，默认 7 |
| `backup_hour_utc` | 每天备份的 UTC 小时，默认 3 |
| `backup_dir` | 备份目录。未设置时在数据库旁边的 `backups/`。环境变量 `BACKUP_DIR` |
| `bot_info.name` | `/start` 欢迎语中的机器人名称 |
| `navigation_links` | 主菜单链接。`enabled: false` 时显示占位按钮 |
| `customer_service` | 主菜单上的客服链接 |
| `submission_rules` | 投稿说明，按纯文本显示 |
| `footer` | 频道正文末尾的文字，`enabled: true` 时生效 |
| `default_tags` | 首次启动写入的标签 |
| `default_reject_reasons` | 首次启动写入的拒绝理由 |

用户 ID 可向 [@userinfobot](https://t.me/userinfobot) 发送任意消息获取。多个管理员写成 `[123, 456]`。

## 运行

在项目目录中启动。`bot.py` 直接导入同目录下的 `config`、`database`、`handlers` 和 `utils`，项目没有单独的安装入口：

```bash
python bot.py
```

用绝对路径 `python /path/to/bot.py` 也可以。不需要设置 `PYTHONPATH`。按 Ctrl+C 停止。

把机器人设为频道管理员，并允许它发消息。`admin_ids` 里的管理员需要先私聊过机器人，否则 Telegram 不投递审核通知。

## 命令

### 用户

| 命令 | 说明 |
|------|------|
| `/start` | 主菜单，并登记用户 |
| `/submit` | 开始投稿 |
| `/mystats` | 查看自己的投稿统计和等级 |
| `/my` | 查看最近投稿和状态 |
| `/cancel` | 取消当前投稿草稿或待输入的封禁/拒绝理由 |
| `/help` | 帮助。管理员会多看到管理命令 |

### 管理员

| 命令 | 说明 |
|------|------|
| `/queue` | 待审核队列，并给出第一篇的通过/拒绝按钮。审核员可用 |
| `/stats` | 用户数、投稿数、通过率和处于「发布中」的数量。审核员可用 |
| `/stuck` | 列出卡在「发布中」的投稿。仅管理员 |
| `/resolve <编号> pending` | 退回待审核。仅管理员 |
| `/resolve <编号> approved` | 标成已通过且不再发送。仅管理员 |
| `/backup` | 立刻备份数据库并把文件发到当前私聊。仅管理员 |
| `/setrole <用户ID> reviewer\|admin\|user` | 设置数据库角色。只有 `admin_ids` 里的人能用 |
| `/ban <用户ID> [理由]` | 封禁。对方还没用过机器人时也会建档并封禁。仅管理员 |
| `/unban <用户ID>` | 解封 |
| `/userinfo <用户ID>` | 查看资料、统计，并可按钮封禁或解封 |
| `/addtag <名称> [emoji]` | 添加标签。仅管理员 |
| `/addreason <理由>` | 添加拒绝理由。仅管理员 |

配置中的管理员，以及数据库角色为 `admin` 或 `reviewer` 的用户，不能被封禁。

审核员（`reviewer`）可以审核和查看队列。封禁、标签、拒绝理由、备份和 `/resolve` 只给配置管理员，以及数据库角色为 `admin` 的用户。新投稿会通知 `admin_ids`，也会通知数据库里的管理员和审核员。

同一篇投稿被一位管理员处理后，其他管理员收到的审核消息会改成「已由某人处理」，并去掉按钮。

每位用户默认最多 3 篇待审核投稿，两次投稿至少间隔 60 秒。把 `max_pending_submissions` 或 `submission_cooldown_seconds` 设为 `0` 可关闭对应限制，也可用环境变量 `MAX_PENDING_SUBMISSIONS` 和 `SUBMISSION_COOLDOWN_SECONDS` 覆盖。

## 审核流程

1. 新投稿发到每位配置管理员的私聊，按钮只有「通过」和「拒绝」。
2. **通过**：有标签时先勾选，再点「确认标签」发布到 `channel_id`。没有标签则直接发布。发布成功后通知投稿者。
3. **拒绝**：列出数据库里的预设理由，或点「自定义理由」后发送一段文字。`/cancel` 放弃这次输入。拒绝原因会发给投稿者。
4. 审核中的标签选择按投稿编号分开保存。处理完一篇，或发送 `/start`、`/cancel`，不会清掉其他稿件已选的标签。

这些按钮只接受管理员。旧消息上的「添加标签」「编辑后发布」「查看统计」「投稿记录」已经没有对应功能，点击后只会提示按钮已停用。

## 实名和匿名

两种投稿都会在 `submissions.user_id` 保存投稿者 ID，用来统计、封禁，以及把审核结果发回本人。

- **实名**：审核通知里包含姓名链接和用户 ID。
- **匿名**：审核通知和 `/queue` 只显示「匿名用户」，不显示姓名和 ID。

发到频道的正文只有标签、投稿内容和页脚，两种模式都不附带作者。匿名隐藏的是审核通知中的身份，不是数据库里的关联。能打开 SQLite 文件的人仍然可以查出 `user_id`。

## 投稿限制

| 项目 | 限制 |
|------|------|
| 媒体数量 | 最多 10 个 |
| 纯文字 | 最多 4096 个字符 |
| 带媒体的说明 | 最多 1024 个字符。先写长文字再加媒体时，完成投稿也会按 1024 拒绝 |

支持的类型：文字、图片、视频、音频（音乐文件）、普通文件。图片和视频可以组成相册；音频只和音频一组，文件只和文件一组，都不会被丢掉。

语音消息、视频留言、贴纸和其他类型会收到「暂不支持」的回复，不会记入投稿。

发布时如果标签和页脚把正文顶过频道限制，超出的部分会再发一条消息，而不是让整次发布失败。

## 安全

- **审核权限**：通过、选标签、确认发布、拒绝、预设理由、自定义理由和返回审核，审核员也可以做。封禁、标签、备份和恢复卡住的稿件只允许管理员。发布和拒绝在写数据库前再查一次。
- **审核可见性**：审核通知保留投稿里的链接格式，并单独列出每一个 URL，避免「点这里」把真实地址藏起来。
- **封禁**：选择投稿方式、接收内容、写入投稿之前都会检查。封禁用户即使还留着旧按钮也不能提交。`create_submission` 对未登记或已封禁用户直接拒绝写入。
- **避免重复发布**：通过时先用条件更新把状态从 `pending` 改成 `publishing`，只有一次更新会成功。频道发送失败会退回 `pending`。发送成功才改成 `approved`，并通过数只加一次。拒绝同样只对仍是 `pending` 的稿件生效。
- **消息格式**：姓名、正文、拒绝和封禁理由等用户内容以 HTML 发送并转义，避免破坏消息格式。

用户内容里的文字、媒体 file_id 和审核记录都在本地 SQLite 中。请限制数据库文件的访问权限。

### 卡在「发布中」

进程在占用稿件之后、写完最终状态之前退出时，该行会停在 `publishing`。`/stats` 里会出现「发布中」。程序不会在启动时自动改回 `pending`，因为频道里可能已经有这条消息，自动退回会造成再发一次。

管理员先看 `/stuck`，再到频道核对，然后：

- 频道里没有这条稿件：`/resolve 编号 pending`，退回待审核。
- 频道里已经有消息：`/resolve 编号 approved`。这会记一次通过，并且不会再发。

若一次发布分成多段，前一段已经成功、后一段失败，状态会退回 `pending`，重试可能把前一段再发一遍。同时点「通过」不会这样：第二个人拿不到这行。

### 备份与部署

每天按 `backup_hour_utc`（默认 UTC 3 点）用 SQLite 的 backup API 写一份数据库副本，只保留最近 `backup_keep` 份（默认 7）。`/backup` 会再做一份并把文件发到私聊。

Docker 把数据库放在卷里：

```bash
export BOT_TOKEN="123456:replace-with-the-token-from-botfather"
docker compose up -d --build
```

`docker-compose.yml` 使用卷 `/data`，`DATABASE_PATH=/data/bot.db`。systemd 示例在 `deploy/telegram-submission-bot.service`。Token 和数据库路径放在 `/etc/telegram-submission-bot.env`，不要写进 unit 文件。

## 等级

等级由累计通过数决定。

| 等级 | 称号 | 通过数 |
|------|------|--------|
| 0 | 🌱 新手 | 0 |
| 1 | 🌿 入门 | 5 |
| 2 | 🌲 活跃 | 15 |
| 3 | ⭐ 热心 | 30 |
| 4 | ⭐⭐ 资深 | 50 |
| 5 | 🌟 专家 | 100 |
| 6 | 🌟🌟 大师 | 200 |
| 7 | 💫 传奇 | 500 |
| 8 | 👑 史诗 | 1000 |
| 9 | 👑👑 神话 | 2000 |
| 10 | 🏆 至尊 | 5000 |

## 测试和持续集成

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

`requirements-dev.txt` 包含运行依赖，以及 `pytest ~=8.3` 和 `ruff ~=0.17`。GitHub Actions（`.github/workflows/ci.yml`）在推送和拉取请求上用 Python 3.10 与 3.12 运行这两项检查。

Dependabot（`.github/dependabot.yml`）每周检查 pip 依赖和 GitHub Actions。

## 常见问题

**发不到频道。** 把机器人加为频道管理员，并打开发送消息权限。同时确认 `channel_id`。

**管理员收不到新投稿。** 核对 `admin_ids`。该用户需要先私聊机器人。

**有人还没 `/start` 就想封禁。** `/ban <用户ID> [理由]` 会先建立用户再封禁。

**审核时看不到「点这里」后面的网址。** 审核通知会保留原有链接格式，并在下面列出全部 URL。

## 许可证

[MIT License](LICENSE)。
