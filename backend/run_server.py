import os
import sys

pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages")
if os.path.isdir(pkg_dir) and pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
