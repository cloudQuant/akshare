#!/usr/bin/env python
# -*- coding:utf-8 -*-

from requests.exceptions import ReadTimeout

from akshare.spot import spot_sge


def test_spot_quotations_sge_timeout_returns_empty(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise ReadTimeout("sge timeout")

    monkeypatch.setattr(spot_sge.requests, "request", raise_timeout)
    monkeypatch.setattr(spot_sge.time, "sleep", lambda seconds: None)

    df = spot_sge.spot_quotations_sge()

    assert df.empty
    assert list(df.columns) == spot_sge._SPOT_QUOTATIONS_SGE_COLUMNS


def test_spot_hist_sge_timeout_returns_empty(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise ReadTimeout("sge timeout")

    monkeypatch.setattr(spot_sge.requests, "request", raise_timeout)
    monkeypatch.setattr(spot_sge.time, "sleep", lambda seconds: None)

    df = spot_sge.spot_hist_sge()

    assert df.empty
    assert list(df.columns) == spot_sge._SPOT_HIST_SGE_COLUMNS


def test_spot_benchmark_sge_timeout_returns_empty(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise ReadTimeout("sge timeout")

    monkeypatch.setattr(spot_sge.requests, "request", raise_timeout)
    monkeypatch.setattr(spot_sge.time, "sleep", lambda seconds: None)

    gold_df = spot_sge.spot_golden_benchmark_sge()
    silver_df = spot_sge.spot_silver_benchmark_sge()

    assert gold_df.empty
    assert list(gold_df.columns) == spot_sge._SPOT_BENCHMARK_SGE_COLUMNS
    assert silver_df.empty
    assert list(silver_df.columns) == spot_sge._SPOT_BENCHMARK_SGE_COLUMNS
