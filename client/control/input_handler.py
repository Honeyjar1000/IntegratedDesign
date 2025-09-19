"""
Input handling and keyboard controls.
"""
from app.constants import STEP_DEG


class InputHandler:
    """Handles keyboard input and converts to control commands."""
    
    def __init__(self, drive_controller, servo_controller, photo_service, app_close_callback):
        self.drive_controller = drive_controller
        self.servo_controller = servo_controller
        self.photo_service = photo_service
        self.app_close_callback = app_close_callback
        self.drive_pressed = set()
    
    def on_key_press(self, event):
        """Handle key press events."""
        code = event.keysym
        
        # Drive controls
        if code in ("Up", "Down", "Left", "Right"):
            if code in self.drive_pressed:
                return
            self.drive_pressed.add(code)
            
            if code == "Up":
                self.drive_controller.drive(1, 1)
            elif code == "Down":
                self.drive_controller.drive(-1, -1)
            elif code == "Left":
                self.drive_controller.drive(-1, 1)
            elif code == "Right":
                self.drive_controller.drive(1, -1)
            return
        
        # Photo capture
        if code == "space":
            self.photo_service.take_photo()
            return
        
        # Servo controls
        if code in ("w", "W"):
            self.servo_controller.nudge_angle(-STEP_DEG)
        elif code in ("s", "S"):
            self.servo_controller.nudge_angle(STEP_DEG)
        elif code in ("a", "A"):
            self.servo_controller.nudge_angle_2(-STEP_DEG)
        elif code in ("d", "D"):
            self.servo_controller.nudge_angle_2(STEP_DEG)
        elif code in ("q", "Q"):
            self.app_close_callback()
    
    def on_key_release(self, event):
        """Handle key release events."""
        code = event.keysym
        if code in self.drive_pressed:
            self.drive_pressed.discard(code)
        
        # Stop driving if no drive keys are pressed
        if not any(k in self.drive_pressed for k in ("Up", "Down", "Left", "Right")):
            self.drive_controller.stop()
