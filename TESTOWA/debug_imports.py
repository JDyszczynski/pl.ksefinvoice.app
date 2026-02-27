import sys
import os
print("CWD:", os.getcwd())
print("sys.path:", sys.path)
try:
    import logic
    print("logic package file:", logic.__file__)
except ImportError:
    print("Could not import logic package directly")

try:
    import logic.jpk_service
    print("logic.jpk_service file:", logic.jpk_service.__file__)
except ImportError:
    print("Could not import logic.jpk_service")
