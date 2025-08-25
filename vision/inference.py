import socketio
import base64
import cv2
import numpy as np
from ultralytics import YOLO
import threading
import socket

# Load model
# model_path = "vision/models/yolov8n.pt"
# model = torch.load(model_path)
model = YOLO("yolov8n.pt") # NOTE: will later change this to load from models/ folder once we have trained one
box, label = 0, 0
inference_running = False

def model_inference_async(frame):
    ''' Runs model_inference on a frame in a separate thread so that the on_video_frame processing loop is not blocked by slow inference steps.
    Updates global bounding box and label variables with the information from the latest inference step.
    '''
    global box, label, inference_running
    inference_running = True
    box_, label_ = model_inference(frame)
    box, label = box_, label_
    inference_running = False

def model_inference(frame):
    ''' Function for running model inference on a single frame
    '''
    res = model(frame)
    if len(res[0].boxes) > 0:
        box = res[0].boxes[0].xyxy[0].cpu().numpy().astype(int)
        label = res[0].boxes[0].cls[0].item()
        return box, label
    return None, None

def get_local_ip():
    ''' Obtains local ip address that devApp is presumably running on.
    '''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Connect to Flask-SocketIO server
sio = socketio.Client()

# Event handlers for connecting and disconnecting
@sio.event
def connect():
    print("Successfully connected to server")

@sio.event
def disconnect(reason=None):
    print("Disconnected from server, reason: ", reason)
    exit(0)

# Event handler for receiving emitted video frames
@sio.on('video_frame')
def on_video_frame(data):
    ''' Receives video frames emitted by server, runs inference, annotates frames and sends them back under 'model_output' event
    '''
    global box, label, inference_running

    # Decode frames
    img_bytes = base64.b64decode(data['data'])
    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    # Start inference in a separate thread if not already running
    if not inference_running:
        threading.Thread(target=model_inference_async, args=(frame.copy(),), daemon=True).start()

    # Annotate current frame with last known box/class
    annotated_frame = frame.copy()
    if box is not None and label is not None:
        x1, y1, x2, y2 = box
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0,255,0), 2)
        cv2.putText(annotated_frame, str(label), (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)

    _, buffer = cv2.imencode('.jpg', annotated_frame)
    img_b64 = base64.b64encode(buffer).decode('utf-8')
    sio.emit('model_output', {'data': img_b64})



if __name__ == "__main__":
    local_ip = get_local_ip()
    server_url = f'http://{local_ip}:5000'
    try:
        sio.connect(server_url)
        sio.wait()
    except KeyboardInterrupt:
        print("Shutting down client")
        sio.disconnect()
        exit(0)