#!/usr/bin/env python3
"""
职位评分 & Excel 输出工具

不负责技能提取（由 AI 根据简历判断），只负责：
1. 接收 AI 提供的简历技能列表
2. 对岗位数据做多维度评分
3. 输出 Excel 报告

用法:
  python3 scoring.py --input data/jobs.json --resume-skills "Linux,Python,Docker,Shell" \\
                     --cities "无锡,苏州" --salary-min 20000 --work-years 6
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
except ImportError:
    sys.exit("需要 openpyxl: pip3 install openpyxl")

try:
    from commute import configure as _commute_configure, calculate_commute, calculate_commute_gps
    _HAS_COMMUTE = True
except ImportError:
    _HAS_COMMUTE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")


def parse_salary(salary_str):
    """解析薪资格式: "30-50K·16薪" → {"min": 30000, "max": 50000, "months": 16}"""
    if not salary_str or "面议" in salary_str:
        return None

    result = {"min": 0, "max": 0, "months": 12}

    m = re.search(r'(\d+)\s*[kK万]?\s*[-–]\s*(\d+)\s*[kK万]', salary_str)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if "万" in salary_str:
            result["min"] = low * 10000
            result["max"] = high * 10000
        else:
            result["min"] = low * 1000
            result["max"] = high * 1000
    else:
        m = re.search(r'(\d+)\s*[kK万]', salary_str)
        if m:
            val = int(m.group(1))
            if "万" in salary_str:
                result["min"] = val * 10000
                result["max"] = val * 10000
            else:
                result["min"] = val * 1000
                result["max"] = val * 1000

    m = re.search(r'·(\d+)薪', salary_str)
    if m:
        result["months"] = int(m.group(1))

    return result


def extract_experience_years(tags):
    """从 tags 中提取经验年限要求"""
    text = " ".join(tags or [])

    m = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*年', text)
    if m:
        return int(m.group(2))

    m = re.search(r'(\d+)\s*年以上', text)
    if m:
        return int(m.group(1))

    m = re.search(r'(\d+)\s*年', text)
    if m:
        return int(m.group(1))

    return 0


def score_skills(job_text, resume_skills, api_skills=None):
    """技能匹配评分 (0-35)
    api_skills: 平台 API 返回的 skills 字段（岗位明确要求的技能列表）
    无 api_skills 时，用简历技能在 JD 文本中做简单匹配
    """
    if not resume_skills:
        return 21, [], []

    text_lower = job_text.lower()
    resume_lower = [s.lower() for s in resume_skills]
    resume_lower_set = set(resume_lower)

    if api_skills:
        matched = [s for s in resume_skills
                   if any(s.lower() in ask.lower() or ask.lower() in s.lower()
                          for ask in api_skills)]
        missing = [s for s in api_skills
                   if not any(rl in s.lower() or s.lower() in rl for rl in resume_lower_set)]
    else:
        matched = [s for s in resume_skills if s.lower() in text_lower]
        missing = []

    ratio = len(matched) / len(resume_skills) if resume_skills else 0
    score = 35 * ratio

    if ratio >= 0.7:
        score = 35 * (0.7 + 0.3 * ratio)
    score = min(score, 35)

    return round(score), matched, missing


def score_salary(salary_data, expected_min, expected_max):
    """薪资匹配评分 (0-20)"""
    if not salary_data:
        return 10, "薪资未知"

    job_min = salary_data["min"]
    job_max = salary_data["max"]

    if job_min >= expected_min and job_max <= expected_max:
        return 20, "在期望范围内"
    elif job_min >= expected_min:
        return 17, "底薪满足"
    elif job_max >= expected_min:
        overlap = (job_max - expected_min) / max(1, job_max - job_min)
        return round(20 * max(0.4, overlap)), "部分重叠"
    else:
        return 6, "低于期望"


def score_experience(required_years, user_years):
    """经验匹配评分 (0-15)"""
    if required_years == 0:
        return 15, "无明确要求"
    if user_years >= required_years:
        return 15, f"满足{required_years}年要求"
    elif user_years >= required_years - 1:
        return 13, f"接近要求({required_years}年)"
    elif user_years >= required_years - 2:
        return 9, f"略有差距({required_years}年)"
    else:
        return 5, f"不满足({required_years}年)"


def score_city(location, preferred_cities):
    """城市匹配评分 (0-15)"""
    if not preferred_cities:
        return 15, "无偏好"
    for city in preferred_cities:
        if city in (location or ""):
            return 15, f"期望城市({city})"
    return 6, "非期望城市"


def score_degree(job_degree, user_degree):
    """学历匹配评分 (0-10)，软匹配不硬卡"""
    _DEGREE_LEVEL = {
        "博士": 5, "硕士": 4, "本科": 3, "大专": 2,
        "中专": 1, "中技": 1, "高中": 0,
    }

    if not job_degree or "不限" in job_degree:
        return 10, "无要求"
    if not user_degree:
        return 7, f"要求{job_degree}，未知用户学历"

    req_level = _DEGREE_LEVEL.get(job_degree, 0)
    user_level = _DEGREE_LEVEL.get(user_degree, 0)

    if user_level >= req_level:
        return 10, f"满足({user_degree}≥{job_degree})"
    elif user_level == req_level - 1:
        return 6, f"略低({user_degree}，要求{job_degree})"
    else:
        return 3, f"差距较大({user_degree}，要求{job_degree})"


def score_company(job):
    """公司质量评分 (0-15)"""
    company = job.get("company", "")
    stage = job.get("company_stage", "")
    size = job.get("company_size", "")

    tier1 = ["阿里巴巴", "腾讯", "字节跳动", "美团", "京东", "百度", "网易", "小米",
             "华为", "拼多多", "滴滴", "快手", "携程", "哔哩哔哩", "小红书", "爱奇艺"]

    if any(t in company for t in tier1):
        return 15, "一线大厂"
    if any(kw in stage for kw in ["上市", "独角兽", "C轮", "D轮"]):
        return 14, f"知名企业({stage})"
    if any(s in size for s in ["10000", "1000-9999"]):
        return 12, "大型企业"
    if any(s in size for s in ["500-999", "100-499"]):
        return 9, "中型企业"
    if "A轮" in stage or "B轮" in stage:
        return 8, "成长型企业"
    return 6, "一般"


def score_commute(commute_data, max_commute=60):
    """通勤评分 (0-15)"""
    if not commute_data:
        return 8, "无通勤数据"

    minutes = commute_data.get("duration_min", 0)

    if minutes <= 15:
        return 15, f"步行级({minutes}分钟)"
    elif minutes <= 30:
        return 14, f"近距({minutes}分钟)"
    elif minutes <= 45:
        return 12, f"适中({minutes}分钟)"
    elif minutes <= max_commute:
        return 9, f"可接受({minutes}分钟)"
    elif minutes <= max_commute * 1.5:
        return 5, f"较远({minutes}分钟)"
    else:
        return 2, f"很远({minutes}分钟)"


def score_job(job, resume_skills, config, commute_data=None):
    """对单个职位打分，返回各维度分数

    评分思路：技能匹配是基础门槛，其他维度是在"能被录用"前提下的加分项。
    技能匹配率作为乘数影响总分，避免"大厂高薪但不匹配"的岗位拿到虚高分。
    """
    salary_data = parse_salary(job.get("salary", ""))

    # 合并所有可用的岗位文本信息
    job_text = " ".join([
        job.get("title", ""),
        job.get("salary", ""),
        " ".join(job.get("tags", [])),
        job.get("location", ""),
        job.get("company", ""),
        job.get("jd_text", ""),
    ])

    required_years = extract_experience_years(job.get("tags", []))
    user_years = config.get("work_years", 0)
    expected_min = config.get("salary_min", 0)
    expected_max = config.get("salary_max", 999999)
    cities = config.get("cities", [])
    user_degree = config.get("user_degree", "")

    api_skills = job.get("skills", [])
    sk_score, matched, missing = score_skills(job_text, resume_skills, api_skills=api_skills)
    sa_score, sa_desc = score_salary(salary_data, expected_min, expected_max)
    ex_score, ex_desc = score_experience(required_years, user_years)
    dg_score, dg_desc = score_degree(job.get("job_degree", ""), user_degree)
    ci_score, ci_desc = score_city(job.get("location", ""), cities)
    co_score, co_desc = score_company(job)

    cm_score, cm_desc = score_commute(commute_data, config.get("max_commute_time", 60))

    # 基础分 = 其他维度的加权平均（不含技能）
    # 权重: 薪资25% 经验20% 通勤15% 城市15% 公司10% 学历15%
    base = (
        (sa_score / 20) * 100 * 0.25 +
        (ex_score / 15) * 100 * 0.20 +
        (dg_score / 10) * 100 * 0.15 +
        (cm_score / 15) * 100 * 0.15 +
        (ci_score / 15) * 100 * 0.15 +
        (co_score / 15) * 100 * 0.10
    )

    # 技能匹配率 → 乘数
    # 匹配率 100% → 乘数 1.0
    # 匹配率 70%  → 乘数 0.8
    # 匹配率 40%  → 乘数 0.4
    # 匹配率 < 30% → 乘数 0.15（几乎不可能被录用）
    skill_ratio = sk_score / 35
    if skill_ratio >= 0.7:
        multiplier = 0.5 + 0.5 * skill_ratio  # 0.85 ~ 1.0
    elif skill_ratio >= 0.4:
        multiplier = 0.3 + 0.5 * skill_ratio  # 0.5 ~ 0.85
    else:
        multiplier = 0.15 + 0.3 * skill_ratio  # 0.15 ~ 0.42

    total = round(base * multiplier, 1)

    return {
        "total": total,
        "skill_score": sk_score, "skill_matched": matched, "skill_missing": missing,
        "salary_score": sa_score, "salary_desc": sa_desc,
        "exp_score": ex_score, "exp_desc": ex_desc,
        "degree_score": dg_score, "degree_desc": dg_desc,
        "city_score": ci_score, "city_desc": ci_desc,
        "company_score": co_score, "company_desc": co_desc,
        "commute_score": cm_score, "commute_desc": cm_desc,
        "commute_data": commute_data,
        "job_degree": job.get("job_degree", ""),
        "api_skills": job.get("skills", []),
        "skill_multiplier": round(multiplier, 2),
    }


def generate_excel(scored_jobs, config):
    """生成 Excel 推荐报告"""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = os.path.join(REPORTS_DIR, f"recommendations_{timestamp}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "职位推荐"

    headers = [
        "推荐", "排名", "岗位名称", "公司名称", "薪资", "地点",
        "综合评分", "技能匹配度", "技能乘数", "薪资评分", "通勤评分", "经验匹配度", "学历匹配度", "城市匹配度", "公司质量",
        "通勤时间", "通勤距离", "匹配技能", "缺失技能", "岗位要求技能", "经验要求", "学历要求", "Boss在线",
        "公司行业", "公司规模", "融资阶段",
        "工作地址",
        "岗位链接",
    ]

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    row_idx = 2

    for rank, item in enumerate(scored_jobs, 1):
        job = item["job"]
        s = item["scores"]
        text = f"{job.get('title', '')} {job.get('company', '')} {' '.join(job.get('tags', []))}"

        row_data = [
            "★" if s.get("recommend") == "strong" else "",
            rank,
            job.get("title", ""),
            job.get("company", ""),
            job.get("salary", ""),
            job.get("location", ""),
            s["total"],
            f"{s['skill_score']}/35",
            f"{s.get('skill_multiplier', 0):.0%}",
            f"{s['salary_score']}/20",
            f"{s['commute_score']}/15",
            f"{s['exp_score']}/15",
            f"{s['degree_score']}/10",
            f"{s['city_score']}/15",
            f"{s['company_score']}/15",
            s.get("commute_desc", ""),
            f"{s['commute_data']['distance_km']}km" if s.get("commute_data") else "",
            ", ".join(s.get("skill_matched", [])),
            ", ".join(s.get("skill_missing", [])),
            ", ".join(s.get("api_skills", [])),
            s.get("exp_desc", ""),
            s.get("job_degree", ""),
            "是" if job.get("online") else "否",
            job.get("company_industry", ""),
            job.get("company_size", ""),
            job.get("company_stage", ""),
            job.get("work_address", ""),
            job.get("link", ""),
        ]

        for col, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        total = s["total"]
        fill = green_fill if total >= 80 else yellow_fill if total >= 60 else None
        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = fill

        row_idx += 1

    col_widths = {
        1: 5, 2: 6, 3: 30, 4: 20, 5: 16, 6: 20, 7: 10,
        8: 12, 9: 8, 10: 10, 11: 10, 12: 12, 13: 10, 14: 12, 15: 10,
        16: 16, 17: 10,
        18: 30, 19: 30, 20: 30, 21: 16, 22: 10, 23: 10,
        24: 14, 25: 14, 26: 14,
        27: 30, 28: 50,
    }
    for col, width in col_widths.items():
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(headers))}{row_idx - 1}"

    wb.save(excel_path)
    return excel_path


def main():
    parser = argparse.ArgumentParser(description="职位评分 & Excel 输出")
    parser.add_argument("--input", required=True, help="岗位 JSON 数据文件")
    parser.add_argument("--resume-skills", required=True, help="简历技能列表（逗号分隔）")
    parser.add_argument("--cities", default="", help="期望城市（逗号分隔）")
    parser.add_argument("--salary-min", type=int, default=0, help="期望最低月薪")
    parser.add_argument("--salary-max", type=int, default=999999, help="期望最高月薪")
    parser.add_argument("--work-years", type=int, default=0, help="工作年限")
    parser.add_argument("--user-degree", default="", help="用户学历（如：本科、硕士）")
    parser.add_argument("--exclude", default="", help="排除关键词（逗号分隔）")
    parser.add_argument("--home-address", default="", help="住址（用于通勤计算）")
    parser.add_argument("--map-key", default="", help="地图 API Key（腾讯或高德）")
    parser.add_argument("--map-provider", default="tencent", choices=["tencent", "amap"],
                        help="地图服务商: tencent 或 amap")
    parser.add_argument("--max-commute", type=int, default=60, help="最大可接受通勤时间（分钟）")
    parser.add_argument("--commute-mode", default="driving", choices=["driving", "transit"],
                        help="通勤方式: driving 或 transit")
    args = parser.parse_args()

    # 加载岗位数据
    with open(args.input, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    resume_skills = [s.strip() for s in args.resume_skills.split(",") if s.strip()]
    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    exclude = [e.strip() for e in args.exclude.split(",") if e.strip()]

    config = {
        "cities": cities,
        "salary_min": args.salary_min,
        "salary_max": args.salary_max,
        "work_years": args.work_years,
        "user_degree": args.user_degree,
        "exclude_keywords": exclude,
        "home_address": args.home_address,
        "max_commute_time": args.max_commute,
        "commute_mode": args.commute_mode,
    }

    commute_enabled = args.home_address and args.map_key and _HAS_COMMUTE
    if commute_enabled:
        _commute_configure(args.map_key, provider=args.map_provider)
        print(f"  通勤计算: 已启用 ({args.map_provider}, 住址: {args.home_address}, 模式: {args.commute_mode})")
    elif args.home_address and not args.map_key:
        print("  通勤计算: 跳过（未提供 --map-key，不影响其他评分）")
    elif args.home_address and not _HAS_COMMUTE:
        print("  通勤计算: 跳过（commute.py 未找到）")

    print(f"\n{'='*60}")
    print(f"  职位评分: {len(jobs)} 个职位")
    print(f"  简历技能: {', '.join(resume_skills[:10])}{'...' if len(resume_skills) > 10 else ''}")
    print(f"  期望城市: {', '.join(cities)}")
    print(f"  期望薪资: {args.salary_min}-{args.salary_max}")
    print(f"{'='*60}\n")

    # Pass 0: 硬过滤 — 淘汰明显不合适的岗位
    filtered_jobs = []
    hard_exclude_reasons = {"salary_low": 0, "exclude_kw": 0, "industry": 0}

    for job in jobs:
        # 1. 薪资过低：岗位薪资上限低于用户期望下限
        salary_data = parse_salary(job.get("salary", ""))
        if salary_data and args.salary_min > 0:
            if salary_data["max"] < args.salary_min * 0.7:
                hard_exclude_reasons["salary_low"] += 1
                continue

        # 2. 排除关键词命中（标题 + 公司 + 标签）
        text = " ".join([
            job.get("title", ""), job.get("company", ""),
            " ".join(job.get("tags", [])),
        ])
        if any(ex in text for ex in exclude):
            hard_exclude_reasons["exclude_kw"] += 1
            continue

        filtered_jobs.append(job)

    excluded_total = len(jobs) - len(filtered_jobs)
    if excluded_total > 0:
        print(f"  硬过滤: 淘汰 {excluded_total} 个（薪资过低: {hard_exclude_reasons['salary_low']}, "
              f"排除词: {hard_exclude_reasons['exclude_kw']}）")
        print(f"  剩余候选: {len(filtered_jobs)} 个\n")

    # Pass 1: 评分（不含通勤）
    scored_jobs = []
    for job in filtered_jobs:
        scores = score_job(job, resume_skills, config)
        scored_jobs.append({"job": job, "scores": scores})

    scored_jobs.sort(key=lambda x: x["scores"]["total"], reverse=True)

    # Pass 2: 仅对符合要求的岗位计算通勤
    if commute_enabled:
        commute_threshold = 55
        candidates = [j for j in scored_jobs if j["scores"]["total"] >= commute_threshold]
        print(f"  通勤计算: {len(candidates)}/{len(scored_jobs)} 个岗位达标(>={commute_threshold}分)，开始查询...")

        for i, item in enumerate(candidates):
            work_addr = item["job"].get("work_address", "")
            if not work_addr:
                continue
            try:
                gps = item["job"].get("gps")
                if gps and gps.get("lat") and gps.get("lng"):
                    commute_data = calculate_commute_gps(
                        args.home_address, gps,
                        mode=args.commute_mode,
                    )
                else:
                    commute_data = calculate_commute(
                        args.home_address, work_addr,
                        mode=args.commute_mode,
                    )
                if commute_data:
                    item["scores"] = score_job(item["job"], resume_skills, config, commute_data=commute_data)
            except Exception as e:
                print(f"    [-] 通勤查询失败: {e}")

        # 重新排序
        scored_jobs.sort(key=lambda x: x["scores"]["total"], reverse=True)

    # 按总分降序
    scored_jobs.sort(key=lambda x: x["scores"]["total"], reverse=True)

    # 百分位推荐：先淘汰明显不合适的，再取 top N%
    # 淘汰条件：技能乘数 < 0.2（几乎不可能被录用）
    viable_jobs = [j for j in scored_jobs if j["scores"].get("skill_multiplier", 1) >= 0.2]
    pruned = len(scored_jobs) - len(viable_jobs)

    top_n = max(5, int(len(viable_jobs) * 0.10))  # 至少5个，取前10%
    highly = viable_jobs[:top_n]

    for item in highly:
        item["scores"]["recommend"] = "strong"

    # 生成 Excel（包含所有 viable，标记推荐等级）
    excel_path = generate_excel(scored_jobs, config)

    print(f"{'='*60}")
    print(f"  总职位: {len(scored_jobs)} | 淘汰(不匹配): {pruned} | 有效候选: {len(viable_jobs)}")
    print(f"  强烈推荐(top 10%, {len(highly)}个) | 其余候选: {len(viable_jobs) - len(highly)}个")
    print(f"  Excel: {excel_path}")
    print(f"{'='*60}")

    for i, item in enumerate(highly[:15], 1):
        j = item["job"]
        s = item["scores"]
        marker = "★" if i <= max(3, int(len(viable_jobs) * 0.03)) else " "
        print(f"  {marker}{i:2d}. [{s['total']:5.1f}] {j.get('title', '')} - {j.get('company', '')}")
        print(f"       {j.get('salary', '')} | {j.get('location', '')} | 技能匹配×{s.get('skill_multiplier', 0):.0%}")

    return excel_path


if __name__ == "__main__":
    main()
