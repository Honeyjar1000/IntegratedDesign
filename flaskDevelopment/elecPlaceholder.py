"""
Socketio client script that acts as a placeholder for the electrical team's payload.
Sends camera frames and audio to the Pi Flask server
"""

import cv2
import socketio
import time
import sounddevice as sd
import threading

# Connect to Flask-SocketIO server
sio = socketio.Client()

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
        sio.emit('e_camera_frame', buffer.tobytes())
        time.sleep(0.05)  # ~20 FPS - NOTE: can change this to increase FPS
    cap.release()

def capture_audio(samplerate=16000, blocksize=1024):
    '''Captures audio from mic and emits to server as raw PCM bytes.
    This takes up the most bandwidth but does not require much encoding or decoding.
    '''
    def callback(indata, frames, time_info, status):
        # indata is a numpy array of shape (blocksize, channels)
        # Convert to bytes and emit
        sio.emit('e_audio_frame', indata.tobytes())
    with sd.InputStream(samplerate=samplerate, channels=1, blocksize=blocksize, callback=callback):
        while True:
            time.sleep(0.1)  # Keep thread alive

if __name__ == "__main__":
    sio.connect("http://172.20.10.11:5000")

    # Start video and audio capture in separate threads
    threading.Thread(target=capture_frames, daemon=True).start()
    threading.Thread(target=capture_audio, daemon=True).start()

    # Keep main thread alive
    while True:
        time.sleep(1)
