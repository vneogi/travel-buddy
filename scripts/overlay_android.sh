#!/usr/bin/env bash
# Overlay Travel Buddy Android customizations after flutter create.
# Run from the mobile/ directory.
set -euo pipefail

MANIFEST="android/app/src/main/AndroidManifest.xml"
APP_BUILD="android/app/build.gradle"

# --- 1. INTERNET permission on the main manifest ---
if ! grep -q 'android.permission.INTERNET' "$MANIFEST"; then
  sed -i '/<manifest/a\    <uses-permission android:name="android.permission.INTERNET"/>' "$MANIFEST"
  echo "overlay: added INTERNET permission to main manifest"
else
  echo "overlay: INTERNET permission already present"
fi

# --- 2. Disable minify for the first field-test APK ---
if grep -q 'minifyEnabled' "$APP_BUILD"; then
  sed -i 's/minifyEnabled.*/minifyEnabled = false/' "$APP_BUILD"
  echo "overlay: set minifyEnabled = false"
fi
# Remove shrinkResources if present (requires minify)
sed -i '/shrinkResources/d' "$APP_BUILD"

echo "overlay: complete"
