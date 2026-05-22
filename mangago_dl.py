"""
Mangago Downloader Module
A module to download manga from Mangago with resume capability using Selenium/Geckodriver.
Usage:
    import mangago_dl
    mangago_dl.download("https://www.mangago.me/read-manga/choir/")
"""
import time
import re
from pathlib import Path
import requests
import urllib3
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path.cwd() / "downloads" / "mangago"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
# Suppress InsecureRequestWarning for the image CDN SSL bypass
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _get_download_session() -> requests.Session:
    """Create a requests session specifically for downloading images."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Referer': 'https://www.mangago.me/'
    })
    # Mount adapter with retries FIRST
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # Bypass SSL verification because Mangago's image CDN has a bad certificate
    session.verify = False
    return session

def _sanitize_filename(name: str, fallback: str = "Unknown") -> str:
    """Remove invalid characters for directory/file names."""
    keepchars = (' ', '-', '_', '.')
    clean = "".join(c for c in name if c.isalnum() or c in keepchars).rstrip()
    return clean if clean else fallback

def _is_chapter_complete(manga_title: str, chapter_name: str) -> bool:
    """Check if a chapter is completely downloaded."""
    chapter_path = BASE_DIR / manga_title / chapter_name
    return (chapter_path / ".completed").exists()

def _download_image(session: requests.Session, img_url: str, save_path: Path) -> bool:
    """Download a single image using requests. Returns True on success."""
    try:
        r = session.get(img_url, timeout=30)
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(r.content)
        return True
    except (requests.RequestException, IOError) as e:
        print(f"Error downloading image {save_path.name}: {e!r}")
        return False

def _extract_image_url(driver, page_url: str) -> tuple[str, str] | tuple[None, None]:
    """
    Navigate to a page URL using Selenium and wait for the dynamic image to load.
    Returns (img_src, img_id) or (None, None) if it fails.
    """
    try:
        driver.get(page_url)
        # Wait up to 10 seconds for the FIRST image inside pic_container to appear
        pic_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a#pic_container > img"))
        )
        # Tiny buffer for JS to populate the src
        time.sleep(0.5)
        img_src = pic_container.get_attribute('src')
        img_id = pic_container.get_attribute('id')
        if not img_src or not img_id:
            return None, None
        return img_src, img_id
    except TimeoutException:
        print(f"Warning: Timed out waiting for image to load at {page_url}")
        return None, None
    except WebDriverException as e:
        print(f"Warning: WebDriver error loading {page_url}: {e!r}")
        return None, None

def _get_page_urls_from_dropdown(driver) -> list[str]:
    """
    Force the page dropdown to be visible via JavaScript, then extract all page URLs.
    This is much safer than guessing the URL structure.
    """
    try:
        # 1. Make the dropdown menu visible using JavaScript
        dropdown = driver.find_element(By.ID, "dropdown-menu-page")
        driver.execute_script("arguments[0].style.display = 'block';", dropdown)
        # 2. Wait a fraction of a second for the DOM to update
        time.sleep(0.2)
        # 3. Grab all the links
        links = dropdown.find_elements(By.TAG_NAME, "a")
        urls = [link.get_attribute('href') for link in links if link.get_attribute('href')]
        # 4. Hide it again (optional, but keeps the DOM clean)
        driver.execute_script("arguments[0].style.display = 'none';", dropdown)
        return urls
    except Exception:
        return []

def _download_chapter(driver, dl_session, manga_title: str, chapter_name: str, chapter_url: str):
    """Download a single chapter's pages dynamically."""
    chapter_path = BASE_DIR / manga_title / chapter_name
    chapter_path.mkdir(parents=True, exist_ok=True)
    try:
        print(f"Loading chapter {chapter_name}...")
        # 1. Navigate to the first page of the chapter
        driver.get(chapter_url)
        # Wait briefly for the page structure to initialize
        time.sleep(1)
        # 2. Extract all page URLs from the dropdown
        page_urls = _get_page_urls_from_dropdown(driver)
        if not page_urls:
            print(f"Warning: Could not extract page URLs for {chapter_name}")
            return
        max_pages = len(page_urls)
        downloaded = 0
        # 3. Iterate and download
        for current_page_num, page_url in enumerate(page_urls, start=1):
            img_src, img_id = _extract_image_url(driver, page_url)
            if not img_src or not img_id:
                continue
            # Extract extension from URL (e.g., .jpeg, .png, .webp)
            url_path = img_src.split('?')[0]
            ext = Path(url_path).suffix if Path(url_path).suffix else '.jpg'
            # Filename pattern: <img id>.<extension>
            filename = f"{img_id}{ext}"
            save_path = chapter_path / filename
            if _download_image(dl_session, img_src, save_path):
                downloaded += 1
        print(f"Downloaded Chapter {chapter_name}: {downloaded}/{max_pages} pages.")
        # Mark chapter as complete only if all pages downloaded
        if downloaded == max_pages:
            (chapter_path / ".completed").touch()
        else:
            print(f"Warning: Chapter {chapter_name} is incomplete. Will retry on next run.")
    except Exception as e:
        print(f"Error processing chapter {chapter_name}: {e!r}")

def download(manga_url: str) -> None:
    """
    Download manga from Mangago.
    Args:
        manga_url (str): Full Mangago manga URL
    Example:
        >>> import mangago_dl
        >>> mangago_dl.download("https://www.mangago.me/read-manga/choir/")
    """
    # Setup Firefox in headless mode
    options = Options()
    options.add_argument("--headless")
    options.set_preference("general.useragent.override", USER_AGENT)
    driver = None
    try:
        driver = webdriver.Firefox(options=options)
        dl_session = _get_download_session()
        print(f"Fetching manga page: {manga_url}")
        driver.get(manga_url)
        # Wait for the chapter table to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "chapter_table"))
            )
        except TimeoutException:
            raise ValueError("Could not find chapter table. The URL might be invalid or site structure changed.")
        # Extract title
        title_elem = driver.find_element(By.TAG_NAME, "h1")
        raw_title = title_elem.text.strip() if title_elem else "Unknown Manga"
        raw_title = raw_title.split('-')[0].strip()
        manga_title = _sanitize_filename(raw_title, fallback="UnknownManga")
        print(f"Downloading: {manga_title}")
        # Extract chapters directly by targeting the links with the specific class
        chapter_link_elems = driver.find_elements(By.CSS_SELECTOR, "a.chico")
        chapters_data = []
        for link_elem in chapter_link_elems:
            chapter_url = link_elem.get_attribute('href')
            # Use JavaScript to get text, which works even if the element is hidden off-screen
            raw_chapter_name = driver.execute_script("return arguments[0].textContent;", link_elem).strip()
            raw_chapter_name = " ".join(raw_chapter_name.split()) # Collapse weird whitespace
            # Extract the chapter ID slug from the URL as a robust fallback for empty names
            url_slug_match = re.search(r'/(mf|uu)/([^/]+)/', chapter_url)
            url_slug = url_slug_match.group(2) if url_slug_match else "UnknownChapter"
            chapter_name = _sanitize_filename(raw_chapter_name, fallback=url_slug)
            if chapter_url:
                chapters_data.append((chapter_name, chapter_url))
        # Chapters on the site are typically listed newest first, so we reverse to download chronologically
        chapters_data.reverse()
        if not chapters_data:
            raise ValueError("No chapters found in the chapter table.")
        # Download series
        for chapter_name, chapter_url in chapters_data:
            if _is_chapter_complete(manga_title, chapter_name):
                print(f"Skipping chapter {chapter_name} (already complete)")
                continue
            _download_chapter(driver, dl_session, manga_title, chapter_name, chapter_url)
        print(f"Download complete for: {manga_title}")
    except ValueError as e:
        print(f"Parsing Error: {e!r}")
    except WebDriverException as e:
        print(f"Browser Error: Is geckodriver installed and in PATH? {e!r}")
    except Exception as e:
        print(f"Unexpected Error: {e!r}")
    finally:
        # Always close the browser when done
        if driver:
            driver.quit()

if __name__ == "__main__":
    ...