import os

from flask import Flask, render_template


def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # a simple page that says hello
    @app.route('/hello')
    def hello():
        return 'Hello, World!'

    # home page — renders an HTML template with data passed in
    @app.route('/')
    def index():
        return render_template(
            'index.html',
            heading='flaskr is running',
            models=['GPT 4.1 Mini', 'GPT 4.1', 'Llama 3.3'],
        )

    # v0.0.1 dashboard page
    @app.route('/dashboard')
    def dashboard():
        rows = [
            {'model': 'GPT-4o Mini', 'vendor': 'OpenAI', 'hosting': 'Azure',
             'agreement': 'Covered', 'agreement_class': 'covered',
             'scored': True, 'accuracy': 4.4, 'completeness': 4.2, 'policy': 4.6, 'tone': 2.7,
             'overall': 4.3, 'latency': '1.5s', 'cost': '$0.008', 'last_eval': '06-02'},
            {'model': 'GPT-4o', 'vendor': 'OpenAI', 'hosting': 'Azure',
             'agreement': 'Covered', 'agreement_class': 'covered',
             'scored': True, 'accuracy': 4.6, 'completeness': 4.4, 'policy': 4.8, 'tone': 2.8,
             'overall': 4.5, 'latency': '1.8s', 'cost': '$0.012', 'last_eval': '06-02'},
            {'model': 'Claude Sonnet 4.6', 'vendor': 'Anthropic', 'hosting': 'Azure',
             'agreement': 'Covered', 'agreement_class': 'covered',
             'scored': True, 'accuracy': 4.7, 'completeness': 4.5, 'policy': 4.9, 'tone': 3.0,
             'overall': 4.6, 'latency': '2.1s', 'cost': '$0.014', 'last_eval': '06-02'},
            {'model': 'Llama 3.1 70B', 'vendor': 'Meta', 'hosting': 'Azure',
             'agreement': 'Covered', 'agreement_class': 'covered',
             'scored': True, 'accuracy': 4.1, 'completeness': 3.9, 'policy': 4.3, 'tone': 2.6,
             'overall': 4.0, 'latency': '3.4s', 'cost': '$0.003', 'last_eval': '06-02'},
            {'model': 'Llama 3.1 8B', 'vendor': 'Meta', 'hosting': 'Azure',
             'agreement': 'Covered', 'agreement_class': 'covered',
             'scored': True, 'accuracy': 3.5, 'completeness': 3.2, 'policy': 3.8, 'tone': 2.3,
             'overall': 3.5, 'latency': '1.4s', 'cost': '$0.001', 'last_eval': '06-02'},
            {'model': 'Mistral 7B', 'vendor': 'Mistral', 'hosting': 'On-prem',
             'agreement': 'N/A', 'agreement_class': '',
             'scored': True, 'accuracy': 3.3, 'completeness': 3.0, 'policy': 3.6, 'tone': 2.4,
             'overall': 3.3, 'latency': '0.9s', 'cost': '$0.000', 'last_eval': '06-02'},
            {'model': 'Qwen 2.5 7B', 'vendor': 'Alibaba', 'hosting': 'HF',
             'agreement': 'Uncovered', 'agreement_class': 'uncovered',
             'scored': True, 'accuracy': 3.7, 'completeness': 3.4, 'policy': 3.5, 'tone': 2.5,
             'overall': 3.5, 'latency': '1.6s', 'cost': '—', 'last_eval': '06-02'},
            {'model': 'Gemini 1.5', 'vendor': 'Google', 'hosting': 'Google',
             'agreement': 'No agreement', 'agreement_class': 'none',
             'scored': False},
            {'model': 'Gemini 1.5 Pro', 'vendor': 'Google', 'hosting': 'Google',
             'agreement': 'No agreement', 'agreement_class': 'none',
             'scored': False},
        ]
        return render_template(
            'dashboard.html',
            version='v0.0.1',
            suite='IT support suite',
            question_count=12,
            rows=rows,
        )
    
    return app
