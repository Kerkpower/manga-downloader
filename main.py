"""
Main script to download manga from multiple sources.

Reads URLs from list.txt and downloads from supported sources:
- MangaDex (mangadex.org)
- DemonicScans (demonicscans.org)
- WeebCentral (weebcentral.com)
"""

import sys

import demonicScans_dl
import mangadex_dl
import weebCentral_dl


def detect_site(url):
    """
    Detect which site a URL belongs to.

    Args:
        url (str): The URL to check

    Returns:
        str: 'mangadex', 'demonicscans', 'weebcentral', or None if unsupported
    """
    url_lower = url.lower().strip()

    if 'mangadex.org' in url_lower:
        return 'mangadex'
    elif 'demonicscans.org' in url_lower:
        return 'demonicscans'
    elif 'weebcentral.com' in url_lower:
        return 'weebcentral'
    else:
        return None


def read_url_list(filename='list.txt'):
    """
    Read URLs from a text file, one per line.

    Args:
        filename (str): Path to the file containing URLs

    Returns:
        list: List of URL strings
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            urls = [
                line.split('#')[0].strip()
                for line in f
                if line.split('#')[0].strip()
            ]
        return urls
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading '{filename}': {e}")
        sys.exit(1)


def main():
    """Main function to process URLs and download manga."""
    print("Reading URL list from list.txt...")
    urls = read_url_list('list.txt')

    print(f"Found {len(urls)} URL(s) to process.\n")

    for i, url in enumerate(urls, 1):
        print(f"\n{'='*60}")
        print(f"Processing URL {i}/{len(urls)}: {url}")
        print(f"{'='*60}")

        site = detect_site(url)

        if site == 'mangadex':
            print("Detected: MangaDex")
            try:
                mangadex_dl.download(url)
                print(f"✓ Successfully processed MangaDex URL: {url}")
            except Exception as e:
                print(f"✗ Error downloading from MangaDex: {e}")

        elif site == 'demonicscans':
            print("Detected: DemonicScans")
            try:
                demonicScans_dl.download(url)
                print(f"✓ Successfully processed DemonicScans URL: {url}")
            except Exception as e:
                print(f"✗ Error downloading from DemonicScans: {e}")

        elif site == 'weebcentral':
            print("Detected: WeebCentral")
            try:
                weebCentral_dl.download(url)
                print(f"✓ Successfully processed WeebCentral URL: {url}")
            except Exception as e:
                print(f"✗ Error downloading from WeebCentral: {e}")

        else:
            print(f"✗ ERROR: Unsupported source for URL: {url}")
            print("  Supported sources: MangaDex (mangadex.org), DemonicScans (demonicscans.org), WeebCentral (weebcentral.com)")
            print("  Skipping this URL...")
            continue

    print(f"\n{'='*60}")
    print("All URLs processed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()