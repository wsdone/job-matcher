# Job Matcher - Claude Code 智能职位匹配技能

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)

一个 Claude Code 技能（Skill），让 AI 帮你自动读取简历、爬取招聘平台、智能评分、生成推荐报告。

输入 `/job-matcher` 即可开始。

## 安装

### 方式一：Claude Code 插件安装（推荐）

```bash
# 添加到 marketplace
/plugin marketplace add wsdone/job-matcher

# 安装插件
/plugin install job-matcher
```

### 方式二：手动安装

```bash
# 克隆到你的项目目录
git clone https://github.com/wsdone/job-matcher.git
cd job-matcher
```

### 安装依赖

```bash
pip install cloakbrowser openpyxl
```

### 可选：配置地图 MCP（通勤计算）

安装腾讯地图 MCP Server 以启用通勤距离计算：

```bash
# 在 Claude Code 中添加 MCP Server
claude mcp add tencent-map -- npx -y @modelcontextprotocol/server-tencent-map
# 设置环境变量
export TENCENT_MAP_KEY="你的腾讯地图Key"
```

不配置地图 MCP 也不影响核心功能，通勤评分会使用默认中性分。

## 工作流程

## 平台支持状态

| 平台 | 状态 | 说明 |
|------|------|------|
| Boss直聘 | ✅ 可用 | 通过内部 API 获取完整数据（明文薪资、公司信息、技能要求、GPS 坐标） |
| 猎聘 | 🔧 开发中 | 反爬检测严格，需进一步调试 |
| 智联招聘 | 🔧 开发中 | 待调试 |
| 前程无忧 | 🔧 开发中 | 待调试 |

## 前置要求

- Python 3.10+
- [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — 反检测浏览器（`pip install cloakbrowser`）
- openpyxl（`pip install openpyxl`）

详细依赖见 `SKILL.md`。

## 项目结构

```
job-matcher/
├── SKILL.md                    # Claude Code 技能定义（完整工作流方法论）
├── scraping/
│   ├── boss_cloak.py           # Boss直聘爬虫（API + HTML 详情）
│   ├── liepin_cloak.py         # 猎聘爬虫（开发中）
│   ├── zhaopin_cloak.py        # 智联招聘爬虫（开发中）
│   └── 51job_cloak.py          # 前程无忧爬虫（开发中）
├── scripts/
│   ├── scoring.py              # 多维度评分 & Excel 输出
│   └── commute.py              # 通勤计算（腾讯地图/高德地图）
├── config/
│   └── profile.yaml.example    # 配置模板
├── data/                       # 爬取数据（gitignored）
└── reports/                    # 评分报告（gitignored）
```

## Boss直聘爬虫

通过 Boss 内部 API 获取列表数据（明文薪资、公司规模/行业/融资、技能要求、学历要求、GPS 坐标），再通过 HTML 抓取详情页的 JD 全文和工作地址。

```bash
# 搜索职位（默认抓取 JD 详情）
python3 scraping/boss_cloak.py --keyword "DevOps" --city "无锡" --pages 3

# 只抓列表不抓详情（更快，但无 JD 文本）
python3 scraping/boss_cloak.py --keyword "DevOps" --city "无锡" --pages 2 --no-detail

# 带筛选条件
python3 scraping/boss_cloak.py --keyword "Java" --city "北京" --salary 405 --experience 105 --degree 206
```

城市编码、筛选代码等见 `scraping/boss_cloak.py` 头部注释。

## 评分系统

```bash
python3 scripts/scoring.py \
  --input data/jobs.json \
  --resume-skills "Linux,Python,Docker,Shell,Kubernetes" \
  --cities "无锡,苏州" \
  --salary-min 20000 \
  --work-years 6 \
  --user-degree "本科" \
  --exclude "外包,猎头,劳务派遣"
```

### 评分逻辑

1. **硬过滤**：薪资过低、排除关键词命中 → 直接淘汰
2. **多维度评分**：技能匹配作为乘数，薪资/经验/学历/通勤/城市/公司加权计算
3. **百分位推荐**：淘汰不可能被录用的，有效候选中 Top 10% 标记为★推荐

| 维度 | 说明 |
|------|------|
| 技能匹配 | 乘数机制（匹配率低则总分大幅降低） |
| 薪资匹配 | 与期望范围的重叠度 |
| 经验匹配 | 是否满足年限要求 |
| 学历匹配 | 软匹配，不硬卡 |
| 通勤评分 | 住址到工作地的通勤时间（可选，需地图 API） |
| 城市匹配 | 是否在期望城市 |
| 公司质量 | 大厂/融资/规模分级 |

### 可选：通勤计算

```bash
# 腾讯地图
python3 scripts/scoring.py ... --home-address "无锡市新吴区xxx" --map-key "YOUR_KEY" --map-provider tencent

# 高德地图
python3 scripts/scoring.py ... --home-address "无锡市新吴区xxx" --map-key "YOUR_KEY" --map-provider amap
```

Boss API 返回的 GPS 坐标可直接用于通勤计算，省去地理编码步骤。

## 许可证

[AGPL-3.0](LICENSE) — 使用、修改、分发均需开源，网络服务使用也需公开源码。
