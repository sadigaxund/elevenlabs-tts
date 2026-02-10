Name:           elevenlabs-tts
Version:        1.0.0
Release:        1%{?dist}
Summary:        Settings application and CLI for ElevenLabs TTS

License:        MIT
URL:            https://github.com/sadigaxund/elevenlabs-tts
Source0:        https://github.com/sadigaxund/elevenlabs-tts/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
BuildRequires:  make

Requires:       python3
Requires:       python3-gobject
Requires:       python3-requests
Requires:       python3-dasbus
Requires:       python3-mutagen
Requires:       gtk4
Requires:       libadwaita
Requires:       gstreamer1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good

%description
ElevenLabs TTS brings professional-grade text-to-speech to your desktop
using the Eleven Labs AI API. Features include high-quality AI voices,
smart caching, GNOME media controls integration, and keyboard shortcut support.
This package provides the settings application and CLI tool.

%prep
%autosetup -n %{name}-%{version}

%build

%install
%make_install

desktop-file-validate %{buildroot}%{_datadir}/applications/com.elevenlabs.tts.settings.desktop
desktop-file-validate %{buildroot}%{_datadir}/applications/com.elevenlabs.tts.desktop

appstream-util validate-relax --nonet %{buildroot}%{_datadir}/metainfo/com.elevenlabs.tts.metainfo.xml

%files
%license LICENSE
%{_bindir}/elevenlabs-tts
%{_bindir}/elevenlabs-tts-settings
%{_datadir}/elevenlabs-tts/
%{_datadir}/applications/com.elevenlabs.tts.settings.desktop
%{_datadir}/applications/com.elevenlabs.tts.desktop
%{_datadir}/icons/hicolor/scalable/apps/elevenlabs-tts.svg
%{_datadir}/metainfo/com.elevenlabs.tts.metainfo.xml

%post
/usr/bin/update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor >/dev/null 2>&1 || :

%postun
/usr/bin/update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor >/dev/null 2>&1 || :

%changelog
* Tue Feb 10 2026 Sadig Akhund <sadigaxund@gmail.com> - 1.0.0-1
- Initial release
- CLI tool for keyboard shortcuts with MPRIS support
- Settings UI for configuration