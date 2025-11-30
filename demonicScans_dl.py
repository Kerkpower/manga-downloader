"""
DemonicScans Downloader Module

A module to download manga from DemonicScans with resume capability.

Usage:
    import demonicScans_dl
    demonicScans_dl.download("https://demonicscans.org/manga/")
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
        raise RuntimeError(f"Failed to create Firefox WebDriver. Make sure Firefox and geckodriver are installed: {e}")


def _extract_manga_info(manga_url, driver=None):
    """
    Extract manga title and chapter data from the manga page.
    
    Args:
        manga_url (str): URL of the manga page
        driver (webdriver.Firefox, optional): Existing WebDriver instance to reuse.
            If None, a new driver will be created and closed after use.
    
    Returns:
        tuple: (title_text, chapter_data)
    """
    should_quit_driver = driver is None
    if driver is None:
        driver = _get_firefox_driver()

    try:
        driver.get(manga_url)
        time.sleep(5)

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        # Extract title
        title = soup.find('h1', class_='border-box big-fat-titles')
        title_text = title.text.strip() if title else None

        # Extract chapter URLs
        chapters_list = soup.find('div', id='chapters-list')
        chapter_data = []

        if chapters_list:
            list_items = chapters_list.find_all('li')
            for li in list_items:
                link = li.find('a')
                if link and link.get('href'):
                    chapter_url = link.get('href')
                    # Parse chapter number from URL
                    parsed = urlparse(chapter_url)
                    params = parse_qs(parsed.query)
                    if 'chapter' in params:
                        chapter_num = params['chapter'][0]
                        try:
                            # Convert to int or float for sorting
                            chapter_num_sort = float(chapter_num) if '.' in chapter_num else int(chapter_num)
                            chapter_data.append((chapter_num, chapter_num_sort, chapter_url))
                        except ValueError:
                            continue

        # Sort by chapter number in ascending order
        chapter_data.sort(key=lambda x: x[1])

        return title_text, chapter_data

    finally:
        if should_quit_driver:
            driver.quit()


def _find_resume_point(manga_path):
    """Find the last downloaded chapter to resume from."""
    existing_chapters = []
    if manga_path.exists():
        for folder in manga_path.iterdir():
            if folder.is_dir():
                try:
                    chapter_num = float(folder.name) if '.' in folder.name else int(folder.name)
                    existing_chapters.append(chapter_num)
                except ValueError:
                    continue

    if existing_chapters:
        last_chapter = max(existing_chapters)
        print(f"\nFound existing downloads. Last chapter: {last_chapter}")
        print(f"Resuming from chapter {last_chapter} (will redownload it)")
        return last_chapter

    return None


def _download_chapter_images(driver, chapter_url, chapter_path):
    """Download all images for a single chapter."""
    full_url = f"https://demonicscans.org{chapter_url}" if not chapter_url.startswith('http') else chapter_url

    driver.get(full_url)
    time.sleep(3)

    chapter_soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Find the main content div
    main_div = chapter_soup.find('div', class_='main-width center-m')

    if not main_div:
        return 0

    # Find all images
    images = main_div.find_all('img', class_='imgholder')

    if not images:
        return 0

    # Create chapter folder
    chapter_path.mkdir(parents=True, exist_ok=True)

    headers = {'User-Agent': USER_AGENT}

    # Download each image
    downloaded = 0
    for page_num, img in enumerate(images, start=1):
        img_url = img.get('src')

        if not img_url:
            print(f"  Page {page_num}: No src attribute")
            continue

        # Make sure URL is absolute
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://demonicscans.org' + img_url

        try:
            response = requests.get(img_url, headers=headers, timeout=10)

            if response.status_code == 200:
                img_path = chapter_path / f"{page_num}.jpg"
                with open(img_path, 'wb') as f:
                    f.write(response.content)
                print(f"  Downloaded page {page_num}")
                downloaded += 1
            else:
                print(f"  Page {page_num}: Status code {response.status_code}")

        except requests.RequestException as e:
            print(f"  Page {page_num}: Error - {e}")

    return downloaded


def download(manga_url, base_download_path='downloads/demonicScans'):
    """
    Download manga from DemonicScans.

    Args:
        manga_url (str): Full DemonicScans manga URL
        base_download_path (str, optional): Base path for downloads. Defaults to 'downloads/demonicScans'

    Example:
        >>> import demonicScans_dl
        >>> demonicScans_dl.download("https://demonicscans.org/manga/S%25252DClass-Hunter-Heals-with-Monsters")
    """
    # Create driver once and reuse it
    try:
        driver = _get_firefox_driver()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    try:
        # Extract manga info (reusing the driver)
        print("Extracting manga information...")
        title_text, chapter_data = _extract_manga_info(manga_url, driver=driver)

        if not title_text or not chapter_data:
            print("Could not extract title or chapters. Aborting.")
            return

        print(f"Title: {title_text}")
        print(f"Total chapters found: {len(chapter_data)}")

        # Create folder structure
        base_path = Path(base_download_path)
        manga_path = base_path / title_text
        manga_path.mkdir(parents=True, exist_ok=True)

        # Find resume point
        resume_from = _find_resume_point(manga_path)

        # Download chapters (reusing the same driver)
        for chapter_num_str, chapter_num_sort, chapter_url in chapter_data:
            # Skip chapters before the resume point
            if resume_from is not None and chapter_num_sort < resume_from:
                print(f"Skipping Chapter {chapter_num_str} (already downloaded)")
                continue

            print(f"\nDownloading Chapter {chapter_num_str}...")

            chapter_path = manga_path / str(chapter_num_str)
            pages_downloaded = _download_chapter_images(driver, chapter_url, chapter_path)

            if pages_downloaded > 0:
                print(f"  Chapter {chapter_num_str} complete ({pages_downloaded} pages)")
            else:
                print(f"  Could not download chapter {chapter_num_str}")

        print("\nAll chapters downloaded!")

    finally:
        driver.quit()


if __name__ == "__main__":
    ...