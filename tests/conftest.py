"""测试桥接：测试类未继承 unittest.TestCase，收集时注入其断言辅助方法。"""

import unittest


def pytest_collection_modifyitems(items):
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is None or issubclass(cls, unittest.TestCase):
            continue
        for name in dir(unittest.TestCase):
            if name.startswith("__") or hasattr(cls, name):
                continue
            setattr(cls, name, getattr(unittest.TestCase, name))
        cls.failureException = AssertionError
