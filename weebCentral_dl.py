"""
WeebCentral Downloader Module

A module to download manga from WeebCentral with resume capability.

Usage:
    import weebcentral_dl
    weebcentral_dl.download("https://weebcentral.com/series/01J76XYCERXE60T7FKXVCCAQ0H/Jujutsu-Kaisen")
"""

import os
import re
import time

import requests
from bs4 import BeautifulSoup



# Headers for requests
HEADER_1 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
}

HEADER_2 = {
    "Hx-Request": "true",
    "Hx-Target": "chapter-list",
    "Sec-Ch-Ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
}


def _extract_series_id(url):
    """Extract series ID from WeebCentral URL."""
    match = re.search(r'/series/([^/]+)', url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract series ID from URL: {url}")


def _extract_chapter_id(url):
    """Extract chapter ID from WeebCentral chapter URL."""
    match = re.search(r'/chapters/([^/]+)', url)
    if match:
        return match.group(1)
    return None


def _get_manga_info(series_url):
    """Get manga title and series ID from the series page."""
    try:
        r = requests.get(series_url, headers=HEADER_1, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')

        # Extract title
        title_elem = soup.find('h1', class_='text-2xl')
        if not title_elem:
            title_elem = soup.find('h1')

        if title_elem:
            manga_title = title_elem.text.strip()
        else:
            raise ValueError("Could not find manga title")

        # Extract series ID from URL
        series_id = _extract_series_id(series_url)

        return manga_title, series_id
    except (requests.RequestException, ValueError) as e:
        raise ValueError(f"Error fetching manga info: {e}")


def _get_chapters(series_url):
    """Get dictionary of chapters from the series page."""
    try:
        # Wait for page to load
        time.sleep(3)

        # First, try to get the full chapter list endpoint
        series_id = _extract_series_id(series_url)
        full_chapter_list_url = f"https://weebcentral.com/series/{series_id}/full-chapter-list"

        print(f"Fetching full chapter list from: {full_chapter_list_url}")
        r = requests.get(full_chapter_list_url, headers=HEADER_2, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.content, 'html.parser')

        chapters = {}

        # Find all chapter links (looking for both "Chapter" and "Episode" patterns)
        chapter_links = soup.find_all('a', href=re.compile(r'/chapters/'))

        for link in chapter_links:
            chapter_url = link.get('href')
            if not chapter_url.startswith('http'):
                chapter_url = 'https://weebcentral.com' + chapter_url

            # Extract chapter/episode number from the span
            # Look for both "Chapter" and "Episode" patterns
            chapter_span = link.find('span', string=re.compile(r'(Chapter|Episode)\s+\d+'))
            if chapter_span:
                chapter_text = chapter_span.text.strip()
                # Remove both "Chapter" and "Episode" prefixes
                chapter_num = chapter_text.replace('Chapter ', '').replace('Episode ', '')
                chapters[chapter_num] = chapter_url

        return chapters
    except (requests.RequestException, ValueError) as e:
        raise ValueError(f"Error fetching chapters: {e}")


def _is_chapter_complete(manga_title, series_id, chapter_num, chapter_id):
    """Check if a chapter is completely downloaded."""
    chapter_path = f"downloads/WeebCentral/{manga_title} - {series_id}/{chapter_num} - {chapter_id}"
    return os.path.exists(os.path.join(chapter_path, ".completed"))


def _download_chapter(manga_title, series_id, chapter_num, chapter_url):
    """Download a single chapter's pages."""
    chapter_id = _extract_chapter_id(chapter_url)
    if not chapter_id:
        print(f"Error: Could not extract chapter ID from {chapter_url}")
        return

    chapter_path = f"downloads/WeebCentral/{manga_title} - {series_id}/{chapter_num} - {chapter_id}"
    os.makedirs(chapter_path, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_num}...")
        time.sleep(3)

        images_url = f"https://weebcentral.com/chapters/{chapter_id}/images"
        r = requests.get(
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
        print(f"Fetching images from: {images_url}")

        r.raise_for_status()

        soup = BeautifulSoup(r.content, 'html.parser')

        manga_images = [img for img in soup.find_all('img') if 'Page' in img.get('alt', '')]

        if not manga_images:
            print(f"Warning: No manga images found for chapter {chapter_num}")

        downloaded = 0
        for idx, img in enumerate(manga_images, 1):
            src = img.get('src')
            if not src:
                continue

            filename = src.split('/')[-1]
            if not filename or '?' in filename:
                ext = '.png'
                if '.jpg' in src or '.jpeg' in src:
                    ext = '.jpg'
                elif '.webp' in src:
                    ext = '.webp'
                filename = f"page_{idx:03d}{ext}"

            try:
                img_r = requests.get(src, headers=HEADER_1, timeout=30)
                img_r.raise_for_status()

                file_path = os.path.join(chapter_path, filename)
                with open(file_path, 'wb') as f:
                    f.write(img_r.content)

                downloaded += 1
                time.sleep(0.2)
            except (requests.RequestException, IOError) as e:
                print(f"Error downloading image {filename} for chapter {chapter_num}: {e}")
                continue

        print(f"Downloaded Chapter {chapter_num}: {downloaded}/{len(manga_images)} pages.")

        # Mark chapter as complete
        with open(os.path.join(chapter_path, ".completed"), 'w') as f:
            f.write("")

    except (requests.RequestException, ValueError) as e:
        print(f"Error downloading chapter {chapter_num}: {e}")


def download(series_url):
    """
    Download manga from WeebCentral.

    Args:
        series_url (str): Full WeebCentral series URL

    Example:
        >>> import weebCentral_dl
        >>> weebCentral_dl.download("https://weebcentral.com/series/01J76XYCERXE60T7FKXVCCAQ0H/Jujutsu-Kaisen")
    """
    # Get manga info
    manga_title, series_id = _get_manga_info(series_url)
    print(f"Downloading: {manga_title}")

    # Get chapters
    chapters = _get_chapters(series_url)

    if not chapters:
        print("No chapters found!")
        return

    # Sort chapters by number
    try:
        sorted_chapters = dict(sorted(chapters.items(), key=lambda x: float(x[0])))
    except ValueError:
        # Fallback to string sorting
        sorted_chapters = dict(sorted(chapters.items()))

    # Find where to resume
    resume_from = None
    for chapter_num, chapter_url in sorted_chapters.items():
        chapter_id = _extract_chapter_id(chapter_url)
        if not _is_chapter_complete(manga_title, series_id, chapter_num, chapter_id):
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
        if _is_chapter_complete(manga_title, series_id, chapter_num, chapter_id):
            print(f"Skipping chapter {chapter_num} (already complete)")
            continue
        _download_chapter(manga_title, series_id, chapter_num, chapter_url)

    print(f"Download complete for: {manga_title}")


if __name__ == "__main__":
    ...