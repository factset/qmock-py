import sys

if sys.version_info[0] < 3:
    # python 2.7
    from thread import get_ident as get_thread_id
    import mock
    if hasattr(mock, "mock"):
        # mock>=1.1
        mock = mock.mock
else:
    # python 3.4+
    from threading import get_ident as get_thread_id
    from unittest import mock

if (sys.version_info < (3, 6, 8)
        or (3, 7, 0) <= sys.version_info < (3, 7, 2)):
    def call_parts(kall):
        return kall.name, kall.parent, kall.from_kall
else:
    def call_parts(kall):
        return kall._mock_name, kall._mock_parent, kall._mock_from_kall
