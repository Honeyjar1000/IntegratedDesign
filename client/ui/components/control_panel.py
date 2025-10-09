"""
Control panel with drive buttons and sliders.
"""
import tkinter as tk
from ui.styles import (
    create_frame, create_button, create_label, create_muted_label, create_scale
)


class ControlPanel:
    """Main control panel with drive buttons, sliders, and settings."""
    
    def __init__(self, parent, callbacks):
        self.callbacks = callbacks
        self.container = create_frame(parent)
        self.container.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        
        # Suppress programmatic slider callbacks
        self._suppress_speed_cb = False
        
        self._create_instruction_label()
        self._create_drive_buttons()
        self._create_speed_control()
        self._create_trim_controls()
        self._create_folder_selection()
    
    def _create_instruction_label(self):
        """Create instruction text."""
        tip = create_muted_label(
            self.container,
            text="Click window to focus. Arrow keys drive. Space saves a photo."
        )
        tip.pack(pady=(0, 8))
    
    def _create_drive_buttons(self):
        """Create drive control buttons."""
        btns = create_frame(self.container)
        btns.pack()
        
        create_button(btns, "Forward (↑)", 
                     lambda: self.callbacks["drive"](1, 1)).pack(side=tk.LEFT, padx=4, pady=4)
        create_button(btns, "Reverse (↓)", 
                     lambda: self.callbacks["drive"](-1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
        create_button(btns, "Pivot Left (←)", 
                     lambda: self.callbacks["drive"](-1, 1)).pack(side=tk.LEFT, padx=4, pady=4)
        create_button(btns, "Pivot Right (→)", 
                     lambda: self.callbacks["drive"](1, -1)).pack(side=tk.LEFT, padx=4, pady=4)
        create_button(btns, "Stop", 
                     self.callbacks["stop"]).pack(side=tk.LEFT, padx=4, pady=4)
    
    def _create_speed_control(self):
        """Create speed limit slider."""
        spd = create_frame(self.container)
        spd.pack(pady=(10, 2))
        
        create_label(spd, text="Speed limit").pack(side=tk.LEFT, padx=(0, 8))
        
        self.speed_val = tk.StringVar(value="50%")
        create_label(spd, textvariable=self.speed_val).pack(side=tk.LEFT, padx=8)
        
        self.speed_scale = create_scale(
            spd, 
            from_=0, 
            to=100, 
            orient="horizontal", 
            length=260,
            command=self._on_speed_input
        )
        self.speed_scale.set(50)
        self.speed_scale.pack(side=tk.LEFT)
    
    def _create_trim_controls(self):
        """Create wheel trim sliders."""
        trim = create_frame(self.container)
        trim.pack(pady=(10, 2))
        
        create_label(trim, text="Wheel trim").grid(row=0, column=0, columnspan=3, sticky="w")
        
        # Left trim
        create_label(trim, text="Left", width=6).grid(row=1, column=0, sticky="e", padx=4)
        
        self.trim_left_val = tk.StringVar(value="1.00×")
        self.trim_left_scale = create_scale(
            trim,
            from_=50,
            to=120,
            orient="horizontal",
            length=260,
            command=self._on_trim_left_input
        )
        self.trim_left_scale.set(100)
        self.trim_left_scale.grid(row=1, column=1, padx=4)
        
        create_label(trim, textvariable=self.trim_left_val, width=6).grid(row=1, column=2, sticky="w")
        
        # Right trim
        create_label(trim, text="Right", width=6).grid(row=2, column=0, sticky="e", padx=4)
        
        self.trim_right_val = tk.StringVar(value="1.00×")
        self.trim_right_scale = create_scale(
            trim,
            from_=50,
            to=120,
            orient="horizontal",
            length=260,
            command=self._on_trim_right_input
        )
        self.trim_right_scale.set(100)
        self.trim_right_scale.grid(row=2, column=1, padx=4)
        
        create_label(trim, textvariable=self.trim_right_val, width=6).grid(row=2, column=2, sticky="w")
    
    def _create_folder_selection(self):
        """Create save folder selection."""
        save = create_frame(self.container)
        save.pack(pady=(10, 2))
        
        create_button(save, "Choose folder…", 
                     self.callbacks["choose_folder"]).pack(side=tk.LEFT, padx=4)
        
        self.save_label = create_muted_label(save, text="")
        self.save_label.pack(side=tk.LEFT, padx=8)
    
    def _on_speed_input(self, value):
        """Handle speed slider input."""
        if self._suppress_speed_cb:
            return
        
        val = int(float(value))
        self.speed_val.set(f"{val}%")
        self.callbacks["speed_change"](val)
    
    def _on_trim_left_input(self, value):
        """Handle left trim slider input."""
        val = int(float(value))
        self.trim_left_val.set(f"{val/100:.2f}×")
        self.callbacks["trim_left_change"](val)
    
    def _on_trim_right_input(self, value):
        """Handle right trim slider input."""
        val = int(float(value))
        self.trim_right_val.set(f"{val/100:.2f}×")
        self.callbacks["trim_right_change"](val)
    
    def update_speed(self, percent):
        """Update speed display (without triggering callback)."""
        self._suppress_speed_cb = True
        try:
            self.speed_scale.set(percent)
            self.speed_val.set(f"{percent}%")
        finally:
            self._suppress_speed_cb = False
    
    def update_trim_left(self, percent):
        """Update left trim display."""
        self.trim_left_scale.set(percent)
        self.trim_left_val.set(f"{percent/100:.2f}×")
    
    def update_trim_right(self, percent):
        """Update right trim display."""
        self.trim_right_scale.set(percent)
        self.trim_right_val.set(f"{percent/100:.2f}×")
    
    def update_save_folder_text(self, text):
        """Update save folder display text."""
        self.save_label.config(text=text)
