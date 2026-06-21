#!/usr/bin/env python
# -*- coding:utf-8 -*-

import akshare as ak


def test_hf_subscribe_exchange_symbol_compat_alias():
    legacy_df = ak.hf_subscribe_exchange_symbol()
    current_df = ak.futures_hq_subscribe_exchange_symbol()

    assert legacy_df.equals(current_df)
    assert list(legacy_df.columns) == ["symbol", "code"]
    assert len(legacy_df) == 30
