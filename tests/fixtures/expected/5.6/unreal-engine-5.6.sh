#! /usr/bin/bash

# Launcher for unreal-engine-src-5.6 (Unreal Engine 5.6).
# Inspired by Alexis Belmonte's upstream unreal-engine.sh.

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: Run this as an unprivileged user; not as root."
    return
fi

if [ -d "${HOME}/.steam/bin" ] && [ ! -L "${HOME}/.steampath" ]; then
    ln -s "${HOME}/.steam/bin" "${HOME}/.steampath"
elif [ ! -d "${HOME}/.steam/bin" ] && [ ! -L "${HOME}/.steampath" ]; then
    mkdir -p "${HOME}/.steam/bin"
    ln -s "${HOME}/.steam/bin" "${HOME}/.steampath"
fi

# Per-minor user-config dir
if [ ! -d "${HOME}/.config/Epic/UnrealEngine/5.6/Intermediate/" ]; then
    mkdir -p "${HOME}/.config/Epic/UnrealEngine/5.6/Intermediate/"
fi

# Preserve upstream typo path (.cnfig) for compatibility with anything that already wrote there
if [ ! -d "${HOME}/.cnfig/Epic/UnrealEngine/5.6/Intermediate/" ]; then
    mkdir -p "${HOME}/.cnfig/Epic/UnrealEngine/5.6/Intermediate/"
fi

if [ ! -f "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop" ]; then
    cp "/usr/share/applications/com.unrealengine.UE5_6Editor.desktop" \
       "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop"
fi

UE5desktopFileChecksum="$(sha256sum "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop" | cut -f 1 -d ' ')"

if [ "${UE5desktopFileChecksum}" == "ChecksumPlaceholder" ]; then
    UE5editorLocation="$(find InstalledLocationPlaceholder -type f -iname 'UnrealEditor')"
    UE5editorPath="$(echo ${UE5editorLocation/UnrealEditor/})"

    sed -i "7c\\Exec=${UE5editorLocation} %F" "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop"
    sed -i "14c\\Path=${UE5editorPath}" "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop"
fi

gio launch "${HOME}/.local/share/applications/com.unrealengine.UE5_6Editor.desktop"
