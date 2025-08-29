# Imports
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import cv2
import base64
import threading
import time

# Initialise Flask app and Flask-Socket server
app = Flask(__name__, template_folder="templates", static_folder="static")
sio = SocketIO(app)

# ---------------- Camera (laptop webcam) ----------------
def capture_frames():
    ''' Function that captures video frames and emits to connected clients via a Socket.IO event 'video_frame'
    '''
    cap = cv2.VideoCapture(0)  # 0 for default laptop camera

    while True:
        success, frame = cap.read()
        if not success:
            continue

        # Encode frames as jpgs
        _, buffer = cv2.imencode('.jpg', frame) 

        # Emit frames under 'video_frame' event
        sio.emit('video_frame', buffer.tobytes())
        time.sleep(0.05)  # ~20 FPS - NOTE: can change this to increase FPS
    cap.release()

@sio.on('model_output')
def handle_model_output(data):
    ''' Receives model output from client running model inference. Emits the annotated images under a new 
    event name. This is necessary since the frontend can only see server events, not client events.
    '''
    # Emit annotated frame to connected clients 
    sio.emit('annotated_frame', data)


@sio.on('connect')
def handle_connect():
    ''' Socket.IO event handler for when a client connects to the Flask Server
    '''
    print('Client connected')

    # Start streaming thread only once, even if multiple clients connect
    if not hasattr(sio, 'camera_thread'):
        sio.camera_thread = threading.Thread(target=capture_frames, daemon=True)
        sio.camera_thread.start()


# ---------------- Dummy motor state ----------------
# Global dictionary for storing motor state
motor_state = {
    "left": {"dir": 0, "duty": 0.0},
    "right": {"dir": 0, "duty": 0.0}
}

@app.route("/")
def index():
    return render_template("index.html")

# Upon velocity command, frontend sends POST request with JSON data -> server updates motor_state dict
@app.post("/drive")
def drive():
    data = request.get_json(force=True)
    left = int(data.get("left", 0))
    right = int(data.get("right", 0))
    motor_state["left"] = {"dir": left, "duty": abs(left)}
    motor_state["right"] = {"dir": right, "duty": abs(right)}
    return jsonify(ok=True, left=motor_state["left"], right=motor_state["right"])

# Upon stop command, frontend sends POST request with JSON data -> server sets motor_state values to 0
@app.post("/stop")
def stop():
    motor_state["left"] = {"dir": 0, "duty": 0.0}
    motor_state["right"] = {"dir": 0, "duty": 0.0}
    return jsonify(ok=True, left=motor_state["left"], right=motor_state["right"])

# Frontend periodically sends GET request to server to retrieve motor_state values for display
@app.get("/status")
def status():
    return jsonify(ok=True, left=motor_state["left"], right=motor_state["right"])

if __name__ == "__main__":
    sio.run(app, host="0.0.0.0", port=5000, debug=True)