"""
DemonicScans Downloader Module

A module to download manga from DemonicScans with resume capability.

Usage:
    import demonicScans_dl
    demonicScans_dl.download("https://demonicscans.org/manga/S%25252DClass-Hunter-Heals-with-Monsters")
"""

import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'


def _get_firefox_driver(headless=True):
    """Create and configure a Firefox WebDriver."""
    try:
        firefox_options = Options()
        if headless:
            firefox_options.add_argument('--headless')
        firefox_options.set_preference('general.useragent.override', USER_AGENT)
        return webdriver.Firefox(options=firefox_options)
    except Exception as e:
        raise RuntimeError(f"Failed to create Firefox WebDriver: {e}")


def _get_expected_page_count(driver, chapter_url):
    """Get the expected number of pages for a chapter."""
    try:
        full_url = f"https://demonicscans.org{chapter_url}" if not chapter_url.startswith('http') else chapter_url
        driver.get(full_url)
        time.sleep(3)

        chapter_soup = BeautifulSoup(driver.page_source, 'html.parser')
        main_div = chapter_soup.find('div', class_='main-width center-m')

        if not main_div:
            return 0

        images = main_div.find_all('img', class_='imgholder')
        return len(images)
    except Exception as e:
        print(f"Error getting page count for chapter: {e}")
        return 0


def _is_chapter_complete(manga_title, chapter_num):
    """Check if a chapter is completely downloaded."""
    chapter_path = Path(f"downloads/demonicScans/{manga_title}/{chapter_num}")
    return (chapter_path / ".completed").exists()


def _download_chapter(driver, manga_title, chapter_num, chapter_url):
    """Download a single chapter's pages."""
    chapter_path = Path(f"downloads/demonicScans/{manga_title}/{chapter_num}")
    chapter_path.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Loading chapter {chapter_num}...")
        full_url = f"https://demonicscans.org{chapter_url}" if not chapter_url.startswith('http') else chapter_url
        print(f"Fetching images from: {full_url}")
        driver.get(full_url)
        time.sleep(3)

        chapter_soup = BeautifulSoup(driver.page_source, 'html.parser')
        main_div = chapter_soup.find('div', class_='main-width center-m')

        if not main_div:
            print(f"Error: Could not find content for chapter {chapter_num}")
            return

        images = main_div.find_all('img', class_='imgholder')

        if not images:
            print(f"Warning: No images found for chapter {chapter_num}")
            return
    except Exception as e:
        print(f"Error fetching chapter data for {chapter_num}: {e}")
        return

    headers = {'User-Agent': USER_AGENT}
    downloaded = 0

    for page_num, img in enumerate(images, start=1):
        img_url = img.get('src')

        if not img_url:
            continue

        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://demonicscans.org' + img_url

        try:
            response = requests.get(img_url, headers=headers, timeout=10)
            response.raise_for_status()

            img_path = chapter_path / f"{page_num}.jpg"
            with open(img_path, 'wb') as f:
                f.write(response.content)
            downloaded += 1
            time.sleep(0.2)
        except (requests.RequestException, IOError) as e:
            print(f"Error downloading page {page_num} for chapter {chapter_num}: {e}")
            continue

    print(f"Downloaded Chapter {chapter_num}: {downloaded}/{len(images)} pages.")

    # Mark chapter as complete
    (chapter_path / ".completed").touch()


def _download_series(driver, manga_title, chapters_data):
    """Download a series with numbered chapters."""
    chapters = {}

    for chapter_num_str, chapter_num_sort, chapter_url in chapters_data:
        chapters[chapter_num_str] = (chapter_num_sort, chapter_url)

    chapters = dict(sorted(chapters.items(), key=lambda x: x[1][0]))

    for chapter_num_str, (_, chapter_url) in chapters.items():
        if _is_chapter_complete(manga_title, chapter_num_str):
            print(f"Skipping chapter {chapter_num_str} (already complete)")
            continue
        _download_chapter(driver, manga_title, chapter_num_str, chapter_url)


def download(manga_url):
    """
    Download manga from DemonicScans.

    Args:
        manga_url (str): Full DemonicScans manga URL

    Example:
        >>> import demonicScans_dl
        >>> demonicScans_dl.download("https://demonicscans.org/manga/S%25252DClass-Hunter-Heals-with-Monsters")
    """
    # Create driver
    try:
        driver = _get_firefox_driver()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    try:
        print(f"Fetching series page from: {manga_url}")
        driver.get(manga_url)
        time.sleep(5)

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        # Extract title
        title = soup.find('h1', class_='border-box big-fat-titles')
        manga_title = title.text.strip() if title else None

        if not manga_title:
            raise ValueError("Could not extract manga title from page")

        print(f"Downloading: {manga_title}")

        # Extract chapter data
        chapters_list = soup.find('div', id='chapters-list')
        chapter_data = []

        if not chapters_list:
            raise ValueError("Could not find chapters list on page")

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

        # Sort by chapter number
        chapter_data.sort(key=lambda x: x[1])

        # Download series
        _download_series(driver, manga_title, chapter_data)

        print(f"Download complete for: {manga_title}")

    except (ValueError, Exception) as e:
        print(f"Error: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    ...
