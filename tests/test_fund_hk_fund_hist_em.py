import pandas as pd

from akshare.fund import fund_em


class _FakeResponse:
    def json(self):
        return {"Data": []}


def test_fund_hk_fund_hist_em_returns_empty_frame_for_missing_dividend_rows(monkeypatch):
    monkeypatch.setattr(fund_em.requests, "get", lambda *args, **kwargs: _FakeResponse())

    result = fund_em.fund_hk_fund_hist_em(code="968000", symbol="分红送配详情")

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == [
        "年份",
        "权益登记日",
        "除息日",
        "分红发放日",
        "分红金额",
        "单位",
    ]


def test_fund_hk_fund_hist_em_returns_empty_frame_for_missing_nav_rows(monkeypatch):
    monkeypatch.setattr(fund_em.requests, "get", lambda *args, **kwargs: _FakeResponse())

    result = fund_em.fund_hk_fund_hist_em(code="968000", symbol="历史净值明细")

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == [
        "净值日期",
        "单位净值",
        "日增长值",
        "日增长率",
        "单位",
    ]
