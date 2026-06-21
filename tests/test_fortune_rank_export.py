import akshare as ak
from akshare.fortune.fortune_500 import fortune_rank


def test_fortune_rank_is_exported_from_top_level_package():
    assert ak.fortune_rank is fortune_rank
