import json
import re
import time
from pathlib import Path
from typing import List, Dict
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BASE_SITEMAP = "https://chrome.google.com/webstore/sitemap"
OLD_DETAIL_PREFIX = "https://chrome.google.com/webstore/detail/"
NEW_DETAIL_PREFIX = "https://chromewebstore.google.com/detail/"
OUT_FILE = "chrome_extensions.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}


def fetch(url: str, is_xml: bool = False) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def get_all_sitemap_urls() -> List[str]:
    """
    Fetch the main sitemap index and extract all sitemap URLs,
    then filter for those that contain extension detail URLs.
    """
    text = fetch(BASE_SITEMAP, is_xml=True)
    root = ET.fromstring(text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    sitemap_urls = []
    for sm in root.findall("sm:sitemap", ns):
        loc = sm.find("sm:loc", ns)
        if loc is not None and loc.text:
            sitemap_urls.append(loc.text.strip())
    return sitemap_urls


def get_extension_urls_from_sitemap(sitemap_url: str) -> List[str]:
    """
    From a single sitemap file, collect all Web Store detail URLs.
    They look like: https://chrome.google.com/webstore/detail/<name>/<id>
    """
    text = fetch(sitemap_url, is_xml=True)
    root = ET.fromstring(text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for url_tag in root.findall("sm:url", ns):
        loc = url_tag.find("sm:loc", ns)
        if loc is not None and loc.text and NEW_DETAIL_PREFIX in loc.text:
            urls.append(loc.text.strip())
    return urls


def extract_id_from_url(url: str) -> str:
    """
    Extract the extension ID (32 chars a-p) from the classic Web Store URL.
    Example: https://chrome.google.com/webstore/detail/name/abcdefghijklmnopabcdefghijklmnop
    """
    # ID is the last path segment
    ext_id = url.rstrip("/").split("/")[-1]
    # Basic sanity check: 32 chars of a-p. [web:5]
    if re.fullmatch(r"[a-p]{32}", ext_id):
        return ext_id
    return ""


def parse_installs(text: str) -> int:
    """
    Convert strings like '200,000+ users' to integer 200000. [web:18]
    """
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def scrape_extension_detail(ext_id: str) -> Dict:
    """
    Visit the new Chrome Web Store detail page and scrape:
    name, author, images, description, category, rating, ratings, installs. [web:18][web:19]
    """
    url = f"{NEW_DETAIL_PREFIX}{ext_id}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return {"id": ext_id}

    soup = BeautifulSoup(resp.text, "html.parser")

    # These selectors are best-effort and may need adjustment if Google changes the DOM again. [web:18]
    # Name: top-level heading.
    name = None
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)

    # Author / publisher: often near the title or in meta tags. [web:19]
    author = None
    author_meta = soup.find("a", class_="cJI8ee")
    if author_meta:
        author = author_meta.get_text(strip=True)
    else:
        # Fallback: common class for publisher; this may change.
        author_span = soup.find("span", string=re.compile("data-publisher-id", re.I))
        if author_span and author_span.next_sibling:
            author = author_span.next_sibling.get_text(strip=True)

    # Images: look for main promo images.
    small_image = None
    large_image = None
    img_tags = soup.find_all("img")
    image_urls = [img.get("src") for img in img_tags if img.get("src")]
    # Prefer lh3.googleusercontent.com images (Chrome asset CDN).
    cdn_images = [u for u in image_urls if "lh3.googleusercontent.com" in u]
    if cdn_images:
        small_image = cdn_images[0]
        if len(cdn_images) > 1:
            large_image = cdn_images[1]

    # Description: try meta first, then visible overview text. [web:18][web:19]
    description = None
    desc_meta = soup.find("meta", attrs={"name": "description"})
    if desc_meta and desc_meta.get("content"):
        description = desc_meta["content"].strip()
    else:
        # Fallback for visible description area.
        desc_div = soup.find("div", attrs={"itemprop": "description"})
        if desc_div:
            description = desc_div.get_text(" ", strip=True)

    # Category: often in breadcrumb links
    category = None
    cat_meta = soup.find("meta", attrs={"itemprop": "applicationCategory"})
    if cat_meta and cat_meta.get("content"):
        category = cat_meta["content"].strip()
    else:
        # Try to find category from breadcrumb links - look for all links with category-like classes
        categories = []
        # Find all links that might be categories (common classes: gqpEIe, FjUAcd, bgp7Ye)
        category_links = soup.find_all("a")
        for link in category_links:
            classes = link.get('class', [])
            class_str = " ".join(classes) if classes else ""
            if "gqpEIe" in class_str or "FjUAcd" in class_str or "bgp7Ye" in class_str:
                text = link.get_text(strip=True)
                # Filter out non-category text like "Extensions" (plural) which is just a header
                if text and text != "Extensions":
                    categories.append(text)
        if categories:
            category = categories

    # Rating and rating count from visible text
    rating = None
    ratings = None
    # Look for pattern like "5 out of 5" or "4.5 out of 5"
    rating_text = soup.find(string=re.compile(r"\d+\.?\d*\s+out of\s+5", re.IGNORECASE))
    if rating_text:
        try:
            rating = float(rating_text.split()[0])
        except ValueError:
            pass
    
    # Look for pattern like "12 ratings" or similar
    ratings_text = soup.find(string=re.compile(r"(\d+)\s+ratings", re.IGNORECASE))
    if ratings_text:
        try:
            ratings = int(re.search(r"(\d+)\s+ratings", ratings_text, re.IGNORECASE).group(1))
        except (ValueError, AttributeError):
            pass

    # Installs (user count): often visible as "200,000+ users". [web:18]
    installs = None
    user_count = soup.find(string=re.compile(r"\d[\d,]+\s+users", re.IGNORECASE))
    if user_count:
        installs = parse_installs(user_count)
    return {
        "id": ext_id,
        "name": name,
        "author": author,
        "smallImage": small_image,
        "largeImage": large_image,
        "description": description,
        "category": category,
        "rating": rating,
        "ratings": ratings,
        "installs": installs,
    }


def main():
    # 1) Collect all sitemap part URLs. [web:11]
    print("Fetching sitemap index...")
    sitemap_urls = get_all_sitemap_urls()
    print(f"Found {len(sitemap_urls)} sitemap parts")

    # 2) Collect all extension URLs from each sitemap.
    all_urls = []
    for i, sm_url in enumerate(sitemap_urls, start=1):
        print(f"[{i}/{len(sitemap_urls)}] Fetching {sm_url}")
        try:
            urls = get_extension_urls_from_sitemap(sm_url)
            all_urls.extend(urls)
        except Exception as e:
            print(f"Error reading sitemap {sm_url}: {e}")
        time.sleep(0.1)  # be gentle

    print(f"Total extension URLs found: {len(all_urls)}")

    # 3) Deduplicate and extract IDs.
    ext_ids = []
    seen_ids = set()
    for url in all_urls:
        ext_id = extract_id_from_url(url)
        if ext_id and ext_id not in seen_ids:
            seen_ids.add(ext_id)
            ext_ids.append(ext_id)

    print(f"Unique extension IDs: {len(ext_ids)}")

    # 4) Scrape details for each extension and write to JSON.
    results = []
    counter = 0
    for i, ext_id in enumerate(ext_ids, start=1):
        print(f"[{i}/{len(ext_ids)}] Scraping {ext_id}")
        try:
            data = scrape_extension_detail(ext_id)
            results.append(data)
        except Exception as e:
            print(f"Error scraping {ext_id}: {e}")
        counter += 1
        if counter > 10:
            out_path = Path(OUT_FILE)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            counter = 0
        # Sleep a bit to reduce load; adjust as needed.
        time.sleep(0.01)

    out_path = Path(OUT_FILE)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(results)} extensions to {out_path.resolve()}")


if __name__ == "__main__":
    main()
