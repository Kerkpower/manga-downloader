"""
DemonicScans Downloader Module

A module to download manga from DemonicScans with resume capability.

Usage:
    import demonicScans_dl
    demonicScans_dl.download("https://demonicscans.org/manga/S%25252DClass-Hunter-Heals-with-Monsters")
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
BASE_DIR = Path.cwd() / "downloads" / "demonicScans"


def _get_session() -> requests.Session:
    """Create and configure a requests Session with retry strategy."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        # Crucial for manga sites: prevents 403 Forbidden on image CDNs
        'Referer': 'https://demonicscans.org/'
    })

    # Configure retries and connection pooling
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def _is_chapter_complete(manga_title: str, chapter_num: str) -> bool:
    """Check if a chapter is completely downloaded."""
    chapter_path = BASE_DIR / manga_title / chapter_num
    return (chapter_path / ".completed").exists()


def _download_image(session: requests.Session, img_url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success, False on failure."""
    try:
        img_response = session.get(img_url, timeout=15)
        img_response.raise_for_status()

        # Determine extension dynamically to prevent JPG/WebP/PNG corruption
        # Try Content-Type header first, fallback to URL path
        content_type = img_response.headers.get('Content-Type', '')
        if 'image/' in content_type:
            ext = content_type.split('/')[-1].strip()
            # Clean up things like 'jpeg; charset=utf-8'
            if ';' in ext: ext = ext.split(';')[0]
        else:
            ext = Path(urlparse(img_url).path).suffix.lstrip('.') or 'jpg'

        if ext == 'jpeg': ext = 'jpg' # Normalize

        final_path = save_path.with_suffix(f'.{ext}')

        with open(final_path, 'wb') as f:
            f.write(img_response.content)

        return True

    except (requests.RequestException, IOError) as e:
        print(f"Error downloading {img_url}: {e!r}")
        return False


def _download_chapter(session: requests.Session, manga_title: str, chapter_num: str, chapter_url: str):
    """Download a single chapter's pages concurrently."""
    chapter_path = BASE_DIR / manga_title / chapter_num
    chapter_path.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_num}...")
        full_url = f"https://demonicscans.org{chapter_url}" if not chapter_url.startswith('http') else chapter_url

        response = session.get(full_url, timeout=10)
        response.raise_for_status()
        chapter_soup = BeautifulSoup(response.text, 'html.parser')

        main_div = chapter_soup.find('div', class_='main-width center-m')
        if not main_div:
            print(f"Error: Could not find content for chapter {chapter_num}")
            return

        images = main_div.find_all('img', class_='imgholder')
        if not images:
            print(f"Warning: No images found for chapter {chapter_num}")
            return

    except requests.RequestException as e:
        print(f"Error fetching chapter data for {chapter_num}: {e!r}")
        return

    # Prepare image URLs
    img_urls = []
    for img in images:
        img_url = img.get('src')
        if not img_url:
            continue
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://demonicscans.org' + img_url
        img_urls.append(img_url)

    # Download images concurrently (up to 5 at a time)
    downloaded = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {
            executor.submit(_download_image, session, url, chapter_path / str(i)): url
            for i, url in enumerate(img_urls, start=1)
        }

        for future in as_completed(future_to_url):
            if future.result():
                downloaded += 1
            time.sleep(0.1)  # Small delay between thread spawns to be polite

    print(f"Downloaded Chapter {chapter_num}: {downloaded}/{len(images)} pages.")

    if downloaded == len(images):
        (chapter_path / ".completed").touch()
    else:
        print(f"Warning: Chapter {chapter_num} is incomplete. Will retry on next run.")


def _download_series(session: requests.Session, manga_title: str, chapters_data: list):
    """Download a series with numbered chapters."""
    chapters = {}
    for chapter_num_str, chapter_num_sort, chapter_url in chapters_data:
        chapters[chapter_num_str] = (chapter_num_sort, chapter_url)

    # Sort by numeric value to ensure proper order (1, 2, 10, not 1, 10, 2)
    chapters = dict(sorted(chapters.items(), key=lambda x: x[1][0]))

    for chapter_num_str, (_, chapter_url) in chapters.items():
        if _is_chapter_complete(manga_title, chapter_num_str):
            print(f"Skipping chapter {chapter_num_str} (already complete)")
            continue

        _download_chapter(session, manga_title, chapter_num_str, chapter_url)


def download(manga_url: str) -> None:
    """
    Download manga from DemonicScans.
    Args:
        manga_url (str): Full DemonicScans manga URL
    """
    session = _get_session()

    try:
        response = session.get(manga_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title = soup.find('h1', class_='border-box big-fat-titles')
        manga_title = title.text.strip() if title else None

        if not manga_title:
            raise ValueError("Could not extract manga title from page")

        # Sanitize title for filesystem (remove invalid chars like /, \, :, etc.)
        keepchars = (' ', '-', '_', '.')
        manga_title = "".join(c for c in manga_title if c.isalnum() or c in keepchars).rstrip()

        print(f"Downloading: {manga_title}")

        # Extract chapter data
        chapters_list = soup.find('div', id='chapters-list')
        if not chapters_list:
            raise ValueError("Could not find chapters list on page")

        chapter_data = []
        list_items = chapters_list.find_all('li')

        for li in list_items:
            link = li.find('a')
            if link and link.get('href'):
                chapter_url = link.get('href')
                parsed = urlparse(chapter_url)
                params = parse_qs(parsed.query)

                if 'chapter' in params:
                    chapter_num = params['chapter'][0]
                    try:
                        chapter_num_sort = float(chapter_num) if '.' in chapter_num else int(chapter_num)
                        chapter_data.append((chapter_num, chapter_num_sort, chapter_url))
                    except ValueError:
                        continue

        if not chapter_data:
            raise ValueError("No chapters found on page")

        chapter_data.sort(key=lambda x: x[1])
        _download_series(session, manga_title, chapter_data)
        print(f"Download complete for: {manga_title}")

    except ValueError as e:
        print(f"Parsing Error: {e!r}")
    except requests.RequestException as e:
        print(f"Network Error: Failed to connect to DemonicScans. {e!r}")

if __name__ == "__main__":
    ...