# get_proxy.py — Enhanced Proxy Manager v2.0
import requests
import uuid
import time
import logging
import threading
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import urllib3

urllib3.disable_warnings()

# ═══════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════
logger = logging.getLogger("proxy_manager")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "\033[90m%(asctime)s\033[0m │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(_handler)


# ═══════════════════════════════════════════════════════
#  AntPeak Proxy Provider
# ═══════════════════════════════════════════════════════
_antpeak_cache: Dict[str, Any] = {
    "token": None,
    "expire": 0,
    "proxy_url": None,
    "proxy_time": 0,
    "lock": threading.Lock(),
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)


def _fetch_antpeak_token() -> Optional[str]:
    """Lấy access token từ AntPeak, cache 10 phút."""
    now = time.time()
    with _antpeak_cache["lock"]:
        if _antpeak_cache["token"] and now < _antpeak_cache["expire"]:
            logger.debug("🔑 AntPeak token (cached)")
            return _antpeak_cache["token"]

    logger.info("🔄 Đang lấy AntPeak token mới...")
    sess = requests.Session()
    sess.headers = {"Content-Type": "application/json", "User-Agent": UA}

    for attempt in range(3):
        try:
            r = sess.post(
                "https://antpeak.com/api/launch/",
                json={
                    "udid": str(uuid.uuid4()),
                    "appVersion": "2.1.7",
                    "platform": "chrome",
                    "platformVersion": UA,
                    "timeZone": "Asia/Ho_Chi_Minh",
                    "deviceName": "Chrome 148",
                },
                timeout=10,
                verify=False,
            )
            if not r.ok:
                logger.warning(f"  ⚠ AntPeak launch HTTP {r.status_code} (lần {attempt+1})")
                time.sleep(1 * (attempt + 1))
                continue

            token = r.json().get("data", {}).get("accessToken")
            if token:
                with _antpeak_cache["lock"]:
                    _antpeak_cache["token"] = token
                    _antpeak_cache["expire"] = now + 600
                logger.info("  ✅ AntPeak token OK")
                return token
            else:
                logger.warning("  ⚠ AntPeak response thiếu accessToken")
        except requests.RequestException as e:
            logger.warning(f"  ⚠ AntPeak lần {attempt+1} lỗi: {e}")
            time.sleep(1 * (attempt + 1))

    logger.error("  ❌ Không lấy được AntPeak token sau 3 lần")
    return None


def _test_proxy_latency(proxy_url: str, timeout: float = 5.0) -> float:
    """Kiểm tra latency của proxy (giây). Trả về 999 nếu fail."""
    start = time.time()
    try:
        r = requests.get(
            "http://cp.cloudflare.com/generate_204",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=timeout,
            verify=False,
        )
        if r.status_code == 204:
            lat = round(time.time() - start, 3)
            return lat
    except Exception:
        pass
    return 999.0


def fetch_antpeak_sg_proxy() -> Optional[str]:
    """Trả về proxy SG nhanh nhất từ AntPeak, cache 1 phút."""
    now = time.time()
    with _antpeak_cache["lock"]:
        if _antpeak_cache["proxy_url"] and (now - _antpeak_cache["proxy_time"]) < 60:
            logger.debug("🌐 AntPeak SG proxy (cached)")
            return _antpeak_cache["proxy_url"]

    token = _fetch_antpeak_token()
    if not token:
        return None

    logger.info("🔍 Đang tìm AntPeak SG proxy...")
    sess = requests.Session()
    sess.headers = {
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Authorization": f"Bearer {token}",
    }

    try:
        r = sess.post(
            "https://antpeak.com/api/server/list/",
            json={"protocol": "https", "region": "sg", "type": 0},
            timeout=10,
            verify=False,
        )
        if not r.ok:
            logger.warning(f"  ⚠ AntPeak server list HTTP {r.status_code}")
            return None

        servers = r.json().get("data", [])
        if not servers:
            logger.warning("  ⚠ Không có server SG nào")
            return None

        # Xây dựng danh sách candidates
        candidates = []
        for srv in servers:
            addr = (srv.get("addresses") or [None])[0]
            if srv.get("username") and srv.get("password") and srv.get("port") and addr:
                candidates.append(
                    f"https://{srv['username']}:{srv['password']}@{addr}:{srv['port']}"
                )

        if not candidates:
            logger.warning("  ⚠ Không có candidate proxy SG hợp lệ")
            return None

        logger.info(f"  📡 Đang test {min(5, len(candidates))} proxy SG...")

        # Test song song, chọn proxy nhanh nhất
        best: Optional[str] = None
        best_latency = 999.0

        with ThreadPoolExecutor(max_workers=min(5, len(candidates))) as executor:
            futures = {
                executor.submit(_test_proxy_latency, c): c
                for c in candidates[:5]
            }
            for future in as_completed(futures):
                proxy_url = futures[future]
                lat = future.result()
                if lat < best_latency:
                    best_latency = lat
                    best = proxy_url

        if best:
            with _antpeak_cache["lock"]:
                _antpeak_cache["proxy_url"] = best
                _antpeak_cache["proxy_time"] = now
            logger.info(f"  ✅ Best SG proxy: {best_latency:.3f}s")
        else:
            logger.warning("  ⚠ Tất cả proxy SG đều timeout")
        return best

    except requests.RequestException as e:
        logger.error(f"  ❌ AntPeak server list error: {e}")
        return None


# ═══════════════════════════════════════════════════════
#  UrbanVPN Proxy Provider (với cache + validation)
# ═══════════════════════════════════════════════════════
class UrbanVpnProxy:
    """Lấy proxy từ UrbanVPN (qua AntPeak tunnel) với caching thông minh."""

    _vn_cache: Dict[str, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()

    CACHE_TTL = 240  # 4 phút

    def __init__(self, external_proxy: Optional[str] = None):
        self.api_base = "https://api-pro.falais.com/rest/v1"
        self.stats_base = "https://stats.falais.com/api/rest/v2"
        self.client_app = "URBAN_VPN_BROWSER_EXTENSION"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        })

        # Nếu không có external_proxy → tự lấy AntPeak
        if external_proxy is None:
            external_proxy = fetch_antpeak_sg_proxy()
        if external_proxy:
            self.session.proxies = {"http": external_proxy, "https": external_proxy}
            logger.debug(f"🔗 UrbanVPN qua external proxy")
        else:
            logger.warning("⚠ UrbanVPN không có external proxy — kết nối trực tiếp")

    # ─── Internal API calls ─────────────────────────────

    def _register_anonymous(self) -> str:
        url = f"{self.api_base}/registrations/clientApps/{self.client_app}/users/anonymous"
        payload = {"clientApp": {"name": self.client_app}}
        resp = self.session.post(url, json=payload, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()["value"]

    def _get_security_token(self, auth_token: str) -> str:
        url = f"{self.api_base}/security/tokens/accs"
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"type": "accs", "clientApp": {"name": self.client_app}}
        resp = self.session.post(url, json=payload, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()["value"]

    def _get_countries(self, jwt_token: str) -> dict:
        url = f"{self.stats_base}/entrypoints/countries"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "X-Client-App": self.client_app,
        }
        resp = self.session.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()

    def _get_proxy_token(self, jwt_token: str, signature: str) -> str:
        url = f"{self.api_base}/security/tokens/accs-proxy"
        headers = {"Authorization": f"Bearer {jwt_token}"}
        payload = {
            "type": "accs-proxy",
            "clientApp": {"name": self.client_app},
            "signature": signature,
        }
        resp = self.session.post(url, json=payload, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()["value"]

    # ─── Public API ─────────────────────────────────────

    def get_proxies_by_country(
        self,
        country_code: str = "US",
        validate: bool = False,
        max_proxies: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách proxy theo quốc gia.
        - validate=True: test latency và sắp xếp theo tốc độ
        - max_proxies: giới hạn số lượng proxy trả về
        """
        country_code = country_code.upper()
        now = time.time()

        # Kiểm tra cache
        with self._cache_lock:
            cached = self._vn_cache.get(country_code)
            if cached and now < cached["expire"]:
                logger.info(f"📦 Cache hit: {country_code} ({len(cached['proxies'])} proxies)")
                return cached["proxies"][:max_proxies]

        logger.info(f"🌍 Đang lấy proxy {country_code} từ UrbanVPN...")

        try:
            auth_token = self._register_anonymous()
            jwt = self._get_security_token(auth_token)
            countries_data = self._get_countries(jwt)
        except Exception as e:
            logger.error(f"  ❌ UrbanVPN auth/countries lỗi: {e}")
            return []

        # Tìm country
        target_servers = []
        country_name = None
        for country in countries_data.get("countries", {}).get("elements", []):
            code = country.get("code", {}).get("iso2", "")
            if code.upper() == country_code:
                country_name = country.get("title")
                servers = country.get("servers", {}).get("elements", [])
                target_servers = servers
                break

        if not target_servers:
            logger.warning(f"  ⚠ Không tìm thấy country {country_code}")
            return []

        logger.info(f"  📡 {country_name}: {len(target_servers)} servers, đang xử lý...")

        # Xử lý song song
        proxies: List[Dict[str, Any]] = []

        def process_server(server: dict) -> List[Dict[str, Any]]:
            results = []
            signature = server.get("signature")
            if not signature:
                return []
            try:
                proxy_username = self._get_proxy_token(jwt, signature)
            except Exception as e:
                logger.debug(f"    ⚠ Proxy token lỗi: {e}")
                return []

            addr = server.get("address", {})
            primary = addr.get("primary")
            if primary:
                results.append({
                    "host": primary.get("host"),
                    "port": primary.get("port"),
                    "scheme": primary.get("scheme", "http"),
                    "username": proxy_username,
                    "password": "1",
                    "country": country_name,
                    "code": country_code,
                })
            for secondary in addr.get("secondary", []):
                results.append({
                    "host": secondary.get("host"),
                    "port": secondary.get("port"),
                    "scheme": secondary.get("scheme", "http"),
                    "username": proxy_username,
                    "password": "1",
                    "country": country_name,
                    "code": country_code,
                })
            return results

        with ThreadPoolExecutor(max_workers=min(10, len(target_servers))) as executor:
            futures = {executor.submit(process_server, s): s for s in target_servers}
            for future in as_completed(futures):
                try:
                    proxies.extend(future.result())
                except Exception as e:
                    logger.debug(f"    ⚠ Server processing error: {e}")

        logger.info(f"  📊 Tìm được {len(proxies)} proxy {country_code}")

        # Validate nếu cần
        if validate and proxies:
            logger.info(f"  🧪 Đang validate {min(10, len(proxies))} proxy...")
            validated = self._validate_proxies(proxies[:10])
            if validated:
                proxies = validated + [p for p in proxies if p not in validated]
                logger.info(f"  ✅ {len(validated)} proxy hoạt động tốt")

        # Lưu cache
        with self._cache_lock:
            self._vn_cache[country_code] = {
                "proxies": proxies,
                "expire": now + self.CACHE_TTL,
            }

        return proxies[:max_proxies]

    def _validate_proxies(
        self, proxies: List[Dict[str, Any]], timeout: float = 6.0
    ) -> List[Dict[str, Any]]:
        """Test latency và trả về danh sách proxy sắp xếp theo tốc độ."""
        results: List[tuple] = []

        def test_one(proxy_info: dict) -> tuple:
            safe_user = quote(proxy_info["username"], safe="")
            safe_pass = quote(proxy_info["password"], safe="")
            url = f"{proxy_info['scheme']}://{safe_user}:{safe_pass}@{proxy_info['host']}:{proxy_info['port']}"
            lat = _test_proxy_latency(url, timeout)
            return (proxy_info, lat)

        with ThreadPoolExecutor(max_workers=min(5, len(proxies))) as executor:
            futures = [executor.submit(test_one, p) for p in proxies]
            for future in as_completed(futures):
                info, lat = future.result()
                if lat < 900:
                    info["latency_ms"] = int(lat * 1000)
                    results.append((info, lat))

        results.sort(key=lambda x: x[1])
        return [r[0] for r in results]

    def invalidate_cache(self, country_code: str = "VN"):
        """Xóa cache cho country cụ thể."""
        with self._cache_lock:
            self._vn_cache.pop(country_code.upper(), None)
        logger.info(f"🗑️ Đã xóa cache proxy {country_code}")

    @classmethod
    def clear_all_cache(cls):
        """Xóa toàn bộ cache."""
        with cls._cache_lock:
            cls._vn_cache.clear()
        logger.info("🗑️ Đã xóa toàn bộ proxy cache")