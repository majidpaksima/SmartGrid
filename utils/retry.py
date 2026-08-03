import time
import functools
from typing import Callable, Type, Tuple


def retry(
    max_attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise
            return None
        return wrapper
    return decorator


def retry_with_backoff(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    backoff: float = 2.0,
) -> tuple:
    if kwargs is None:
        kwargs = {}
    last_exception = None
    current_delay = base_delay
    for attempt in range(1, max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            return (True, result, None)
        except Exception as e:
            last_exception = e
            if attempt < max_attempts:
                time.sleep(current_delay)
                current_delay *= backoff
            else:
                return (False, None, str(last_exception))
    return (False, None, str(last_exception))
