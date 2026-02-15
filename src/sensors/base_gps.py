from typing import Optional, Callable, List, TypeVar
from .base import BaseSensor

T = TypeVar('T')

class BaseGPSDevice(BaseSensor[T]):
    """
    Intermediate base class for GPS devices.
    Encapsulates GPS-specific shared logic and interface.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add GPS-specific shared initialization here
