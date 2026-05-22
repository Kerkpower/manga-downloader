"""
WeebCentral Downloader Module

A module to download manga from WeebCentral with resume capability.

Usage:
    import weebcentral_dl
    weebcentral_dl.download("https://weebcentral.com/series/01J76XYCERXE60T7FKXVCCAQ0H/Jujutsu-Kaisen")
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Base download directory
BASE_DIR = Path.cwd() / "downloads" / "WeebCentral"

# Headers for requests
HEADER_1 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
    "Referer": "https://weebcentral.com/"
}
HEADER_2 = {
    "Hx-Request": "true",
    "Hx-Target": "chapter-list",
    "Sec-Ch-Ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
    "Referer": "https://weebcentral.com/"
}


def _get_session() -> requests.Session:
    """Create and configure a requests Session with retry strategy."""
    session = requests.Session()

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


def _extract_series_id(url: str) -> str:
    """Extract series ID from WeebCentral URL."""
    match = re.search(r'/series/([^/]+)', url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract series ID from URL: {url}")


def _extract_chapter_id(url: str) -> str | None:
    """Extract chapter ID from WeebCentral chapter URL."""
    match = re.search(r'/chapters/([^/]+)', url)
    if match:
        return match.group(1)
    return None


def _sanitize_filename(name: str) -> str:
    """Remove invalid characters for directory/file names."""
    keepchars = (' ', '-', '_', '.')
    return "".join(c for c in name if c.isalnum() or c in keepchars).rstrip()


def _get_manga_info(session: requests.Session, series_url: str) -> tuple[str, str]:
    """Get manga title and series ID from the series page."""
    try:
        r = session.get(series_url, headers=HEADER_1, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')

        # Extract title
        title_elem = soup.find('h1', class_='text-2xl') or soup.find('h1')
        if title_elem:
            manga_title = _sanitize_filename(title_elem.text.strip())
        else:
            raise ValueError("Could not find manga title")

        # Extract series ID from URL
        series_id = _extract_series_id(series_url)
        return manga_title, series_id

    except (requests.RequestException, ValueError) as e:
        raise ValueError(f"Error fetching manga info: {e!r}")


def _get_chapters(session: requests.Session, series_url: str) -> dict[str, str]:
    """Get dictionary of chapters from the series page."""
    try:
        series_id = _extract_series_id(series_url)
        full_chapter_list_url = f"https://weebcentral.com/series/{series_id}/full-chapter-list"
        print(f"Fetching full chapter list from: {full_chapter_list_url}")

        r = session.get(full_chapter_list_url, headers=HEADER_2, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')

        chapters = {}
        chapter_links = soup.find_all('a', href=re.compile(r'/chapters/'))

        for link in chapter_links:
            chapter_url = link.get('href')
            if not chapter_url.startswith('http'):
                chapter_url = 'https://weebcentral.com' + chapter_url

            # Target the specific empty-class span that holds the chapter label
            chapter_span = link.find('span', class_='')
            if chapter_span:
                chapter_text = chapter_span.text.strip()
                # Extract the trailing number (int or decimal) from whatever prefix is used
                match = re.search(r'([\d.]+)$', chapter_text)
                if match:
                    chapter_num = match.group(1)
                    chapters[chapter_num] = chapter_url
                else:
                    # No number found — use sanitised full text as fallback key
                    safe_text = _sanitize_filename(chapter_text)
                    print(f"Warning: No number found in '{chapter_text}', using '{safe_text}' as key")
                    chapters[safe_text] = chapter_url

        return chapters

    except (requests.RequestException, ValueError) as e:
        raise ValueError(f"Error fetching chapters: {e!r}")


def _is_chapter_complete(manga_title: str, series_id: str, chapter_num: str, chapter_id: str) -> bool:
    """Check if a chapter is completely downloaded."""
    chapter_path = BASE_DIR / f"{manga_title} - {series_id}" / f"{chapter_num} - {chapter_id}"
    return (chapter_path / ".completed").exists()


def _download_image(session: requests.Session, img_url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success, False on failure."""
    try:
        img_r = session.get(img_url, headers=HEADER_1, timeout=30)
        img_r.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(img_r.content)
        return True
    except (requests.RequestException, IOError) as e:
        print(f"Error downloading image {save_path.name}: {e!r}")
        return False


def _download_chapter(session: requests.Session, manga_title: str, series_id: str, chapter_num: str, chapter_url: str):
    """Download a single chapter's pages concurrently."""
    chapter_id = _extract_chapter_id(chapter_url)
    if not chapter_id:
        print(f"Error: Could not extract chapter ID from {chapter_url}")
        return

    chapter_path = BASE_DIR / f"{manga_title} - {series_id}" / f"{chapter_num} - {chapter_id}"
    chapter_path.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_num}...")
        images_url = f"https://weebcentral.com/chapters/{chapter_id}/images"

        r = session.get(
            images_url,
            headers={
                **HEADER_1,
                "HX-Request": "true",
                "HX-Current-URL": f"https://weebcentral.com/chapters/{chapter_id}",
            },
            params={
                "is_prev": "False",
                "current_page": "1",
                "reading_style": "long_strip",
            },
            timeout=30
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.content, 'html.parser')
        manga_images = [img for img in soup.find_all('img') if 'Page' in img.get('alt', '')]

        if not manga_images:
            print(f"Warning: No manga images found for chapter {chapter_num}")
            return

        # Prepare image URLs and destination paths
        download_tasks = []
        for idx, img in enumerate(manga_images, 1):
            src = img.get('src')
            if not src:
                continue

            filename = src.split('/')[-1]
            if not filename or '?' in filename:
                # Fallback naming logic
                ext = '.png'
                if '.jpg' in src or '.jpeg' in src:
                    ext = '.jpg'
                elif '.webp' in src:
                    ext = '.webp'
                filename = f"page_{idx:03d}{ext}"

            save_path = chapter_path / filename
            download_tasks.append((src, save_path))

        # Download images concurrently
        downloaded = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                executor.submit(_download_image, session, url, path): url
                for url, path in download_tasks
            }

            for future in as_completed(future_to_url):
                if future.result():
                    downloaded += 1
                time.sleep(0.1)  # Small delay between thread spawns to be polite

        print(f"Downloaded Chapter {chapter_num}: {downloaded}/{len(manga_images)} pages.")

        # Only mark as complete if all pages downloaded successfully
        if downloaded == len(manga_images):
            (chapter_path / ".completed").touch()
        else:
            print(f"Warning: Chapter {chapter_num} is incomplete. Will retry on next run.")

    except (requests.RequestException, ValueError) as e:
        print(f"Error downloading chapter {chapter_num}: {e!r}")


def _sort_chapters_key(item: tuple[str, str]):
    """Key function for sorting chapters. Attempts float, falls back to string."""
    try:
        return float(item[0])
    except ValueError:
        return item[0]


def download(series_url: str) -> None:
    """
    Download manga from WeebCentral.
    Args:
        series_url (str): Full WeebCentral series URL
    Example:
        >>> import weebcentral_dl
        >>> weebcentral_dl.download("https://weebcentral.com/series/01J76XYCERXE60T7FKXVCCAQ0H/Jujutsu-Kaisen")
    """
    session = _get_session()

    try:
        # Get manga info
        manga_title, series_id = _get_manga_info(session, series_url)
        print(f"Downloading: {manga_title}")

        # Get chapters
        chapters = _get_chapters(session, series_url)
        if not chapters:
            print("No chapters found!")
            return

        # Sort chapters properly
        sorted_chapters = dict(sorted(chapters.items(), key=_sort_chapters_key))

        # Find where to resume
        resume_from = None
        for chapter_num, chapter_url in sorted_chapters.items():
            chapter_id = _extract_chapter_id(chapter_url)
            if chapter_id and not _is_chapter_complete(manga_title, series_id, chapter_num, chapter_id):
                resume_from = chapter_num
                break

        if resume_from is not None:
            print(f"Resuming from chapter {resume_from}")
        else:
            print("All chapters already downloaded and complete!")
            return

        # Download from resume point onwards
        for chapter_num, chapter_url in sorted_chapters.items():
            chapter_id = _extract_chapter_id(chapter_url)
            if chapter_id and _is_chapter_complete(manga_title, series_id, chapter_num, chapter_id):
                print(f"Skipping chapter {chapter_num} (already complete)")
                continue
            _download_chapter(session, manga_title, series_id, chapter_num, chapter_url)

        print(f"Download complete for: {manga_title}")

    except ValueError as e:
        print(f"Error: {e!r}")
    except requests.RequestException as e:
        print(f"Network Error: Failed to complete downloads. {e!r}")


if __name__ == "__main__":
    ...