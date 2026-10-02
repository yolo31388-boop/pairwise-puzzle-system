"""测试辅助：测试类未继承 unittest.TestCase，这里补上 assertIsNotNone。

不修改测试文件本身，只通过 conftest 注入缺失的断言方法。
"""

from tests.test_puzzle import TestPuzzleSystem


def _assert_is_not_none(self, obj, msg=None):
    assert obj is not None, msg or "unexpectedly None"


TestPuzzleSystem.assertIsNotNone = _assert_is_not_none
