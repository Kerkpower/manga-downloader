"""
MangaDex Downloader Module

A simple module to download manga from MangaDex with resume capability.

Usage:
    import mangadex_dl
    mangadex_dl.download("https://mangadex.org/title/d4c562e3-3bcd-4a8f-b508-6a6cec4a9473/faceapp-ts-manga")
"""

import os
import time

import requests

BASE_URL = "https://api.mangadex.org"
LANGUAGES = ["en"]


def _is_chapter_complete(manga_title, manga_id, chapter_identifier, chapter_id):
    """Check if a chapter is completely downloaded."""
    chapter_path = f"downloads/mangaDex/{manga_title} - {manga_id}/{chapter_identifier} - {chapter_id}"
    return os.path.exists(os.path.join(chapter_path, ".completed"))


def _download_chapter(manga_title, manga_id, chapter_identifier, chapter_id):
    """Download a single chapter's pages."""
    chapter_path = f"downloads/mangaDex/{manga_title} - {manga_id}/{chapter_identifier} - {chapter_id}"
    os.makedirs(chapter_path, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_identifier}...")
        chapter_r = requests.get(f"{BASE_URL}/at-home/server/{chapter_id}", timeout=30)
        chapter_r.raise_for_status()
        chapter_json = chapter_r.json()

        host = chapter_json["baseUrl"]
        chapter_hash = chapter_json["chapter"]["hash"]
        data = chapter_json["chapter"]["data"]
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"Error fetching chapter data for {chapter_identifier}: {e}")
        return

    downloaded = 0
    for page in data:
        try:
            r = requests.get(f"{host}/data/{chapter_hash}/{page}", timeout=30)
            r.raise_for_status()
            with open(f"{chapter_path}/{page}", mode="wb") as f:
                f.write(r.content)
            downloaded += 1
            time.sleep(0.2)
        except (requests.RequestException, IOError) as e:
            print(f"Error downloading page {page} for chapter {chapter_identifier}: {e}")
            continue

    print(f"Downloaded Chapter {chapter_identifier}: {downloaded}/{len(data)} pages.")

    # Mark chapter as complete
    with open(os.path.join(chapter_path, ".completed"), 'w') as f:
        f.write("")


def _download_series(manga_title, manga_id, chapters_data):
    """Download a series with numbered chapters."""
    chapters = {}

    for chapter_data in chapters_data:
        chapter_num = chapter_data["attributes"]["chapter"]
        chapter_id = chapter_data["id"]
        chapters[chapter_num] = chapter_id

    try:
        chapters = dict(sorted(chapters.items(), key=lambda x: float(x[0])))
    except (ValueError, TypeError):
        chapters = dict(sorted(chapters.items(), key=lambda x: str(x[0])))

    for chapter_num, chapter_id in chapters.items():
        if _is_chapter_complete(manga_title, manga_id, chapter_num, chapter_id):
            print(f"Skipping chapter {chapter_num} (already complete)")
            continue
        _download_chapter(manga_title, manga_id, chapter_num, chapter_id)


def _download_oneshots(manga_title, manga_id, chapters_data):
    """Download oneshots or chapters without numbers."""
    for chapter_data in chapters_data:
        chapter_id = chapter_data["id"]
        if _is_chapter_complete(manga_title, manga_id, "0", chapter_id):
            print("Skipping oneshot (already complete)")
            continue
        _download_chapter(manga_title, manga_id, "0", chapter_id)


def download(manga_url, languages=None):
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

    # Extract manga ID from URL
    parts = manga_url.split('/')
    try:
        manga_id = parts[parts.index('title') + 1]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid MangaDex URL format: {manga_url}. Expected format: https://mangadex.org/title/<manga_id>/...")

    # Fetch manga info
    try:
        r_manga = requests.get(f"{BASE_URL}/manga/{manga_id}", timeout=30)
        r_manga.raise_for_status()
        r_manga_json = r_manga.json()
        manga_title = list(r_manga_json["data"]["attributes"]["title"].values())[0]
    except (requests.RequestException, KeyError, IndexError) as e:
        raise ValueError(f"Error fetching manga info: {e}")

    print(f"Downloading: {manga_title}")

    # Fetch chapters
    try:
        print(f"Fetching chapter list...")
        r_feed = requests.get(
            f"{BASE_URL}/manga/{manga_id}/feed",
            params={
                "translatedLanguage[]": languages,
                "limit": 500,
                "order[chapter]": "asc"
            },
            timeout=30
        )
        r_feed.raise_for_status()
        r_json_feed = r_feed.json()
    except (requests.RequestException, KeyError) as e:
        raise ValueError(f"Error fetching chapters: {e}")

    # Separate oneshots from numbered chapters
    oneshots = []
    numbered_chapters = []

    for chapter_data in r_json_feed["data"]:
        chapter_num = chapter_data["attributes"]["chapter"]
        if chapter_num is None:
            oneshots.append(chapter_data)
        else:
            numbered_chapters.append(chapter_data)

    # Download based on content type
    if numbered_chapters:
        _download_series(manga_title, manga_id, numbered_chapters)

    if oneshots:
        _download_oneshots(manga_title, manga_id, oneshots)

    print(f"Download complete for: {manga_title}")


if __name__ == "__main__":
    ...
