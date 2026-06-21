from types import SimpleNamespace

import requests


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

    monkeypatch.setattr(stock_fund_em, "request_eastmoney", fake_request_eastmoney, raising=False)
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

    monkeypatch.setattr(stock_fund_em, "request_eastmoney", fake_request_eastmoney, raising=False)
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
            json=lambda: {
                "data": {
                    "klines": ["2024-06-03,1,2,3,4,5,6,0,7,8,0,0,9,0"]
                }
            },
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

    monkeypatch.setattr(stock_gpzy_em.requests, "get", lambda *args, **kwargs: EmptyResponse())

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
        raise requests.ConnectionError("primary endpoint should use SZSE fallback helper")

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
