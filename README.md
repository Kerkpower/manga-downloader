# Manga Downloader

Downloads manga from MangaDex, WeebCentral, and DemonicScans with resume capability.

## Supported Sources

- MangaDex (mangadex.org)
- DemonicScans (demonicscans.org)
- WeebCentral (weebcentral.com)

## Requirements

- Python 3.7+
- Firefox browser
- geckodriver

## Installation

Install dependencies:
```
pip install -r requirements.txt
```

Install Firefox and geckodriver if needed. On Linux:
```
sudo apt-get install firefox firefox-geckodriver
```

## Usage

1. Add URLs to `list.txt`, one per line:
```
https://mangadex.org/title/91ffbbbe-4090-474b-b514-eced62b57be8/ori-no-naka
https://demonicscans.org/manga/Skeleton-Warrior
```

2. Run:
```
python main.py
```

Downloads are saved to `downloads/` directory.

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

## Resume

The script automatically resumes from the last incomplete chapter if you run it again.
