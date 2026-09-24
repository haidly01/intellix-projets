import os
import sys

_vendor_path = os.path.join(os.path.dirname(__file__), "vendor")
if os.path.isdir(_vendor_path) and _vendor_path not in sys.path:
    sys.path.insert(0, _vendor_path)

from . import models
from . import controllers
