import pandas as pd

from akshare.stock_feature import stock_a_below_net_asset_statistics as below_net


class _FakeResponse:
    def json(self):
        return [
            {
                "belowNetAsset": 36,
                "totalCompany": 1352,
                "date": "2005-01-05",
                "close": 1251.94,
            }
        ]


def test_stock_a_below_net_asset_statistics_accepts_current_legulegu_shape(monkeypatch):
    monkeypatch.setattr(below_net.requests, "get", lambda *args, **kwargs: _FakeResponse())

    result = below_net.stock_a_below_net_asset_statistics()

    assert list(result.columns) == [
        "date",
        "below_net_asset",
        "total_company",
        "below_net_asset_ratio",
    ]
    assert result.loc[0, "date"] == pd.Timestamp("2005-01-05").date()
    assert result.loc[0, "below_net_asset"] == 36
    assert result.loc[0, "total_company"] == 1352
    assert result.loc[0, "below_net_asset_ratio"] == round(36 / 1352, 4)
