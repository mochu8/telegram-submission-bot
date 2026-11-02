# Telegram 专业级投稿机器人

一个功能完整的 Telegram 投稿机器人，适合高流量曝光频道使用。

## ✨ 功能特点

### 投稿功能
- 📝 支持文字、图片、视频、音频投稿
- 🖼️ 支持多图投稿（最多10张）
- 🕶️ 支持匿名投稿
- 📊 投稿状态追踪

### 审核功能
- ✅ 一键通过并发布到频道
- ❌ 预设拒绝理由 + 自定义理由
- 🏷️ 添加标签分类
- 📬 自动通知投稿者审核结果

### 用户管理
- 👥 用户等级系统（根据通过数自动升级）
- 🔒 封禁/解封功能
- 📈 投稿统计查询

### 标签系统
- 🏷️ 预设标签选择
- ➕ 管理员可添加新标签
- 📊 标签使用次数统计

## 📋 快速开始

需要 Python >= 3.10。

### 1. 获取 Bot Token

1. 在 Telegram 中找 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`
3. 按提示设置机器人名称和用户名
4. 复制获得的 Token

### 2. 获取你的用户 ID

1. 在 Telegram 中找 [@userinfobot](https://t.me/userinfobot)
2. 发送任意消息
3. 复制返回的数字 ID

### 3. 配置机器人

复制示例配置后再填写，不要把真实 Token 提交到仓库：

```bash
cp config.example.json config.json
```

`config.json`：

```json
{
  "bot_token": "123456:replace-with-the-token-from-botfather",
  "admin_ids": [123456789],
  "channel_id": "@your_channel",
  "channel_name": "示例频道",
  "database_path": "bot.db"
}
```

也可以不把 Token 写进文件，启动前设置环境变量。`BOT_TOKEN` 会覆盖配置文件里的 `bot_token`。`DATABASE_PATH` 会覆盖 `database_path`；相对路径按配置文件所在目录解析，并保存为绝对路径。

```bash
export BOT_TOKEN="123456:replace-with-the-token-from-botfather"
export DATABASE_PATH="/var/lib/submission-bot/bot.db"
```

启动时会检查 Token 格式。机器人只处理私聊里的消息和按钮回调。

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 运行机器人

```bash
python bot.py
```

## 📁 项目结构

```
telegram-submission-bot/
├── bot.py                 # 主程序入口
├── config.py              # 配置管理
├── config.example.json    # 配置示例（复制为 config.json）
├── requirements.txt       # 运行依赖
├── requirements-dev.txt   # 测试和检查依赖
├── LICENSE
│
├── database/
│   ├── models.py          # 数据库模型
│   └── db.py              # 数据库操作
│
├── handlers/
│   ├── start.py           # /start 等命令
│   ├── submission.py      # 投稿处理
│   ├── review.py          # 审核处理
│   └── admin.py           # 管理员命令
│
├── utils/
│   ├── auth.py            # 管理员校验
│   ├── keyboard.py        # 键盘生成
│   ├── helpers.py         # 辅助函数
│   └── media.py           # 媒体发送
│
└── tests/                 # pytest
```

## ⌨️ 命令列表

### 普通用户
| 命令 | 说明 |
|------|------|
| `/start` | 启动机器人 |
| `/submit` | 开始投稿 |
| `/mystats` | 查看我的投稿统计 |
| `/cancel` | 取消当前操作 |
| `/help` | 显示帮助 |

### 管理员
| 命令 | 说明 |
|------|------|
| `/queue` | 查看待审核队列 |
| `/stats` | 查看总体统计 |
| `/ban <ID> <原因>` | 封禁用户 |
| `/unban <ID>` | 解封用户 |
| `/userinfo <ID>` | 查看用户信息 |
| `/addtag <名称> <emoji>` | 添加标签 |
| `/addreason <理由>` | 添加拒绝理由 |

## ⚙️ 配置说明

| 配置项 | 说明 |
|--------|------|
| `bot_token` | 从 BotFather 获取的 Token。可被环境变量 `BOT_TOKEN` 覆盖 |
| `admin_ids` | 管理员用户 ID 数组 |
| `channel_id` | 发布投稿的频道 ID（@xxx 格式） |
| `database_path` | SQLite 文件路径。可被环境变量 `DATABASE_PATH` 覆盖；相对路径会按配置文件目录转成绝对路径 |
| `channel_name` | 频道显示名称 |
| `navigation_links` | 导航链接配置 |
| `customer_service` | 客服链接 |
| `default_tags` | 默认标签列表 |
| `default_reject_reasons` | 默认拒绝理由 |

## 📊 用户等级

| 等级 | 称号 | 通过数要求 |
|------|------|----------|
| 0 | 🌱 新手 | 0 |
| 1 | 🌿 入门 | 5 |
| 2 | 🌲 活跃 | 15 |
| 3 | ⭐ 热心 | 30 |
| 4 | ⭐⭐ 资深 | 50 |
| 5 | 🌟 专家 | 100 |
| 6+ | 👑 大师+ | 200+ |

## ❓ 常见问题

**Q: 机器人无法发送到频道**
A: 确保机器人是频道管理员，且有发送消息权限

**Q: 投稿后管理员收不到通知**
A: 检查 `config.json` 中的 `admin_ids` 是否正确

**Q: 如何添加多个管理员？**
A: 在 `admin_ids` 数组中添加多个 ID，如 `[123, 456, 789]`

## 开发

Python >= 3.10。

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## 📄 许可证

MIT License。全文见 [LICENSE](LICENSE)。
