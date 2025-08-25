# ECE4191 Wildlife Observation System
## Development Environment
Readme for the ECE4191 web application and backend server. 
### Packages
Run ```pip install flask flask-socketio opencv-python python-socketio[client] ultralytics numpy``` to install required packages.

### Overview
The current pipeline uses a Flask server hosted on a Raspberry Pi Zero 2W to facilitate communication between a frontend and multiple clients. Clients include our own computer, which will access the Pi's camera stream to perform visual detection/classification, as well as the electrical teams' computers, which will pass processed sensor data to the server.

The dev environment is minimal at the moment since the priority was learning how WebSockets worked and how to access camera data with an inference script.

devApp.py runs a local Flask server on your computer for development purposes. Currently it uses dummy values to keep track of keyboard inputs and automatically opens the laptop camera as a placeholder for the Pi's camera stream. 

inference.py downloads YOLOv8 nano, which is the smallest + fastest V8 model for detection, and uses it to run inference on camera frames. On my (Brandon's) computer each inference takes >250ms which means a maximum of 4 frames/sec can be processed. This means that the script cannot run inference on every camera frame. The script listens for camera frames emitted by the server and runs inference in a separate thread. The latest bounding box and label is then annotated onto the latest frame and sent back to the server for displaying on the frontend. This means that while the annotated stream is up to date with the raw camera stream, the **bounding boxes shown are old by the time they are annotated onto the stream, causing noticeable lag**. 

### Flask Server and WebSockets
Client <---> Flask Server ---> Frontend
On a high level:
- Flask server receives camera frames from hardware
- Server encodes frames and sends them under 'video_frame' event
- Client (our computer) listens for video_frame events, and runs ```model_inference``` if it is not already running
- Client takes latest frame, annotates it with the latest bounding box (even if it is several frames old) and emits frames under 'model_output' event
- Server listens for 'model_output' events and emits annotated frames under 'annotated_frame' event so that the frontend can access annotated frames - **frontend cannot directly access events emitted by clients**
- Frontend does **JavaScript Bullshit** to handle receipt and display of annotated frames
- I'm sorry idk how the html works atm but we can renovate it later to make it cleaner and the frontend prettier

### Terminal Commands
```python flaskDevelopment/devApp.py``` to run the Flask server and web application. Click on local address to open web app.

In a separate terminal run ```python vision/inference.py```. Give it a 10 sec and you should see a second camera feed appear on the frontend with the bounding box.

```ctrl-c``` in the terminal running devApp.py to shutdown both the server and the client.