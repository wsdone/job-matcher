#!/usr/bin/env python3
"""
通勤计算工具 - 腾讯地图 Web Service API

功能：
1. 地址 → 经纬度（地理编码）
2. 两地通勤距离/时间（驾车/公交）
3. 结果缓存，避免重复 API 调用
"""

import json
import os
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "data", ".commute_cache.json")

_api_key = ""


def configure(api_key):
    global _api_key
    _api_key = api_key


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _api_get(path, params):
    params["key"] = _api_key
    qs = urllib.parse.urlencode(params)
    url = f"https://apis.map.qq.com/ws{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "JobMatcher/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(address):
    """地址 → {"lat": float, "lng": float, "city": str} 或 None"""
    cache = _load_cache()
    key = f"geo:{address}"
    if key in cache:
        return cache[key]

    data = _api_get("/ws/geocoder/v1/", {"address": address})
    if data.get("status") != 0:
        return None

    loc = data["result"]["location"]
    city = data["result"].get("ad_info", {}).get("city", "")
    result = {"lat": loc["lat"], "lng": loc["lng"], "city": city}

    cache[key] = result
    _save_cache(cache)
    time.sleep(0.2)
    return result


def calculate_commute(from_addr, to_addr, mode="driving"):
    """
    计算两地通勤距离和时间。

    mode: "driving" 或 "transit"
    返回: {"distance_km": float, "duration_min": int} 或 None
    """
    from_loc = geocode(from_addr)
    to_loc = geocode(to_addr)

    if not from_loc or not to_loc:
        return None

    cache = _load_cache()
    cache_key = f"route:{mode}:{from_addr}→{to_addr}"
    if cache_key in cache:
        return cache[cache_key]

    from_str = f"{from_loc['lat']},{from_loc['lng']}"
    to_str = f"{to_loc['lat']},{to_loc['lng']}"

    if mode == "transit":
        city = from_loc.get("city", "")
        params = {"from": from_str, "to": to_str, "city": city}
        data = _api_get("/ws/direction/v1/transit/", params)
    else:
        params = {"from": from_str, "to": to_str}
        data = _api_get("/ws/direction/v1/driving/", params)

    if data.get("status") != 0:
        return None

    routes = data.get("result", {}).get("routes", [])
    if not routes:
        return None

    route = routes[0]
    result = {
        "distance_km": round(route.get("distance", 0) / 1000, 1),
        "duration_min": round(route.get("duration", 0) / 60),
    }

    cache[cache_key] = result
    _save_cache(cache)
    time.sleep(0.25)
    return result
