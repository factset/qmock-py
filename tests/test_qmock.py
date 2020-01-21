from collections import OrderedDict
import signal
import sys
from threading import Thread
import unittest

import qmock
from qmock._python_compat import get_thread_id, mock

# arbitrary targets for qmock.patch() tests
import datetime, json, xml.etree.ElementTree
DATETIME_DATE = "datetime.date"
JSON_LOADS = "json.loads"
XML_ETREE_ELEMENTTREE = "xml.etree.ElementTree"

PY2 = sys.version_info[0] < 3

class QMockErrorsInThreadsTests(unittest.TestCase):
    def test_str(self):
        error = qmock.QMockErrorsInThreads(
            [RuntimeError("foo"), ValueError("bar"), KeyError("baz")]
        )
        self.assertEqual(
            str(error),
            "Unhandled QMock errors raised in other threads:"
            " ["
                + repr(RuntimeError("foo")) + ", "
                + repr(ValueError("bar")) + ", "
                + repr(KeyError("baz"))
            + "]"
        )

class patchTests(unittest.TestCase):
    def setUp(self):
        self._assert_no_patches()

    def tearDown(self):
        self._assert_no_patches()

    def _assert_no_patches(self):
        self._assert_datetime_is_not_patched()
        self._assert_json_is_not_patched()
        self._assert_xml_etree_is_not_patched()

    def _assert_datetime_is_not_patched(self):
        self.assertEqual(
            str(datetime.date(1, 2, 3)),
            "0001-02-03"
        )

    def _assert_json_is_not_patched(self):
        self.assertEqual(
            json.loads("[1,2,3]"),
            [1, 2, 3]
        )

    def _assert_xml_etree_is_not_patched(self):
        self.assertEqual(
            xml.etree.ElementTree.fromstring("<foo />").tag,
            "foo"
        )

    def _force_unexpected_call_in_thread(self, qm):
        try:
            thread = Thread(target=qm.an_unknown_call)
            thread.start()
            # we expect the thread to die immediately because of an
            # UnexpectedCall. the alarms are an abundance of caution.
            signal.alarm(1)
            thread.join()
            signal.alarm(0)
        except BaseException as ex:
            self.fail("Thread setup caught: {0!r}".format(ex))

    def _assert_thread_qmock_errors(self, errors_in_thread_error):
        """
            QMockErrorsInThreads.errors should contain a single
            UnexpectedCall raised in a different thread.
        """
        qmock_errors_from_threads = errors_in_thread_error.errors
        self.assertEqual(len(qmock_errors_from_threads), 1)

        qmock_error_tid, qmock_error = qmock_errors_from_threads[0]
        self.assertNotEqual(qmock_error_tid, get_thread_id())
        self.assertIsInstance(qmock_error, qmock.UnexpectedCall)

    def _assert_patched_func_error(self, errors_in_thread_error,
                                   expected_func_error_type):
        """
            in Python 3, when multiple exceptions are being handled at once,
            each exception has a __context__ which is the last exception
            raised before this one (or `None`, if this is the first
            exception in the current batch of active exceptions).

            so QMockErrorsInThreads.__context__ should be the exception
            raised by the function/scope being patched.
        """
        if PY2:
            # Python 2 has no __context__
            return
        patched_func_error = errors_in_thread_error.__context__
        if expected_func_error_type is None:
            self.assertIsNone(patched_func_error)
        else:
            self.assertIsInstance(patched_func_error, expected_func_error_type)


    def test_empty_function_decorator_succeeds(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            qm.call_queue.push(qmock.call.bar(), 5)
            self.assertEqual(qm.bar(), 5)

        foo() # no raise == success

    # a little silly because nothing is being patched, but just in case.
    def test_empty_function_decorator_cleans_up_on_func_exception(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            raise RuntimeError("TEST")

        self.assertRaises(RuntimeError, foo)

    def test_empty_function_decorator_raises_on_exit_if_queue_not_empty(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            qm.call_queue.push(qmock.call.bar(), 5)

        self.assertRaises(qmock.CallQueueNotEmpty, foo)

    def test_empty_function_decorator_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            # would raise CallQueueNotEmpty if not handling RuntimeError
            qm.call_queue.push(qmock.call.bar(), 5)
            raise RuntimeError("TEST")

        self.assertRaises(RuntimeError, foo)

    def test_empty_function_decorator_raises_on_exit_if_errors_in_threads(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            self._force_unexpected_call_in_thread(qm)

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_empty_function_decorator_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        @qmock.patch()
        def foo(qm):
            self._assert_no_patches()
            # raises QMockErrorsInThreads on top of RuntimeError
            self._force_unexpected_call_in_thread(qm)
            raise RuntimeError("TEST")

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, RuntimeError)


    def test_single_patch_function_decorator_succeeds(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
            self.assertEqual(datetime.date(1, 2, 3), 7)
        self._assert_no_patches()

        foo()

    def test_single_patch_function_decorator_cleans_up_on_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            raise ValueError("TEST")
        self._assert_no_patches()

        self.assertRaises(ValueError, foo)

    def test_single_patch_function_decorator_cleans_up_on_bad_patch(self):
        @qmock.patch(dt="datetime.BAD")
        def foo(qm):
            self.fail("This test function should not run.")
        self._assert_no_patches()

        self.assertRaises(AttributeError, foo)

    def test_single_patch_function_decorator_raises_on_exit_if_queue_not_empty(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
        self._assert_no_patches()

        self.assertRaises(qmock.CallQueueNotEmpty, foo)

    def test_single_patch_function_decorator_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            # would raise CallQueueNotEmpty if not handling ValueError
            qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
            raise ValueError("TEST")
        self._assert_no_patches()

        self.assertRaises(ValueError, foo)

    def test_single_patch_function_decorator_raises_on_exit_if_errors_in_threads(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            self._force_unexpected_call_in_thread(qm)
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_single_patch_function_decorator_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            # raises QMockErrorsInThreads on top of ValueError
            self._force_unexpected_call_in_thread(qm)
            raise ValueError("TEST")
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, ValueError)


    def test_multi_patch_function_decorator_succeeds(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

            self.assertEqual(datetime.date(1, 2, 3), "a")
            self.assertEqual(xml.etree.ElementTree.fromstring("<foo />"), "b")
            self.assertEqual(json.loads("[1,2,3]"), "c")
        self._assert_no_patches()

        foo()

    def test_multi_patch_function_decorator_cleans_up_on_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            raise KeyError("TEST")
        self._assert_no_patches()

        self.assertRaises(KeyError, foo)

    def test_multi_patch_function_decorator_cleans_up_on_bad_patch(self):
        @qmock.patch(dt=DATETIME_DATE, json="json.BAD", et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            self.fail("This test function should not run.")
        self._assert_no_patches()

        self.assertRaises(AttributeError, foo)

    def test_multi_patch_function_decorator_raises_on_exit_if_queue_not_empty(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")
        self._assert_no_patches()

        self.assertRaises(qmock.CallQueueNotEmpty, foo)

    def test_multi_patch_function_decorator_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            # would raise CallQueueNotEmpty if not handling KeyError
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")
            raise KeyError("TEST")
        self._assert_no_patches()

        self.assertRaises(KeyError, foo)

    def test_multi_patch_function_decorator_raises_on_exit_if_errors_in_threads(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            self._force_unexpected_call_in_thread(qm)
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_multi_patch_function_decorator_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            # raises QMockErrorsInThreads on top of KeyError
            self._force_unexpected_call_in_thread(qm)
            raise KeyError("TEST")
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, KeyError)


    def test_stacked_function_decorator_succeeds(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

            self.assertEqual(datetime.date(1, 2, 3), "a")
            self.assertEqual(xml.etree.ElementTree.fromstring("<foo />"), "b")
            self.assertEqual(json.loads("[1,2,3]"), "c")
        self._assert_no_patches()
        foo()

    def test_stacked_function_decorator_cleans_up_on_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            raise IndexError("TEST")
        self._assert_no_patches()

        self.assertRaises(IndexError, foo)

    def test_stacked_function_decorator_cleans_up_on_bad_patch(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json="json.BAD")
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            self.fail("This test function should not run.")
        self._assert_no_patches()

        self.assertRaises(AttributeError, foo)

    def test_stacked_function_decorator_raises_on_exit_if_queue_not_empty(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")
        self._assert_no_patches()

        self.assertRaises(qmock.CallQueueNotEmpty, foo)

    def test_stacked_function_decorator_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            # would raise CallQueueNotEmpty if not handling IndexError
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")
            raise IndexError("TEST")
        self._assert_no_patches()

        self.assertRaises(IndexError, foo)

    def test_stacked_function_decorator_raises_on_exit_if_errors_in_threads(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            self._force_unexpected_call_in_thread(qm)
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_stacked_function_decorator_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(json=JSON_LOADS)
        @qmock.patch(et=XML_ETREE_ELEMENTTREE)
        def foo(qm):
            # raises QMockErrorsInThreads on top of IndexError
            self._force_unexpected_call_in_thread(qm)
            raise IndexError("TEST")
        self._assert_no_patches()

        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            foo()

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, IndexError)


    def test_class_decorator_only_patches_test_methods(self):
        @qmock.patch(dt=DATETIME_DATE)
        class Foo(object):
            fizz = "a"
            test_buzz = "b"
            def bar(foo_self):
                self._assert_no_patches()
            def test_baz(foo_self, qm):
                qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
                self.assertEqual(datetime.date(1, 2, 3), 7)

        self._assert_no_patches()
        f = Foo()
        self._assert_no_patches()
        self.assertEqual(f.fizz, "a")
        self._assert_no_patches()
        self.assertEqual(f.test_buzz, "b")
        self._assert_no_patches()
        f.bar()
        self._assert_no_patches()
        f.test_baz()


    def test_mixed_decorator_patches(self):
        @qmock.patch(dt=DATETIME_DATE, json=JSON_LOADS)
        class Foo(object):
            @qmock.patch(et=XML_ETREE_ELEMENTTREE)
            def test_mixed(foo_self, qm):
                qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
                qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
                qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

                self.assertEqual(datetime.date(1, 2, 3), "a")
                self.assertEqual(xml.etree.ElementTree.fromstring("<foo />"), "b")
                self.assertEqual(json.loads("[1,2,3]"), "c")

            def test_no_cross_mix_between_methods(foo_self, qm):
                self._assert_xml_etree_is_not_patched()

                qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
                qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

                self.assertEqual(datetime.date(1, 2, 3), "a")
                self.assertEqual(json.loads("[1,2,3]"), "c")

            @qmock.patch(et="xml.etree.BAD")
            def test_bad_patch(foo_self, qm):
                self.fail("This test function should not run.")

        self._assert_no_patches()
        f = Foo()
        self._assert_no_patches()
        f.test_mixed()
        self._assert_no_patches()
        f.test_no_cross_mix_between_methods()
        self._assert_no_patches()
        self.assertRaises(AttributeError, f.test_bad_patch)


    def test_empty_context_manager_succeeds(self):
        with qmock.patch() as qm:
            self._assert_no_patches()
            qm.call_queue.push(qmock.call.bar(), 5)
            self.assertEqual(qm.bar(), 5)

    # a little silly because nothing is being patched, but just in case.
    def test_empty_context_manager_cleans_up_on_func_exception(self):
        with self.assertRaises(RuntimeError):
            with qmock.patch() as qm:
                self._assert_no_patches()
                raise RuntimeError("TEST")

    def test_empty_context_manager_raises_on_exit_if_queue_not_empty(self):
        with self.assertRaises(qmock.CallQueueNotEmpty):
            with qmock.patch() as qm:
                self._assert_no_patches()
                qm.call_queue.push(qmock.call.bar(), 5)

    def test_empty_context_manager_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        with self.assertRaises(RuntimeError):
            with qmock.patch() as qm:
                self._assert_no_patches()
                # would raise CallQueueNotEmpty if not handling RuntimeError
                qm.call_queue.push(qmock.call.bar(), 5)
                raise RuntimeError("TEST")

    def test_empty_context_manager_raises_on_exit_if_errors_in_threads(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch() as qm:
                self._assert_no_patches()
                self._force_unexpected_call_in_thread(qm)

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_empty_context_manager_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch() as qm:
                self._assert_no_patches()
                # raises QMockErrorsInThreads on top of RuntimeError
                self._force_unexpected_call_in_thread(qm)
                raise RuntimeError("TEST")

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, RuntimeError)


    def test_single_patch_context_manager_succeeds(self):
        with qmock.patch(dt=DATETIME_DATE) as qm:
            qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
            self.assertEqual(datetime.date(1, 2, 3), 7)

    def test_single_patch_context_manager_cleans_up_on_func_exception(self):
        with self.assertRaises(ValueError):
            with qmock.patch(dt=DATETIME_DATE) as qm:
                raise ValueError("TEST")

    def test_single_patch_context_manager_cleans_up_on_bad_patch(self):
        with self.assertRaises(AttributeError):
            with qmock.patch(dt="datetime.BAD") as qm:
                self.fail("This context should not be entered.")

    def test_single_patch_context_manager_raises_on_exit_if_queue_not_empty(self):
        with self.assertRaises(qmock.CallQueueNotEmpty):
            with qmock.patch(dt=DATETIME_DATE) as qm:
                qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)

    def test_single_patch_context_manager_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        with self.assertRaises(ValueError):
            with qmock.patch(dt=DATETIME_DATE) as qm:
                # would raise CallQueueNotEmpty if not handling ValueError
                qm.call_queue.push(qmock.call.dt(1, 2, 3), 7)
                raise ValueError("TEST")

    def test_single_patch_context_manager_raises_on_exit_if_errors_in_threads(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch(dt=DATETIME_DATE) as qm:
                self._force_unexpected_call_in_thread(qm)

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_single_patch_context_manager_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch(dt=DATETIME_DATE) as qm:
                # raises QMockErrorsInThreads on top of ValueError
                self._force_unexpected_call_in_thread(qm)
                raise ValueError("TEST")

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, ValueError)


    def test_multi_patch_function_decorator_succeeds(self):
        with qmock.patch(
            dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
        ) as qm:
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
            qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

            self.assertEqual(datetime.date(1, 2, 3), "a")
            self.assertEqual(xml.etree.ElementTree.fromstring("<foo />"), "b")
            self.assertEqual(json.loads("[1,2,3]"), "c")

    def test_multi_patch_context_manager_cleans_up_on_func_exception(self):
        with self.assertRaises(KeyError):
            with qmock.patch(
                dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
            ) as qm:
                raise KeyError("TEST")

    def test_multi_patch_context_manager_cleans_up_on_bad_patch(self):
        with self.assertRaises(AttributeError):
            with qmock.patch(
                dt=DATETIME_DATE, json="json.BAD", et=XML_ETREE_ELEMENTTREE
            ) as qm:
                self.fail("This context should not be entered.")

    def test_multi_patch_context_manager_raises_on_exit_if_queue_not_empty(self):
        with self.assertRaises(qmock.CallQueueNotEmpty):
            with qmock.patch(
                dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
            ) as qm:
                qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
                qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
                qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")

    def test_multi_patch_context_manager_doesnt_raise_on_exit_if_queue_not_empty_and_func_exception(self):
        with self.assertRaises(KeyError):
            with qmock.patch(
                dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
            ) as qm:
                # would raise CallQueueNotEmpty if not handling KeyError
                qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
                qm.call_queue.push(qmock.call.et.fromstring("<foo />"), "b")
                qm.call_queue.push(qmock.call.json("[1,2,3]"), "c")
                raise KeyError("TEST")

    def test_multi_patch_context_manager_raises_on_exit_if_errors_in_threads(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch(
                dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
            ) as qm:
                self._force_unexpected_call_in_thread(qm)

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, None)

    def test_multi_patch_context_manager_still_raises_on_exit_if_errors_in_threads_and_func_exception(self):
        with self.assertRaises(qmock.QMockErrorsInThreads) as assertion:
            with qmock.patch(
                dt=DATETIME_DATE, json=JSON_LOADS, et=XML_ETREE_ELEMENTTREE
            ) as qm:
                # raises QMockErrorsInThreads on top of KeyError
                self._force_unexpected_call_in_thread(qm)
                raise KeyError("TEST")

        self._assert_thread_qmock_errors(assertion.exception)
        self._assert_patched_func_error(assertion.exception, KeyError)

    #
    # degenerate cases
    #

    def test_duplicate_patch_succeeds(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(dt=DATETIME_DATE)
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            self.assertEqual(datetime.date(1, 2, 3), "a")
        self._assert_no_patches()
        foo()

    # this also indirectly tests that stacked patches are applied strictly
    # bottom-up.
    def test_same_patch_on_different_attr_is_weird(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(date=DATETIME_DATE)
        def foo(qm):
            # this is the wrong call to expect because the last patch for
            # datetime.date was assigned to the `dt` attr
            qm.call_queue.push(qmock.call.date(1, 2, 3), "a")
            with self.assertRaises(qmock.UnexpectedCall):
                datetime.date(1, 2, 3)

            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            self.assertEqual(datetime.date(1, 2, 3), "a")
        self._assert_no_patches()
        foo()

    def test_different_patch_on_same_attr_is_also_weird(self):
        @qmock.patch(dt=DATETIME_DATE)
        @qmock.patch(dt="datetime.datetime")
        def foo(qm):
            qm.call_queue.push(qmock.call.dt(1, 2, 3), "a")
            qm.call_queue.push(qmock.call.dt(4, 5, 6), "b")
            qm.call_queue.push(qmock.call.dt(7, 8, 9), "c")

            self.assertEqual(datetime.date(1, 2, 3), "a")
            self.assertEqual(datetime.datetime(4, 5, 6), "b")
            self.assertEqual(datetime.date(7, 8, 9), "c")
        self._assert_no_patches()
        foo()

class QMockTests(unittest.TestCase):
    def test_root_assigned_attributes(self):
        qm = qmock.QMock()
        qm.foo = 5

        self.assertIs(qm.foo, 5)  # retained across accesses
        self.assertIsInstance(qm.foo, int)
        self.assertRaises(TypeError, qm.foo) # not callable

    def test_root_generated_attributes(self):
        qm = qmock.QMock()

        self.assertIsNot(qm.foo, qm.baz)
        self.assertIs(qm.foo, qm.foo)  # retained across accesses
        self.assertIsInstance(qm.foo, qmock._qmock._CallProxy)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo() # empty CallQueue

        qm.call_queue.push(qmock.call.foo(), 5)

        self.assertIs(qm.foo(), 5)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo() # empty CallQueue

    def test_nested_assigned_attributes(self):
        qm = qmock.QMock()
        qm.foo.bar = 5

        self.assertIs(qm.foo.bar, 5)  # retained across accesses
        self.assertIsInstance(qm.foo.bar, int)
        self.assertRaises(TypeError, qm.foo.bar) # not callable

        self.assertIsNot(qm.foo, qm.baz)
        self.assertIs(qm.foo, qm.foo) # retained across accesses
        self.assertIsInstance(qm.foo, qmock._qmock._CallProxy)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo() # empty CallQueue

    def test_nested_generated_attributes(self):
        qm = qmock.QMock()

        self.assertIsNot(qm.foo.bar, qm.foo.baz)
        self.assertIsNot(qm.foo.bar, qm.baz.bar)
        self.assertIs(qm.foo.bar, qm.foo.bar) # retained across accesses
        self.assertIsInstance(qm.foo.bar, qmock._qmock._CallProxy)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo.bar() # empty CallQueue

        self.assertIsNot(qm.foo, qm.baz)
        self.assertIs(qm.foo, qm.foo)  # retained across accesses
        self.assertIsInstance(qm.foo, qmock._qmock._CallProxy)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo() # empty CallQueue

        qm.call_queue.push(qmock.call.foo.bar(), 5)

        self.assertIs(qm.foo.bar(), 5)
        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo.bar() # empty CallQueue

    def test_assigned_attributes_are_attached(self):
        qm = qmock.QMock()

        m = mock.Mock()
        qm.foo = m

        with self.assertRaises(qmock.UnexpectedCall):
            m()

    def test_root_magic_methods(self):
        qm = qmock.QMock()

        with self.assertRaises(qmock.UnexpectedCall):
            str(qm) # empty CallQueue

        qm.call_queue.push(qmock.call.__getattr__("__str__")(qm), "test")

        self.assertEqual(str(qm), "test")

        with self.assertRaises(qmock.UnexpectedCall):
            str(qm) # empty CallQueue

    def test_nested_magic_methods(self):
        qm = qmock.QMock()

        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo < 5 # empty CallQueue

        qm.call_queue.push(qmock.call.foo.__getattr__("__lt__")(qm.foo, 5), "test")

        self.assertEqual((qm.foo < 5), "test")

        with self.assertRaises(qmock.UnexpectedCall):
            qm.foo < 5 # empty CallQueue

    def test_magic_methods_are_always_the_same_object(self):
        qm = qmock.QMock()

        method = qm.__len__

        self.assertIs(method, qm.__len__)
        self.assertIs(method, qm.__len__)
        self.assertIs(method, qm.__len__)

    def test_magic_methods_are_unique(self):
        qm = qmock.QMock()

        self.assertIsNot(qm.__len__, qm.foo.__len__)
        self.assertIsNot(qm.__len__, qm.bar.__len__)
        self.assertIsNot(qm.foo.__len__, qm.bar.__len__)

        qm.call_queue.assert_empty()

        qm.call_queue.push(qmock.call.__getattr__("__len__")(qm), 1)
        qm.call_queue.push(qmock.call.foo.__getattr__("__len__")(qm.foo), 2)
        qm.call_queue.push(qmock.call.bar.__getattr__("__len__")(qm.bar), 3)
        qm.call_queue.push(qmock.call.bar.__getattr__("__len__")(qm.bar), 4)

        with self.assertRaises(qmock.UnexpectedCall):
            len(qm.foo) # wrong call; expected len(qm)

        self.assertEqual(len(qm.foo), 2)

        with self.assertRaises(qmock.UnexpectedCall):
            len(qm.foo) # wrong call; expected len(qm.bar)

        self.assertEqual(len(qm.bar), 4)

        qm.call_queue.assert_empty()

    def test_can_be_a_context_manager(self):
        qm = qmock.QMock()

        qm.call_queue.assert_empty()

        with self.assertRaises(qmock.UnexpectedCall):
            with qm as foo: # empty CallQueue
                pass

        qm.call_queue.assert_empty()

        qm.call_queue.push(qmock.call.__getattr__("__enter__")(qm), qm.foo)
        qm.call_queue.push(qmock.call.foo(), 7357)
        qm.call_queue.push(qmock.call.__getattr__("__exit__")(qm, None, None, None), None)

        with qm as foo:
            self.assertEqual(foo(), 7357)

        qm.call_queue.assert_empty()

    def test_mock_calls_returns_proxy(self):
        qm = qmock.QMock()

        self.assertIsInstance(qm.mock_calls, qmock._qmock._MockCallsProxy)

    def test_eq(self):
        alpha = qmock.QMock()
        bravo = qmock.QMock()

        self.assertTrue(alpha == alpha)
        self.assertTrue(bravo == bravo)
        self.assertFalse(alpha == bravo)
        self.assertFalse(bravo == alpha)

    def test_is_callable(self):
        qm = qmock.QMock()

        with self.assertRaises(qmock.UnexpectedCall):
            qm() # empty CallQueue

        qm.call_queue.push(qmock.call(), 5)

        self.assertIs(qm(), 5)

    def test_mock_return_assigned_attributes(self):
        qm = qmock.QMock()
        qm.foo = 5
        self.assertIs(
            qm.mock_return(qmock.call.foo),
            5
        )

        qm = qmock.QMock()
        qm.foo.return_value = 6
        self.assertIs(
            qm.mock_return(qmock.call.foo()),
            6
        )

        qm = qmock.QMock()
        qm.return_value = 7
        self.assertIs(
            qm.mock_return(qmock.call()),
            7
        )

        qm = qmock.QMock()
        qm.return_value.foo = 8
        self.assertIs(
            qm.mock_return(qmock.call().foo),
            8
        )

        qm = qmock.QMock()
        qm.return_value.foo.return_value.bar.return_value.baz.barf.return_value = 9
        self.assertIs(
            qm.mock_return(qmock.call(x=1).foo(y=2).bar(5).baz.barf(z={6: 7}, w=8)),
            9
        )

    def test_mock_return_generated_attributes(self):
        qm = qmock.QMock()

        self.assertIs(
            qm.mock_return(qmock.call.foo),
            qm.foo
        )
        self.assertIs(
            qm.mock_return(qmock.call.foo()),
            qm.foo.return_value
        )
        self.assertIs(
            qm.mock_return(qmock.call()),
            qm.return_value
        )
        self.assertIs(
            qm.mock_return(qmock.call().foo),
            qm.return_value.foo
        )
        self.assertIs(
            qm.mock_return(qmock.call(x=1).foo(y=2).bar(5).baz.barf(z={6: 7}, w=8)),
            qm.return_value.foo.return_value.bar.return_value.baz.barf.return_value
        )

    def test_mock_return_null_call(self):
        qm = qmock.QMock()

        self.assertRaises(
            AttributeError,
            qm.mock_return,
            qmock.call
        )

class CallQueueTests(unittest.TestCase):
    def test_push_attribute_call(self):
        qm = qmock.QMock()
        cq = qm.call_queue

        self.assertRaises(
            qmock.BadCall,
            cq.push,
            qmock.call.foo,
            "bar"
        )

        self.assertEqual(len(cq.pop_errors), 0)

    def test_push_function_call(self):
        qm = qmock.QMock()
        cq = qm.call_queue

        self.assertEqual(len(cq._queue), 0)

        cq.push(qmock.call.foo(), "bar")

        self.assertEqual(
            tuple(
                (expected_call, self._copy_mock_side_effect(mock_result))
                for expected_call, mock_result in cq._queue
            ),
            (
                (qmock.call.foo(), ("bar",)),
            )
        )

        self.assertEqual(len(cq._queue), 1)
        self.assertEqual(qm.foo(), "bar")

        cq.assert_empty()
        self.assertEqual(len(cq.pop_errors), 0)

    def test_push_all_attribute_call(self):
        qm = qmock.QMock()
        cq = qm.call_queue

        self.assertRaises(
            qmock.BadCall,
            cq.push_all,
            qmock.call(x=1).foo(y=2).bar(5).baz.barf,
            10
        )

        self.assertEqual(len(cq.pop_errors), 0)

    def test_push_all_function_call(self):
        qm = qmock.QMock()
        cq = qm.call_queue
        cq.push_all(qmock.call(x=1).foo(y=2).bar(5).baz.barf(z={6: 7}, w=8), 10)

        self.assertEqual(
            tuple(
                (expected_call, self._copy_mock_side_effect(mock_result))
                for expected_call, mock_result in cq._queue
            ),
            (
                (
                    qmock.call(x=1),
                    (qm.return_value,)
                ),
                (
                    qmock.call(x=1).foo(y=2),
                    (qm.return_value.foo.return_value,)
                ),
                (
                    qmock.call(x=1).foo(y=2).bar(5),
                    (qm.return_value.foo.return_value.bar.return_value,)
                ),
                (
                    qmock.call(x=1).foo(y=2).bar(5).baz.barf(z={6: 7}, w=8),
                    (10,)
                )
            )
        )

        self.assertEqual(len(cq._queue), 4)
        self.assertEqual(qm(x=1).foo(y=2).bar(5).baz.barf(z={6: 7}, w=8), 10)

        cq.assert_empty()
        self.assertEqual(len(cq.pop_errors), 0)

    def test_pop_value_result(self):
        qm = qmock.QMock()
        cq = qm.call_queue
        cq.push(qmock.call.foo(), 7357)

        self.assertEqual(cq._pop(qmock.call.foo()), 7357)

        cq.assert_empty()
        self.assertEqual(len(cq.pop_errors), 0)

    def test_pop_exception_result(self):
        qm = qmock.QMock()
        cq = qm.call_queue
        cq.push(qmock.call.foo(), ValueError("test"))

        with self.assertRaises(ValueError) as assertion:
            cq._pop(qmock.call.foo())
        self.assertEqual(str(assertion.exception), "test")

        cq.assert_empty()
        self.assertEqual(len(cq.pop_errors), 0)

    def test_pop_raises_when_empty(self):
        qm = qmock.QMock()
        cq = qm.call_queue

        self.assertRaises(qmock.UnexpectedCall, cq._pop, qmock.call.foo())

        self.assertEqual(len(cq.pop_errors), 1)
        record = cq.pop_errors[0]
        self.assertEqual(record.thread_id, get_thread_id())
        self.assertIsInstance(record.error, qmock.UnexpectedCall)
        self.assertEqual(
            str(record.error),
            "Queue is empty. call: call.foo()"
        )

    def test_pop_raises_when_call_doesnt_match_expectation(self):
        qm = qmock.QMock()
        cq = qm.call_queue
        cq.push(qmock.call.foo(), 7357)

        self.assertRaises(qmock.UnexpectedCall, cq._pop, qmock.call.not_foo())

        self.assertEqual(len(cq.pop_errors), 1)
        record = cq.pop_errors[0]
        self.assertEqual(record.thread_id, get_thread_id())
        self.assertIsInstance(record.error, qmock.UnexpectedCall)
        self.assertEqual(
            str(record.error),
            "Call does not match expectation. actual: call.not_foo(); expected: call.foo()"
        )

    def test_assert_empty(self):
        qm = qmock.QMock()
        cq = qm.call_queue

        cq.assert_empty()

        cq.push(qmock.call.foo(), "bar")

        self.assertRaises(qmock.CallQueueNotEmpty, cq.assert_empty)

        cq._pop(qmock.call.foo())

        cq.assert_empty()
        self.assertEqual(len(cq.pop_errors), 0)

    def _copy_mock_side_effect(self, m):
        """
            mock.Mock.side_effect is stored as a <tupleiterator>,
            so iterating consumes it. so we'll consume it, store a copy,
            re-populate it, and return the copy
        """
        side_effect = tuple(m.side_effect)
        m.side_effect = side_effect
        return side_effect
