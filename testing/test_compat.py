import sys
from functools import partial
from functools import wraps

import pytest
from _pytest.compat import _PytestWrapper
from _pytest.compat import cached_property
from _pytest.compat import get_real_func
from _pytest.compat import is_generator
from _pytest.compat import safe_getattr
from _pytest.compat import safe_isclass
from _pytest.outcomes import OutcomeException


def test_is_generator():
    def zap():
        yield  # pragma: no cover

    def foo():
        pass  # pragma: no cover

    assert is_generator(zap)
    assert not is_generator(foo)


def test_real_func_loop_limit():
    class Evil:
        def __init__(self):
            self.left = 1000

        def __repr__(self):
            return "<Evil left={left}>".format(left=self.left)

        def __getattr__(self, attr):
            if not self.left:
                raise RuntimeError("it's over")  # pragma: no cover
            self.left -= 1
            return self

    evil = Evil()

    with pytest.raises(
        ValueError,
        match=(
            "could not find real function of <Evil left=800>\n"
            "stopped at <Evil left=800>"
        ),
    ):
        get_real_func(evil)


def test_get_real_func():
    """Check that get_real_func correctly unwraps decorators until reaching the real function"""

    def decorator(f):
        @wraps(f)
        def inner():
            pass  # pragma: no cover

        return inner

    def func():
        pass  # pragma: no cover

    wrapped_func = decorator(decorator(func))
    assert get_real_func(wrapped_func) is func

    wrapped_func2 = decorator(decorator(wrapped_func))
    assert get_real_func(wrapped_func2) is func

    # special case for __pytest_wrapped__ attribute: used to obtain the function up until the point
    # a function was wrapped by pytest itself
    wrapped_func2.__pytest_wrapped__ = _PytestWrapper(wrapped_func)
    assert get_real_func(wrapped_func2) is wrapped_func


def test_get_real_func_partial():
    """Test get_real_func handles partial instances correctly"""

    def foo(x):
        return x

    assert get_real_func(foo) is foo
    assert get_real_func(partial(foo)) is foo


def test_is_generator_asyncio(testdir):
    testdir.makepyfile(
        """
        from _pytest.compat import is_generator
        import asyncio
        @asyncio.coroutine
        def baz():
            yield from [1,2,3]

        def test_is_generator_asyncio():
            assert not is_generator(baz)
    """
    )
    # avoid importing asyncio into pytest's own process,
    # which in turn imports logging (#8)
    result = testdir.runpytest_subprocess()
    result.stdout.fnmatch_lines(["*1 passed*"])


def test_is_generator_async_syntax(testdir):
    testdir.makepyfile(
        """
        from _pytest.compat import is_generator
        def test_is_generator_py35():
            async def foo():
                await foo()

            async def bar():
                pass

            assert not is_generator(foo)
            assert not is_generator(bar)
    """
    )
    result = testdir.runpytest()
    result.stdout.fnmatch_lines(["*1 passed*"])


@pytest.mark.skipif(
    sys.version_info < (3, 6), reason="async gen syntax available in Python 3.6+"
)
def test_is_generator_async_gen_syntax(testdir):
    testdir.makepyfile(
        """
        from _pytest.compat import is_generator
        def test_is_generator_py36():
            async def foo():
                yield
                await foo()

            async def bar():
                yield

            assert not is_generator(foo)
            assert not is_generator(bar)
    """
    )
    result = testdir.runpytest()
    result.stdout.fnmatch_lines(["*1 passed*"])


class ErrorsHelper:
    @property
    def raise_baseexception(self):
        raise BaseException("base exception should be raised")

    @property
    def raise_exception(self):
        raise Exception("exception should be catched")

    @property
    def raise_fail_outcome(self):
        pytest.fail("fail should be catched")


def test_helper_failures():
    helper = ErrorsHelper()
    with pytest.raises(Exception):
        helper.raise_exception
    with pytest.raises(OutcomeException):
        helper.raise_fail_outcome


def test_safe_getattr():
    helper = ErrorsHelper()
    assert safe_getattr(helper, "raise_exception", "default") == "default"
    assert safe_getattr(helper, "raise_fail_outcome", "default") == "default"
    with pytest.raises(BaseException):
        assert safe_getattr(helper, "raise_baseexception", "default")


def test_safe_isclass():
    assert safe_isclass(type) is True

    class CrappyClass(Exception):
        # Type ignored because it's bypassed intentionally.
        @property  # type: ignore
        def __class__(self):
            assert False, "Should be ignored"

    assert safe_isclass(CrappyClass()) is False


def test_cached_property() -> None:
    ncalls = 0

    class Class:
        @cached_property
        def prop(self) -> int:
            nonlocal ncalls
            ncalls += 1
            return ncalls

    c1 = Class()
    assert ncalls == 0
    assert c1.prop == 1
    assert c1.prop == 1
    c2 = Class()
    assert ncalls == 1
    assert c2.prop == 2
    assert c1.prop == 1
