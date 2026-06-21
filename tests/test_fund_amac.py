#!/usr/bin/env python
# -*- coding:utf-8 -*-

import pandas as pd

from akshare.fund import fund_amac


def test_amac_futures_info_uses_supported_page_size(monkeypatch):
    calls = []

    def fake_post_json(url, **kwargs):
        calls.append(kwargs["params"].copy())
        if len(calls) == 1:
            return {"totalPages": 1}
        return {
            "content": [
                {
                    "mpiName": "期货资管计划",
                    "mpiProductCode": "SAMS24",
                    "aoiName": "期货公司",
                    "mpiTrustee": "托管人",
                    "mpiCreateDate": "2026-05-25",
                    "tzlx": "期货和衍生品类",
                    "sfjgh": "否",
                    "registeredDate": "2026-06-01",
                    "dueDate": "2036-05-24",
                    "fundStatus": "正在运作",
                }
            ]
        }

    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    df = fund_amac.amac_futures_info()

    assert calls[0]["size"] == "20"
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == fund_amac._AMAC_FUTURES_INFO_COLUMNS


def test_amac_fund_info_default_fetches_through_total_pages(monkeypatch):
    page_calls = []

    def fake_post_json(url, **kwargs):
        params = kwargs["params"].copy()
        if not page_calls:
            page_calls.append(params)
            return {"totalPages": 2001}
        page_calls.append(params)
        return {
            "content": [
                {
                    "fundName": f"基金{params['page']}",
                    "managerName": "管理人",
                    "managerType": "私募证券投资基金管理人",
                    "workingState": "正在运作",
                    "putOnRecordDate": 1717200000000,
                    "establishDate": 1717113600000,
                    "mandatorName": "托管人",
                }
            ]
        }

    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    df = fund_amac.amac_fund_info(start_page="1999")

    fetched_pages = [call["page"] for call in page_calls[1:]]
    assert fetched_pages == [1998, 1999, 2000]
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == fund_amac._AMAC_FUND_INFO_COLUMNS
