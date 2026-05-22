"""
MangaDex Downloader Module

A simple module to download manga from MangaDex with resume capability.

Usage:
    import mangadex_dl
    mangadex_dl.download("https://mangadex.org/title/d4c562e3-3bcd-4a8f-b508-6a6cec4a9473/faceapp-ts-manga")
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.mangadex.org"
BASE_DIR = Path.cwd() / "downloads" / "mangaDex"
LANGUAGES = ["en"]


def _get_session() -> requests.Session:
    """Create and configure a requests Session with retry strategy."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://mangadex.org/"  # Crucial for MangaDex@Home servers
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


def _sanitize_filename(name: str) -> str:
    """Remove invalid characters for directory/file names."""
    keepchars = (' ', '-', '_', '.')
    return "".join(c for c in name if c.isalnum() or c in keepchars).rstrip()


def _is_chapter_complete(manga_title: str, manga_id: str, chapter_identifier: str, chapter_id: str) -> bool:
    """Check if a chapter is completely downloaded."""
    chapter_path = BASE_DIR / f"{manga_title} - {manga_id}" / f"{chapter_identifier} - {chapter_id}"
    return (chapter_path / ".completed").exists()


def _download_image(session: requests.Session, img_url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success, False on failure."""
    try:
        r = session.get(img_url, timeout=30)
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(r.content)
        return True
    except (requests.RequestException, IOError) as e:
        print(f"Error downloading image {save_path.name}: {e!r}")
        return False


def _download_chapter(session: requests.Session, manga_title: str, manga_id: str, chapter_identifier: str, chapter_id: str):
    """Download a single chapter's pages concurrently."""
    chapter_path = BASE_DIR / f"{manga_title} - {manga_id}" / f"{chapter_identifier} - {chapter_id}"
    chapter_path.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_identifier}...")
        chapter_r = session.get(f"{BASE_URL}/at-home/server/{chapter_id}", timeout=30)
        chapter_r.raise_for_status()
        chapter_json = chapter_r.json()

        host = chapter_json["baseUrl"]
        chapter_hash = chapter_json["chapter"]["hash"]
        data = chapter_json["chapter"]["data"]
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Error fetching chapter data for {chapter_identifier}: {e!r}")
        return

    # Prepare download tasks
    download_tasks = []
    for page in data:
        img_url = f"{host}/data/{chapter_hash}/{page}"
        save_path = chapter_path / page
        download_tasks.append((img_url, save_path))

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
            time.sleep(0.05)  # Tiny delay between spawns to be polite

    print(f"Downloaded Chapter {chapter_identifier}: {downloaded}/{len(data)} pages.")

    # Only mark as complete if all pages downloaded successfully
    if downloaded == len(data):
        (chapter_path / ".completed").touch()
    else:
        print(f"Warning: Chapter {chapter_identifier} is incomplete. Will retry on next run.")


def _sort_chapters_key(item: tuple[str, str]):
    """Key function for sorting chapters. Attempts float, falls back to string."""
    try:
        return float(item[0])
    except (ValueError, TypeError):
        return str(item[0])


def _download_series(session: requests.Session, manga_title: str, manga_id: str, chapters_data: list):
    """Download a series with numbered chapters."""
    chapters = {}
    for chapter_data in chapters_data:
        chapter_num = chapter_data["attributes"]["chapter"]
        chapter_id = chapter_data["id"]
        chapters[chapter_num] = chapter_id

    chapters = dict(sorted(chapters.items(), key=_sort_chapters_key))

    for chapter_num, chapter_id in chapters.items():
        if _is_chapter_complete(manga_title, manga_id, chapter_num, chapter_id):
            print(f"Skipping chapter {chapter_num} (already complete)")
            continue
        _download_chapter(session, manga_title, manga_id, chapter_num, chapter_id)


def _download_oneshots(session: requests.Session, manga_title: str, manga_id: str, chapters_data: list):
    """Download oneshots or chapters without numbers."""
    for chapter_data in chapters_data:
        chapter_id = chapter_data["id"]
        if _is_chapter_complete(manga_title, manga_id, "0", chapter_id):
            print("Skipping oneshot (already complete)")
            continue
        _download_chapter(session, manga_title, manga_id, "0", chapter_id)


def download(manga_url: str, languages: list[str] | None = None) -> None:
    """
    Download manga from MangaDex.
    Args:
        manga_url (str): Full MangaDex manga URL
        languages (list, optional): List of language codes. Defaults to ["en"]
    Example:
        >>> import mangadex_dl
        >>> mangadex_dl.download("https://mangadex.org/title/5a547d1d-576b-477f-8cb3-70a3b4187f8a/jojo-s-bizarre-adventure-part-1-phantom-blood")
    """
    if languages is None:
        languages = LANGUAGES

    session = _get_session()

    # Extract manga ID from URL
    parts = manga_url.split('/')
    try:
        manga_id = parts[parts.index('title') + 1]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid MangaDex URL format: {manga_url}. Expected format: https://mangadex.org/title/<manga_id>/...")

    # Fetch manga info
    try:
        r_manga = session.get(f"{BASE_URL}/manga/{manga_id}", timeout=30)
        r_manga.raise_for_status()
        r_manga_json = r_manga.json()
        raw_title = list(r_manga_json["data"]["attributes"]["title"].values())[0]
        manga_title = _sanitize_filename(raw_title)
    except (requests.RequestException, KeyError, IndexError) as e:
        raise ValueError(f"Error fetching manga info: {e!r}")

    print(f"Downloading: {manga_title}")

    # Fetch chapters (Handling Pagination to get >500 chapters)
    all_chapters_data = []
    offset = 0
    limit = 500

    try:
        print("Fetching chapter list...")
        while True:
            r_feed = session.get(
                f"{BASE_URL}/manga/{manga_id}/feed",
                params={
                    "translatedLanguage[]": languages,
                    "limit": limit,
                    "offset": offset,
                    "order[chapter]": "asc"
                },
                timeout=30
            )
            r_feed.raise_for_status()
            r_json_feed = r_feed.json()

            chunk = r_json_feed["data"]
            all_chapters_data.extend(chunk)

            total = r_json_feed["total"]
            offset += limit

            if offset >= total:
                break

            print(f"Fetched {offset}/{total} chapters...")
            time.sleep(0.5)  # Brief pause to avoid hammering the API

    except (requests.RequestException, KeyError) as e:
        raise ValueError(f"Error fetching chapters: {e!r}")

    # Separate oneshots from numbered chapters
    oneshots = []
    numbered_chapters = []

    for chapter_data in all_chapters_data:
        chapter_num = chapter_data["attributes"]["chapter"]
        if chapter_num is None:
            oneshots.append(chapter_data)
        else:
            numbered_chapters.append(chapter_data)

    # Download based on content type
    if numbered_chapters:
        _download_series(session, manga_title, manga_id, numbered_chapters)
    if oneshots:
        _download_oneshots(session, manga_title, manga_id, oneshots)

    print(f"Download complete for: {manga_title}")


if __name__ == "__main__":
    ...