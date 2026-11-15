# DRIFT Mobile

Android-oriented touch-control adaptation of the supplied Pygame DRIFT game.

## Included
- Landscape fullscreen layout
- Tap-to-play title screen
- On-screen left/right, gas, brake and handbrake controls
- On-screen reset control
- Original drift physics, scoring, cones, tyre marks, smoke and synthesized audio retained

## Build the APK with GitHub Actions (recommended on Windows)

This project includes `.github/workflows/android.yml` so GitHub can build the APK on an Ubuntu runner with the Android SDK/NDK and Buildozer.

1. Extract this ZIP.
2. Create a new **private** repository on GitHub.
3. Upload the contents of the `drift_android` folder to the repository (the `.github` folder must be included) and commit them to `main`.
4. Open the repository's **Actions** tab. Select **Build DRIFT Android APK**, then choose **Run workflow** if it has not started automatically.
5. Wait for the workflow to finish. Open the successful run and download the artifact named **DRIFT-Android-debug-APK**.
6. Extract the artifact; it contains the debug APK. Transfer it to your Android phone and install it. Android may ask you to allow installation from the app you used to open the file.

The workflow builds a debug APK, not a Play Store release. The APK must be tested on a real Android device.

## Build locally on Linux

Install Java, Android SDK/NDK and Buildozer, then run:

```bash
python3 -m pip install buildozer cython==0.29.36
buildozer android debug
```

The APK is written to `bin/` after a successful build.
