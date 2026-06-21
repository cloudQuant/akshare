import pandas as pd

from akshare.stock import stock_hot_search_baidu


class _DeniedResponse:
    def json(self):
        return {"QueryID": "0", "ResultCode": "403", "Result": []}


def test_stock_hot_search_baidu_returns_empty_frame_for_denied_response(monkeypatch):
    monkeypatch.setattr(
        stock_hot_search_baidu.requests,
        "get",
        lambda *args, **kwargs: _DeniedResponse(),
    )

    result = stock_hot_search_baidu.stock_hot_search_baidu()

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == ["名称/代码", "涨跌幅", "综合热度"]
