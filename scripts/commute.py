#!/usr/bin/env python3
"""
通勤计算工具 - 支持腾讯地图和高德地图 API

功能：
1. 地址 → 经纬度（地理编码）
2. 两地通勤距离/时间（驾车/公交）
3. 结果缓存，避免重复 API 调用

用法:
  # 腾讯地图
  from commute import configure, calculate_commute
  configure(api_key="YOUR_TENCENT_KEY", provider="tencent")

  # 高德地图
  configure(api_key="YOUR_AMAP_KEY", provider="amap")

  result = calculate_commute("北京市朝阳区望京SOHO", "北京市海淀区中关村", mode="driving")
  # → {"distance_km": 12.3, "duration_min": 25}
"""

import json
import os
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "data", ".commute_cache.json")

_api_key = ""
_provider = "tencent"  # 默认腾讯


def configure(api_key, provider="tencent"):
    global _api_key, _provider
    _api_key = api_key
    _provider = provider


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


def _api_get(url, params):
    params["key"] = _api_key
    qs = urllib.parse.urlencode(params)
    full_url = f"{url}?{qs}"
    req = urllib.request.Request(full_url, headers={"User-Agent": "JobMatcher/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── 腾讯地图 ──────────────────────────────────────────────

def _tencent_geocode(address):
    data = _api_get("https://apis.map.qq.com/ws/geocoder/v1/", {"address": address})
    if data.get("status") != 0:
        return None
    loc = data["result"]["location"]
    city = data["result"].get("ad_info", {}).get("city", "")
    return {"lat": loc["lat"], "lng": loc["lng"], "city": city}


def _tencent_route(from_loc, to_loc, mode):
    from_str = f"{from_loc['lat']},{from_loc['lng']}"
    to_str = f"{to_loc['lat']},{to_loc['lng']}"

    if mode == "transit":
        city = from_loc.get("city", "")
        params = {"from": from_str, "to": to_str, "city": city}
        data = _api_get("https://apis.map.qq.com/ws/direction/v1/transit/", params)
    else:
        params = {"from": from_str, "to": to_str}
        data = _api_get("https://apis.map.qq.com/ws/direction/v1/driving/", params)

    if data.get("status") != 0:
        return None

    routes = data.get("result", {}).get("routes", [])
    if not routes:
        return None

    route = routes[0]
    return {
        "distance_km": round(route.get("distance", 0) / 1000, 1),
        "duration_min": round(route.get("duration", 0) / 60),
    }


# ── 高德地图 ──────────────────────────────────────────────

def _amap_geocode(address):
    data = _api_get("https://restapi.amap.com/v3/geocode/geo", {"address": address})
    if data.get("status") != "1" or not data.get("geocodes"):
        return None
    geo = data["geocodes"][0]
    location = geo["location"]  # "lng,lat"
    lng, lat = location.split(",")
    city = geo.get("city", "") or ""
    return {"lat": float(lat), "lng": float(lng), "city": city}


def _amap_route(from_loc, to_loc, mode):
    origin = f"{from_loc['lng']},{from_loc['lat']}"
    destination = f"{to_loc['lng']},{to_loc['lat']}"

    if mode == "transit":
        city = from_loc.get("city", "")
        params = {"origin": origin, "destination": destination, "city": city}
        data = _api_get("https://restapi.amap.com/v3/direction/transit/integrated", params)
        if data.get("status") != "1":
            return None
        routes = data.get("route", {}).get("transits", [])
        if not routes:
            return None
        route = routes[0]
        distance = float(route.get("distance", 0))
        duration = float(route.get("duration", 0))
    else:
        params = {"origin": origin, "destination": destination}
        data = _api_get("https://restapi.amap.com/v3/direction/driving", params)
        if data.get("status") != "1":
            return None
        routes = data.get("route", {}).get("paths", [])
        if not routes:
            return None
        route = routes[0]
        distance = float(route.get("distance", 0))
        duration = float(route.get("duration", 0))

    return {
        "distance_km": round(distance / 1000, 1),
        "duration_min": round(duration / 60),
    }


# ── 公共接口 ──────────────────────────────────────────────

def geocode(address):
    """地址 → {"lat": float, "lng": float, "city": str} 或 None"""
    cache = _load_cache()
    key = f"geo:{_provider}:{address}"
    if key in cache:
        return cache[key]

    if _provider == "amap":
        result = _amap_geocode(address)
    else:
        result = _tencent_geocode(address)

    if result:
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
    cache_key = f"route:{_provider}:{mode}:{from_addr}→{to_addr}"
    if cache_key in cache:
        return cache[cache_key]

    if _provider == "amap":
        result = _amap_route(from_loc, to_loc, mode)
    else:
        result = _tencent_route(from_loc, to_loc, mode)

    if result:
        cache[cache_key] = result
        _save_cache(cache)
    time.sleep(0.25)
    return result
