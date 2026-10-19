# !/usr/bin/env python
"""
Date: 2025/12/31
Desc: HTTP 请求工具函数

Eastmoney session environment variables:
- AKSHARE_EASTMONEY_COOKIE: Cookie header value; takes precedence over files.
- AKSHARE_EASTMONEY_COOKIE_FILE: Cookie cache path
  (default: ~/.cache/akshare/eastmoney_cookie.txt).
- AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND: command that prints a fresh Cookie
  header; run after a session failure before the request is retried.
- AKSHARE_EASTMONEY_COOKIE_REFRESH_TIMEOUT: refresh timeout in seconds (default 120).
- AKSHARE_EASTMONEY_INTERACTIVE_AUTH: open a browser for manual verification
  when no refresh command produces a Cookie; defaults to on for interactive
  desktop terminals with Selenium installed.
"""

import random
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

_EASTMONEY_DELAY_HOST = "push2delay.eastmoney.com"
_EASTMONEY_PUSH_HOSTS = (
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
)
_EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json,text/plain,*/*",
}
_EASTMONEY_FAILED_HOSTS: dict[tuple[str, str], float] = {}
_EASTMONEY_FAILURE_COOLDOWN = 60.0
_EASTMONEY_COOKIE_REFRESH_LOCK = threading.Lock()
_EASTMONEY_COOKIE_REFRESH_INTERVAL = 60.0
_EASTMONEY_LAST_COOKIE_REFRESH = 0.0
_SZSE_FAILED_HOSTS: set[str] = set()
_SZSE_HOST = "www.szse.cn"
_SZSE_DEFAULT_RESOLVE_IPS = ("113.108.107.138",)
_SZSE_DEFAULT_RESOLVE_IPS_BY_HOST = {
    _SZSE_HOST: _SZSE_DEFAULT_RESOLVE_IPS,
    "investor.szse.cn": ("58.251.50.138", "113.108.107.138"),
    "www.sse.org.cn": ("58.251.50.138", "113.108.107.138"),
}
_DEFAULT_BROWSER_UA = "Mozilla/5.0"


def _reset_eastmoney_fallback_cache() -> None:
    global _EASTMONEY_LAST_COOKIE_REFRESH
    _EASTMONEY_FAILED_HOSTS.clear()
    _EASTMONEY_LAST_COOKIE_REFRESH = 0.0


def _eastmoney_cookie_path() -> Path | None:
    if os.environ.get("AKSHARE_EASTMONEY_COOKIE") is not None:
        return None
    configured_path = os.environ.get("AKSHARE_EASTMONEY_COOKIE_FILE")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".cache" / "akshare" / "eastmoney_cookie.txt"


def _validate_eastmoney_cookie(cookie: str) -> str:
    cookie = cookie.strip()
    if not cookie:
        return ""
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[len("cookie:") :].strip()
    if "\r" in cookie or "\n" in cookie:
        raise ValueError("Eastmoney Cookie must be a single-line HTTP header value")
    if "=" not in cookie:
        raise ValueError("Eastmoney Cookie must contain name=value pairs")
    return cookie


def _get_eastmoney_cookie() -> str:
    cookie = os.environ.get("AKSHARE_EASTMONEY_COOKIE")
    if cookie is None:
        cookie_path = _eastmoney_cookie_path()
        if cookie_path is None:
            return ""
        if not cookie_path.exists() and not os.environ.get(
            "AKSHARE_EASTMONEY_COOKIE_FILE"
        ):
            return ""
        cookie = cookie_path.read_text(encoding="utf-8")
    return _validate_eastmoney_cookie(cookie)


def _save_eastmoney_cookie(cookie: str) -> None:
    cookie_path = _eastmoney_cookie_path()
    if cookie_path is None:
        return
    cookie_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=cookie_path.parent,
        prefix=".eastmoney-cookie-",
        delete=False,
    )
    try:
        with temporary:
            temporary.write(cookie)
        os.chmod(temporary.name, 0o600)
        os.replace(temporary.name, cookie_path)
    except BaseException:
        Path(temporary.name).unlink(missing_ok=True)
        raise


def _eastmoney_cookie_refresh_timeout() -> float:
    try:
        return max(
            1.0,
            float(os.environ.get("AKSHARE_EASTMONEY_COOKIE_REFRESH_TIMEOUT", "120")),
        )
    except ValueError:
        return 120.0


def _interactive_eastmoney_auth_enabled() -> bool:
    configured = os.environ.get("AKSHARE_EASTMONEY_INTERACTIVE_AUTH")
    if configured is not None:
        return configured.strip().lower() not in {"", "0", "false", "no", "off"}
    if not sys.stdout.isatty():
        return False
    if platform.system() in {"Darwin", "Windows"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _refresh_eastmoney_cookie_with_command(timeout: float) -> str:
    command = os.environ.get("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "").strip()
    if not command:
        return ""
    try:
        result = subprocess.run(
            shlex.split(command, posix=platform.system() != "Windows"),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    try:
        return _validate_eastmoney_cookie(result.stdout)
    except ValueError:
        return ""


def _refresh_eastmoney_cookie_with_browser(timeout: float) -> str:
    if not _interactive_eastmoney_auth_enabled():
        return ""
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
    except ImportError:
        return ""
    if sys.stderr.isatty():
        print(
            "Eastmoney session expired; complete the browser verification to refresh it.",
            file=sys.stderr,
            flush=True,
        )
    driver = None
    try:
        driver = webdriver.Chrome()
        driver.set_page_load_timeout(30)
        driver.get("https://quote.eastmoney.com/")
        driver.set_script_timeout(8)
        verification = """
            const done = arguments[arguments.length - 1];
            fetch(
              'https://push2his.eastmoney.com/api/qt/stock/kline/get'
              + '?secid=0.000001&klt=101&fqt=1&lmt=1&end=20500101'
              + '&fields1=f1&fields2=f51,f52&ut=fa5fd1943c7b386f172d6893dbfba10b',
              {credentials: 'include'}
            ).then(r => r.json()).then(data => done(data.rc === 0))
             .catch(() => done(false));
        """
        deadline = time.monotonic() + timeout
        next_check = time.monotonic()
        while time.monotonic() < deadline:
            if time.monotonic() >= next_check:
                try:
                    if driver.execute_async_script(verification):
                        cookies = {
                            item["name"]: item["value"]
                            for item in driver.get_cookies()
                            if item.get("domain", "")
                            .lstrip(".")
                            .endswith("eastmoney.com")
                        }
                        return _validate_eastmoney_cookie(
                            "; ".join(f"{k}={v}" for k, v in cookies.items())
                        )
                except WebDriverException:
                    pass
                next_check = time.monotonic() + 5
            time.sleep(1)
        return ""
    except (WebDriverException, OSError):
        return ""
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _refresh_eastmoney_cookie(previous_cookie: str) -> str:
    global _EASTMONEY_LAST_COOKIE_REFRESH
    try:
        current_cookie = _get_eastmoney_cookie()
    except (OSError, ValueError):
        current_cookie = ""
    if current_cookie and current_cookie != previous_cookie:
        return current_cookie
    now = time.monotonic()
    if now - _EASTMONEY_LAST_COOKIE_REFRESH < _EASTMONEY_COOKIE_REFRESH_INTERVAL:
        return ""
    with _EASTMONEY_COOKIE_REFRESH_LOCK:
        try:
            current_cookie = _get_eastmoney_cookie()
        except (OSError, ValueError):
            current_cookie = ""
        if current_cookie and current_cookie != previous_cookie:
            return current_cookie
        now = time.monotonic()
        if now - _EASTMONEY_LAST_COOKIE_REFRESH < _EASTMONEY_COOKIE_REFRESH_INTERVAL:
            return ""
        _EASTMONEY_LAST_COOKIE_REFRESH = now
        timeout = _eastmoney_cookie_refresh_timeout()
        refreshed = _refresh_eastmoney_cookie_with_command(timeout)
        if not refreshed:
            refreshed = _refresh_eastmoney_cookie_with_browser(timeout)
        if refreshed and refreshed != previous_cookie:
            try:
                _save_eastmoney_cookie(refreshed)
            except OSError:
                pass
            return refreshed
    return ""


def _is_eastmoney_cookie_failure(exc: BaseException | None) -> bool:
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code in {401, 403}
    if isinstance(exc, requests.Timeout):
        return True
    if isinstance(exc, requests.ConnectionError):
        message = repr(exc)
        return any(
            marker in message
            for marker in (
                "RemoteDisconnected",
                "Connection aborted",
                "Connection reset",
                "Empty reply",
                "timed out",
            )
        )
    return False


def _eastmoney_curl_interface() -> str:
    raw = os.environ.get("AKSHARE_EASTMONEY_CURL_INTERFACE", "").strip()
    if raw:
        return "" if raw.lower() in {"0", "false", "no", "off"} else raw
    if os.environ.get("AKSHARE_EASTMONEY_AUTO_CURL_INTERFACE", "1").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return ""
    return "en0" if platform.system() == "Darwin" else ""


def _szse_curl_interface() -> str:
    raw = os.environ.get("AKSHARE_SZSE_CURL_INTERFACE", "").strip()
    if raw:
        return "" if raw.lower() in {"0", "false", "no", "off"} else raw
    if os.environ.get("AKSHARE_SZSE_AUTO_CURL_INTERFACE", "1").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return ""
    return "en0" if platform.system() == "Darwin" else ""


def _szse_resolve_ips(host: str = _SZSE_HOST) -> list[str]:
    raw = os.environ.get("AKSHARE_SZSE_RESOLVE_IPS")
    if raw is not None:
        if raw.strip().lower() in {"0", "false", "no", "off"}:
            return []
        return [
            item.strip() for item in raw.replace(";", ",").split(",") if item.strip()
        ]
    if os.environ.get("AKSHARE_SZSE_AUTO_RESOLVE", "1").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return []
    return list(_SZSE_DEFAULT_RESOLVE_IPS_BY_HOST.get(host, ()))


def _request_hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _is_push2his_url(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host == "push2his.eastmoney.com" or host.endswith(".push2his.eastmoney.com")


def _eastmoney_failed_host_key(host: str) -> str:
    host = host.lower()
    for item in _EASTMONEY_PUSH_HOSTS:
        if host == item or host.endswith(f".{item}"):
            return item
    return host


def _prepared_get_url(url: str, params: Dict | None) -> str:
    request = requests.Request("GET", url, params=params)
    return request.prepare().url


def _request_eastmoney_with_curl_interface(
    url: str,
    params: Dict | None,
    headers: Dict,
    timeout: int | float | None,
    interface: str,
) -> requests.Response:
    curl_bin = os.environ.get("AKSHARE_EASTMONEY_CURL_BIN") or shutil.which("curl")
    if not curl_bin:
        raise requests.ConnectionError("curl executable not found")
    prepared_url = _prepared_get_url(url, params)
    effective_timeout = timeout if timeout is not None else 15
    max_time = str(effective_timeout)
    marker = "AKSHARE_HTTP_STATUS:"
    command = [
        curl_bin,
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        max_time,
        "--interface",
        interface,
        "-A",
        headers.get("User-Agent", _EASTMONEY_HEADERS["User-Agent"]),
        "-e",
        headers.get("Referer", _EASTMONEY_HEADERS["Referer"]),
        "--write-out",
        f"\n{marker}%{{http_code}}",
        prepared_url,
    ]
    for key, value in headers.items():
        if key in {"User-Agent", "Referer"}:
            continue
        command[-1:-1] = ["-H", f"{key}: {value}"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=effective_timeout + 1
        )
    except subprocess.TimeoutExpired as exc:
        raise requests.Timeout("Eastmoney curl request timed out") from exc
    except OSError as exc:
        raise requests.ConnectionError("could not execute curl") from exc
    if result.returncode == 28:
        raise requests.Timeout(result.stderr.strip() or "curl request timed out")
    if result.returncode != 0:
        raise requests.ConnectionError(result.stderr.strip() or "curl request failed")
    body, separator, status_text = result.stdout.rpartition(marker)
    if not separator:
        raise requests.ConnectionError("curl response missing HTTP status")
    response = requests.Response()
    response.status_code = int(status_text.strip() or 0)
    response._content = body.rstrip("\n").encode("utf-8")
    response.url = prepared_url
    response.encoding = "utf-8"
    response.raise_for_status()
    return response


def _request_with_curl_interface_bytes(
    url: str,
    params: Dict | None,
    headers: Dict,
    timeout: int | float | None,
    interface: str,
) -> requests.Response:
    curl_bin = os.environ.get("AKSHARE_CURL_BIN") or shutil.which("curl")
    if not curl_bin:
        raise requests.ConnectionError("curl executable not found")
    prepared_url = _prepared_get_url(url, params)
    max_time = str(timeout if timeout is not None else 15)
    marker = b"\nAKSHARE_HTTP_STATUS:"
    command = [
        curl_bin,
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        max_time,
        "--interface",
        interface,
        "-A",
        headers.get("User-Agent", _DEFAULT_BROWSER_UA),
        "--write-out",
        marker.decode() + "%{http_code}",
        prepared_url,
    ]
    for key, value in headers.items():
        if key == "User-Agent":
            continue
        command[-1:-1] = ["-H", f"{key}: {value}"]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise requests.ConnectionError(stderr or "curl request failed")
    body, separator, status_text = result.stdout.rpartition(marker)
    if not separator:
        raise requests.ConnectionError("curl response missing HTTP status")
    response = requests.Response()
    response.status_code = int(status_text.strip() or b"0")
    response._content = body
    response.url = prepared_url
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    response.raise_for_status()
    return response


def _request_with_curl_resolve_bytes(
    url: str,
    params: Dict | None,
    headers: Dict,
    timeout: int | float | None,
    resolve_ip: str,
) -> requests.Response:
    curl_bin = os.environ.get("AKSHARE_CURL_BIN") or shutil.which("curl")
    if not curl_bin:
        raise requests.ConnectionError("curl executable not found")
    prepared_url = _prepared_get_url(url, params)
    parts = urlsplit(prepared_url)
    host = parts.hostname
    if not host:
        raise requests.ConnectionError("request URL missing host")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    max_time = str(timeout if timeout is not None else 15)
    marker = b"\nAKSHARE_HTTP_STATUS:"
    command = [
        curl_bin,
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        max_time,
        "--resolve",
        f"{host}:{port}:{resolve_ip}",
        "-A",
        headers.get("User-Agent", _DEFAULT_BROWSER_UA),
        "--write-out",
        marker.decode() + "%{http_code}",
        prepared_url,
    ]
    for key, value in headers.items():
        if key == "User-Agent":
            continue
        command[-1:-1] = ["-H", f"{key}: {value}"]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise requests.ConnectionError(stderr or "curl request failed")
    body, separator, status_text = result.stdout.rpartition(marker)
    if not separator:
        raise requests.ConnectionError("curl response missing HTTP status")
    response = requests.Response()
    response.status_code = int(status_text.strip() or b"0")
    response._content = body
    response.url = prepared_url
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    response.raise_for_status()
    return response


def _request_szse_with_curl_fallbacks(
    url: str,
    params: Dict | None,
    headers: Dict,
    timeout: int | float | None,
    interface: str,
    max_retries: int,
) -> requests.Response:
    last_exception = None
    if interface:
        for attempt in range(max_retries):
            try:
                return _request_with_curl_interface_bytes(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    interface=interface,
                )
            except requests.RequestException as exc:
                last_exception = exc
                if attempt < max_retries - 1:
                    time.sleep(0.2 * (attempt + 1))
    host = _request_hostname(url)
    for resolve_ip in _szse_resolve_ips(host):
        for attempt in range(max_retries):
            try:
                return _request_with_curl_resolve_bytes(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    resolve_ip=resolve_ip,
                )
            except requests.RequestException as exc:
                last_exception = exc
                if attempt < max_retries - 1:
                    time.sleep(0.2 * (attempt + 1))
    if last_exception is not None:
        raise last_exception
    raise requests.ConnectionError("no SZSE curl fallback is available")


def eastmoney_fallback_urls(url: str) -> list[str]:
    """Return Eastmoney request URL candidates with push2delay fallback."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    urls = [url]
    if host == _EASTMONEY_DELAY_HOST:
        return urls
    if any(host == item or host.endswith(f".{item}") for item in _EASTMONEY_PUSH_HOSTS):
        fallback = urlunsplit(
            (
                parts.scheme,
                _EASTMONEY_DELAY_HOST,
                parts.path,
                parts.query,
                parts.fragment,
            )
        )
        if fallback not in urls:
            urls.append(fallback)
    return urls


def request_eastmoney(
    url: str,
    params: Dict = None,
    headers: Dict = None,
    timeout: int | float | None = 15,
    max_retries: int = 2,
    _allow_cookie_refresh: bool = True,
    **kwargs,
) -> requests.Response:
    """Request Eastmoney push APIs with an optional verified website session."""
    request_headers = requests.structures.CaseInsensitiveDict(_EASTMONEY_HEADERS)
    if headers:
        request_headers.update(headers)
    parts = urlsplit(_prepared_get_url(url, None))
    primary_host_key = _eastmoney_failed_host_key(parts.hostname or "")
    managed_cookie = ""
    if (
        parts.scheme == "https"
        and primary_host_key in (*_EASTMONEY_PUSH_HOSTS, _EASTMONEY_DELAY_HOST)
        and "Cookie" not in request_headers
        and "cookies" not in kwargs
    ):
        managed_cookie = _get_eastmoney_cookie()
        if managed_cookie:
            request_headers["Cookie"] = managed_cookie
    has_cookie = "Cookie" in request_headers or "cookies" in kwargs
    last_exception = None
    urls = eastmoney_fallback_urls(url)
    cache_key = (primary_host_key, parts.path)
    if (
        not has_cookie
        and _EASTMONEY_FAILED_HOSTS.get(cache_key, 0) > time.monotonic()
        and len(urls) > 1
    ):
        urls = urls[1:] + urls[:1]
    else:
        _EASTMONEY_FAILED_HOSTS.pop(cache_key, None)
    primary_failed = False
    for candidate_url in urls:
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    candidate_url,
                    params=params,
                    headers=request_headers,
                    timeout=timeout,
                    **kwargs,
                )
                response.raise_for_status()
                if candidate_url == url:
                    _EASTMONEY_FAILED_HOSTS.pop(cache_key, None)
                elif primary_failed:
                    # Only prefer a proven fallback, without indefinitely extending its TTL.
                    _EASTMONEY_FAILED_HOSTS[cache_key] = (
                        time.monotonic() + _EASTMONEY_FAILURE_COOLDOWN
                    )
                return response
            except requests.RequestException as exc:
                last_exception = exc
                if candidate_url == url and len(urls) > 1:
                    primary_failed = True
                    interface = _eastmoney_curl_interface()
                    if (
                        interface
                        and _is_push2his_url(candidate_url)
                        and not kwargs
                        and not has_cookie
                        and "Authorization" not in request_headers
                    ):
                        try:
                            response = _request_eastmoney_with_curl_interface(
                                candidate_url,
                                params=params,
                                headers=request_headers,
                                timeout=timeout,
                                interface=interface,
                            )
                            _EASTMONEY_FAILED_HOSTS.pop(cache_key, None)
                            return response
                        except requests.RequestException as curl_exc:
                            last_exception = curl_exc
                if attempt < max_retries - 1:
                    time.sleep(0.2 * (attempt + 1))
    _EASTMONEY_FAILED_HOSTS.pop(cache_key, None)
    if last_exception is not None:
        if (
            _allow_cookie_refresh
            and managed_cookie
            and _is_eastmoney_cookie_failure(last_exception)
        ):
            refreshed_cookie = _refresh_eastmoney_cookie(managed_cookie)
            if refreshed_cookie and refreshed_cookie != managed_cookie:
                refreshed_headers = dict(headers or {})
                refreshed_headers["Cookie"] = refreshed_cookie
                return request_eastmoney(
                    url,
                    params=params,
                    headers=refreshed_headers,
                    timeout=timeout,
                    max_retries=max_retries,
                    _allow_cookie_refresh=False,
                    **kwargs,
                )
        raise last_exception
    return requests.get(
        url,
        params=params,
        headers=request_headers,
        timeout=timeout,
        **kwargs,
    )


def request_szse(
    url: str,
    params: Dict = None,
    headers: Dict = None,
    timeout: int | float | None = 15,
    max_retries: int = 2,
    **kwargs,
) -> requests.Response:
    """Request SZSE endpoints, retrying through a local interface when needed."""
    request_headers = {"User-Agent": _DEFAULT_BROWSER_UA}
    if headers:
        request_headers.update(headers)
    interface = _szse_curl_interface()
    host = _request_hostname(url)
    has_resolve_fallback = bool(_szse_resolve_ips(host))
    if host in _SZSE_FAILED_HOSTS and (interface or has_resolve_fallback):
        return _request_szse_with_curl_fallbacks(
            url,
            params=params,
            headers=request_headers,
            timeout=timeout,
            interface=interface,
            max_retries=max_retries,
        )
    try:
        response = requests.get(
            url,
            params=params,
            headers=request_headers,
            timeout=timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        _SZSE_FAILED_HOSTS.add(host)
        if not interface and not has_resolve_fallback:
            raise
        try:
            return _request_szse_with_curl_fallbacks(
                url,
                params=params,
                headers=request_headers,
                timeout=timeout,
                interface=interface,
                max_retries=max_retries,
            )
        except requests.RequestException as fallback_exc:
            raise fallback_exc from exc


def request_with_retry(
    url: str,
    params: Dict = None,
    timeout: int = 15,
    max_retries: int = 3,
    base_delay: float = 1.0,
    random_delay_range: Tuple[float, float] = (0.5, 1.5),
) -> requests.Response:
    """
    带重试机制的 HTTP GET 请求
    :param url: 请求 URL
    :type url: str
    :param params: 请求参数
    :type params: dict
    :param timeout: 超时时间（秒）
    :type timeout: int
    :param max_retries: 最大重试次数
    :type max_retries: int
    :param base_delay: 基础延迟时间（秒），用于指数退避
    :type base_delay: float
    :param random_delay_range: 随机延迟范围（秒）
    :type random_delay_range: tuple
    :return: Response 对象
    :rtype: requests.Response
    :raises: 最后一次请求的异常
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            # 每次请求创建新的 Session，避免复用连接
            with requests.Session() as session:
                # 禁用连接池复用
                adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
                session.mount("http://", adapter)
                session.mount("https://", adapter)

                response = session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response

        except (requests.RequestException, ValueError) as e:
            last_exception = e

            if attempt < max_retries - 1:
                # 指数退避 + 随机抖动
                delay = base_delay * (2**attempt) + random.uniform(*random_delay_range)
                time.sleep(delay)

    raise last_exception
