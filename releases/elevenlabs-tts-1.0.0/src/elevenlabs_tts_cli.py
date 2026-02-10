#!/usr/bin/env python3
"""
ElevenLabs TTS CLI - New implementation with GStreamer playback
Integrates TTS generation with MPRIS media controls
"""

import sys
import os
import hashlib
import argparse
import requests
import subprocess
from pathlib import Path
from datetime import datetime
import threading

# GStreamer and GLib
from gi.repository import GLib

# Mutagen for metadata
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TXXX
from mutagen.mp3 import MP3

# Local imports
from lib.gst import GStreamerPlayer
from lib.mpris import build_track, Playlist
from lib.DBUS import MprisSessionMessageBus, MprisPlayerInterface, MprisRootInterface, MprisEventLoop
from lib.database import (
    get_config, get_active_api_key, get_history_by_hash, 
    add_history, get_history, CACHE_DIR
)

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_selection():
    """Get selected text via wl-paste (Wayland) or xclip (X11)."""
    try:
        # Try Wayland first
        result = subprocess.run(
            ["wl-paste", "-p"], 
            capture_output=True, 
            text=True, 
            timeout=1
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    try:
        # Fallback to X11
        result = subprocess.run(
            ["xclip", "-o", "-selection", "primary"],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    return None


def hash_text(text):
    """Compute MD5 hash of text for cache lookup."""
    return hashlib.md5(text.encode()).hexdigest()


def get_next_order_id():
    """Get the next order_id by counting existing history entries."""
    history = get_history()
    return len(history) + 1


def write_metadata(audio_path, text, voice_name, order_id, text_hash):
    """Write ID3 metadata to MP3 file using mutagen."""
    try:
        audio = MP3(audio_path, ID3=ID3)
        
        # Add ID3 tag if it doesn't exist
        try:
            audio.add_tags()
        except Exception:
            pass
        
        # Title (preview - first 40 chars)
        title_preview = text[:40] + "..." if len(text) > 40 else text
        audio.tags.add(TIT2(encoding=3, text=title_preview))
        
        # Artist (voice name)
        audio.tags.add(TPE1(encoding=3, text=voice_name.split(' ')[0]))
        
        # Album
        audio.tags.add(TALB(encoding=3, text="ElevenLabs TTS"))
        
        # Custom frames
        audio.tags.add(TXXX(encoding=3, desc='order_id', text=str(order_id)))
        audio.tags.add(TXXX(encoding=3, desc='text_hash', text=text_hash))
        audio.tags.add(TXXX(encoding=3, desc='full_text', text=text))
        
        audio.save()
        print(f"✅ Metadata written (order_id={order_id})")
        
    except Exception as e:
        print(f"⚠️  Failed to write metadata: {e}")


def generate_tts(text):
    """
    Generate TTS audio via ElevenLabs API.
    Returns audio file path or None on failure.
    """
    # Get configuration
    api_key = get_active_api_key()
    if not api_key:
        print("❌ No API key configured. Please run settings UI first.")
        return None
    
    voice_id = get_config("voice_id", "")
    if not voice_id:
        print("❌ No voice selected. Please run settings UI first.")
        return None
    
    model_id = get_config("model_id", "eleven_multilingual_v2")
    stability = get_config("stability", 50) / 100
    similarity_boost = get_config("similarity_boost", 75) / 100
    voice_name = get_config("voice_name", "ElevenLabs")
    
    # Make API request
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key["api_key"],
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }
    
    print(f"🎤 Generating TTS with voice '{voice_name}'...")
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}"
            try:
                detail = response.json().get("detail", {})
                if isinstance(detail, dict):
                    error_msg += f": {detail.get('message', 'Unknown error')}"
                else:
                    error_msg += f": {detail}"
            except:
                pass
            print(f"❌ {error_msg}")
            return None
        
        # Save audio file
        text_hash = hash_text(text)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}_{text_hash}.mp3"
        audio_path = CACHE_DIR / filename
        
        with open(audio_path, "wb") as f:
            f.write(response.content)
        
        print(f"✅ Audio saved: {filename}")
        
        # Write metadata
        order_id = get_next_order_id()
        write_metadata(audio_path, text, voice_name, order_id, text_hash)
        
        # Add to database history
        add_history(
            text=text,
            audio_file=str(audio_path),
            voice_name=voice_name,
            model_id=model_id,
            text_hash=text_hash,
            thumbnail_url=""
        )
        
        return str(audio_path)
        
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return None
    except Exception as e:
        print(f"❌ Error during generation: {e}")
        return None


def build_tts_playlist():
    """Build playlist from cached TTS audio files."""
    history = get_history()  # Returns newest first
    
    if not history:
        return None
    
    tracks = []
    for item in history:
        audio_file = item.get("audio_file", "")
        if audio_file and Path(audio_file).exists():
            try:
                track = build_track(audio_file)
                tracks.append(track)
            except Exception as e:
                print(f"⚠️  Failed to load track {audio_file}: {e}")
                continue
    
    if not tracks:
        return None
    
    # Reverse to get oldest first (chronological order)
    tracks.reverse()
    
    return Playlist(tracks)


def start_playback(playlist, start_index=0):
    """
    Start MPRIS playback with the given playlist.
    Extracted from playback.py with adaptations.
    """
    if not playlist or len(playlist) == 0:
        print("❌ Empty playlist")
        return
    
    # Get track to start with
    first_track = playlist[start_index] if start_index < len(playlist) else playlist[0]
    playlist.current_track = first_track
    playlist._history.append(first_track)
    
    print(f"\n🎵 Starting playlist with: {first_track.name}")
    
    # Initialize GStreamer player
    player = GStreamerPlayer()
    
    # Start GLib main loop in background
    def run_glib_mainloop():
        loop = GLib.MainLoop()
        loop.run()
    
    glib_thread = threading.Thread(target=run_glib_mainloop, daemon=True)
    glib_thread.start()
    
    # MPRIS configuration
    player_identity = "ElevenLabs TTS" 
    bus_suffix = "elevenlabs_tts"
    bus_name = f"org.mpris.MediaPlayer2.{bus_suffix}"
    object_path = "/org/mpris/MediaPlayer2"
    
    # Navigation callbacks
    def on_next_track():
        next_track = playlist.next_track()
        if next_track:
            print(f"\n⏭️  Next: {next_track.name}")
            player.set_uri(next_track.uri)
            return next_track
        return None
    
    def on_previous_track():
        prev_track = playlist.previous_track()
        if prev_track:
            print(f"\n⏮️  Previous: {prev_track.name}")
            player.set_uri(prev_track.uri)
            return prev_track
        return None
    
    def on_exit_program():
        print(f"\n\n👋 Playback finished")
        player.stop()
        bus.disconnect()
        sys.exit(0)
    
    # Set initial track
    player.set_uri(first_track.uri)
    
    # Connect to D-Bus
    bus = MprisSessionMessageBus()
    
    # Create MPRIS interfaces
    root_obj = MprisRootInterface(player_identity)
    interface = MprisPlayerInterface(
        initial_track=first_track,
        gst_player=player,
        on_next_track=on_next_track,
        on_previous_track=on_previous_track,
        on_exit_program=on_exit_program
    )
    
    # Sync LoopStatus with playlist repeat mode
    _original_loop_status_setter = type(interface).LoopStatus.fset
    def synced_loop_status_setter(self, status):
        _original_loop_status_setter(self, status)
        if status == "None":
            playlist.set_repeat('off')
        elif status == "Track":
            playlist.set_repeat('one')
        elif status == "Playlist":
            playlist.set_repeat('all')
    
    type(interface).LoopStatus = property(
        type(interface).LoopStatus.fget,
        synced_loop_status_setter
    )
    
    # Publish objects
    bus.publish_object(object_path, root_obj)
    bus.publish_object(object_path, interface)
    bus.register_service(bus_name)
    
    # Start playback
    player.play()
    
    print(f"\n✅ MPRIS service ready: {bus_name}")
    print(f"🎧 Now playing: {first_track.name}")
    print(f"📊 Playlist: {len(playlist)} track(s)")
    print("\n⏹️  Press Ctrl+C to exit\n")
    
    # Run event loop
    loop = MprisEventLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        player.stop()
        bus.disconnect()
        print("✅ Goodbye!")


def main():
    parser = argparse.ArgumentParser(description="ElevenLabs TTS CLI")
    parser.add_argument("--replay", action="store_true", 
                       help="Replay all cached TTS audio")
    args = parser.parse_args()
    
    if args.replay:
        # Replay mode: build playlist from cache
        print("🔄 Loading cached TTS audio...")
        playlist = build_tts_playlist()
        
        if not playlist:
            print("❌ No cached audio found")
            sys.exit(1)
        
        start_playback(playlist)
    
    else:
        # TTS mode: capture text and generate
        text = get_selection()
        
        if not text:
            print("❌ No text selected")
            sys.exit(1)
        
        print(f"📝 Selected text: {text[:50]}{'...' if len(text) > 50 else ''}")
        
        # Check cache
        text_hash = hash_text(text)
        cached = get_history_by_hash(text_hash)
        
        if cached and cached.get("audio_file"):
            audio_file = cached["audio_file"]
            if Path(audio_file).exists():
                print(f"✅ Using cached audio")
                # Build playlist with just this track
                track = build_track(audio_file)
                playlist = Playlist([track])
                start_playback(playlist)
                return
        
        # Generate new TTS
        audio_path = generate_tts(text)
        
        if not audio_path:
            sys.exit(1)
        
        # Build playlist with the new track
        track = build_track(audio_path)
        playlist = Playlist([track])
        start_playback(playlist)


if __name__ == "__main__":
    main()
