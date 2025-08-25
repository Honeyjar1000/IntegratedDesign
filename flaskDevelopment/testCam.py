import cv2
cap = cv2.VideoCapture(0)
success, frame = cap.read()
print(success)
cap.release()