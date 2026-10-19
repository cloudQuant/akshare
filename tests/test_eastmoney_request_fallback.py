import subprocess
from types import SimpleNamespace

import pytest
import requests


@pytest.fixture(autouse=True)
def reset_eastmoney_cache(monkeypatch):
    import akshare.utils.request as request_utils

    request_utils._reset_eastmoney_fallback_cache()
    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "off")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "")
    monkeypatch.setenv("AKSHARE_EASTMONEY_INTERACTIVE_AUTH", "0")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE_FILE", raising=False)
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", raising=False)
    yield
    request_utils._reset_eastmoney_fallback_cache()


@pytest.fixture
def eastmoney_requests(monkeypatch):
    import akshare.utils.request as request_utils

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    return calls


@pytest.mark.parametrize(
    "host",
    ["push2his.eastmoney.com", "7.push2his.eastmoney.com", "push2delay.eastmoney.com"],
)
def test_eastmoney_cookie_from_environment(monkeypatch, eastmoney_requests, host):
    from akshare.utils.request import request_eastmoney

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", " verified=session ")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", "/unused-cookie-file")

    request_eastmoney(f"https://{host}/api/qt/stock/kline/get", max_retries=1)

    assert eastmoney_requests[0][1]["headers"]["Cookie"] == "verified=session"


@pytest.mark.parametrize("explicit_path", [False, True])
def test_eastmoney_cookie_file_is_loaded_and_refreshed(
    monkeypatch, tmp_path, eastmoney_requests, explicit_path
):
    from akshare.utils.request import request_eastmoney

    cookie_file = tmp_path / ".cache" / "akshare" / "eastmoney_cookie.txt"
    cookie_file.parent.mkdir(parents=True)
    cookie_file.write_text("verified=first\n", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    if explicit_path:
        monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    request_eastmoney(url, max_retries=1)
    cookie_file.write_text("verified=refreshed", encoding="utf-8")
    request_eastmoney(url, max_retries=1)

    assert [call[1]["headers"]["Cookie"] for call in eastmoney_requests] == [
        "verified=first",
        "verified=refreshed",
    ]


def test_eastmoney_empty_cookie_environment_disables_cache(
    monkeypatch, tmp_path, eastmoney_requests
):
    from akshare.utils.request import request_eastmoney

    cookie_file = tmp_path / "cookie.txt"
    cookie_file.write_text("verified=session", encoding="utf-8")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))

    request_eastmoney(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert "Cookie" not in eastmoney_requests[0][1]["headers"]


def test_eastmoney_missing_default_cookie_file_allows_anonymous_requests(
    monkeypatch, tmp_path, eastmoney_requests
):
    from akshare.utils.request import request_eastmoney

    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))

    request_eastmoney(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert "Cookie" not in eastmoney_requests[0][1]["headers"]


@pytest.mark.parametrize("header_name", ["Cookie", "cookie"])
def test_eastmoney_caller_cookie_header_takes_precedence(
    monkeypatch, eastmoney_requests, header_name
):
    from akshare.utils.request import request_eastmoney

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "cached=session")
    request_eastmoney(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        headers={header_name: "caller=session"},
        max_retries=1,
    )

    assert eastmoney_requests[0][1]["headers"]["Cookie"] == "caller=session"


def test_eastmoney_caller_cookie_jar_takes_precedence(monkeypatch, eastmoney_requests):
    from akshare.utils.request import request_eastmoney

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "cached=session")
    request_eastmoney(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        cookies={"caller": "session"},
        max_retries=1,
    )

    assert "Cookie" not in eastmoney_requests[0][1]["headers"]
    assert eastmoney_requests[0][1]["cookies"] == {"caller": "session"}


@pytest.mark.parametrize(
    "url",
    [
        "http://push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://example.test/api/qt/stock/kline/get",
        "https://push2his.eastmoney.com.example.test/api/qt/stock/kline/get",
        "https://example.test\\@push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://example.test\\@7.push2his.eastmoney.com/api/qt/stock/kline/get",
    ],
)
def test_eastmoney_cookie_is_not_sent_to_untrusted_urls(
    monkeypatch, eastmoney_requests, url
):
    from akshare.utils.request import request_eastmoney

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "verified=session")
    request_eastmoney(url, max_retries=1)

    assert "Cookie" not in eastmoney_requests[0][1]["headers"]


@pytest.mark.parametrize(
    "cookie", ["must-not-leak\nX-Test: value", "must-not-leak\rX-Test: value"]
)
def test_eastmoney_rejects_multiline_cookies_without_exposing_values(
    monkeypatch, cookie
):
    from akshare.utils.request import request_eastmoney

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", cookie)
    with pytest.raises(ValueError, match="single-line") as exc:
        request_eastmoney("https://push2his.eastmoney.com/api/qt/stock/kline/get")
    assert "must-not-leak" not in str(exc.value)


@pytest.mark.parametrize(
    "headers", [{"cookie": "verified=session"}, {"authorization": "private-token"}]
)
def test_eastmoney_credentials_are_not_exposed_to_curl(monkeypatch, headers):
    import akshare.utils.request as request_utils

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    calls = []

    def fake_get(candidate, **kwargs):
        calls.append(candidate)
        if candidate == url:
            raise requests.ConnectionError("temporary disconnect")
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def unexpected_curl(*args, **kwargs):
        pytest.fail("credentials must not be passed through subprocess arguments")

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "en0")
    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", unexpected_curl)

    request_utils.request_eastmoney(url, headers=headers, max_retries=1)
    assert calls == [url, "https://push2delay.eastmoney.com/api/qt/stock/kline/get"]


def test_eastmoney_verified_session_rechecks_failed_primary(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    calls = []

    def fake_get(candidate, **kwargs):
        calls.append(candidate)
        if len(calls) == 1:
            raise requests.ConnectionError("anonymous request failed")
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    request_utils.request_eastmoney(url, max_retries=1)
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE", "verified=session")
    request_utils.request_eastmoney(url, max_retries=1)

    assert calls == [
        url,
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get",
        url,
    ]


def test_eastmoney_fallback_urls_replace_push2_hosts():
    from akshare.utils.request import eastmoney_fallback_urls

    assert eastmoney_fallback_urls(
        "https://82.push2.eastmoney.com/api/qt/clist/get"
    ) == [
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
    ]
    assert eastmoney_fallback_urls(
        "https://7.push2his.eastmoney.com/api/qt/stock/kline/get"
    ) == [
        "https://7.push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get",
    ]


def test_request_eastmoney_uses_push2delay_after_primary_connection_error(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_eastmoney

    called_urls = []

    def fake_get(url, **kwargs):
        called_urls.append(url)
        if "push2delay.eastmoney.com" in url:
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
                raise_for_status=lambda: None,
            )
        raise requests.ConnectionError("empty response")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    response = request_eastmoney(
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        params={"pn": "1"},
        timeout=1,
        max_retries=1,
    )

    assert response.status_code == 200
    assert called_urls == [
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
    ]


def test_request_eastmoney_skips_failed_primary_host_on_later_calls(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_eastmoney

    request_utils._reset_eastmoney_fallback_cache()
    called_urls = []

    def fake_get(url, **kwargs):
        called_urls.append(url)
        if "push2delay.eastmoney.com" in url:
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
                raise_for_status=lambda: None,
            )
        raise requests.ConnectionError("empty response")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    request_eastmoney(
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        params={"pn": "1"},
        timeout=1,
        max_retries=1,
    )
    request_eastmoney(
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        params={"pn": "2"},
        timeout=1,
        max_retries=1,
    )

    assert called_urls == [
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
    ]


def test_request_eastmoney_skips_failed_push2_subdomains(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_eastmoney

    request_utils._reset_eastmoney_fallback_cache()
    called_urls = []

    def fake_get(url, **kwargs):
        called_urls.append(url)
        if "push2delay.eastmoney.com" in url:
            return SimpleNamespace(
                status_code=200,
                text='{"data":{"total":1,"diff":[{"f12":"000001"}]}}',
                raise_for_status=lambda: None,
            )
        raise requests.ConnectionError("empty response")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    request_eastmoney(
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        params={"pn": "1"},
        timeout=1,
        max_retries=1,
    )
    request_eastmoney(
        "https://69.push2.eastmoney.com/api/qt/clist/get",
        params={"pn": "1"},
        timeout=1,
        max_retries=1,
    )

    assert called_urls == [
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
    ]


def test_request_eastmoney_tries_curl_interface_before_push2his_delay(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_eastmoney

    request_utils._reset_eastmoney_fallback_cache()
    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "en0")
    called_urls = []
    called_curl = []

    def fake_get(url, **kwargs):
        called_urls.append(url)
        raise requests.ConnectionError("empty response")

    def fake_run(command, **kwargs):
        called_curl.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout='{"data":{"klines":["2024-06-03,1,2"]}}\nAKSHARE_HTTP_STATUS:200',
            stderr="",
        )

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_eastmoney(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": "0.000001"},
        timeout=1,
        max_retries=1,
    )

    assert response.status_code == 200
    assert response.json()["data"]["klines"] == ["2024-06-03,1,2"]
    assert called_urls == ["https://push2his.eastmoney.com/api/qt/stock/kline/get"]
    assert "--interface" in called_curl[0]
    assert "en0" in called_curl[0]
    assert not any("push2delay.eastmoney.com" in item for item in called_urls)


def _cookie_failure():
    return requests.ConnectionError(
        "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
    )


def _write_cookie(tmp_path, cookie):
    cookie_file = tmp_path / "eastmoney_cookie.txt"
    cookie_file.write_text(cookie, encoding="utf-8")
    return cookie_file


def test_eastmoney_refresh_command_updates_cookie_and_retries(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []
    commands = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        if len(called) == 1:
            raise _cookie_failure()
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_run(command, **kwargs):
        commands.append((command, kwargs["timeout"]))
        return SimpleNamespace(returncode=0, stdout="Cookie: refreshed=2\n", stderr="")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_utils.request_eastmoney(
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert response.status_code == 200
    assert called == ["old=1", "refreshed=2"]
    assert commands == [(["refresh-cookie"], 120.0)]
    assert cookie_file.read_text(encoding="utf-8") == "refreshed=2"
    assert cookie_file.stat().st_mode & 0o777 == 0o600


def test_eastmoney_refresh_survives_unwritable_cache(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        if len(called) == 1:
            raise _cookie_failure()
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="new=2", stderr=""
        ),
    )
    monkeypatch.setattr(
        request_utils,
        "_save_eastmoney_cookie",
        lambda _: (_ for _ in ()).throw(OSError("read-only cache")),
    )

    response = request_utils.request_eastmoney(
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert response.status_code == 200
    assert called == ["old=1", "new=2"]


def test_eastmoney_refresh_rereads_externally_updated_cookie_file(
    monkeypatch, tmp_path
):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    called = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        if len(called) == 1:
            cookie_file.write_text("external=2", encoding="utf-8")
            raise _cookie_failure()
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils,
        "_refresh_eastmoney_cookie_with_browser",
        lambda _: pytest.fail("unexpected browser"),
    )

    request_utils.request_eastmoney(
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert called == ["old=1", "external=2"]


@pytest.mark.parametrize(
    "refresh_result",
    [
        SimpleNamespace(returncode=1, stdout="", stderr="failed"),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="first=1\nsecond=2", stderr=""),
        SimpleNamespace(returncode=0, stdout="not-a-cookie", stderr=""),
        SimpleNamespace(returncode=0, stdout="old=1", stderr=""),
    ],
)
def test_eastmoney_refresh_without_new_cookie_does_not_retry(
    monkeypatch, tmp_path, refresh_result
):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        raise _cookie_failure()

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: refresh_result,
    )

    with pytest.raises(requests.ConnectionError):
        request_utils.request_eastmoney(
            "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
        )

    assert called == ["old=1"]


def test_eastmoney_refresh_timeout_keeps_original_failure(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_TIMEOUT", "2")
    called = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        raise _cookie_failure()

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == 2.0
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    with pytest.raises(requests.ConnectionError):
        request_utils.request_eastmoney(
            "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
        )

    assert called == ["old=1"]


def test_eastmoney_refresh_retries_only_once(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []
    commands = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        raise _cookie_failure()

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="new=2", stderr="")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    with pytest.raises(requests.ConnectionError):
        request_utils.request_eastmoney(
            "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
        )

    assert called == ["old=1", "new=2"]
    assert commands == [["refresh-cookie"]]


def test_eastmoney_refresh_obeys_cooldown(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []
    commands = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        raise _cookie_failure()

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="new=2", stderr="")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)
    url = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"

    with pytest.raises(requests.ConnectionError):
        request_utils.request_eastmoney(url, max_retries=1)
    with pytest.raises(requests.ConnectionError):
        request_utils.request_eastmoney(url, max_retries=1)

    assert called == ["old=1", "new=2", "new=2"]
    assert commands == [["refresh-cookie"]]


def test_eastmoney_refresh_skips_caller_managed_credentials(
    monkeypatch, eastmoney_requests
):
    import akshare.utils.request as request_utils

    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("unexpected refresh"),
    )

    def fake_get(url, **kwargs):
        raise _cookie_failure()

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    for kwargs in (
        {"headers": {"Cookie": "caller=1"}},
        {"cookies": {"caller": "1"}},
        {"headers": {"Authorization": "private"}},
    ):
        with pytest.raises(requests.ConnectionError):
            request_utils.request_eastmoney(
                "https://push2delay.eastmoney.com/api/qt/stock/kline/get",
                max_retries=1,
                **kwargs,
            )


def test_eastmoney_refresh_skips_non_session_failures(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("unexpected refresh"),
    )

    def fake_get(url, **kwargs):
        raise requests.ConnectionError("Name or service not known")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    with pytest.raises(requests.ConnectionError, match="Name or service"):
        request_utils.request_eastmoney(
            "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
        )


def test_eastmoney_refresh_on_http_forbidden(monkeypatch, tmp_path):
    import akshare.utils.request as request_utils

    cookie_file = _write_cookie(tmp_path, "old=1")
    monkeypatch.delenv("AKSHARE_EASTMONEY_COOKIE")
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("AKSHARE_EASTMONEY_COOKIE_REFRESH_COMMAND", "refresh-cookie")
    called = []

    def fake_get(url, **kwargs):
        called.append(kwargs["headers"]["Cookie"])
        if len(called) == 1:
            response = requests.Response()
            response.status_code = 403
            raise requests.HTTPError("forbidden", response=response)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="new=2", stderr=""
        ),
    )

    request_utils.request_eastmoney(
        "https://push2delay.eastmoney.com/api/qt/stock/kline/get", max_retries=1
    )

    assert called == ["old=1", "new=2"]


@pytest.mark.parametrize(
    "error, expected",
    [
        (requests.Timeout("timed out"), True),
        (requests.ConnectionError("RemoteDisconnected()"), True),
        (requests.ConnectionError("Connection reset by peer"), True),
        (requests.ConnectionError("Name or service not known"), False),
        (requests.ConnectionError("certificate verify failed"), False),
    ],
)
def test_eastmoney_cookie_failure_detection(error, expected):
    from akshare.utils.request import _is_eastmoney_cookie_failure

    assert _is_eastmoney_cookie_failure(error) is expected


def test_eastmoney_interactive_auth_requires_opt_in(monkeypatch):
    import akshare.utils.request as request_utils

    monkeypatch.setenv("AKSHARE_EASTMONEY_INTERACTIVE_AUTH", "0")
    assert request_utils._interactive_eastmoney_auth_enabled() is False
    monkeypatch.setenv("AKSHARE_EASTMONEY_INTERACTIVE_AUTH", "1")
    assert request_utils._interactive_eastmoney_auth_enabled() is True


def test_eastmoney_browser_refresh_disabled_without_opt_in(monkeypatch):
    import akshare.utils.request as request_utils

    monkeypatch.setenv("AKSHARE_EASTMONEY_INTERACTIVE_AUTH", "0")
    assert request_utils._refresh_eastmoney_cookie_with_browser(1) == ""


@pytest.mark.parametrize("verified", [True, False])
def test_eastmoney_browser_refresh_collects_only_verified_site_cookies(
    monkeypatch, verified
):
    import sys
    import types
    from akshare.utils import request as request_utils

    class FakeDriver:
        def __init__(self):
            self.quit_called = False

        def set_page_load_timeout(self, value):
            assert value == 30

        def get(self, url):
            assert url == "https://quote.eastmoney.com/"

        def set_script_timeout(self, value):
            assert value == 8

        def execute_async_script(self, script):
            assert "credentials: 'include'" in script
            return verified

        def get_cookies(self):
            return [
                {"name": "session", "value": "new", "domain": ".eastmoney.com"},
                {"name": "quote", "value": "value", "domain": "quote.eastmoney.com"},
                {"name": "foreign", "value": "nope", "domain": ".example.test"},
            ]

        def quit(self):
            self.quit_called = True

    driver = FakeDriver()
    webdriver_module = types.ModuleType("selenium.webdriver")
    webdriver_module.Chrome = lambda: driver
    exceptions_module = types.ModuleType("selenium.common.exceptions")
    exceptions_module.WebDriverException = RuntimeError
    selenium_module = types.ModuleType("selenium")
    selenium_module.webdriver = webdriver_module
    monkeypatch.setitem(sys.modules, "selenium", selenium_module)
    monkeypatch.setitem(sys.modules, "selenium.webdriver", webdriver_module)
    monkeypatch.setitem(
        sys.modules, "selenium.common", types.ModuleType("selenium.common")
    )
    monkeypatch.setitem(sys.modules, "selenium.common.exceptions", exceptions_module)
    monkeypatch.setenv("AKSHARE_EASTMONEY_INTERACTIVE_AUTH", "1")
    monkeypatch.setattr(request_utils.time, "sleep", lambda _: None)

    cookie = request_utils._refresh_eastmoney_cookie_with_browser(1)

    assert driver.quit_called
    if verified:
        assert cookie == "session=new; quote=value"
        assert "foreign" not in cookie
    else:
        assert cookie == ""


def test_eastmoney_curl_success_remains_available_on_later_calls(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    called_urls = []
    called_curl = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        raise requests.ConnectionError("primary connection failed")

    def fake_curl(candidate, **kwargs):
        called_curl.append(candidate)
        return response

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "en0")
    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils, "_request_eastmoney_with_curl_interface", fake_curl
    )

    for _ in range(2):
        assert request_utils.request_eastmoney(url, max_retries=1) is response

    assert called_urls == [url, url]
    assert called_curl == [url, url]


def test_eastmoney_primary_retry_success_is_not_cached_as_failure(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if len(called_urls) == 1:
            raise requests.ConnectionError("temporary disconnect")
        return response

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.time, "sleep", lambda _: None)

    assert request_utils.request_eastmoney(url, max_retries=2) is response
    assert request_utils.request_eastmoney(url, max_retries=1) is response
    assert called_urls == [url, url, url]


def test_eastmoney_cached_fallback_failure_retries_primary(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/clist/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if len(called_urls) in (1, 3):
            raise requests.ConnectionError("temporary disconnect")
        return response

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    for _ in range(2):
        assert request_utils.request_eastmoney(url, max_retries=1) is response

    assert called_urls == [url, fallback, fallback, url]


def test_eastmoney_failed_primary_is_rechecked_after_cooldown(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/clist/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)
    clock = [0.0]

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if len(called_urls) == 1:
            raise requests.ConnectionError("temporary disconnect")
        return response

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.time, "monotonic", lambda: clock[0])

    assert request_utils.request_eastmoney(url, max_retries=1) is response
    clock[0] = 30.0
    assert request_utils.request_eastmoney(url, max_retries=1) is response
    clock[0] = 61.0
    assert request_utils.request_eastmoney(url, max_retries=1) is response
    assert called_urls == [url, fallback, fallback, url]


def test_eastmoney_failure_cache_does_not_affect_other_endpoints(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/clist/get"
    other_url = "https://push2.eastmoney.com/api/qt/stock/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if len(called_urls) == 1:
            raise requests.ConnectionError("temporary disconnect")
        return response

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    assert request_utils.request_eastmoney(url, max_retries=1) is response
    assert request_utils.request_eastmoney(other_url, max_retries=1) is response
    assert called_urls == [url, fallback, other_url]


def test_eastmoney_total_failure_does_not_poison_primary(monkeypatch):
    import akshare.utils.request as request_utils

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/clist/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if len(called_urls) <= 2:
            raise requests.ConnectionError("network unavailable")
        return response

    monkeypatch.setattr(request_utils.requests, "get", fake_get)

    with pytest.raises(requests.ConnectionError, match="network unavailable"):
        request_utils.request_eastmoney(url, max_retries=1)
    assert request_utils.request_eastmoney(url, max_retries=1) is response
    assert called_urls == [url, fallback, url]


@pytest.mark.parametrize(
    "failure", [subprocess.TimeoutExpired("curl", 1), OSError("curl unavailable")]
)
def test_eastmoney_curl_process_failure_continues_to_fallback(monkeypatch, failure):
    import akshare.utils.request as request_utils

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        if candidate == url:
            raise requests.ConnectionError("primary connection failed")
        return response

    def fake_run(*args, **kwargs):
        raise failure

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "en0")
    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_BIN", "curl")
    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    assert request_utils.request_eastmoney(url, timeout=1, max_retries=1) is response
    assert called_urls == [url, fallback]


@pytest.mark.parametrize("timeout, effective_timeout", [(None, 15), (0.5, 0.5)])
def test_eastmoney_curl_process_has_bounded_timeout(
    monkeypatch, timeout, effective_timeout
):
    import akshare.utils.request as request_utils

    def fake_run(command, **kwargs):
        assert command[command.index("--max-time") + 1] == str(effective_timeout)
        assert kwargs["timeout"] == effective_timeout + 1
        return SimpleNamespace(
            returncode=0,
            stdout='{"data":{"klines":[]}}\nAKSHARE_HTTP_STATUS:200',
            stderr="",
        )

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_BIN", "curl")
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_utils._request_eastmoney_with_curl_interface(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": "0.000001"},
        headers={},
        timeout=timeout,
        interface="en0",
    )
    assert response.json() == {"data": {"klines": []}}


@pytest.mark.parametrize(
    "options", [{"stream": True}, {"proxies": {}}, {"verify": True}, {"cookies": {}}]
)
def test_eastmoney_curl_does_not_discard_request_options(monkeypatch, options):
    import akshare.utils.request as request_utils

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    fallback = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
    called_urls = []
    response = SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    def fake_get(candidate, **kwargs):
        called_urls.append(candidate)
        for key, value in options.items():
            assert kwargs[key] == value
        if candidate == url:
            raise requests.ConnectionError("primary connection failed")
        return response

    def unexpected_curl(*args, **kwargs):
        pytest.fail("curl does not support these request options")

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_INTERFACE", "en0")
    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(
        request_utils, "_request_eastmoney_with_curl_interface", unexpected_curl
    )

    assert request_utils.request_eastmoney(url, max_retries=1, **options) is response
    assert called_urls == [url, fallback]


def test_eastmoney_curl_exit_timeout_raises_requests_timeout(monkeypatch):
    import akshare.utils.request as request_utils

    monkeypatch.setenv("AKSHARE_EASTMONEY_CURL_BIN", "curl")
    monkeypatch.setattr(
        request_utils.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=28, stderr="operation timed out"
        ),
    )

    with pytest.raises(requests.Timeout, match="operation timed out"):
        request_utils._request_eastmoney_with_curl_interface(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params=None,
            headers={},
            timeout=1,
            interface="en0",
        )


def test_request_szse_uses_curl_interface_and_preserves_binary(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_szse

    called_curl = []
    monkeypatch.setenv("AKSHARE_SZSE_CURL_INTERFACE", "en0")

    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("default route failed")

    def fake_run(command, **kwargs):
        called_curl.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=b"PK\x03\x04xlsx-bytes\nAKSHARE_HTTP_STATUS:200",
            stderr=b"",
        )

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_szse(
        "https://www.szse.cn/api/report/ShowReport",
        params={"SHOWTYPE": "xlsx"},
        timeout=1,
    )

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04xlsx-bytes"
    assert "--interface" in called_curl[0]
    assert "en0" in called_curl[0]


def test_request_szse_uses_resolved_cdn_ip_after_interface_fails(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_szse

    request_utils._SZSE_FAILED_HOSTS.clear()
    called_curl = []
    monkeypatch.setenv("AKSHARE_SZSE_CURL_INTERFACE", "en0")
    monkeypatch.setenv("AKSHARE_SZSE_RESOLVE_IPS", "113.108.107.138")

    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("default route failed")

    def fake_run(command, **kwargs):
        called_curl.append(command)
        if "--resolve" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=b"PK\x03\x04xlsx-bytes\nAKSHARE_HTTP_STATUS:200",
                stderr=b"",
            )
        return SimpleNamespace(returncode=7, stdout=b"", stderr=b"interface failed")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_szse(
        "https://www.szse.cn/api/report/ShowReport",
        params={"SHOWTYPE": "xlsx"},
        timeout=1,
        max_retries=1,
    )

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04xlsx-bytes"
    assert any("--interface" in item for item in called_curl[0])
    assert "--resolve" in called_curl[1]
    assert "www.szse.cn:443:113.108.107.138" in called_curl[1]


def test_request_szse_uses_host_specific_resolved_cdn_ip(monkeypatch):
    import akshare.utils.request as request_utils
    from akshare.utils.request import request_szse

    request_utils._SZSE_FAILED_HOSTS.clear()
    called_curl = []
    monkeypatch.setenv("AKSHARE_SZSE_CURL_INTERFACE", "en0")
    monkeypatch.delenv("AKSHARE_SZSE_RESOLVE_IPS", raising=False)

    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("default route failed")

    def fake_run(command, **kwargs):
        called_curl.append(command)
        if "--resolve" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=b'{"data":[{"code":"10000001"}]}\nAKSHARE_HTTP_STATUS:200',
                stderr=b"",
            )
        return SimpleNamespace(returncode=7, stdout=b"", stderr=b"interface failed")

    monkeypatch.setattr(request_utils.requests, "get", fake_get)
    monkeypatch.setattr(request_utils.subprocess, "run", fake_run)

    response = request_szse(
        "https://investor.szse.cn/api/report/ShowReport/data",
        params={"SHOWTYPE": "JSON"},
        timeout=1,
        max_retries=1,
    )

    assert response.status_code == 200
    assert response.json()["data"] == [{"code": "10000001"}]
    assert "--resolve" in called_curl[1]
    assert "investor.szse.cn:443:58.251.50.138" in called_curl[1]


def test_stock_zh_a_spot_batches_same_source_quotes_and_preserves_schema(monkeypatch):
    import pandas as pd
    from akshare.stock_feature import stock_hist_em

    codes = [f"{i:06}" for i in range(1, 501)] + [
        "600519",
        "300750",
        "920001",
        "000001",
    ]
    batches = []
    monkeypatch.setattr(
        stock_hist_em, "stock_info_a_code_name", lambda: pd.DataFrame({"code": codes})
    )
    monkeypatch.setattr(stock_hist_em.time, "sleep", lambda _: None)

    def fake_request(url, params, **kwargs):
        assert url == "https://push2.eastmoney.com/api/qt/ulist.np/get"
        batch = params["secids"].split(",")
        batches.append(batch)
        rows = []
        for secid in batch:
            market, code = secid.split(".")
            row = {f"f{i}": str(i) for i in range(1, 26)}
            row.update(
                {
                    "f12": code,
                    "f13": int(market),
                    "f14": "东财" + code,
                    "f2": "-" if code == "000001" else "11.65",
                    "f3": "-" if code == "000001" else code[-3:],
                    "f99999": "ignored",
                }
            )
            rows.append(dict(reversed(list(row.items()))))
        return SimpleNamespace(json=lambda: {"data": {"diff": rows}})

    monkeypatch.setattr(stock_hist_em, "request_eastmoney", fake_request)
    result = stock_hist_em.stock_zh_a_spot_em()

    assert [len(batch) for batch in batches] == [500, 3]
    assert batches[1] == ["1.600519", "0.300750", "0.920001"]
    assert len(result) == result["代码"].nunique() == 503
    assert result["序号"].tolist() == list(range(1, 504))
    assert result["涨跌幅"].dropna().is_monotonic_decreasing
    assert result.iloc[-1]["代码"] == "000001"
    assert pd.isna(result.iloc[-1]["最新价"])
    assert result.loc[result["代码"] == "600519", "名称"].item() == "东财600519"
    assert result.loc[result["代码"] == "600519", "成交量"].item() == 5
    assert result.loc[result["代码"] == "600519", "最新价"].item() == 11.65
    assert list(result.columns) == [
        "序号",
        "代码",
        "名称",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "最高",
        "最低",
        "今开",
        "昨收",
        "量比",
        "换手率",
        "市盈率-动态",
        "市净率",
        "总市值",
        "流通市值",
        "涨速",
        "5分钟涨跌",
        "60日涨跌幅",
        "年初至今涨跌幅",
    ]


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"diff": []},
        {"diff": [{"f12": "000001", "f13": 0}]},
        {"diff": [{"f12": "000001", "f13": 0}, {"f12": "000001", "f13": 0}]},
    ],
)
def test_stock_zh_a_spot_rejects_incomplete_quote_batches(monkeypatch, data):
    import pandas as pd
    from akshare.stock_feature import stock_hist_em

    monkeypatch.setattr(
        stock_hist_em,
        "stock_info_a_code_name",
        lambda: pd.DataFrame({"code": ["000001", "600519"]}),
    )
    monkeypatch.setattr(
        stock_hist_em,
        "request_eastmoney",
        lambda *args, **kwargs: SimpleNamespace(json=lambda: {"data": data}),
    )

    with pytest.raises(RuntimeError, match="incomplete A-share quote batch"):
        stock_hist_em.stock_zh_a_spot_em()


def test_stock_zh_a_spot_rejects_empty_security_list(monkeypatch):
    import pandas as pd
    from akshare.stock_feature import stock_hist_em

    monkeypatch.setattr(
        stock_hist_em, "stock_info_a_code_name", lambda: pd.DataFrame({"code": []})
    )
    with pytest.raises(RuntimeError, match="security list is empty"):
        stock_hist_em.stock_zh_a_spot_em()


@pytest.mark.parametrize("fail_second_page", [False, True])
def test_bse_security_roster_uses_bounded_session_and_keeps_first_page(
    monkeypatch, fail_second_page
):
    import json
    from akshare.stock import stock_info

    calls = []
    closed = []
    stock_info.stock_info_bj_name_code.cache_clear()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def mount(self, prefix, adapter):
            assert prefix == "https://www.bse.cn/"
            assert adapter.max_retries.total == 2
            assert adapter.max_retries.allowed_methods == frozenset({"POST"})

        def post(self, url, data, headers, timeout):
            assert url == "https://www.bse.cn/nqxxController/nqxxCnzq.do"
            assert timeout == 10
            assert "Cookie" not in headers
            page = int(data["page"])
            calls.append(page)
            if page == 1 and fail_second_page:
                raise requests.ConnectionError("roster page failed")
            row = {f"field{i}": "" for i in range(48)}
            row.update(
                {
                    "field0": "2026-01-01",
                    "field22": "2026-10-19",
                    "field38": f"92000{page + 1}",
                    "field40": f"证券{page + 1}",
                }
            )
            payload = [{"totalPages": 2, "content": [row]}]
            return SimpleNamespace(
                text="(" + json.dumps(payload) + ")", raise_for_status=lambda: None
            )

    monkeypatch.setattr(stock_info.requests, "Session", FakeSession)
    try:
        if fail_second_page:
            with pytest.raises(requests.ConnectionError, match="roster page failed"):
                stock_info.stock_info_bj_name_code()
            assert stock_info.stock_info_bj_name_code.cache_info().currsize == 0
        else:
            result = stock_info.stock_info_bj_name_code()
            assert result["证券代码"].tolist() == ["920001", "920002"]
            assert result["证券简称"].tolist() == ["证券1", "证券2"]
        assert calls == [0, 1]
        assert closed == [True]
    finally:
        stock_info.stock_info_bj_name_code.cache_clear()


def test_stock_zh_a_hist_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.stock_feature import stock_hist_em

    class EmptyKlineResponse:
        status_code = 200
        text = '{"data":{"klines":[]}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"klines": []}}

    def fake_request_eastmoney(*args, **kwargs):
        return EmptyKlineResponse()

    monkeypatch.setattr(stock_hist_em, "request_eastmoney", fake_request_eastmoney)

    result = stock_hist_em.stock_zh_a_hist(
        symbol="000001",
        start_date="20240601",
        end_date="20240630",
    )

    assert result.empty


def test_fund_etf_hist_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.fund import fund_etf_em

    def fake_get_market_id(symbol):
        return 0

    def fake_eastmoney_json(*args, **kwargs):
        return {"data": {"klines": []}}

    monkeypatch.setattr(fund_etf_em, "get_market_id", fake_get_market_id)
    monkeypatch.setattr(fund_etf_em, "_get_eastmoney_fund_json", fake_eastmoney_json)

    result = fund_etf_em.fund_etf_hist_em(
        symbol="159707",
        start_date="20240601",
        end_date="20240630",
    )

    assert result.empty


def test_fund_lof_hist_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.fund import fund_lof_em

    def fake_code_map():
        return {"166009": 0}

    def fake_eastmoney_json(*args, **kwargs):
        return {"data": {"klines": []}}

    monkeypatch.setattr(fund_lof_em, "_fund_lof_code_id_map_em", fake_code_map)
    monkeypatch.setattr(fund_lof_em, "_get_eastmoney_lof_json", fake_eastmoney_json)

    result = fund_lof_em.fund_lof_hist_em(
        symbol="166009",
        start_date="20240601",
        end_date="20240630",
    )

    assert result.empty


def test_stock_hk_hist_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.stock_feature import stock_hist_em

    class EmptyKlineResponse:
        status_code = 200
        text = '{"data":{"klines":[]}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"klines": []}}

    def fake_request_eastmoney(*args, **kwargs):
        return EmptyKlineResponse()

    monkeypatch.setattr(stock_hist_em, "request_eastmoney", fake_request_eastmoney)

    result = stock_hist_em.stock_hk_hist(
        symbol="00593",
        start_date="20240601",
        end_date="20240630",
    )

    assert result.empty


def test_stock_us_hist_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.stock_feature import stock_hist_em

    class EmptyKlineResponse:
        status_code = 200
        text = '{"data":{"klines":[]}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"klines": []}}

    def fake_request_eastmoney(*args, **kwargs):
        return EmptyKlineResponse()

    monkeypatch.setattr(stock_hist_em, "request_eastmoney", fake_request_eastmoney)

    result = stock_hist_em.stock_us_hist(
        symbol="105.AAPL",
        start_date="20240601",
        end_date="20240630",
    )

    assert result.empty


def test_stock_sector_fund_flow_rank_uses_request_eastmoney(monkeypatch):
    from akshare.stock import stock_fund_em

    called_urls = []
    row_values = [
        "BK0420",
        1.23,
        10.5,
        "汽车服务",
        100000,
        20000,
        1.1,
        30000,
        1.2,
        40000,
        1.3,
        50000,
        1.4,
        "-",
        5.5,
        "示例股份",
        "000001",
        "Y",
    ]
    diff = [{f"f{i}": value for i, value in enumerate(row_values)}]

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"total":1,"diff":[]}}',
            json=lambda: {"data": {"total": 1, "diff": diff}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    monkeypatch.setattr(
        stock_fund_em, "request_eastmoney", fake_request_eastmoney, raising=False
    )
    monkeypatch.setattr(stock_fund_em.requests, "get", fake_requests_get)

    result = stock_fund_em.stock_sector_fund_flow_rank(
        indicator="今日",
        sector_type="行业资金流",
    )

    assert len(result) == 1
    assert result.loc[0, "名称"] == "汽车服务"
    assert result.loc[0, "今日主力净流入最大股"] == "示例股份"
    assert called_urls == [
        "https://push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    ]


def test_stock_fund_flow_klines_use_request_eastmoney(monkeypatch):
    from akshare.stock import stock_fund_em

    called_urls = []

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"klines":["2024-06-03,1,2"]}}',
            json=lambda: {"data": {"klines": ["2024-06-03,1,2"]}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    monkeypatch.setattr(
        stock_fund_em, "request_eastmoney", fake_request_eastmoney, raising=False
    )
    monkeypatch.setattr(stock_fund_em.requests, "get", fake_requests_get)

    result = stock_fund_em._get_eastmoney_fund_flow_klines(
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        {"secid": "90.BK1034"},
        "汽车服务",
        "sector",
    )

    assert result == ["2024-06-03,1,2"]
    assert called_urls == [
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    ]


def test_futures_hist_em_uses_request_eastmoney(monkeypatch):
    from akshare.futures import futures_hist_em

    called_urls = []

    def fake_symbol_map():
        return (
            {"热卷主连": 113},
            {"热卷主连": "hc888"},
            {"hc": 113},
            {"热卷": 113},
        )

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"klines":["2024-06-03,1,2,3,4,5,6,0,7,8,0,0,9,0"]}}',
            json=lambda: {"data": {"klines": ["2024-06-03,1,2,3,4,5,6,0,7,8,0,0,9,0"]}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    monkeypatch.setattr(futures_hist_em, "__get_exchange_symbol_map", fake_symbol_map)
    monkeypatch.setattr(
        futures_hist_em,
        "request_eastmoney",
        fake_request_eastmoney,
        raising=False,
    )
    monkeypatch.setattr(futures_hist_em.requests, "get", fake_requests_get)

    result = futures_hist_em.futures_hist_em(
        symbol="热卷主连",
        period="daily",
        start_date="20240601",
        end_date="20240630",
    )

    assert len(result) == 1
    assert result.loc[0, "收盘"] == 2
    assert called_urls == ["https://push2his.eastmoney.com/api/qt/stock/kline/get"]


def test_futures_global_hist_uses_request_eastmoney(monkeypatch):
    from akshare.futures import futures_hf_em

    called_urls = []

    def fake_request(url, **kwargs):
        called_urls.append(url)
        assert kwargs["params"]["secid"] == "101.HG00Y"
        return SimpleNamespace(
            json=lambda: {
                "data": {
                    "code": "HG00Y",
                    "name": "COMEX铜",
                    "klines": ["2026-10-09,1,2,3,4,5,6,0,7,8,0,0,9,4294967295"],
                }
            }
        )

    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("must use the shared request helper")

    monkeypatch.setattr(futures_hf_em, "request_eastmoney", fake_request, raising=False)
    monkeypatch.setattr(futures_hf_em.requests, "get", fake_get)

    result = futures_hf_em.futures_global_hist_em(symbol="HG00Y")

    assert called_urls == ["https://push2his.eastmoney.com/api/qt/stock/kline/get"]
    assert result.loc[0, "最新价"] == 2
    assert result.loc[0, "代码"] == "HG00Y"
    assert result.loc[0, "日增"] == -1
    assert list(result.columns) == [
        "日期",
        "代码",
        "名称",
        "开盘",
        "最新价",
        "最高",
        "最低",
        "总量",
        "涨幅",
        "持仓",
        "日增",
    ]


@pytest.mark.parametrize("data", [None, {"klines": []}])
def test_futures_global_hist_returns_empty_for_missing_klines(monkeypatch, data):
    from akshare.futures import futures_hf_em

    response = SimpleNamespace(json=lambda: {"data": data})
    monkeypatch.setattr(
        futures_hf_em,
        "request_eastmoney",
        lambda *args, **kwargs: response,
        raising=False,
    )
    monkeypatch.setattr(futures_hf_em.requests, "get", lambda *args, **kwargs: response)

    assert futures_hf_em.futures_global_hist_em(symbol="HG00Y").empty


def test_stock_hsgt_hold_stock_returns_empty_when_result_missing(monkeypatch):
    from akshare.stock_feature import stock_hsgt_em

    class FakePageResponse:
        text = '<div class="title">个股排行<span class="t">（2024-08-16）</span></div>'

    class FakeApiResponse:
        def json(self):
            return {"success": False, "result": None, "message": "服务器繁忙"}

    def fake_get(url, **kwargs):
        if "hsgtcg/list.html" in url:
            return FakePageResponse()
        return FakeApiResponse()

    monkeypatch.setattr(stock_hsgt_em.requests, "get", fake_get)

    result = stock_hsgt_em.stock_hsgt_hold_stock_em()

    assert result.empty
    assert list(result.columns) == [
        "序号",
        "代码",
        "名称",
        "今日收盘价",
        "今日涨跌幅",
        "今日持股-股数",
        "今日持股-市值",
        "今日持股-占流通股比",
        "今日持股-占总股本比",
        "5日增持估计-股数",
        "5日增持估计-市值",
        "5日增持估计-市值增幅",
        "5日增持估计-占流通股比",
        "5日增持估计-占总股本比",
        "所属板块",
        "日期",
    ]


def test_stock_gpzy_bank_returns_empty_when_result_missing(monkeypatch):
    from akshare.stock_feature import stock_gpzy_em

    class EmptyResponse:
        def json(self):
            return {"success": False, "result": None, "message": "返回数据为空"}

    monkeypatch.setattr(
        stock_gpzy_em.requests, "get", lambda *args, **kwargs: EmptyResponse()
    )

    result = stock_gpzy_em.stock_gpzy_distribute_statistics_bank_em()

    assert result.empty
    assert list(result.columns) == [
        "序号",
        "质押机构",
        "质押公司数量",
        "质押笔数",
        "质押数量",
        "未达预警线比例",
        "达到预警线未达平仓线比例",
        "达到平仓线比例",
    ]


def test_stock_cyq_returns_empty_when_eastmoney_klines_empty(monkeypatch):
    from akshare.stock_feature import stock_cyq_em

    class EmptyKlineResponse:
        def json(self):
            return {"data": {"klines": []}}

    monkeypatch.setattr(
        stock_cyq_em,
        "request_eastmoney",
        lambda *args, **kwargs: EmptyKlineResponse(),
        raising=False,
    )

    result = stock_cyq_em.stock_cyq_em(symbol="000001")

    assert result.empty
    assert list(result.columns) == [
        "日期",
        "获利比例",
        "平均成本",
        "90成本-低",
        "90成本-高",
        "90集中度",
        "70成本-低",
        "70成本-高",
        "70集中度",
    ]


def test_stock_szse_area_summary_uses_request_szse(monkeypatch):
    from io import BytesIO

    import pandas as pd

    from akshare.stock import stock_summary

    called_urls = []
    payload = BytesIO()
    pd.DataFrame(
        {
            "序号": [1],
            "地区": ["深圳"],
            "总交易额(元)": ["1,000"],
            "占市场%": [1.2],
            "股票交易额(元)": ["800"],
            "基金交易额(元)": ["100"],
            "债券交易额(元)": ["100"],
        }
    ).to_excel(payload, index=False)

    def fake_request_szse(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(content=payload.getvalue())

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError(
            "primary endpoint should use SZSE fallback helper"
        )

    monkeypatch.setattr(stock_summary, "request_szse", fake_request_szse, raising=False)
    monkeypatch.setattr(stock_summary.requests, "get", fake_requests_get)

    result = stock_summary.stock_szse_area_summary(date="202203")

    assert len(result) == 1
    assert result.loc[0, "总交易额"] == 1000
    assert called_urls == ["https://www.szse.cn/api/report/ShowReport"]


def test_famous_and_pink_spot_use_request_eastmoney(monkeypatch):
    from akshare.stock import stock_hk_famous, stock_us_famous, stock_us_pink

    called_urls = []

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"diff":[],"total":0}}',
            json=lambda: {"data": {"diff": [], "total": 0}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    for module in (stock_hk_famous, stock_us_famous, stock_us_pink):
        monkeypatch.setattr(
            module,
            "request_eastmoney",
            fake_request_eastmoney,
            raising=False,
        )
        monkeypatch.setattr(module.requests, "get", fake_requests_get)

    assert stock_hk_famous.stock_hk_famous_spot_em().empty
    assert stock_us_famous.stock_us_famous_spot_em().empty
    assert stock_us_pink.stock_us_pink_spot_em().empty
    assert called_urls == [
        "https://69.push2.eastmoney.com/api/qt/clist/get",
        "https://69.push2.eastmoney.com/api/qt/clist/get",
        "https://23.push2.eastmoney.com/api/qt/clist/get",
    ]


def test_board_minute_functions_use_request_eastmoney(monkeypatch):
    from akshare.stock import stock_board_concept_em, stock_board_industry_em

    called_urls = []

    def fake_name_df():
        import pandas as pd

        return pd.DataFrame(
            {
                "板块名称": ["小金属", "数据要素"],
                "板块代码": ["BK1027", "BK1123"],
            }
        )

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"trends":[]}}',
            json=lambda: {"data": {"trends": []}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    monkeypatch.setattr(
        stock_board_industry_em,
        "__stock_board_industry_name_em",
        fake_name_df,
    )
    monkeypatch.setattr(
        stock_board_concept_em,
        "__stock_board_concept_name_em",
        fake_name_df,
    )
    for module in (stock_board_industry_em, stock_board_concept_em):
        monkeypatch.setattr(
            module,
            "request_eastmoney",
            fake_request_eastmoney,
            raising=False,
        )
        monkeypatch.setattr(module.requests, "get", fake_requests_get)

    assert stock_board_industry_em.stock_board_industry_hist_min_em(
        symbol="小金属", period="1"
    ).empty
    assert stock_board_concept_em.stock_board_concept_hist_min_em(
        symbol="数据要素", period="1"
    ).empty
    assert called_urls == [
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
    ]


def test_reits_realtime_uses_request_eastmoney(monkeypatch):
    from akshare.reits import reits_basic

    called_urls = []

    def fake_request_eastmoney(url, **kwargs):
        called_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"data":{"diff":[]}}',
            raise_for_status=lambda: None,
            json=lambda: {"data": {"diff": []}},
        )

    def fake_requests_get(*args, **kwargs):
        raise requests.ConnectionError("primary endpoint should use fallback helper")

    monkeypatch.setattr(
        reits_basic,
        "request_eastmoney",
        fake_request_eastmoney,
        raising=False,
    )
    monkeypatch.setattr(reits_basic.requests, "get", fake_requests_get)

    assert reits_basic.reits_realtime_em().empty
    assert called_urls == ["https://95.push2.eastmoney.com/api/qt/clist/get"]
