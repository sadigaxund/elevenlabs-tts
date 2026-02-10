#!/usr/bin/env python3
"""
ElevenLabs TTS Settings - GTK4 settings application
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib
import threading
import sys
from pathlib import Path
import requests

from lib.database import (
    get_config, set_config, get_all_config,
    get_api_keys, add_api_key, delete_api_key, 
    update_api_key_quota, update_api_key_label,
    get_active_api_key,
    CACHE_DIR
)

# Professional naming
APP_ID = "com.elevenlabs.tts.settings"

# Static model list
MODELS = [
    {"name": "Eleven v3 (Latest)", "model_id": "eleven_v3"},
    {"name": "Eleven Multilingual v2", "model_id": "eleven_multilingual_v2"},
    {"name": "Eleven Flash v2.5 (Fast)", "model_id": "eleven_flash_v2_5"},
]

class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="ElevenLabs TTS Settings")
        self.set_default_size(600, 750)
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)
        
        # Header bar
        header = Adw.HeaderBar()
        main_box.append(header)
        
        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        main_box.append(self.toast_overlay)
        
        # Scrolled content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.toast_overlay.set_child(scrolled)
        
        # Clamp settings width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(550)
        scrolled.set_child(clamp)
        
        # Settings box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(12)
        box.set_margin_end(12)
        clamp.set_child(box)
        
        # --- API Keys Section ---
        box.append(self.create_api_keys_section())
        
        # --- Voice Settings Section ---
        box.append(self.create_voice_section())
        
        # --- Parameters Section ---
        box.append(self.create_voice_params_section())
        
        # --- Cache Settings Section ---
        box.append(self.create_cache_settings_section())
        
        # Save Button Container
        save_box = Gtk.Box(halign=Gtk.Align.END)
        self.save_btn = Gtk.Button(label="Save Settings")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.add_css_class("pill")
        self.save_btn.connect("clicked", self.on_save)
        # self.save_btn.set_sensitive(False) # Default disabled, enable on change
        save_box.append(self.save_btn)
        box.append(save_box)
        
        # Load voices
        self.voices = []
        self.load_voices()
        
        # Refresh quotas on startup
        self.refresh_all_quotas()
        
        # Mark initial state for "changes detection"
        # (For simplicity we enable save always to avoid bugs with detection logic complexity)
        # self.save_btn.set_sensitive(True) 

    def create_api_keys_section(self):
        group = Adw.PreferencesGroup(title="ElevenLabs API Keys", 
            description="Manage your API keys. Quota is fetched automatically.")
        
        # Keys List
        self.keys_list_box = Gtk.ListBox()
        self.keys_list_box.add_css_class("boxed-list")
        self.keys_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        group.add(self.keys_list_box)
        
        # Add Key Expander Row (Simplified)
        add_row = Adw.ExpanderRow(title="Add New Key", subtitle="Enter API key to validate")

        # Input Box Row inside Expander
        input_container = Adw.ActionRow()
        
        # Layout for inputs
        inputs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inputs_box.set_valign(Gtk.Align.CENTER)
        
        self.key_value_entry = Gtk.Entry(placeholder_text="sk_abcdef...")
        self.key_value_entry.set_width_chars(35)
        self.key_value_entry.set_hexpand(True)
        
        self.add_key_btn = Gtk.Button(label="Validate & Add")
        self.add_key_btn.add_css_class("accent")
        self.add_key_btn.connect("clicked", self.on_add_key_clicked)
        
        # Add a spinner for loading state
        self.add_spinner = Gtk.Spinner()
        
        inputs_box.append(self.key_value_entry)
        inputs_box.append(self.add_spinner)
        inputs_box.append(self.add_key_btn)
        
        input_container.add_suffix(inputs_box)
        add_row.add_row(input_container)
        
        group.add(add_row)
        
        # Refresh list initially
        self.refresh_keys_list()
        
        return group

    def refresh_keys_list(self):
        # Clear existing
        while child := self.keys_list_box.get_first_child():
            self.keys_list_box.remove(child)
            
        api_keys = get_api_keys()
        active_key = get_active_api_key()
        active_id = active_key["id"] if active_key else -1
            
        if not api_keys:
            row = Adw.ActionRow(title="No API keys added")
            self.keys_list_box.append(row)
            return

        for idx, key in enumerate(api_keys):
            row = Adw.ActionRow(title=key["label"])
            
            # Subtitle with quota
            used = key["character_count"]
            limit = key["character_limit"]
            percent = (used / limit * 100) if limit > 0 else 0
            
            status = "🔴 Exhausted" if key["exhausted"] else "🟢 Active"
            if key["id"] == active_id:
                status += " (Current)"
                row.add_css_class("success") # Highlight current
                
            row.set_subtitle(f"{used:,} / {limit:,} chars used ({int(percent)}%) • {status}")
            
            # Actions
            select_btn = Gtk.Button(icon_name="emblem-ok-symbolic")
            select_btn.set_tooltip_text("Set as Active")
            select_btn.add_css_class("flat")
            if key["id"] == active_id:
                select_btn.add_css_class("success")
                select_btn.set_sensitive(False)
            select_btn.connect("clicked", lambda b, i=idx: self.on_select_key(i))

            edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
            edit_btn.set_tooltip_text("Rename Label")
            edit_btn.add_css_class("flat")
            edit_btn.connect("clicked", lambda b, i=idx: self.on_edit_label(i))

            refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
            refresh_btn.set_tooltip_text("Refresh Quota")
            refresh_btn.add_css_class("flat")
            refresh_btn.connect("clicked", lambda b, i=idx: self.refresh_quota(i))
            
            del_btn = Gtk.Button(icon_name="user-trash-symbolic")
            del_btn.set_tooltip_text("Delete Key")
            del_btn.add_css_class("flat")
            del_btn.add_css_class("error")
            del_btn.connect("clicked", lambda b, i=idx: self.delete_key(i))
            
            row.add_suffix(select_btn)
            row.add_suffix(edit_btn)
            row.add_suffix(refresh_btn)
            row.add_suffix(del_btn)
            self.keys_list_box.append(row)

    def create_voice_section(self):
        group = Adw.PreferencesGroup(title="Voice Selection",
            description="Choose the voice and AI model.")
            
        # Voice Dropdown
        self.voice_row = Adw.ComboRow(title="Voice")
        self.voice_row.set_model(Gtk.StringList.new(["Loading..."]))
        
        # Add Refresh Button for voices
        voice_refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        voice_refresh_btn.set_tooltip_text("Refresh Voices from API")
        voice_refresh_btn.add_css_class("flat")
        voice_refresh_btn.set_valign(Gtk.Align.CENTER)
        voice_refresh_btn.connect("clicked", lambda _: self.load_voices(manual=True))
        self.voice_row.add_suffix(voice_refresh_btn)
        
        group.add(self.voice_row)
        
        # Model Dropdown
        self.model_row = Adw.ComboRow(title="Model Selection")
        model_names = [m["name"] for m in MODELS]
        self.model_row.set_model(Gtk.StringList.new(model_names))
        
        # Set current model
        current_model = get_config("model_id", "eleven_multilingual_v2")
        for i, m in enumerate(MODELS):
            if m["model_id"] == current_model:
                self.model_row.set_selected(i)
                break
                
        group.add(self.model_row)
        
        # Output Format
        self.format_row = Adw.ComboRow(title="Output Quality")
        formats = ["mp3_44100_128", "mp3_44100_192", "mp3_22050_32"]
        format_names = ["Standard (128kbps)", "High (192kbps)", "Low (32kbps)"]
        self.format_row.set_model(Gtk.StringList.new(format_names))
        
        current_format = get_config("output_format", "mp3_44100_128")
        if current_format in formats:
            self.format_row.set_selected(formats.index(current_format))
            
        group.add(self.format_row)
        
        return group

    def create_voice_params_section(self):
        group = Adw.PreferencesGroup(title="Voice Parameters",
            description="Fine-tune the speech output.")
            
        # Helper to create scroll-disabled scale
        def create_scale_row(title, subtitle, min_val, max_val, step, current_val, is_float=False):
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_val, max_val, step)
            scale.set_value(current_val)
            scale.set_size_request(180, -1)
            scale.set_valign(Gtk.Align.CENTER)
            scale.set_draw_value(False)
            
            # Disable scroll
            scroll_ctrl = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
            scroll_ctrl.connect("scroll", lambda *_: True)
            scale.add_controller(scroll_ctrl)
            
            # Label
            label_text = f"{current_val:.2f}" if is_float else f"{int(current_val)}%"
            label = Gtk.Label(label=label_text)
            label.set_width_chars(5)
            label.add_css_class("monospace")
            label.set_valign(Gtk.Align.CENTER)
            
            # Update label on change
            def on_change(s):
                val = s.get_value()
                txt = f"{val:.2f}" if is_float else f"{int(val)}%"
                label.set_text(txt)
            scale.connect("value-changed", on_change)
            
            row.add_suffix(scale)
            row.add_suffix(label)
            
            return row, scale
        
        # Stability
        self.stability_row, self.stability_scale = create_scale_row(
            "Stability", "Higher = more consistent, Lower = more expressive",
            0, 100, 1, get_config("stability", 50)
        )
        group.add(self.stability_row)
        
        # Similarity
        self.similarity_row, self.similarity_scale = create_scale_row(
            "Similarity Boost", "Higher = closer to original voice",
            0, 100, 1, get_config("similarity_boost", 75)
        )
        group.add(self.similarity_row)
        
        # Speed
        self.speed_row, self.speed_scale = create_scale_row(
            "Speed", "0.7 = slower, 1.0 = normal, 1.2 = faster",
            0.7, 1.2, 0.01, get_config("speed", 1.0), is_float=True
        )
        group.add(self.speed_row)

        # Volume
        self.volume_row, self.volume_scale = create_scale_row(
            "Playback Volume", "Values above 100% will amplify sound",
            0, 200, 1, get_config("volume", 100)
        )
        group.add(self.volume_row)
        
        return group
    
    def create_cache_settings_section(self):
        group = Adw.PreferencesGroup(title="Cache Settings",
            description="Control TTS clip history and cache.")
        
        # Unlimited cache toggle
        self.unlimited_row = Adw.SwitchRow(title="Unlimited Cache",
            subtitle="Keep all TTS clips without limit")
        self.unlimited_row.set_active(get_config("cache_unlimited", False))
        self.unlimited_row.connect("notify::active", self.on_unlimited_toggled)
        group.add(self.unlimited_row)
        
        # Max clips spinner
        self.max_clips_row = Adw.ActionRow(title="Max History Clips",
            subtitle="Number of recent clips to keep")
        
        self.max_clips_spin = Gtk.SpinButton.new_with_range(5, 500, 5)
        self.max_clips_spin.set_value(get_config("max_history", 10))
        self.max_clips_spin.set_valign(Gtk.Align.CENTER)
        
        self.max_clips_row.add_suffix(self.max_clips_spin)
        group.add(self.max_clips_row)
        
        # Visibility logic
        self.max_clips_row.set_visible(not self.unlimited_row.get_active())

        # Cache Size & Clear
        self.cache_size_row = Adw.ActionRow(title="Used Cache Size",
            subtitle=f"{self.get_cache_size():.1f} MB")
            
        clear_btn = Gtk.Button(label="Clear Cache")
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self.on_clear_cache)
        
        self.cache_size_row.add_suffix(clear_btn)
        group.add(self.cache_size_row)
        
        return group

    def on_unlimited_toggled(self, row, param):
        is_unlimited = row.get_active()
        self.max_clips_row.set_visible(not is_unlimited)

    def get_cache_size(self):
        """Get cache directory size in MB."""
        if not CACHE_DIR.exists():
            return 0.0
        total = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
        return total / (1024 * 1024)
    
    def on_clear_cache(self, button):
        """Clear the audio cache."""
        if CACHE_DIR.exists():
            try:
                for f in CACHE_DIR.glob("*.mp3"):
                    f.unlink()
                self.cache_size_row.set_subtitle("0.0 MB")
                self.show_toast("Cache cleared")
            except Exception as e:
                self.show_toast(f"Error: {str(e)[:30]}")

    def on_add_key_clicked(self, button):
        api_key = self.key_value_entry.get_text().strip()
        
        if not api_key:
            self.show_toast("Please enter an API key")
            return
        
        # Disable inputs
        self.key_value_entry.set_sensitive(False)
        self.add_key_btn.set_sensitive(False)
        self.add_spinner.start()
        
        # Perform validation in thread
        threading.Thread(target=self.validate_and_add_key, args=(api_key,), daemon=True).start()

    def validate_and_add_key(self, api_key):
        try:
            # 1. Check Subscription endpoint to validate key & get quota
            response = requests.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": api_key},
                timeout=10
            )
            
            if response.status_code != 200:
                msg = f"Invalid Key (HTTP {response.status_code})"
                GLib.idle_add(self.after_add_error, msg)
                return

            data = response.json()
            quota_used = data.get("character_count", 0)
            quota_limit = data.get("character_limit", 10000)
            exhausted = quota_used >= quota_limit
            
            # 2. Get User Info for Label
            user_resp = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": api_key},
                timeout=10
            )
            
            label = "API Key"
            if user_resp.status_code == 200:
                user_data = user_resp.json()
                label = user_data.get("first_name") or "API Key"

            # 3. Add to Database
            add_api_key(label, api_key)
            
            # Get the ID of the key we just added (last one) to update quota
            keys = get_api_keys()
            new_key_id = keys[-1]["id"]
            update_api_key_quota(new_key_id, quota_used, quota_limit, exhausted)
            
            GLib.idle_add(self.after_add_success)
            
        except Exception as e:
            GLib.idle_add(self.after_add_error, f"Error: {str(e)[:30]}")

    def after_add_success(self):
        self.key_value_entry.set_text("")
        self.key_value_entry.set_sensitive(True)
        self.add_key_btn.set_sensitive(True)
        self.add_spinner.stop()
        self.refresh_keys_list()
        self.show_toast("Key Added")
        
        # If this is the first key, load voices automatically
        if len(get_api_keys()) == 1:
            self.load_voices()

    def after_add_error(self, message):
        self.key_value_entry.set_sensitive(True)
        self.add_key_btn.set_sensitive(True)
        self.add_spinner.stop()
        self.show_toast(message)

    def on_edit_label(self, idx):
        api_keys = get_api_keys()
        if idx >= len(api_keys): return
        key_entry = api_keys[idx]

        # Use Adw.MessageDialog for a professional rename prompt
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Rename API Key",
            body="Enter a new label for this key:"
        )
        
        # Entry for new name
        entry = Gtk.Entry(text=key_entry["label"])
        entry.set_margin_top(12)
        entry.set_margin_bottom(12)
        entry.connect("activate", lambda *_: dialog.response("save"))
        
        # Wrap in a box for padding
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(entry)
        dialog.set_extra_child(box)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "save":
                new_label = entry.get_text().strip()
                if new_label:
                    update_api_key_label(key_entry["id"], new_label)
                    self.refresh_keys_list()
                    self.show_toast("Label updated")
            d.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def on_select_key(self, idx):
        set_config("active_key_index", idx)
        self.refresh_keys_list()
        self.load_voices() # Reload voices for the new active key
        self.show_toast("Active key changed")

    def delete_key(self, idx):
        api_keys = get_api_keys()
        if idx < len(api_keys):
            delete_api_key(api_keys[idx]["id"])
            self.refresh_keys_list()
            self.show_toast("API key deleted")

    def refresh_quota(self, idx):
        api_keys = get_api_keys()
        if idx >= len(api_keys):
            return
        
        key_entry = api_keys[idx]
        key_id = key_entry["id"]
        
        # Show loading state on row? (Simple: just toast)
        self.show_toast("Refreshing quota...")
        
        def fetch():
            try:
                response = requests.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers={"xi-api-key": key_entry["api_key"]},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    count = data.get("character_count", 0)
                    limit = data.get("character_limit", 10000)
                    exhausted = count >= limit
                    
                    update_api_key_quota(key_id, count, limit, exhausted)
                    
                    GLib.idle_add(self.refresh_keys_list)
                    GLib.idle_add(self.show_toast, "Quota Updated")
                else:
                    GLib.idle_add(self.show_toast, f"Error: HTTP {response.status_code}")
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Error: {str(e)[:30]}")
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def refresh_all_quotas(self):
        """Refresh quotas for all API keys on startup."""
        api_keys = get_api_keys()
        if not api_keys:
            return
        
        def fetch_all():
            for key_entry in api_keys:
                try:
                    response = requests.get(
                        "https://api.elevenlabs.io/v1/user/subscription",
                        headers={"xi-api-key": key_entry["api_key"]},
                        timeout=5
                    )
                    if response.status_code == 200:
                        data = response.json()
                        count = data.get("character_count", 0)
                        limit = data.get("character_limit", 10000)
                        exhausted = count >= limit
                        update_api_key_quota(key_entry["id"], count, limit, exhausted)
                except Exception:
                    pass
            GLib.idle_add(self.refresh_keys_list)
        
        threading.Thread(target=fetch_all, daemon=True).start()

    def load_voices(self, manual=False):
        active_key = get_active_api_key()
        if not active_key:
            if manual:
                self.show_toast("Add an API key first")
            return
            
        def fetch():
            try:
                if manual:
                    GLib.idle_add(self.show_toast, "Refreshing voices...")
                response = requests.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": active_key["api_key"]},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    voices = data.get("voices", [])
                    # Sort voices alphabetically
                    voices.sort(key=lambda x: x.get("name", ""))
                    
                    GLib.idle_add(self.update_voice_list, voices)
                    if manual:
                        GLib.idle_add(self.show_toast, f"Loaded {len(voices)} voices")
                else:
                    if manual:
                        GLib.idle_add(self.show_toast, f"Error: HTTP {response.status_code}")
                # ...
            except Exception as e:
                GLib.idle_add(self.show_toast, f"Voice load error: {str(e)[:20]}")
                
        threading.Thread(target=fetch, daemon=True).start()

    def update_voice_list(self, voices):
        self.voices = voices
        model = Gtk.StringList.new([v.get("name", "Unknown") for v in voices])
        self.voice_row.set_model(model)
        
        # Restore selection
        saved_id = get_config("voice_id", "")
        # Default if none
        if not saved_id and voices:
            # Try to find 'Rachel' or first one
            for v in voices:
                if "Rachel" in v.get("name", ""):
                    saved_id = v.get("voice_id")
                    break
            if not saved_id:
                saved_id = voices[0].get("voice_id")
                
        for i, v in enumerate(voices):
            if v.get("voice_id") == saved_id:
                self.voice_row.set_selected(i)
                break

    def on_save(self, button):
        # Save voice selection
        voice_idx = self.voice_row.get_selected()
        if voice_idx < len(self.voices):
            set_config("voice_id", self.voices[voice_idx].get("voice_id", ""))
            set_config("voice_name", self.voices[voice_idx].get("name", ""))
        
        # Save model selection
        model_idx = self.model_row.get_selected()
        if model_idx < len(MODELS):
            set_config("model_id", MODELS[model_idx]["model_id"])
        
        # Save format
        formats = ["mp3_44100_128", "mp3_44100_192", "mp3_22050_32"]
        format_idx = self.format_row.get_selected()
        if format_idx < len(formats):
            set_config("output_format", formats[format_idx])
        
        # Save sliders
        set_config("stability", int(self.stability_scale.get_value()))
        set_config("similarity_boost", int(self.similarity_scale.get_value()))
        set_config("speed", round(self.speed_scale.get_value(), 2))
        set_config("volume", int(self.volume_scale.get_value()))
        
        # Save cache settings
        set_config("max_history", int(self.max_clips_spin.get_value()))
        set_config("cache_unlimited", self.unlimited_row.get_active())
        
        self.show_toast("Settings Saved")

    def show_toast(self, message):
        toast = Adw.Toast(title=message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

class SettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        GLib.set_application_name("ElevenLabs TTS")
        GLib.set_prgname(APP_ID)
        
    def do_activate(self):
        win = SettingsWindow(self)
        win.set_icon_name("elevenlabs-tts")
        win.present()

def main():
    app = SettingsApp()
    return app.run(None)

if __name__ == "__main__":
    main()
