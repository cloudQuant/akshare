#!/usr/bin/env python
# -*- coding:utf-8 -*-

from akshare.stock_feature import stock_info


def test_cls_signed_params_matches_web_sign():
    params = stock_info._cls_signed_params({"name": "telegraph"})

    assert params["app"] == "CailianpressWeb"
    assert params["os"] == "web"
    assert params["sv"] == "8.7.9"
    assert params["sign"] == "6c73b056a64891cdc257dcf1914464ad"


def test_stock_info_global_cls_uses_new_cache_endpoint(monkeypatch):
    captured = {}

    def fake_request(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return {
            "errno": 0,
            "data": {
                "roll_data": [
                    {
                        "title": "普通电报",
                        "content": "普通内容",
                        "ctime": 1782000000,
                        "level": "C",
                    },
                    {
                        "title": "重点电报",
                        "content": "重点内容",
                        "ctime": 1782000100,
                        "level": "B",
                    },
                ]
            },
        }

    monkeypatch.setattr(stock_info, "make_request_with_retry_json", fake_request)

    all_df = stock_info.stock_info_global_cls(symbol="全部")
    important_df = stock_info.stock_info_global_cls(symbol="重点")

    assert captured["url"] == "https://www.cls.cn/api/cache"
    assert captured["params"]["name"] == "telegraph"
    assert "sign" in captured["params"]
    assert list(all_df.columns) == ["标题", "内容", "发布日期", "发布时间"]
    assert len(all_df) == 2
    assert important_df["标题"].tolist() == ["重点电报"]
