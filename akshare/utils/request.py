# !/usr/bin/env python
"""
Date: 2025/12/31
Desc: HTTP 请求工具函数
"""

import random
import os
import platform
import shutil
import subprocess
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
    _EASTMONEY_FAILED_HOSTS.clear()


def _get_eastmoney_cookie() -> str:
    cookie = os.environ.get("AKSHARE_EASTMONEY_COOKIE")
    if cookie is None:
        configured_path = os.environ.get("AKSHARE_EASTMONEY_COOKIE_FILE")
        cookie_path = (
            Path(configured_path).expanduser()
            if configured_path
            else Path.home() / ".cache" / "akshare" / "eastmoney_cookie.txt"
        )
        if not configured_path and not cookie_path.exists():
            return ""
        cookie = cookie_path.read_text(encoding="utf-8")
    cookie = cookie.strip()
    if "\r" in cookie or "\n" in cookie:
        raise ValueError("Eastmoney Cookie must be a single-line HTTP header value")
    return cookie


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
    **kwargs,
) -> requests.Response:
    """Request Eastmoney push APIs with an optional verified website session."""
    request_headers = requests.structures.CaseInsensitiveDict(_EASTMONEY_HEADERS)
    if headers:
        request_headers.update(headers)
    parts = urlsplit(_prepared_get_url(url, None))
    primary_host_key = _eastmoney_failed_host_key(parts.hostname or "")
    if (
        parts.scheme == "https"
        and primary_host_key in (*_EASTMONEY_PUSH_HOSTS, _EASTMONEY_DELAY_HOST)
        and "Cookie" not in request_headers
        and "cookies" not in kwargs
    ):
        cookie = _get_eastmoney_cookie()
        if cookie:
            request_headers["Cookie"] = cookie
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
