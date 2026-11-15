DRIFT - Android Buildozer project

IMPORTANT:
This project packages the supplied Pygame game using Buildozer. It is a
starting build configuration, not a guarantee that the Pygame Android recipe
will compile successfully on the first run. The original game currently uses
keyboard controls; touchscreen controls have not yet been added.

HOW TO USE:
1. Extract this ZIP.
2. Upload the CONTENTS of the DRIFT_Buildozer_Project folder to your GitHub
   repository (main.py, buildozer.spec, and .github/workflows/android.yml).
3. In GitHub, open Actions and run "Build DRIFT Android APK", or push a commit.
4. When the workflow completes, open its run, scroll to Artifacts, and download
   DRIFT-Android-APK. Extract it to get the APK.

The workflow uses Buildozer directly. It does not run a Gradle-version
detection action, which caused the earlier "No file ... matched" error.
