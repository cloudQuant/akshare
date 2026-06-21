#!/usr/bin/env python
# -*- coding:utf-8 -*-

import pytest

from akshare.fx import fx_quote_baidu


def test_parse_foreign_rank_new_tablelist_payload():
    data_json = {
        "ResultCode": "0",
        "Result": {
            "list": {
                "body": [
                    {
                        "code": "CNYUSD",
                        "name": "人民币美元",
                        "price": "0.1380",
                        "increase": "0.0001",
                        "ratio": "+0.0700%",
                    }
                ]
            }
        },
    }

    df = fx_quote_baidu._parse_foreign_rank(data_json)

    assert list(df.columns) == fx_quote_baidu._FX_QUOTE_BAIDU_COLUMNS
    assert df.loc[0, "代码"] == "CNYUSD"
    assert df.loc[0, "最新价"] == 0.138
    assert df.loc[0, "涨跌幅"] == pytest.approx(0.0007)
