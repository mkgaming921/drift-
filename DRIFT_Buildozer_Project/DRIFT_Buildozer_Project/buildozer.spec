[app]
title = DRIFT
package.name = drift
package.domain = org.mkgaming921
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,pygame
orientation = landscape
fullscreen = 1

[buildozer]
log_level = 2
warn_on_root = 1

[app:android]
android.api = 35
android.minapi = 23
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.bootstrap = sdl2
