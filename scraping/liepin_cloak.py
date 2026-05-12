"""
猎聘职位爬取 - CloakBrowser 增强版

用法：
  python3 liepin_cloak.py --keyword "Java开发" --city "无锡" --pages 3
  python3 liepin_cloak.py --keyword "DevOps" --city "苏州" --pages 2 --no-detail
  python3 liepin_cloak.py --keyword "Java" --city "北京" --debug  # 保存调试页面
"""

import argparse
import json
import os
import time
from urllib.parse import urlencode, quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
PROFILE_DIR = os.path.join(BASE_DIR, ".cloak_profile_liepin")
COOKIES_FILE = os.path.join(BASE_DIR, "liepin_cookies.json")
FINGERPRINT_SEED = str(hash(PROFILE_DIR) % 100000)  # 每个 profile 自动生成唯一指纹

LIEPIN_URL = "https://www.liepin.com"

# 猎聘城市代码 (URL path 前缀)
CITY_CODES = {
    "北京": "city-bj", "上海": "city-sh", "深圳": "city-sz",
    "广州": "city-gz", "杭州": "city-hz", "成都": "city-cd",
    "南京": "city-nj", "武汉": "city-wh", "西安": "city-xa",
    "重庆": "city-cq", "苏州": "city-suzhou", "天津": "city-tj",
    "长沙": "city-cs", "郑州": "city-zz", "东莞": "city-dg",
    "沈阳": "city-sy", "青岛": "city-qd", "合肥": "city-hf",
    "佛山": "city-fs", "无锡": "city-wx",
    "厦门": "city-xm", "福州": "city-fz", "大连": "city-dl",
    "哈尔滨": "city-heb", "长春": "city-cc", "石家庄": "city-sjz",
    "济南": "city-jn", "昆明": "city-km", "贵阳": "city-gy",
    "南昌": "city-nc", "南宁": "city-nn", "太原": "city-ty",
    "常州": "city-cz", "南通": "city-nt", "宁波": "city-nb",
    "温州": "city-wz", "珠海": "city-zh", "烟台": "city-yt",
}


def get_city_code(city_name):
    return CITY_CODES.get(city_name, "")


def _is_logged_in(context):
    cookies = context.cookies()
    token_names = {c.get("name", "") for c in cookies}
    return bool(token_names & {"ltoken", "liepin_token", "user_track"})


def _wait_for_login(context, page, max_wait=180):
    print("[*] 等待登录...请在浏览器中扫码/登录")
    for i in range(max_wait):
        time.sleep(1)
        if _is_logged_in(context):
            print(f"[+] 登录成功！(等待了 {i+1} 秒)")
            _save_cookies(context)
            return True
        if i > 0 and i % 30 == 0:
            print(f"[*] 仍在等待... ({i}/{max_wait}s)")
    return False


def _save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)


def _extract_jobs(page):
    jobs = []
    try:
        page.wait_for_selector(".job-card-pc-container, .job-detail-box", timeout=15000)
    except Exception:
        _save_debug(page, "no_cards")
        return jobs

    time.sleep(2)
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)

    cards = page.query_selector_all(".job-card-pc-container")
    if not cards:
        _save_debug(page, "empty_cards")
        return jobs

    for card in cards:
        try:
            job = {}

            # 主链接区
            job_link = card.query_selector("a[data-nick='job-detail-job-info'], a[href*='liepin.com/job/']")
            if not job_link:
                continue

            # 标题: data-nick 链接内的 div[title]
            el = job_link.query_selector("div[title]")
            job["title"] = el.get_attribute("title") or el.inner_text().strip() if el else ""
            if not job["title"]:
                el = job_link.query_selector(".ellipsis-1")
                job["title"] = el.inner_text().strip() if el else ""

            # 薪资: 链接内包含 k/万/薪 的 span
            job["salary"] = ""
            for span in job_link.query_selector_all("span"):
                text = span.inner_text().strip()
                if text and ("k" in text.lower() or "万" in text or "薪" in text) and "-" in text:
                    job["salary"] = text
                    break

            # 地点: 【城市】括号内的 span.ellipsis-1
            job["location"] = ""
            el = card.query_selector("[data-nick='job-detail-job-info'] .ellipsis-1:not([title])")
            if el:
                text = el.inner_text().strip()
                # 排除标题（标题有 title 属性）
                if text and text != job["title"]:
                    job["location"] = text

            # 链接
            href = job_link.get_attribute("href") or ""
            job["link"] = href if href.startswith("http") else f"{LIEPIN_URL}{href}"

            # 公司: data-nick="job-detail-company-info" 区域
            el = card.query_selector("[data-nick='job-detail-company-info'] .ellipsis-1")
            job["company"] = el.inner_text().strip() if el else ""

            # 标签: 经验/学历等（job_link 内的小 span）
            tags = []
            for t in job_link.query_selector_all("span"):
                text = t.inner_text().strip()
                if text and text not in (job["salary"], "急聘", "【", "】") and len(text) < 15:
                    if "年" in text or "学历" in text or "本科" in text or "硕士" in text or "大专" in text:
                        tags.append(text)
            # 公司信息里的标签（行业/规模）
            for t in card.query_selector_all("[data-nick='job-detail-company-info'] span"):
                text = t.inner_text().strip()
                if text and ("人" in text or "融资" in text or "上市" in text) and len(text) < 20:
                    tags.append(text)
            job["tags"] = tags

            # 招聘者
            el = card.query_selector("[class*='recruiter']")
            job["boss_info"] = el.inner_text().strip() if el else ""

            job["online"] = card.query_selector("[class*='online'], .online-icon") is not None

            if job["title"]:
                jobs.append(job)
        except Exception:
            continue

    return jobs


def _fetch_job_detail(page, job):
    link = job.get("link", "")
    if not link:
        return job

    try:
        page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # JD 文本
        jd_parts = []
        for sel in [".job-description", ".job-desc", "[class*='describe']", ".content.content-word"]:
            for el in page.query_selector_all(sel):
                text = el.inner_text().strip()
                if text:
                    jd_parts.append(text)
        if jd_parts:
            job["jd_text"] = "\n".join(jd_parts)

        # 公司信息
        for item in page.query_selector_all("[class*='company-info'] li, .job-company-info li"):
            text = item.inner_text().strip()
            if "行业" in text:
                job["company_industry"] = text.split("行业")[-1].strip().lstrip("：:")
            elif "规模" in text or "人数" in text:
                job["company_size"] = text.split("规模")[-1].split("人数")[-1].strip().lstrip("：:")
            elif "融资" in text or "上市" in text:
                job["company_stage"] = text.split("融资")[-1].split("上市")[-1].strip().lstrip("：:")

        # 工作地址
        el = page.query_selector("[class*='address'], [class*='location-detail'], .job-address")
        if el:
            addr = el.inner_text().strip()
            if addr and len(addr) > 2:
                job["work_address"] = addr

    except Exception as e:
        print(f"    [-] 详情抓取失败: {e}")

    return job


def _save_debug(page, suffix="debug"):
    os.makedirs(DATA_DIR, exist_ok=True)
    content = page.content()
    path = os.path.join(DATA_DIR, f"liepin_{suffix}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[*] 调试页面已保存: {path}")


def _enrich_with_details(ctx, all_jobs):
    page = ctx.new_page()
    total = len(all_jobs)
    print(f"\n  开始抓取 JD 详情: 共 {total} 个职位")

    for i, job in enumerate(all_jobs):
        if not job.get("link"):
            continue
        print(f"  [{i+1}/{total}] {job.get('title', '')} - {job.get('company', '')}")
        _fetch_job_detail(page, job)
        time.sleep(3 + (i % 3))

    page.close()
    return all_jobs


def _save_and_show(all_jobs, keyword, city):
    os.makedirs(DATA_DIR, exist_ok=True)
    output_file = os.path.join(DATA_DIR, f"jobs_liepin_{keyword}_{city}_{int(time.time())}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"  共 {len(all_jobs)} 个职位 → {output_file}")
    print(f"{'='*70}")
    for i, job in enumerate(all_jobs[:20], 1):
        print(f"  {i:3d}. {job['title']}")
        print(f"       {job.get('salary', '')}  {job.get('company', '')}  {job.get('location', '')}")
    if len(all_jobs) > 20:
        print(f"  ... 还有 {len(all_jobs) - 20} 个")
    return output_file


def run(keyword="Java开发", city="北京", pages=3, fetch_detail=True, debug=False):
    from cloakbrowser import launch_persistent_context

    city_code = get_city_code(city)

    if city_code:
        base_url = f"{LIEPIN_URL}/{city_code}/zhaopin/"
    else:
        base_url = f"{LIEPIN_URL}/zhaopin/"

    print(f"\n{'='*60}")
    print(f"  猎聘: {keyword} @ {city}")
    print(f"  目标: {pages} 页")
    print(f"{'='*60}\n")

    ctx = launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        humanize=True,
        args=[f"--fingerprint={FINGERPRINT_SEED}"],
    )

    page = ctx.new_page()

    # 第一页
    params = {"key": keyword}
    first_url = f"{base_url}?{urlencode(params)}"
    print(f"[*] 正在打开: {first_url}")
    page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    if debug:
        _save_debug(page, "search_page_1")

    # 登录检测
    page_url = page.url
    if "login" in page_url or "passport" in page_url:
        print("[!] 需要登录")
        if _wait_for_login(ctx, page):
            time.sleep(2)
            page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        else:
            print("[-] 登录超时")
            ctx.close()
            return []
    elif not _is_logged_in(ctx):
        print("[*] 未检测到登录态，尝试继续...")

    # 逐页爬取
    all_jobs = []
    seen_links = set()

    for page_num in range(1, pages + 1):
        if page_num > 1:
            params["curPage"] = page_num
            url = f"{base_url}?{urlencode(params)}"
            print(f"\n[*] 第 {page_num} 页: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            if debug:
                _save_debug(page, f"search_page_{page_num}")

        jobs = _extract_jobs(page)
        new_count = 0
        for job in jobs:
            link = job.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                all_jobs.append(job)
                new_count += 1

        print(f"[+] 第 {page_num} 页: 找到 {len(jobs)} 个, 新增 {new_count} 个 (总计 {len(all_jobs)})")

        if not jobs:
            print(f"[-] 第 {page_num} 页无数据，停止翻页")
            break

        if page_num < pages:
            delay = 2 + (page_num % 3)
            time.sleep(delay)

    # JD 详情
    if fetch_detail and all_jobs:
        _enrich_with_details(ctx, all_jobs)

    _save_cookies(ctx)
    ctx.close()

    if all_jobs:
        return _save_and_show(all_jobs, keyword, city)
    else:
        print("[-] 未获取到职位数据")
        return []


def main():
    parser = argparse.ArgumentParser(description="猎聘爬取 (CloakBrowser)")
    parser.add_argument("--keyword", type=str, default="Java开发", help="搜索关键词")
    parser.add_argument("--city", type=str, default="北京", help="城市")
    parser.add_argument("--pages", type=int, default=3, help="爬取页数")
    parser.add_argument("--no-detail", action="store_true", help="不抓取 JD 详情页")
    parser.add_argument("--debug", action="store_true", help="保存调试页面 HTML")

    args = parser.parse_args()
    run(args.keyword, args.city, args.pages, fetch_detail=not args.no_detail, debug=args.debug)


if __name__ == "__main__":
    main()
