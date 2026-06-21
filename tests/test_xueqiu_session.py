#!/usr/bin/env python
# -*- coding:utf-8 -*-

from akshare.stock import stock_xq
from akshare.stock_fundamental import stock_basic_info_xq


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text="{}"):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_xueqiu_company_fetches_dynamic_page_cookie(monkeypatch):
    calls = []

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            if "company.json" in url:
                return _FakeResponse(
                    {
                        "data": {
                            "company": {
                                "org_id": "T000071215",
                                "org_name_cn": "赛力斯集团股份有限公司",
                            }
                        }
                    }
                )
            return _FakeResponse()

    monkeypatch.setattr(stock_basic_info_xq.requests, "Session", FakeSession)

    df = stock_basic_info_xq.stock_individual_basic_info_xq(symbol="SH601127")

    assert calls[0][0] == "https://xueqiu.com/snowman/S/SH601127/detail"
    assert "company.json" in calls[1][0]
    assert df.loc[df["item"] == "org_id", "value"].iloc[0] == "T000071215"


def test_xueqiu_quote_fetches_dynamic_page_cookie(monkeypatch):
    calls = []

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            if "quote.json" in url:
                return _FakeResponse(
                    {
                        "data": {
                            "quote": {
                                "symbol": "SH600000",
                                "name": "浦发银行",
                                "current": 10.5,
                                "time": 1782000000000,
                            }
                        }
                    }
                )
            return _FakeResponse()

    monkeypatch.setattr(stock_xq.requests, "Session", FakeSession)

    df = stock_xq.stock_individual_spot_xq(symbol="SH600000")

    assert calls[0][0] == "https://xueqiu.com/snowman/S/SH600000/detail"
    assert "quote.json" in calls[1][0]
    assert df.loc[df["item"] == "代码", "value"].iloc[0] == "SH600000"
