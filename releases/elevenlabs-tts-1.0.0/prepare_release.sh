#!/bin/bash
# Script to prepare source tarball and build RPM
# Usage: ./prepare_release.sh

VERSION="1.0.0"
NAME="elevenlabs-tts"
FULLNAME="${NAME}-${VERSION}"

echo "📦 Preparing release ${FULLNAME}..."

# Setup RPM build environment
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Create temporary directory for tarball
echo "  📂 Creating source directory..."
rm -rf "/tmp/${FULLNAME}"
mkdir -p "/tmp/${FULLNAME}"

# Copy files
echo "  📄 Copying source files..."
cp -r src/ packaging/ Makefile LICENSE README.md pyproject.toml requirements.txt "/tmp/${FULLNAME}/"

# Create tarball
echo "  🗜️  Creating tarball..."
cd /tmp
tar -czf "${FULLNAME}.tar.gz" "${FULLNAME}"
mv "${FULLNAME}.tar.gz" ~/rpmbuild/SOURCES/
cd - > /dev/null

# Copy spec file
echo "  📄 Copying spec file..."
cp packaging/rpm/elevenlabs-tts.spec ~/rpmbuild/SPECS/

echo ""
echo "✅ Preparation complete!"
echo "   Source: ~/rpmbuild/SOURCES/${FULLNAME}.tar.gz"
echo "   Spec:   ~/rpmbuild/SPECS/${NAME}.spec"
echo ""
echo "🚀 To build the RPM, run:"
echo "   rpmbuild -ba ~/rpmbuild/SPECS/${NAME}.spec"
echo ""
echo "📦 The RPM will be in: ~/rpmbuild/RPMS/noarch/"
