# Manga Downloader
Downloads manga from MangaDex, WeebCentral, Mangago, and DemonicScans with resume capability.

## Supported Sources
- MangaDex (mangadex.org)
- DemonicScans (demonicscans.org)
- WeebCentral (weebcentral.com)
- Mangago (mangago.me)

## Requirements
- Python 3.10+
- Firefox browser
- geckodriver

## Installation
Install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

Install Firefox and geckodriver if needed. On Linux:
```bash
sudo apt-get install firefox firefox-geckodriver
```
*(On Windows/Mac, download Firefox from mozilla.org and Geckodriver from GitHub, ensuring geckodriver is in your system PATH.)*

## Usage
1. Add URLs to `list.txt`, one per line:
```text
https://mangadex.org/title/91ffbbbe-4090-474b-b514-eced62b57be8/ori-no-naka
https://demonicscans.org/manga/Skeleton-Warrior
```

2. Run:
```bash
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
python main.py
```
Downloads are saved to the `downloads/` directory.

## Using Modules Directly
MangaDex:
```python
import mangadex_dl
mangadex_dl.download("https://mangadex.org/title/...")
```

DemonicScans:
```python
import demonicScans_dl
demonicScans_dl.download("https://demonicscans.org/manga/...")
```

WeebCentral:
```python
import weebCentral_dl
weebCentral_dl.download("https://weebcentral.com/series/...")
```

Mangago:
```python
import mangago_dl
mangago_dl.download("https://www.mangago.me/read-manga/...")
```

## Resume Capability
The script automatically resumes from the last incomplete chapter if you run it again. It tracks progress using hidden `.completed` files in each chapter folder. If a chapter download is interrupted, it will retry the missing pages on the next run.