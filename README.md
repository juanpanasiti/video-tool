# video-tool

A desktop application designed for trimming video files into named clips, extracting audio tracks, applying fade effects, burning subtitles, adding text watermarks, and concatenating clips. Built with [NiceGUI](https://nicegui.io/), [MoviePy](https://zulko.github.io/moviepy/), and [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

---

## Installation as a Global Tool (via `uv`)

You can install `video-tool` as a standalone global CLI tool using [uv](https://docs.astral.sh/uv/) on **Windows** and **Linux**. Once installed, the `vtool` and `video-tool` commands are available anywhere in your terminal.

### 1. Install `uv` (if not already installed)

- **Linux / macOS:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

After installing `uv`, restart your terminal or run `uv tool update-shell` so that the tool binary directory (`~/.local/bin` on Linux or `%USERPROFILE%\.local\bin` on Windows) is in your `PATH`.

---

### 2. Install directly from GitHub (without downloading the project)

You do **not** need to clone or download the repository to install `video-tool`. `uv` can install it directly from the Git repository on both Windows and Linux:

```bash
uv tool install git+https://github.com/<username>/video-tool.git
```

*(Replace `<username>` with the GitHub user or organization name.)*

- **Windows:** Native windows use the Microsoft Edge WebView2 runtime (built into Windows 10 and 11).
- **Linux:** Native windows automatically bundle a Qt 6.4 WebEngine backend so the desktop window works out of the box inside isolated `uv tool` environments. If you prefer opening the UI in your default web browser (e.g., on headless Linux or WSL), pass `--browser`:
  ```bash
  vtool --browser
  ```

---

### 3. Run Directly Without Installing (`uvx`)

If you want to run `video-tool` on-demand without installing it permanently:

```bash
uvx --from git+https://github.com/<username>/video-tool.git video-tool
```

Or in browser mode:

```bash
uvx --from git+https://github.com/<username>/video-tool.git video-tool --browser
```

---

### 4. Install from Local Source (if you cloned the repository)

If you have cloned or downloaded the project locally:

```bash
cd video-tool
uv tool install .
```

---

## Usage

Once installed, execute `vtool` or `video-tool` from any folder:

```bash
# Open using current directory as source, output to ./output
vtool

# Specify source directory containing videos
vtool /path/to/videos

# Specify source directory and custom output directory
vtool /path/to/videos --target /path/to/clips

# Run in default web browser instead of native desktop window
vtool --browser
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `SOURCE` | Positional argument: directory containing video files | Current working directory (`.`) |
| `-t`, `--target` | Target directory where exported clips and audio will be saved | `<SOURCE>/output` |
| `--browser` | Open the UI in the system's default browser instead of a native window | `False` (native window) |
| `-h`, `--help` | Show CLI help and options | — |

---

## Updating and Uninstalling

- **Update to the latest version:**
  ```bash
  uv tool upgrade video-tool
  ```

- **Uninstall:**
  ```bash
  uv tool uninstall video-tool
  ```

---

## Development

If you want to contribute or develop `video-tool`:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<username>/video-tool.git
   cd video-tool
   ```

2. **Sync dependencies and dev tools:**
   ```bash
   uv sync --extra dev
   ```

3. **Run code quality checks:**
   ```bash
   # Code formatting & linting
   uv run ruff check .

   # Type checking
   uv run mypy domain application infrastructure presentation main.py

   # Clean Architecture boundary validation
   uv run lint-imports

   # Run test suite
   uv run pytest
   ```

4. **Run local app:**
   ```bash
   uv run vtool
   ```
