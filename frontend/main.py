"""Run dev server: uv run python3 -m frontend.main (or python3 main.py --host)."""

import os

from frontend import create_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    create_app().run(debug=True, host="0.0.0.0", port=port)
