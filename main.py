"""Convenience dev entry: python main.py"""

from frontend import create_app

if __name__ == "__main__":
    create_app().run(debug=True)
