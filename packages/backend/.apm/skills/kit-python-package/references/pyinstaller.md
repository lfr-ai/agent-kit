# Freezing applications with PyInstaller

PyInstaller bundles a Python application, its dependencies, and an interpreter
into a folder or a single executable for users without Python. It is a
distribution step for applications, not for libraries; publish libraries as
wheels.

## One-folder versus one-file

| Aspect | One-folder (`--onedir`, default) | One-file (`--onefile`) |
| --- | --- | --- |
| Output | `dist/app/app.exe` plus `dist/app/_internal/` | Single `dist/app.exe` |
| Start-up | Fast; runs in place | Slower; unpacks to a temporary `_MEI*` folder on every start |
| `sys._MEIPASS` | Path of `_internal` inside the bundle | Path of the temporary extraction folder |
| Writable data next to the app | Survives restarts | Lost when the process exits |
| Antivirus false positives | Less common | More common (self-extracting behavior) |
| Updates | Replace changed files | Replace the whole executable |
| Distribution | Zip or installer | Copy one file |

Prefer one-folder plus an installer or archive for anything non-trivial; choose
one-file when single-file delivery is a hard requirement and start-up time is
acceptable.

## Build from a spec file

Generate once with `pyi-makespec`, then commit the spec and build with
`pyinstaller app.spec --clean --noconfirm`. The spec is Python code that creates
`Analysis`, `PYZ`, `EXE`, and (for one-folder) `COLLECT`. Command-line options
other than paths, `--clean`, `--noconfirm`, `--log-level`, and `--upx-dir` are
ignored when building from a spec. The [spec template](../assets/app.spec.template)
supports both modes through an environment switch.

## Hidden imports

PyInstaller follows static `import` statements. Modules imported dynamically
(`importlib.import_module`, plugin entry points, string-configured backends,
some optional dependencies) are missed and fail at runtime with
`ModuleNotFoundError`.

- Add them with `hiddenimports=[...]` in the spec, or
  `collect_submodules("order_tools.exporters")` for plugin packages.
- Many popular libraries ship hooks (in `pyinstaller-hooks-contrib`); keep it
  updated.
- Packages that call `importlib.metadata.version()` or discover entry points need
  their distribution metadata: `copy_metadata("order-tools")`.
- Diagnose with the `warn-*.txt` and `xref-*.html` files in the build directory,
  and by running the frozen app's full smoke test, not just `--help`.

## Data files

- Collect package data with `collect_data_files("order_tools")` so files land at
  the same relative path as in the installed package. Then
  `importlib.resources` and `Path(__file__).parent` both work in the bundle.
- Use `datas=[("assets/logo.png", "assets")]` for files outside packages; the
  second element is the destination folder inside the bundle.
- Never write into the bundle. Store user data and logs under the platform's
  user data directory; in one-file mode, bundle files are temporary copies.
- Detect frozen mode with `getattr(sys, "frozen", False)` only when behavior must
  differ; prefer resource APIs that work in both modes.

## Binaries and platforms

- PyInstaller is not a cross-compiler. Build each target operating system and
  architecture on that platform (CI matrix runners).
- Build on the oldest OS version you support; newer system libraries may be
  required by binaries built on newer systems.
- Disable UPX (`upx=False`) unless you have measured a benefit; compressed
  binaries break on some platforms and increase false positives.

## Code signing

- Unsigned executables trigger operating system warnings (SmartScreen on
  Windows, Gatekeeper on macOS) and are more likely to be quarantined.
- Windows: sign the executable (and installer) with an Authenticode certificate
  using `signtool sign /fd sha256 /tr <timestamp-url> /td sha256 <file>` after
  the build. Always timestamp so signatures outlive the certificate.
- macOS: set `codesign_identity` and `entitlements_file` in the spec or sign
  afterwards with `codesign`, then notarize with `xcrun notarytool` and staple.
- Keep signing keys in a hardware-backed or cloud signing service reachable only
  from the release pipeline; never in the repository or on developer machines.
- Signing is an operator-approved release step; authoring sessions prepare the
  pipeline, they do not hold keys.

## Verification

1. Build in CI from a clean checkout with locked dependencies.
2. Run the frozen executable's smoke tests on each target platform, including a
   path that loads data files and every dynamically imported plugin.
3. Record the bundle file list and checksums as release evidence.
4. Scan the output for accidentally bundled secrets, `.env` files, and test data.

The [CI build template](../assets/ci-build.yml.template) builds wheels and
frozen executables per platform and runs these smoke checks.

## Sources

- <https://pyinstaller.org/en/stable/operating-mode.html>
- <https://pyinstaller.org/en/stable/spec-files.html>
- <https://pyinstaller.org/en/stable/runtime-information.html>
- <https://pyinstaller.org/en/stable/when-things-go-wrong.html>
- <https://pyinstaller.org/en/stable/hooks.html>
- <https://pyinstaller.org/en/stable/usage.html>
- <https://pyinstaller.org/en/stable/feature-notes.html>
- <https://learn.microsoft.com/windows/win32/seccrypto/signtool>
- <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution>
