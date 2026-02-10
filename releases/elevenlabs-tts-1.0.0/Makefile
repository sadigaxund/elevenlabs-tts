# Makefile for ElevenLabs TTS Application
# Supports both direct user installation and RPM packaging

# PREFIX is the final installation path
PREFIX ?= $(HOME)/.local
BINDIR = $(PREFIX)/bin
DATADIR = $(PREFIX)/share
APPDIR = $(DATADIR)/elevenlabs-tts
ICONDIR = $(DATADIR)/icons/hicolor/scalable/apps
DESKTOPDIR = $(DATADIR)/applications
METAINFODIR = $(DATADIR)/metainfo
LICENSEDIR = $(DATADIR)/licenses/elevenlabs-tts

# DESTDIR is used for staged installations (e.g., RPM buildroot)
DESTDIR ?=

# Local target paths (including DESTDIR)
TARGET_BINDIR = $(DESTDIR)$(BINDIR)
TARGET_APPDIR = $(DESTDIR)$(APPDIR)
TARGET_ICONDIR = $(DESTDIR)$(ICONDIR)
TARGET_DESKTOPDIR = $(DESTDIR)$(DESKTOPDIR)
TARGET_METAINFODIR = $(DESTDIR)$(METAINFODIR)
TARGET_LICENSEDIR = $(DESTDIR)$(LICENSEDIR)

# Source paths
SRC_DIR = src
PKG_GNOME = packaging/gnome
PKG_RPM = packaging/rpm

# Python files
PYTHON_FILES = elevenlabs_tts_cli.py elevenlabs_tts_settings.py
LIB_DIR = $(SRC_DIR)/lib

.PHONY: all install uninstall clean

all:
	@echo "Nothing to build. Run 'make install' to install."

install:
	@echo "📦 Installing ElevenLabs TTS..."
	
	# Create directories
	@mkdir -p $(TARGET_BINDIR)
	@mkdir -p $(TARGET_APPDIR)
	@mkdir -p $(TARGET_APPDIR)/lib
	@mkdir -p $(TARGET_ICONDIR)
	@mkdir -p $(TARGET_DESKTOPDIR)
	@mkdir -p $(TARGET_METAINFODIR)
	@mkdir -p $(TARGET_LICENSEDIR)
	
	# Install Python files
	@echo "  📄 Installing application files..."
	@install -m 755 $(SRC_DIR)/elevenlabs_tts_cli.py $(TARGET_APPDIR)/
	@install -m 755 $(SRC_DIR)/elevenlabs_tts_settings.py $(TARGET_APPDIR)/
	@cp -r $(LIB_DIR)/* $(TARGET_APPDIR)/lib/
	
	# Install icon
	@echo "  🎨 Installing icon..."
	@install -m 644 $(PKG_GNOME)/elevenlabs-tts.svg $(TARGET_ICONDIR)/elevenlabs-tts.svg
	
	# Install AppStream metadata
	@echo "  📋 Installing metadata..."
	@install -m 644 $(PKG_GNOME)/com.elevenlabs.tts.metainfo.xml $(TARGET_METAINFODIR)/
	
	# Install license
	@install -m 644 LICENSE $(TARGET_LICENSEDIR)/
	
	# Install desktop entries (with path substitution)
	# IMPORTANT: We substitute %INSTALL_DIR% with the FINAL $(APPDIR), not the staged path
	@echo "  🖥️  Installing desktop entries..."
	@sed 's|%INSTALL_DIR%|$(APPDIR)|g' $(PKG_GNOME)/elevenlabs-tts-settings.desktop > $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.settings.desktop
	@sed 's|%INSTALL_DIR%|$(APPDIR)|g' $(PKG_GNOME)/elevenlabs-tts.desktop > $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.desktop
	@chmod 644 $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.settings.desktop
	@chmod 644 $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.desktop
	
	# Create wrapper scripts
	@echo "  🔗 Creating wrapper scripts..."
	@echo '#!/bin/bash' > $(TARGET_BINDIR)/elevenlabs-tts
	@echo 'exec python3 $(APPDIR)/elevenlabs_tts_cli.py "$$@"' >> $(TARGET_BINDIR)/elevenlabs-tts
	@chmod 755 $(TARGET_BINDIR)/elevenlabs-tts
	@echo '#!/bin/bash' > $(TARGET_BINDIR)/elevenlabs-tts-settings
	@echo 'exec python3 $(APPDIR)/elevenlabs_tts_settings.py "$$@"' >> $(TARGET_BINDIR)/elevenlabs-tts-settings
	@chmod 755 $(TARGET_BINDIR)/elevenlabs-tts-settings
	
	# Update desktop database (only if not in DESTDIR/staged mode)
	@if [ -z "$(DESTDIR)" ]; then \
		echo "  🔄 Updating desktop database..."; \
		update-desktop-database $(TARGET_DESKTOPDIR) 2>/dev/null || true; \
		gtk-update-icon-cache -f -t $(DATADIR)/icons/hicolor 2>/dev/null || true; \
	fi
	
	@echo ""
	@echo "✅ Installation complete!"
	@echo ""
	@echo "📋 Next steps:"
	@echo "  1. Run 'elevenlabs-tts-settings' to configure API keys and voice"
	@echo "  2. Bind 'elevenlabs-tts' to a keyboard shortcut (e.g., Super+T)"
	@echo "     Settings → Keyboard → Custom Shortcuts"
	@echo "     Command: $(BINDIR)/elevenlabs-tts"
	@echo ""

uninstall:
	@echo "🗑️  Uninstalling ElevenLabs TTS..."
	@rm -rf $(TARGET_APPDIR)
	@rm -f $(TARGET_BINDIR)/elevenlabs-tts
	@rm -f $(TARGET_BINDIR)/elevenlabs-tts-settings
	@rm -f $(TARGET_ICONDIR)/elevenlabs-tts.svg
	@rm -f $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.settings.desktop
	@rm -f $(TARGET_DESKTOPDIR)/com.elevenlabs.tts.desktop
	@rm -f $(TARGET_METAINFODIR)/com.elevenlabs.tts.metainfo.xml
	@rm -rf $(TARGET_LICENSEDIR)
	@if [ -z "$(DESTDIR)" ]; then \
		update-desktop-database $(TARGET_DESKTOPDIR) 2>/dev/null || true; \
		gtk-update-icon-cache -f -t $(DATADIR)/icons/hicolor 2>/dev/null || true; \
	fi
	@echo "✅ Uninstallation complete"

clean:
	@echo "🧹 Cleaning build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "✅ Clean complete"
