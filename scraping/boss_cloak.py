"""
Boss直聘职位爬取 - CloakBrowser 增强版

支持：翻页、多条件筛选、去重、JD详情抓取

用法：
  # 基础搜索（默认3页，自动抓取详情）
  python3 boss_cloak.py --keyword "Java开发" --city "北京"

  # 只抓列表，不抓详情
  python3 boss_cloak.py --keyword "Java开发" --city "北京" --no-detail

  # 筛选薪资（40-50K）
  python3 boss_cloak.py --keyword "Java开发" --city "北京" --salary 405

  # 组合筛选 + 5页
  python3 boss_cloak.py --keyword "Java开发" --city "北京" --salary 405 --experience 105 --degree 206 --pages 5

筛选代码参考：
  薪资:   405=40-50K  505=50K+  306=30-40K  205=20-30K  104=10-20K
  经验:   101=应届  102=1年以内  104=1-3年  105=3-5年  106=5-10年  107=10年以上
  学历:   206=本科  207=硕士  208=博士  209=大专  210=中专/中技
  公司规模: 301=0-20人  302=20-99人  303=100-499人  304=500-999人  305=1000-9999人  306=10000人以上
  融资阶段: 801=未融资  802=天使轮  803=A轮  804=B轮  805=C轮  806=D轮及以上  807=已上市  808=不需要融资
"""

import argparse
import json
import os
import time
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
PROFILE_DIR = os.path.join(BASE_DIR, ".cloak_profile")
COOKIES_FILE = os.path.join(BASE_DIR, "boss_cookies.json")
FINGERPRINT_SEED = "42069"

BOSS_URL = "https://www.zhipin.com"

CITY_CODES = {
    "北京": "101010100", "上海": "101020100", "深圳": "101280100",
    "广州": "101280600", "杭州": "101210100", "成都": "101270100",
    "南京": "101190100", "武汉": "101200100", "西安": "101110100",
    "重庆": "101040100", "苏州": "101190400", "天津": "101030100",
    "长沙": "101250100", "郑州": "101180100", "东莞": "101281600",
    "沈阳": "101070100", "青岛": "101120200", "合肥": "101220100",
    "佛山": "101280800", "无锡": "101190200",
    # 新增城市
    "厦门": "101230200", "福州": "101230100", "泉州": "101230500",
    "珠海": "101280700", "惠州": "101280300", "中山": "101281700",
    "济南": "101120100", "烟台": "101120500", "威海": "101121300",
    "大连": "101070200", "哈尔滨": "101050100", "长春": "101060100",
    "石家庄": "101090100", "太原": "101100100", "兰州": "101160100",
    "昆明": "101290100", "贵阳": "101180300", "南昌": "101240100",
    "南宁": "101300100", "海口": "101310100", "三亚": "101310200",
    "常州": "101191100", "南通": "101190500", "徐州": "101190300",
    "扬州": "101190700", "镇江": "101190800", "盐城": "101190900",
    "泰州": "101191000", "嘉兴": "101210300", "绍兴": "101210500",
    "金华": "101210900", "温州": "101210700", "台州": "101210600",
    "宁波": "101210400", "湖州": "101210200", "芜湖": "101220300",
    "洛阳": "101180500", "保定": "101090200", "廊坊": "101090600",
    "唐山": "101090300", "赣州": "101240400", "桂林": "101300500",
    "潍坊": "101120600", "临沂": "101120900", "淄博": "101120300",
    "襄阳": "101200200", "宜昌": "101200900",
}


def get_city_code(city_name):
    return CITY_CODES.get(city_name, "101010100")


def _is_logged_in(context):
    cookies = context.cookies()
    token_names = {c.get("name", "") for c in cookies}
    return bool(token_names & {"geek_zp_token", "bst", "bstz"})


def _wait_for_login(context, page, max_wait=180):
    print("[*] 等待登录...请在浏览器中扫码")
    for i in range(max_wait):
        time.sleep(1)
        if _is_logged_in(context):
            print(f"[+] 登录成功！(等待了 {i+1} 秒)")
            cookies = context.cookies()
            with open(COOKIES_FILE, "w") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            return True
        if i > 0 and i % 30 == 0:
            print(f"[*] 仍在等待... ({i}/{max_wait}s)")
    return False


def _extract_jobs(page):
    jobs = []
    try:
        page.wait_for_selector(".job-card-wrap", timeout=10000)
    except Exception:
        content = page.content()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "debug_page.html"), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[-] 未找到职位卡片，页面已保存到 {DATA_DIR}/debug_page.html")
        return jobs

    time.sleep(1)
    # 滚动加载
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)

    cards = page.query_selector_all(".job-card-wrap")
    for card in cards:
        try:
            job = {}
            el = card.query_selector(".job-name")
            job["title"] = el.inner_text().strip() if el else ""

            el = card.query_selector(".job-salary")
            job["salary"] = el.inner_text().strip() if el else ""

            el = card.query_selector(".company-location")
            job["location"] = el.inner_text().strip() if el else ""

            # 公司名（卡片右侧公司区域）
            company_el = card.query_selector(".company-name a")
            job["company"] = company_el.inner_text().strip() if company_el else ""

            # Boss 信息（姓名/职位）
            el = card.query_selector(".boss-name")
            job["boss_info"] = el.inner_text().strip() if el else ""

            el = card.query_selector("a[href*='job_detail']")
            if el:
                href = el.get_attribute("href") or ""
                job["link"] = href if href.startswith("http") else f"{BOSS_URL}{href}"
            else:
                job["link"] = ""

            tags_el = card.query_selector_all(".tag-list li")
            job["tags"] = [t.inner_text().strip() for t in tags_el if t.inner_text().strip()]

            el = card.query_selector(".boss-online-icon")
            job["online"] = el is not None

            # Boss头像链接可能是公司页面
            company_el = card.query_selector("a[href*='/gongsi/']")
            if company_el:
                company_href = company_el.get_attribute("href") or ""
                job["company_link"] = company_href if company_href.startswith("http") else f"{BOSS_URL}{company_href}"
            else:
                job["company_link"] = ""

            if job["title"]:
                jobs.append(job)
        except Exception:
            continue
    return jobs


def _fetch_job_detail(page, job):
    """访问职位详情页，提取完整 JD 文本、公司信息和公司地址"""
    link = job.get("link", "")
    if not link:
        return job

    try:
        page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # 提取 JD 文本
        jd_parts = []
        for selector in [".job-sec-text", ".job-detail-section", ".job-desc"]:
            els = page.query_selector_all(selector)
            for el in els:
                text = el.inner_text().strip()
                if text:
                    jd_parts.append(text)
        if jd_parts:
            job["jd_text"] = "\n".join(jd_parts)

        # 提取公司详情
        company_info = {}
        for item in page.query_selector_all(".job-company-info li, .company-info li"):
            text = item.inner_text().strip()
            if "行业" in text:
                company_info["industry"] = text.split("行业")[-1].strip().lstrip("：:")
            elif "规模" in text or "人数" in text:
                company_info["size"] = text.split("规模")[-1].split("人数")[-1].strip().lstrip("：:")
            elif "融资" in text:
                company_info["stage"] = text.split("融资")[-1].strip().lstrip("：:")

        if company_info.get("industry"):
            job["company_industry"] = company_info["industry"]
        if company_info.get("size"):
            job["company_size"] = company_info["size"]
        if company_info.get("stage"):
            job["company_stage"] = company_info["stage"]

        # 提取详情页中的工作地址
        el = page.query_selector(".job-location")
        if el:
            addr = el.inner_text().strip()
            # 清理多余文本（"点击查看地图" 等）
            addr = addr.replace("点击查看地图", "").strip()
            if addr and len(addr) > 2:
                job["work_address"] = addr

    except Exception as e:
        print(f"    [-] 详情抓取失败: {e}")

    return job


def _enrich_with_details(ctx, all_jobs):
    """逐个访问详情页，丰富职位数据"""
    page = ctx.new_page()
    total = len(all_jobs)

    print(f"\n{'='*60}")
    print(f"  开始抓取 JD 详情: 共 {total} 个职位")
    print(f"{'='*60}")

    for i, job in enumerate(all_jobs):
        link = job.get("link", "")
        if not link:
            continue

        print(f"  [{i+1}/{total}] {job.get('title', '')} - {job.get('company', '')}")
        _fetch_job_detail(page, job)

        # 延迟避免触发限制
        delay = 3 + (i % 3)
        time.sleep(delay)

    page.close()
    print(f"[+] JD 详情抓取完成")
    return all_jobs


def _save_and_show(all_jobs, keyword, city):
    os.makedirs(DATA_DIR, exist_ok=True)
    output_file = os.path.join(DATA_DIR, f"jobs_boss_{keyword}_{city}_{int(time.time())}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"  共 {len(all_jobs)} 个职位 → {output_file}")
    print(f"{'='*70}")
    for i, job in enumerate(all_jobs[:25], 1):
        tags = " | ".join(job.get("tags", []))
        online = "🟢" if job.get("online") else ""
        print(f"  {i:3d}. {online} {job['title']}")
        print(f"       {job['salary']}  {job['company']}  {job['location']}")
        if tags:
            print(f"       {tags}")
    if len(all_jobs) > 25:
        print(f"  ... 还有 {len(all_jobs) - 25} 个")
    print(f"{'='*70}")
    return output_file


def run(keyword="Java开发", city="北京", pages=3, salary="", experience="",
        degree="", scale="", stage="", fetch_detail=True):
    from cloakbrowser import launch_persistent_context

    city_code = get_city_code(city)

    # 构建基础搜索参数
    params = {"query": keyword, "city": city_code}
    if salary:
        params["salary"] = salary
    if experience:
        params["experience"] = experience
    if degree:
        params["degree"] = degree
    if scale:
        params["scale"] = scale
    if stage:
        params["stage"] = stage

    print(f"\n{'='*60}")
    print(f"  Boss直聘: {keyword} @ {city}")
    filter_desc = []
    if salary: filter_desc.append(f"薪资={salary}")
    if experience: filter_desc.append(f"经验={experience}")
    if degree: filter_desc.append(f"学历={degree}")
    if scale: filter_desc.append(f"规模={scale}")
    if stage: filter_desc.append(f"融资={stage}")
    if filter_desc:
        print(f"  筛选: {', '.join(filter_desc)}")
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

    # 1. 先访问第一页，检查登录状态
    params["page"] = 1
    first_url = f"{BOSS_URL}/web/geek/jobs?{urlencode(params)}"
    print(f"[*] 正在打开: {first_url}")
    page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    if not _is_logged_in(ctx):
        print("[!] 需要登录，请在浏览器中扫码")
        if _wait_for_login(ctx, page):
            time.sleep(2)
            page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        else:
            print("[-] 登录超时")
            ctx.close()
            return []
    else:
        print("[+] 已登录，开始爬取")

    # 2. 逐页爬取
    all_jobs = []
    seen_links = set()

    for page_num in range(1, pages + 1):
        if page_num > 1:
            params["page"] = page_num
            url = f"{BOSS_URL}/web/geek/jobs?{urlencode(params)}"
            print(f"\n[*] 第 {page_num} 页: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

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

        # 页间延迟，避免触发频率限制
        if page_num < pages:
            delay = 2 + (page_num % 3)
            print(f"[*] 等待 {delay} 秒...")
            time.sleep(delay)

    # 3. 抓取 JD 详情
    if fetch_detail and all_jobs:
        _enrich_with_details(ctx, all_jobs)

    # 4. 保存结果
    cookies = ctx.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

    ctx.close()

    if all_jobs:
        output_file = _save_and_show(all_jobs, keyword, city)
        print(f"\n[+] 数据已保存，可直接用于 job-matcher 匹配")
        return all_jobs
    else:
        print("[-] 未获取到职位数据")
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Boss直聘爬取 (CloakBrowser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
筛选代码:
  薪资: 405=40-50K  505=50K+  306=30-40K  205=20-30K
  经验: 101=应届  104=1-3年  105=3-5年  106=5-10年  107=10年+
  学历: 209=大专  206=本科  207=硕士  208=博士
  规模: 303=100-499人  304=500-999人  305=1000-9999人  306=10000人+
  融资: 807=已上市  806=D轮+  808=不需融资

示例:
  python3 boss_cloak.py --keyword "产品经理" --city "上海" --pages 5
  python3 boss_cloak.py --keyword "Java" --city "北京" --salary 405 --experience 105 --degree 206
        """,
    )
    parser.add_argument("--keyword", type=str, default="Java开发", help="搜索关键词")
    parser.add_argument("--city", type=str, default="北京", help="城市")
    parser.add_argument("--pages", type=int, default=3, help="爬取页数 (默认3页)")
    parser.add_argument("--salary", type=str, default="", help="薪资代码")
    parser.add_argument("--experience", type=str, default="", help="经验代码")
    parser.add_argument("--degree", type=str, default="", help="学历代码")
    parser.add_argument("--scale", type=str, default="", help="公司规模代码")
    parser.add_argument("--stage", type=str, default="", help="融资阶段代码")
    parser.add_argument("--no-detail", action="store_true", help="不抓取 JD 详情页")

    args = parser.parse_args()
    run(args.keyword, args.city, args.pages, args.salary, args.experience,
        args.degree, args.scale, args.stage, fetch_detail=not args.no_detail)


if __name__ == "__main__":
    main()
