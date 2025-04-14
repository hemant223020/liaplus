from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/health')
def health():
    return {"status": "healthy"}

if __name__ == '_main_':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))