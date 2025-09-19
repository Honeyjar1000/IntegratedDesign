#!/usr/bin/env python3
"""
Main entry point for the robot control client application.
"""

# CRITICAL: Completely disable signal handling in socketio/engineio before any imports
import signal
import sys

# Store the original signal function
_original_signal = signal.signal

# Create a signal handler that completely ignores SIGINT
def _no_sigint_handler(sig, handler):
    """Signal handler that ignores SIGINT to prevent Tkinter conflicts."""
    if sig == signal.SIGINT:
        # Return a dummy handler that does nothing
        return lambda sig, frame: None
    else:
        # Allow other signals to be handled normally
        return _original_signal(sig, handler)

# Replace signal.signal globally before any socketio imports
signal.signal = _no_sigint_handler

# Also patch the signal module in sys.modules to ensure all imports get the patched version
sys.modules['signal'].signal = _no_sigint_handler

if __name__ == "__main__":
    # Additional patching to prevent runtime signal handler issues
    try:
        import engineio.base_client
        # Disable the signal handler in engineio
        if hasattr(engineio.base_client, 'signal_handler'):
            engineio.base_client.signal_handler = lambda sig, frame: None
    except ImportError:
        pass
    
    try:
        import socketio.base_client
        # Disable the signal handler in socketio
        if hasattr(socketio.base_client, 'signal_handler'):
            socketio.base_client.signal_handler = lambda sig, frame: None
    except ImportError:
        pass
    
    from app.application import RobotControlApp
    app = RobotControlApp()
    app.mainloop()
