---
name: job-matcher
description: "智能职位匹配助手 - AI 驱动的简历分析、职位爬取、多维度评分。输入 /job-matcher 开始。"
---

# Job Matcher - 智能职位匹配助手

## 工作流程

### Phase 1: 读取简历，提取技能

1. 让用户提供简历文件路径
2. 用 Read 工具读取简历（支持 PDF/MD/TXT）
3. AI 分析简历，提取核心技能、工作年限、经验亮点
4. 根据简历内容，AI 自主决定搜索关键词（不要问用户）

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

对用户选择的平台，用 AI 确定的关键词逐个爬取。每次只能运行一个爬虫（共用浏览器 profile）。

```bash
# 每个平台的爬取命令
python3 scraping/boss_cloak.py --keyword "关键词" --city "城市" --pages 3 --no-detail
python3 scraping/liepin_cloak.py --keyword "关键词" --city "城市" --pages 3 --no-detail
python3 scraping/zhaopin_cloak.py --keyword "关键词" --city "城市" --pages 3 --no-detail
python3 scraping/51job_cloak.py --keyword "关键词" --city "城市" --pages 3 --no-detail
```

- AI 根据简历自主确定多个搜索关键词，逐个搜索
- `--no-detail` 先只抓列表，后续对精选岗位抓详情

搜索完成后合并去重：

```python
# AI 执行去重逻辑：读取所有 JSON，按 link 去重
```

### Phase 6: AI 筛选

AI 根据简历内容，从所有爬取结果中筛选真正匹配的岗位。筛选标准由 AI 判断，不是硬编码规则。

### Phase 7: 评分 & 输出 Excel

使用 `scripts/scoring.py` 对筛选后的岗位打分并生成 Excel：

```bash
python3 scripts/scoring.py \
  --input data/filtered_jobs.json \
  --resume-skills "Linux,Python,Docker,Shell,信创,构建系统" \
  --cities "无锡,苏州" \
  --salary-min 20000 \
  --work-years 6 \
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
- `--work-years`: 工作年限
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

### Phase 8: (可选) 抓取 JD 详情

对 Excel 中高分岗位，去掉 `--no-detail` 抓取完整 JD：

```bash
python3 scraping/boss_cloak.py --keyword "关键词" --city "城市" --pages 1
```

AI 阅读 JD 详情后给出更精准的匹配建议。

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
