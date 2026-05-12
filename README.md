# Job Matcher - 智能职位匹配助手

AI 驱动的职位匹配工具：读取简历 → 爬取 Boss直聘 → 多维度评分 → 输出 Excel 报告。

## 前置要求

- Python 3.8+
- [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — 反检测浏览器
- openpyxl (`pip install openpyxl`)

## 项目结构

```
job-matcher/
├── SKILL.md                    # Claude Code 技能定义（方法论）
├── scraping/
│   └── boss_cloak.py           # Boss直聘爬虫（CloakBrowser）
├── scripts/
│   └── scoring.py              # 评分 & Excel 输出
├── config/
│   └── profile.yaml.example    # 配置模板
├── data/                       # 爬取数据
└── reports/                    # 评分报告
```

## 工具用法

### 爬虫

```bash
# 搜索职位（自动抓取 JD 详情）
python3 scraping/boss_cloak.py --keyword "Linux系统工程师" --city "无锡" --pages 3

# 只抓列表不抓详情（更快）
python3 scraping/boss_cloak.py --keyword "DevOps" --city "苏州" --pages 2 --no-detail
```

城市编码、筛选代码等见 `scraping/boss_cloak.py` 头部注释。

### 评分

```bash
python3 scripts/scoring.py \
  --input data/jobs.json \
  --resume-skills "Linux,Python,Docker,Shell" \
  --cities "无锡,苏州" \
  --salary-min 20000 \
  --work-years 6
```

输出带筛选功能的 Excel 报告到 `reports/`。

## 许可证

MIT License
