"""Run dev server: uv run python -m frontend.main"""

from frontend import create_app

if __name__ == "__main__":
    create_app().run(debug=True, host="0.0.0.0")
