import sys
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

class GStreamerPlayer:
    def __init__(self):
        Gst.init(None)
        self.pipeline = Gst.ElementFactory.make("playbin", "player")
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_bus_message)
        self.duration = Gst.CLOCK_TIME_NONE
        
        # Volume properties
        self._volume = 1.0  # Default volume (100%)
        self._muted = False
        
        # Callback for track end
        self._on_track_end_callback = None

    def set_on_track_end_callback(self, callback):
        """Set callback to be called when track finishes (EOS)."""
        self._on_track_end_callback = callback

    def on_bus_message(self, bus, message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            print("🎵 GStreamer: End of Stream (track finished)")
            # Call the callback if set
            if self._on_track_end_callback:
                self._on_track_end_callback()
            else:
                self.pipeline.set_state(Gst.State.NULL)
                print("Playback finished.")
        elif mtype == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = message.parse_error()
            print(f"Error: {err.message}")
        elif mtype == Gst.MessageType.DURATION_CHANGED:
            self._update_duration()
        elif mtype == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                if new_state == Gst.State.PLAYING:
                    self._update_duration()

    def _update_duration(self):
        """Query and update the duration of current media."""
        success, self.duration = self.pipeline.query_duration(Gst.Format.TIME)
        if success:
            seconds = self.duration / Gst.SECOND
            print(f"Duration: {seconds:.2f} seconds")
        else:
            self.duration = Gst.CLOCK_TIME_NONE
            print("Duration query failed")

    def set_uri(self, uri):
        """Set the file URI to play."""
        self.pipeline.set_property("uri", uri)
        self.duration = Gst.CLOCK_TIME_NONE

    def play(self):
        self.pipeline.set_state(Gst.State.PLAYING)

    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)

    def stop(self):
        self.pipeline.set_state(Gst.State.NULL)

    def set_position(self, seconds):
        """
        Set playback position to specific time in seconds.
        
        Args:
            seconds (float): Time position in seconds
        """
        if not self.pipeline or self.duration == Gst.CLOCK_TIME_NONE:
            print("Cannot set position: No media loaded or duration unknown")
            return False
        
        position_ns = seconds * Gst.SECOND
        
        if position_ns < 0:
            position_ns = 0
        elif self.duration > 0 and position_ns > self.duration:
            position_ns = self.duration - (Gst.SECOND * 0.1)
        
        success = self.pipeline.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            position_ns
        )
        
        if success:
            print(f"Seeked to {seconds:.2f} seconds")
        else:
            print(f"Failed to seek to {seconds:.2f} seconds")
        
        return success

    def seek(self, offset_seconds):
        """
        Seek forward or backward by specified offset.
        
        Args:
            offset_seconds (float): Positive = forward, Negative = backward
        """
        success, current_pos = self.pipeline.query_position(Gst.Format.TIME)
        
        if not success:
            print("Cannot seek: Could not query current position")
            return False
        
        current_seconds = current_pos / Gst.SECOND
        new_seconds = current_seconds + offset_seconds
        
        if new_seconds < 0:
            new_seconds = 0
            print("Seeked to beginning")
        
        return self.set_position(new_seconds)

    def get_position(self):
        """Get current playback position in seconds."""
        success, position = self.pipeline.query_position(Gst.Format.TIME)
        if success:
            return position / Gst.SECOND
        return 0.0

    def get_duration(self):
        """Get total duration in seconds."""
        if self.duration != Gst.CLOCK_TIME_NONE:
            return self.duration / Gst.SECOND
        return 0.0

    # VOLUME CONTROL METHODS
    def set_volume(self, volume_level):
        """
        Set volume level.
        
        Args:
            volume_level (float): 0.0 (silent) to 1.0 (100% / max volume)
                                  Can be >1.0 for amplification (e.g., 2.0 = 200%)
        """
        if volume_level < 0:
            volume_level = 0
        
        self._volume = volume_level
        
        # If muted, we store the volume but don't apply it until unmuted
        if not self._muted:
            self.pipeline.set_property("volume", volume_level)
            print(f"Volume set to {volume_level:.2f} ({volume_level*100:.0f}%)")
        
        return volume_level

    def get_volume(self):
        """Get current volume level (0.0 to 1.0+)."""
        return self._volume

    def set_volume_percent(self, percent):
        """
        Set volume as a percentage.
        
        Args:
            percent (int/float): 0 to 100 (or more for amplification)
        """
        volume_level = percent / 100.0
        return self.set_volume(volume_level)

    def get_volume_percent(self):
        """Get current volume as percentage."""
        return self._volume * 100

    def volume_up(self, increment=0.1):
        """
        Increase volume by specified increment.
        
        Args:
            increment (float): Amount to increase volume by (default: 0.1 = 10%)
        """
        new_volume = self._volume + increment
        return self.set_volume(new_volume)

    def volume_down(self, decrement=0.1):
        """
        Decrease volume by specified decrement.
        
        Args:
            decrement (float): Amount to decrease volume by (default: 0.1 = 10%)
        """
        new_volume = self._volume - decrement
        return self.set_volume(new_volume)

    def toggle_mute(self):
        """Toggle mute on/off."""
        return self.set_mute(not self._muted)

    def set_mute(self, muted):
        """
        Set mute state.
        
        Args:
            muted (bool): True to mute, False to unmute
        """
        self._muted = muted
        
        if muted:
            # Store current volume and set to 0
            self.pipeline.set_property("volume", 0.0)
            print("Muted")
        else:
            # Restore to stored volume
            self.pipeline.set_property("volume", self._volume)
            print(f"Unmuted (volume: {self._volume:.2f})")
        
        return self._muted

    def is_muted(self):
        """Check if audio is muted."""
        return self._muted

# Example usage
# @lambda _:_()
def test():
    from . import path_to_uri

    uri = path_to_uri('./tracks/Suzume - RADWIMPS ft. Toaka.mp3')

    # Example usage
    player = GStreamerPlayer()
    player.set_uri(uri)
    player.play()

    import asyncio
    import threading
    from gi.repository import GLib

    def run_glib_mainloop():
        """Run GLib's main loop in a background thread"""
        loop = GLib.MainLoop()
        loop.run()

    async def main():
        # Start GLib main loop in background thread
        glib_thread = threading.Thread(target=run_glib_mainloop, daemon=True)
        glib_thread.start()
        
        # Your async code runs here
        print("GLib running in background, async code continues...")
        
        for i in range(11):
            await asyncio.sleep(1)
            print(f"Async task {i+1}")
            player.volume_up()

    # Run it
    asyncio.run(main())

    import time

    time.sleep(5)

