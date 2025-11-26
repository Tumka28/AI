import logging
from flask import Flask

app = Flask(__name__)

# Лог файлыг тохируулах
logging.basicConfig(filename='flask.log', level=logging.DEBUG)

@app.route('/')
def hello_world():
    app.logger.info('Hello World хандалт хийсэн')
    return 'Hello, World!'

if __name__ == "__main__":
    app.run(debug=True)

