# `qmock-py`
> A framework for Queue-based call validation on mock objects.

## Rationale
### Background
To verify calls on a mock object, the standard `mock` library builds a history
of received calls which the test writer inspects after the target code is run.
The workflow is:
1. Set up return values and side-effects on `Mock` objects.
2. Run target code.
3. Inspect `Mock` objects to assert the correct functions were called with the
   correct args.

`qmock` takes a different approach. `qmock` consumes a pre-populated queue of
expected calls *while* the target code is running. The `qmock` workflow:
1. Push pairs of `(expected call, result)` onto a call queue.
2. Run target code.
3. Assert the call queue is empty.

### Benefits
#### Readability
The main goal of `qmock` is to make mock-dependent tests easier to read.

With `unittest.mock`, results and expected calls are declared separately and
backwards. Results are set up at the start of a test and calls are verified at
the end:
```python
m = unittest.mock.Mock()

# 1. set up results
m.foo.return_value = "a value"
m.bar.side_effect = (Exception("an exception"), "not an exception")
...

# 2. run target code
...

# 3. inspect mock, verify calls were correct
self.assertEquals(
    m.mock_calls,
    [
        unittest.mock.call.bar(),
        unittest.mock.call.foo(),
        unittest.mock.call.bar(),
        ...
    ]
)
```

This code flow is awkward. Effects (results) are stated long before their causes
(calls). Calls are globally ordered, but results are ordered separately for each
method. Understanding the test requires collating calls and results, which can
be difficult with multiple dynamic (ie: iterable) side-effects. All of this
obfuscates the expected behavior of the target code.

With `qmock`, everything is declared in one place and in-order. Expected calls
are explicitly paired with their results, so it's easier to follow the expected
behavior of the target code:
```python
qm = qmock.QMock()

# 1. set up expected calls and results
qm.call_queue.push(qmock.call.bar(), Exception("an exception"))
qm.call_queue.push(qmock.call.foo(), "a value")
qm.call_queue.push(qmock.call.bar(), "not an exception")
...

# 2. run target code
...

# 3. verify all calls were consumed
qm.call_queue.assert_empty()
```

#### Testability
A secondary goal of `qmock` is to encourage writing *testable* code.

`qmock` is more strict than `mock` because the expected calls must be completely
deterministic. There is no option for "fuzzy" comparison of call arguments or
non-deterministic call ordering. The idea is that non-deterministic code is
generally hard (or impossible) to test and should be avoided whenever possible.

Of course there are situations where non-determinism is unavoidable (eg, multi-
threading) and the strictness of `qmock` will not work out-of-the-box. These
cases should be rare enough for `qmock` to remain useful, and such cases may
still be adaptable to `qmock` (albeit with some extra work).

#### Preventing Forgetfulness
One bonus of `qmock`'s approach is that testers cannot forget to make the proper
assertions about mocked calls. If the queue is not set up, then the test will
just fail.

You can still forget to `assert_empty()` at the end of the test, but
`qmock.patch()` can fix that too.

## Usage
### Classes
#### `qmock.QMock`
The `QMock` class is the primary utility of `qmock`. It retains the core
features of `unittest.mock.Mock`:
- callable;
- child mocks automatically attached on attribute access.

The big difference is how function calls are handled.

With `qmock`, setup for calls is performed on the root `QMock` object, not on
its children. The call queue is populated by calling `.call_queue.push()` on the
root `QMock`, instead of setting `.side_effect` or `.return_value` on each child
`Mock`.

Then, after you run your target code, instead of inspecting a list of calls, you
just invoke `.call_queue.assert_empty()` to verify all calls were consumed from
the queue and nothing was missed.

For more usage information, see `help(qmock.QMock)`.

#### `qmock.patch`
Like `unittest.mock.patch`, `qmock.patch` temporarily mocks out modules and can
be applied as a class decorator, a function decorator, or a context manager. But
`qmock.patch` provides a few extra features and the usage is a little different.

Basic decorator usage looks like:
```python
@qmock.patch(baz="foo.bar.baz")
def test_xyz(self, qm):
    ...
```

This is different from `unittest.mock.patch()` is several ways:
- `qmock.patch()` requires module paths to be provided via kwargs.
- `qmock.patch()` creates a root `QMock` and attaches mock modules to it by
  using kwarg names as attr names.
- Stacked `@qmock.patch()` decorators will share one `QMock`. All mock modules
  are attached to the same `QMock` and that `QMock` is the only argument
  injected into the decorated function(s). But, stacking usually isn't necessary
  because...
- One `qmock.patch()` can mock multiple modules (still using one root `QMock`).
- On exit of the mocked scope:
    + `QMock.call_queue.assert_empty()` is automatically called (unless
      there is an active exception being handled).
    + `qmock` exceptions thrown in other threads will be reported by raising a
      new exception in the current thread.

Constructing `QMock`s and performing assertions on scope exit helps reduce the
boiler-plate needed to use `qmock`, making `@qmock.patch()` useful even when no
modules need to be patched.

For more usage information, see `help(qmock.patch)`.

#### `qmock.call`
An convenient alias for `unittest.mock.call`.

### Exceptions
#### `qmock.UnexpectedCall`
- Raised when:
    + `QMock` receives a `call` but the queue is empty;
    + `QMock` receives a `call` that does not match the next `call` in the queue.
- Subclass of `BaseException`.

#### `qmock.BadCall`
- Raised when:
    + `QMock.call_queue.push()` (or `push_all()`) is given a `call` representing
      an attribute fetch instead of a function call. For example, `call.foo()`
      represents a valid call, but `call.foo` represents an attribute fetch,
      which cannot be verified by `qmock`.
- Subclass of `ValueError`.

#### `qmock.CallQueueNotEmpty`
- Raised when:
    + `QMock.call_queue.assert_empty()` is called but the queue is not empty.
- Subclass of `AssertionError`.

#### `qmock.QMockErrorsInThreads`
- Raised when:
    + `qmock.patch()` detects a `qmock` exception in another thread.
- Subclass of `AssertionError`.

## Development
### Python Version Support
`qmock-py` intends to support all active Python versions. This is currently:
- Python 2.7
- PYthon 3.5+

#### Source
All versions-specific imports and shims are collected in
`src/qmock/_python_compat.py`.

#### Tests
For testing, we would normally lean on `tox` to set up each Python environment.
This works for testing multiple *minor* versions of Python (eg, `3.6` and `3.7`)
because we can have multiple minors installed. Unfortunately, there were
breaking changes to `unittest.mock` across *patch* versions (eg: from Python
`3.6.7` to `3.6.8`) and we can't have multiple patches installed at the same
time. So we have to manually iterate through environments and run `tox` in each.
This is done by `test_all_envs.sh`.

If you run `tox` directly, it will use the current `python` command.
