from flask import render_template, render_template_string

from frontend.catalog import GATEWAY_MODELS
from frontend.mockup_data import DASHBOARD_ROWS

_CATALOG = """
<h1>Gateway catalog</h1>
<p>From <code>frontend/catalog.py</code> — see <code>docs/gateway-models.md</code>.</p>
<table border="1" cellpadding="6">
  <tr><th>LiteLLM model</th><th>Alias</th><th>Notes</th></tr>
  {% for m in models %}
  <tr>
    <td>{{ m.id }}</td>
    <td>{{ m.alias or "—" }}</td>
    <td>{{ m.notes or "—" }}</td>
  </tr>
  {% endfor %}
</table>
<p><a href="{{ url_for('dashboard') }}">Efficacy mockup table</a></p>
"""


def register_routes(app):
    @app.route("/hello")
    def hello():
        return "Hello, World!"

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            heading="Nutrition label (frontend)",
            models=[m["id"] for m in GATEWAY_MODELS],
        )

    @app.route("/dashboard")
    def dashboard():
        return render_template(
            "dashboard.html",
            version="v0.0.1",
            suite="IT support suite",
            question_count=12,
            rows=DASHBOARD_ROWS,
        )

    @app.route("/models")
    def models_catalog():
        return render_template_string(_CATALOG, models=GATEWAY_MODELS)
