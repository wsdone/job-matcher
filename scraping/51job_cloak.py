"""
前程无忧(51job)职位爬取 - CloakBrowser 增强版

使用 51job 移动端 we.51job.com 搜索接口

用法：
  python3 51job_cloak.py --keyword "Java开发" --city "无锡" --pages 3
  python3 51job_cloak.py --keyword "DevOps" --city "苏州" --pages 2 --no-detail
  python3 51job_cloak.py --keyword "Java" --city "北京" --debug
"""

import argparse
import json
import os
import time
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
PROFILE_DIR = os.path.join(BASE_DIR, ".cloak_profile_51job")
COOKIES_FILE = os.path.join(BASE_DIR, "51job_cookies.json")
FINGERPRINT_SEED = str(hash(PROFILE_DIR) % 100000)

JOB51_SEARCH_URL = "https://we.51job.com/m/search"
JOB51_LOGIN_URL = "https://login.51job.com/"

# 前程无忧城市代码 (jobArea 参数)
CITY_CODES = {
    "北京": "010000", "上海": "020000", "深圳": "040000",
    "广州": "030200", "杭州": "080200", "成都": "090200",
    "南京": "070200", "武汉": "180200", "西安": "200200",
    "重庆": "060000", "苏州": "070300", "天津": "050000",
    "长沙": "130200", "郑州": "170200", "东莞": "030800",
    "沈阳": "110200", "青岛": "120300", "合肥": "150200",
    "佛山": "030400", "无锡": "070500",
    "厦门": "090300", "福州": "090100", "大连": "110300",
    "哈尔滨": "100200", "长春": "100100", "石家庄": "160200",
    "济南": "120200", "昆明": "250200", "贵阳": "240200",
    "南昌": "140200", "南宁": "260200", "太原": "190200",
    "常州": "070600", "南通": "070800", "宁波": "080300",
    "温州": "080500", "珠海": "030600", "烟台": "120500",
}


def get_city_code(city_name):
    return CITY_CODES.get(city_name, "010000")


def _is_logged_in(context):
    cookies = context.cookies()
    token_names = {c.get("name", "") for c in cookies}
    return bool(token_names & {"uid", "ps", "_c_i_p"})


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
        page.wait_for_selector(".joblist", timeout=15000)
    except Exception:
        _save_debug(page, "no_cards")
        return jobs

    time.sleep(2)
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)

    cards = page.query_selector_all(".joblist")
    if not cards:
        _save_debug(page, "empty_cards")
        return jobs

    for card in cards:
        try:
            job = {}

            # 从 sensorsdata 提取结构化数据
            sensors = card.get_attribute("sensorsdata") or ""
            if sensors:
                try:
                    data = json.loads(sensors)
                    job["title"] = data.get("jobTitle", "")
                    job["salary"] = data.get("jobSalary", "")
                    job["location"] = data.get("jobArea", "")
                    job_id = data.get("jobId", "")
                    if job_id:
                        job["link"] = f"https://we.51job.com/m/job-detail/{job_id}.html"
                    else:
                        job["link"] = ""
                except json.JSONDecodeError:
                    pass

            # CSS 选择器补充/覆盖
            if not job.get("title"):
                el = card.query_selector(".jname")
                job["title"] = el.inner_text().strip() if el else ""

            if not job.get("salary"):
                el = card.query_selector(".sal")
                job["salary"] = el.inner_text().strip() if el else ""

            if not job.get("location"):
                el = card.query_selector(".area .s")
                job["location"] = el.inner_text().strip() if el else ""

            # 公司名
            el = card.query_selector(".cname")
            job["company"] = el.inner_text().strip() if el else ""

            # 公司信息（类型+规模）
            el = card.query_selector(".info em")
            if el:
                info_text = el.inner_text().strip()
                parts = [p.strip() for p in info_text.split(" ") if p.strip()]
                for p in parts:
                    if "人" in p:
                        job["company_size"] = p
                    elif p in ("民营", "国企", "外资", "合资", "上市公司", "创业公司"):
                        job["company_stage"] = p

            # 标签（经验/学历）
            tags = []
            for t in card.query_selector_all(".tabs .fl"):
                text = t.inner_text().strip()
                if text:
                    tags.append(text)
            job["tags"] = tags

            # HR 信息
            el = card.query_selector(".hrinfo")
            job["boss_info"] = el.inner_text().strip() if el else ""

            job["online"] = False

            if job.get("title"):
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
        for sel in [".des", ".job-description", "[class*='describe']", ".cn_content"]:
            for el in page.query_selector_all(sel):
                text = el.inner_text().strip()
                if text:
                    jd_parts.append(text)
        if jd_parts:
            job["jd_text"] = "\n".join(jd_parts)

        # 公司信息
        for item in page.query_selector_all("[class*='company'] li, .info li"):
            text = item.inner_text().strip()
            if "行业" in text:
                job["company_industry"] = text.split("行业")[-1].strip().lstrip("：:")
            elif "规模" in text or "人数" in text:
                job["company_size"] = text.split("规模")[-1].split("人数")[-1].strip().lstrip("：:")

        # 工作地址
        el = page.query_selector("[class*='address'], [class*='location']")
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
    path = os.path.join(DATA_DIR, f"51job_{suffix}.html")
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
    output_file = os.path.join(DATA_DIR, f"jobs_51job_{keyword}_{city}_{int(time.time())}.json")
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

    print(f"\n{'='*60}")
    print(f"  前程无忧: {keyword} @ {city}")
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

    # 必须登录 — 先检查登录态
    if not _is_logged_in(ctx):
        print("[!] 需要登录前程无忧")
        page.goto(JOB51_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        if not _wait_for_login(ctx, page):
            print("[-] 登录超时，退出")
            ctx.close()
            return []
    else:
        print("[+] 已登录")

    # 搜索（使用移动端 we.51job.com）
    keyword_encoded = quote(keyword)

    for page_num in range(1, pages + 1):
        url = f"{JOB51_SEARCH_URL}?keyword={keyword_encoded}&jobArea={city_code}&pageNum={page_num}"
        if page_num == 1:
            print(f"[*] 正在打开: {url}")
        else:
            print(f"\n[*] 第 {page_num} 页: {url}")

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)

        if debug:
            _save_debug(page, f"search_page_{page_num}")

        # 首次搜索时检查是否有数据
        if page_num == 1:
            content = page.content()
            if len(content) < 100:
                _save_debug(page, "empty_first")
                print("[-] 页面为空，可能需要重新登录")
                ctx.close()
                return []

        break  # TODO: 分页逻辑待完善

    # 提取当前页数据
    all_jobs = []
    seen_links = set()

    jobs = _extract_jobs(page)
    new_count = 0
    for job in jobs:
        link = job.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            all_jobs.append(job)
            new_count += 1

    print(f"[+] 第 1 页: 找到 {len(jobs)} 个, 新增 {new_count} 个 (总计 {len(all_jobs)})")

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
    parser = argparse.ArgumentParser(description="前程无忧爬取 (CloakBrowser)")
    parser.add_argument("--keyword", type=str, default="Java开发", help="搜索关键词")
    parser.add_argument("--city", type=str, default="北京", help="城市")
    parser.add_argument("--pages", type=int, default=3, help="爬取页数")
    parser.add_argument("--no-detail", action="store_true", help="不抓取 JD 详情页")
    parser.add_argument("--debug", action="store_true", help="保存调试页面 HTML")

    args = parser.parse_args()
    run(args.keyword, args.city, args.pages, fetch_detail=not args.no_detail, debug=args.debug)


if __name__ == "__main__":
    main()
