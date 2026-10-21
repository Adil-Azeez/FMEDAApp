# Windows deployment

## Release build

Build on 64-bit Windows 10 (1809+) or Windows 11 using **64-bit Python 3.12**.
Python and Inno Setup are needed only on the release builder, never on end-user PCs.
From this application's root folder:

```bat
py -3.12 -m venv .build-venv
.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
build.bat
```

`build.bat` runs `pyinstaller --noconfirm FMEDA.spec`, preferring `.build-venv`.
`clean_build.bat` verifies and removes only `build`, `dist`, and `installer` within
this folder, then rebuilds. It refuses linked output directories. Keep custom
work files outside those three generated directories.

Change only `APP_VERSION` in `fmeda_tool/version.py` for a release. The UI, exports,
Windows EXE version resource and installer version all derive from it. Application
versioning does not change project, document, library or JSON schema versions.

## Installer

With Inno Setup 6.3+ installed on the builder:

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" FMEDA_Setup.iss
```

Output: `installer\FMEDA_Setup_v1.0.0.exe` for the initial version. Distribute that
one file. It installs the entire one-directory PyInstaller bundle, creates Start
Menu and desktop shortcuts, and registers an uninstaller. Users need no Python,
PyQt, Office, Git, editor, or development environment. Keep the installer AppId
unchanged for upgrades. It is a per-user installation and needs no elevation.

```text
%LOCALAPPDATA%\Programs\FMEDA Tool\
    FMEDA Tool.exe
    _internal\
        python312.dll, Python extensions and runtime libraries
        PyQt6\Qt6\... (Qt DLLs, qwindows, image and print plugins)
        data\fmeda.sqlite                 (release snapshot, read-only use)
        data\components_db.json
        data\seed\Combined_Exida_Component_library_version2.json
        fmeda_tool\db\schema.sql
        fmeda_tool\services\calculation_service.py
        assets\FMEDA.ico

%LOCALAPPDATA%\FMEDA Tool\
    fmeda.sqlite                          (operational, writable user copy)
    projects\                            (default JSON save directory)
    logs\
```

The executable must travel with its full `_internal` directory. The installer
does this automatically. A user can choose another project location with Save As.
Opening existing JSON files does not require placing them in the default folder.
Upgrades and uninstall preserve the operational database, projects and logs.

## Resources and database behavior

`fmeda_tool/paths.py` locates immutable resources in the source root in development
or `sys._MEIPASS` in a frozen build. Writable paths never depend on the launch
working directory. Development retains the existing root `data` and `logs` layout.
`FMEDA_DATA_DIR` overrides the writable data root; `FMEDA_DB_PATH` and the existing
test database override still take precedence for the SQLite path.

The spec makes a SQLite backup of the current `data/fmeda.sqlite`, including
committed WAL data, without altering that database. This preserves the current
library, including custom component records. Review that library before releasing
it to other users. If no operational database exists on the builder, the snapshot
is initialized from the existing seed JSON. User projects/backups, logs, tests,
scratch files and development environments are never included in the installer.

On first run, a new user's database is copied from the bundled snapshot. Existing
user databases are never replaced by a newer release snapshot. Existing schema
compatibility handling remains in DatabaseService. An unreadable installed-user
database produces a startup error and is preserved for recovery. For migration
from the source application, close it and copy its database to the new user's
operational path before first launch; keep a backup and copy any active SQLite
WAL consistently (or create a SQLite backup). Open projects from their existing
locations or copy them separately.

The complete import/asset audit covered all 63 original application Python files.
Runtime third-party dependencies are PyQt6, pydantic/pydantic-core and openpyxl;
SQLite is Python's bundled extension. PDF generation uses QtPrintSupport, with no
Office, reportlab, browser, or external PDF engine. There were no external report
templates, images, icons or configuration files in the original application;
reports and styles are defined in Python. The new Windows icon is included, and
the spec also collects optional root `icons`, `images`, `templates` and `config`
directories if later added. The duplicate seed filename is not needed: the
canonical seed is included. Calculation source is bundled for Formula Reference
implementation links. No engineering calculation code has been changed.

## Verification

Run the complete existing pytest suite with pytest and pytest-qt in a test
environment. Tests use isolated SQLite databases.

```bat
.build-venv\Scripts\python.exe -m pip install pytest pytest-qt
set QT_QPA_PLATFORM=offscreen
.build-venv\Scripts\python.exe -m pytest tests -q
set QT_QPA_PLATFORM=
```

The EXE includes an opt-in release smoke check. Supply a **new, empty/nonexistent
output directory**; it refuses an existing directory to avoid replacing data.
Run it from a different working directory to test resource independence:

```powershell
$exe = (Resolve-Path '.\dist\FMEDA Tool\FMEDA Tool.exe').Path
$output = Join-Path $PWD 'scratch\release-check'
$process = Start-Process -FilePath $exe -ArgumentList @('--deployment-check', "`"$output`"") -WorkingDirectory $env:TEMP -WindowStyle Hidden -Wait -PassThru
Get-Content (Join-Path $output 'deployment-check.json')
if ($process.ExitCode -ne 0) { throw 'Deployment check failed' }
```

This checks packaged startup, SQLite integrity and persistence, custom components,
project save/open/Save As, diagnostic measures, deviations, mitigations, Formula
Reference and its source links, icon loading, actual Excel and PDF exports. All
test data remains in that output folder. Normal launch still opens the usual UI.
Release validation should also install the generated setup on a clean Windows
test account/VM without Python or development tools, exercise normal UI workflows,
upgrade over an earlier build, and confirm user files survive uninstall. The
installer compiler and a clean-machine installation test are separate from the
automated application tests. Sign the EXE and installer with your organization's
code-signing certificate as part of your release process if available.

Packaging references: [PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html),
[runtime resource paths](https://www.pyinstaller.org/en/stable/runtime-information.html),
[Inno Setup per-user mode](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).

### Preparation verification (2026-10-08)

- Full suite: 339 passed, 1 skipped, 8 existing pydantic deprecation warnings.
- PyInstaller 6.22.0 Windows x64 build succeeded; EXE ProductVersion/FileVersion: 1.0.0.
- The frozen executable passed the deployment check from an unrelated working
  directory with Python paths removed and PATH restricted to Windows System32.
- Normal console-free startup passed separately using isolated writable data;
  the database, log and default project directories were created successfully.
- Inno Setup is not installed on this build host: installer compilation and
  clean-machine installation/upgrade/uninstall testing remain release-builder steps.
