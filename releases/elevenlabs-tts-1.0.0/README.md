# ElevenLabs TTS

Text-to-Speech application using ElevenLabs API with MPRIS media controls integration.

## Features

- 🎤 **ElevenLabs TTS Integration** - High-quality text-to-speech generation
- 🔑 **Multi-API Key Management** - Automatic quota rotation
- 🎵 **MPRIS Media Controls** - Full GNOME integration with media keys
- 💾 **Smart Caching** - Reuse previously generated audio
- 🎨 **Settings Application** - Easy-to-use GTK4 configuration UI
- ⌨️ **Keyboard Shortcut Support** - Quick TTS from selected text

## Installation

### Option 1: Quick Install (Local User)

This is the fastest way to install for the current user (no root required).

1.  **Install system dependencies** (Fedora/RHEL):
    ```bash
    sudo dnf install python3-gobject gtk4 libadwaita python3-requests \
        python3-dasbus gstreamer1 gstreamer1-plugins-base \
        gstreamer1-plugins-good python3-mutagen
    ```

2.  **Install application**:
    ```bash
    make install
    ```
    This installs everything to `~/.local/` (binaries, desktop entries, icons).

### Option 2: System Package (RPM)

Best for system-wide installation or distribution on Fedora/RHEL/CentOS.

1.  **Prepare the source tarball**:
    ```bash
    ./prepare_release.sh
    ```
    This creates `~/rpmbuild/SOURCES/elevenlabs-tts-1.0.0.tar.gz`.

2.  **Build the RPM**:
    ```bash
    rpmbuild -ba ~/rpmbuild/SPECS/elevenlabs-tts.spec
    ```

3.  **Install the RPM**:
    ```bash
    sudo dnf install ~/rpmbuild/RPMS/noarch/elevenlabs-tts-1.0.0-1.fc*.noarch.rpm
    ```

## Usage

### Settings Application

Configure API keys, voice, and parameters:

```bash
elevenlabs-tts-settings
```

Or find "ElevenLabs TTS Settings" in your application menu.

### TTS CLI

Generate TTS from selected text:

```bash
elevenlabs-tts
```

**Recommended**: Bind this to a keyboard shortcut (e.g., Super+T):
1. Open Settings → Keyboard → Custom Shortcuts
2. Add new shortcut with command: `elevenlabs-tts`

Replay all cached audio:

```bash
elevenlabs-tts --replay
```

## Requirements

- Python 3.10+
- GTK4 / Libadwaita
- GStreamer
- Required Python packages:
  - gi (PyGObject)
  - requests
  - dasbus
  - mutagen

Install dependencies on Fedora/RHEL:

```bash
sudo dnf install python3-gobject gtk4 libadwaita python3-requests \
    python3-dasbus gstreamer1 gstreamer1-plugins-base \
    gstreamer1-plugins-good python3-mutagen
```

## Configuration

Settings and cache are stored following XDG Base Directory Specification:

- Config: `~/.config/com.elevenlabs.tts/`
- Data: `~/.local/share/com.elevenlabs.tts/`
- Cache: `~/.cache/com.elevenlabs.tts/`

## Uninstallation

```bash
make uninstall
```

To also remove user data:

```bash
rm -rf ~/.config/com.elevenlabs.tts ~/.local/share/com.elevenlabs.tts ~/.cache/com.elevenlabs.tts
```

## License

MIT

## Troubleshooting & Desktop Integration

### App not showing in GNOME menu?

1. **Update desktop database:**
   ```bash
   update-desktop-database ~/.local/share/applications
   ```

2. **Update icon cache:**
   ```bash
   gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor
   ```

3. **Restart GNOME Shell:** `Alt+F2`, type `r`, Enter.

4. **Log out and back in** if issues persist.

### Commands don't work?

Ensure `~/.local/bin` is in your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

### Where are files installed?

| File Type | Source | Installed Location |
|-----------|--------|-------------------|
| Python files | `src/*.py`, `src/lib/` | `~/.local/share/elevenlabs-tts/` |
| Desktop entries | `packaging/gnome/*.desktop` | `~/.local/share/applications/` |
| Icon | `packaging/gnome/elevenlabs-tts.svg` | `~/.local/share/icons/hicolor/scalable/apps/` |
| Commands | (generated) | `~/.local/bin/` |
