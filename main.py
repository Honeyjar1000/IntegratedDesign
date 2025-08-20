# scp -r D:\uni\ECE4179\project\IntegratedDesign\* tom@raspberrypi:~/Documents/
# scp -r /Users/ahila/Desktop/IntegratedDesign/* ahila@raspberrypi.local:/home/tom/Documents/ - AHILA

"""
Flask automatically looks for:

a templates/ folder → for HTML files used by render_template()
a static/ folder → for CSS, JS, and images
"""

from flask import Flask, render_template
import cv2
from matplotlib import pyplot as plt

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True)


# for any new route or URL, you just add @app.route(“/url-path”) followed by a Python function



    