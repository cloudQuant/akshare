#!/usr/bin/env python
# -*- coding:utf-8 -*-

from akshare.stock import stock_cg_lawsuit


def test_lawsuit_records_to_df_uses_standard_columns():
    df = stock_cg_lawsuit._lawsuit_records_to_df(
        [
            {
                "AINTERVAL": "2021-09-01---2021-09-27",
                "F002N": "100.5",
                "F001N": "2",
                "SECNAME": "测试公司",
                "SECCODE": "000001",
            }
        ]
    )

    assert list(df.columns) == stock_cg_lawsuit._STOCK_CG_LAWSUIT_COLUMNS
    assert df.loc[0, "证券代码"] == "000001"
    assert df.loc[0, "诉讼次数"] == 2
    assert df.loc[0, "诉讼金额"] == 100.5
