---
name: job-matcher
description: "智能职位匹配助手 - AI 驱动的简历分析、职位爬取、多维度评分。输入 /job-matcher 开始。"
---

# Job Matcher - 智能职位匹配助手

## 工作流程

### Phase 1: 深度阅读简历，理解用户画像

这一步的目标不是提取关键词列表，而是**真正理解这个人**。

1. 让用户提供简历文件路径
2. 用 Read 工具读取简历（支持 PDF/MD/TXT）
3. **深度分析简历**，产出用户画像：

   - **技能盘点**：会什么？熟练度如何？核心技能 vs 边缘技能
   - **基本信息**：学历、工作年限、当前公司
   - **经验解读**：在哪些公司做过什么？解决了什么问题？有什么成果？
   - **短板识别**：明显不具备的技能或经验（如某用户做了 6 年运维开发但没碰过前端）
   - **职业定位**：基于经验，适合哪些方向？哪些方向虽然感兴趣但可能力不从心？

4. **向用户确认理解**：用 AskUserQuestion 把分析结果展示给用户，确认 AI 的理解是否准确：
   - "我看到你的核心经验是 XX 和 YY，对吗？"
   - "你在 ZZ 方面似乎没有太多经验，这个方向的工作你会考虑吗？"
   - "你的职业目标更偏向管理还是技术深度？"

5. 基于确认后的理解，**AI 自主决定搜索关键词**（不要问用户），关键词应该：
   - 覆盖用户能胜任的岗位（如"运维开发"、"DevOps"）
   - 也包含用户可能匹配的边缘岗位（如"Python开发"——虽然偏开发但技能可迁移）
   - 排除明显不匹配的方向

### Phase 2: 确认偏好 & 选择平台

用 AskUserQuestion 收集：
- 期望城市（可多选）
- 薪资范围
- 排除关键词（如外包、猎头）
- **选择搜索平台**（可多选）：Boss直聘、猎聘、智联招聘、前程无忧

### Phase 3: 登录检查 & 平台登录

所有平台均需登录才能爬取。按以下流程操作：

1. **检查登录状态**：对用户选择的每个平台，检查对应 cookie 文件是否存在且未过期
   - Boss直聘: `scraping/boss_cookies.json`
   - 猎聘: `scraping/liepin_cookies.json`
   - 智联招聘: `scraping/zhaopin_cookies.json`
   - 前程无忧: `scraping/51job_cookies.json`

2. **逐个登录**：对未登录的平台，运行爬虫触发登录流程（浏览器会自动打开登录页），用户手动扫码/登录。一次只登录一个平台：

```bash
# 每个平台会打开浏览器等待登录，登录后自动关闭
python3 scraping/boss_cloak.py --keyword "测试" --city "北京" --pages 1 --no-detail
```

3. **Cookie 有效期**（参考值，实际以平台为准）：
   - Boss直聘: ~24小时
   - 猎聘: ~7天
   - 智联招聘: ~7天
   - 前程无忧: ~7天

4. **所有平台登录完成后**，进入自动爬取阶段

### Phase 4: 通勤配置（可选）

用 AskUserQuestion 询问用户是否配置通勤计算：
- 如果用户提供了住址，询问地图 API 配置：
  - **腾讯地图**: https://lbs.qq.com/dev/console/application/mine 获取 Key
  - **高德地图**: https://lbs.amap.com/dev/key/app 获取 Key
- 如果用户不配置地图 API，通勤评分使用默认中性分（8/15），不影响其他维度

### Phase 5: 自动爬取

对用户选择的平台，用 AI 确定的关键词逐个爬取。每次只能运行一个爬虫（共用浏览器 profile）。**默认抓取 JD 详情页**，获取完整职位描述和公司信息。

```bash
# 每个平台的爬取命令（默认抓详情）
python3 scraping/boss_cloak.py --keyword "关键词" --city "城市" --pages 3
python3 scraping/liepin_cloak.py --keyword "关键词" --city "城市" --pages 3
python3 scraping/zhaopin_cloak.py --keyword "关键词" --city "城市" --pages 3
python3 scraping/51job_cloak.py --keyword "关键词" --city "城市" --pages 3
```

- AI 根据简历自主确定多个搜索关键词，逐个搜索
- 每个职位都会访问详情页提取 JD 文本、公司信息、工作地址

搜索完成后合并去重：

```python
# AI 执行去重逻辑：读取所有 JSON，按 link 去重
```

### Phase 6: AI 筛选（增量式处理）

**核心策略：基于 Phase 1 的用户画像来判断匹配度，不是机械匹配关键词。**

**边看边记，逐批处理：**

1. **每个关键词爬取完成后立即筛选**，不要等所有关键词都爬完再处理
2. **明显不匹配的直接丢弃**（如排除关键词命中、完全不相关的岗位）
3. **匹配的立即记录**到筛选结果文件
4. 每批处理完后汇总，避免数据量过大导致遗漏

**筛选时的思考方式：**

- 不要只看 JD 里的技能关键词，要理解这个岗位的**实际工作内容**
- 对照用户画像：这个人能胜任吗？哪些部分匹配？哪些需要学习但可迁移？
- 考虑成长性：有些岗位虽然不是完美匹配，但对用户职业发展有利
- 考虑现实性：薪资、地点、通勤是否合理？用户会不会真的去投？
- 排除规则：外包/猎头/劳务派遣/实习/应届 — 这些是硬排除，不用犹豫

**示例：**
- 用户是 6 年运维开发经验，看到一个"Python 后端开发"岗 → 技能高度可迁移，应该保留
- 同一个用户看到一个"前端 React 开发"岗 → 完全不匹配，直接排除
- 用户没碰过某个技术但 JD 里写了 → 不是排除理由，记为"缺失技能"即可，用户可以学

### Phase 7: 评分 & 输出 Excel

使用 `scripts/scoring.py` 对筛选后的岗位打分并生成 Excel：

```bash
python3 scripts/scoring.py \
  --input data/filtered_jobs.json \
  --resume-skills "Linux,Python,Docker,Shell,信创,构建系统" \
  --cities "无锡,苏州" \
  --salary-min 20000 \
  --work-years 6 \
  --user-degree "本科" \
  --exclude "外包,猎头,劳务派遣" \
  --home-address "无锡市新吴区xxx小区" \
  --map-key "YOUR_MAP_KEY" \
  --map-provider tencent \
  --max-commute 60 \
  --commute-mode driving
```

参数说明：
- `--resume-skills`: AI 从简历提取的技能（逗号分隔）
- `--cities`: 期望城市
- `--salary-min/max`: 期望月薪范围
- `--work-years`: AI 从简历提取的工作年限
- `--user-degree`: AI 从简历提取的学历（如：本科、硕士）
- `--exclude`: 排除关键词
- `--home-address`: 住址（启用通勤计算，需配合 --map-key）
- `--map-key`: 地图 API Key（腾讯或高德）
- `--map-provider`: tencent（默认）或 amap
- `--max-commute`: 最大可接受通勤时间（分钟，默认60）
- `--commute-mode`: driving（驾车）或 transit（公交）

**如果用户未配置地图 API**，省略 `--home-address` 和 `--map-key`，通勤评分自动使用中性默认分。

评分维度（满分100）：
| 维度 | 权重 | 说明 |
|------|------|------|
| 技能匹配 | 30% | 岗位信息中命中的简历技能比例 |
| 薪资匹配 | 20% | 薪资区间与期望的重叠度 |
| 通勤评分 | 15% | 住址到工作地的通勤时间（地图API，可选） |
| 经验匹配 | 15% | 是否满足经验年限要求 |
| 城市匹配 | 10% | 是否在期望城市 |
| 公司质量 | 10% | 大厂/融资/规模分级 |

输出 Excel 包含：排名、岗位名称、公司、薪资、地点、各维度评分、通勤时间/距离、匹配技能、岗位链接等。

### Phase 8: 推荐报告

AI 根据评分结果和 JD 详情，为用户生成推荐报告，重点推荐 80 分以上的岗位，给出匹配理由和投递建议。

## 依赖安装

首次使用前需安装以下依赖：

```bash
# 必需依赖
pip3 install cloakbrowser openpyxl

# 安装 CloakBrowser 的定制 Chromium 浏览器（首次运行自动触发，也可手动安装）
python3 -c "from cloakbrowser import ensure_binary; ensure_binary()"

# CloakBrowser 依赖 Playwright，安装时自动拉取
pip3 install playwright
```

| 依赖 | 用途 | 安装命令 |
|------|------|---------|
| `cloakbrowser` >= 0.3.27 | 反检测浏览器（CloakBrowser） | `pip3 install cloakbrowser` |
| `openpyxl` | Excel 报告生成 | `pip3 install openpyxl` |
| `playwright` | 浏览器自动化（cloakbrowser 依赖） | `pip3 install playwright` |
| Python >= 3.10 | 运行环境 | 系统自带或 pyenv |

注意：
- CloakBrowser 首次运行会下载定制的 Chromium 二进制文件（~200MB）
- 不需要 `npm install`，不依赖 Node.js
- 不需要安装 Playwright 的浏览器（`playwright install`），CloakBrowser 自带定制版

## 平台支持

| 平台 | 脚本 | 搜索接口 | 需要登录 |
|------|------|---------|---------|
| Boss直聘 | `scraping/boss_cloak.py` | `zhipin.com/web/geek/jobs` | 是 |
| 猎聘 | `scraping/liepin_cloak.py` | `liepin.com/{city}/zhaopin/` | 是 |
| 智联招聘 | `scraping/zhaopin_cloak.py` | `sou.zhaopin.com/?jl=&kw=` | 是 |
| 前程无忧 | `scraping/51job_cloak.py` | `we.51job.com/m/search` | 是 |

每个平台支持 50+ 城市代码，城市编码见各脚本头部。

## 项目结构

```
job-matcher/
├── SKILL.md                    # 本文件：方法论
├── requirements.txt            # Python 依赖
├── config/
│   └── profile.yaml.example    # 配置模板
├── scraping/
│   ├── boss_cloak.py           # Boss直聘爬虫
│   ├── liepin_cloak.py         # 猎聘爬虫
│   ├── zhaopin_cloak.py        # 智联招聘爬虫
│   └── 51job_cloak.py          # 前程无忧爬虫
├── scripts/
│   ├── scoring.py              # 评分 & Excel 工具
│   └── commute.py              # 通勤计算（腾讯地图/高德地图）
├── data/                       # 爬取数据（gitignored）
└── reports/                    # Excel 报告（gitignored）
```
