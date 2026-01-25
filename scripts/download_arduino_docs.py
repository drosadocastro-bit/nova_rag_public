"""
Download Arduino hardware documentation for Phase 3 corpus.

Downloads key Arduino hardware reference pages as HTML files for ingestion.
"""

import requests
from pathlib import Path
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path("data/phase3_corpus/hardware_electronics")

# Arduino documentation pages to download
ARDUINO_PAGES = [
    {
        "url": "https://docs.arduino.cc/hardware/uno-rev3",
        "filename": "arduino_uno_rev3.html",
        "description": "Arduino Uno Rev3 Hardware Reference"
    },
    {
        "url": "https://docs.arduino.cc/hardware/mega-2560-rev3",
        "filename": "arduino_mega_2560.html",
        "description": "Arduino Mega 2560 Hardware Reference"
    },
    {
        "url": "https://docs.arduino.cc/hardware/nano",
        "filename": "arduino_nano.html",
        "description": "Arduino Nano Hardware Reference"
    },
    {
        "url": "https://docs.arduino.cc/learn/starting-guide/getting-started-arduino",
        "filename": "arduino_getting_started.html",
        "description": "Arduino Getting Started Guide"
    },
]


def download_page(url: str, output_path: Path, description: str) -> bool:
    """
    Download a single page.
    
    Args:
        url: URL to download from
        output_path: Path to save file
        description: Description for logging
    
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading: {description}")
        logger.info(f"  URL: {url}")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        file_size_kb = output_path.stat().st_size / 1024
        logger.info(f"  ✓ Saved: {output_path.name} ({file_size_kb:.1f} KB)")
        
        return True
    
    except requests.exceptions.RequestException as e:
        logger.error(f"  ✗ Failed: {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False


def main():
    """Main entry point."""
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info("="*60)
    
    # Download pages
    success_count = 0
    failed_urls = []
    
    for page in ARDUINO_PAGES:
        output_path = OUTPUT_DIR / page["filename"]
        
        if download_page(page["url"], output_path, page["description"]):
            success_count += 1
        else:
            failed_urls.append(page["url"])
        
        logger.info("")  # Blank line between downloads
    
    # Summary
    logger.info("="*60)
    logger.info("Download Summary")
    logger.info("="*60)
    logger.info(f"Successful: {success_count}/{len(ARDUINO_PAGES)}")
    logger.info(f"Failed: {len(failed_urls)}")
    
    if failed_urls:
        logger.warning("\nFailed URLs:")
        for url in failed_urls:
            logger.warning(f"  - {url}")
    
    # Calculate total size
    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.glob("*.html"))
    total_size_mb = total_size / (1024 * 1024)
    
    logger.info(f"\nTotal downloaded: {total_size_mb:.2f} MB")
    logger.info(f"Files in directory: {len(list(OUTPUT_DIR.glob('*.html')))}")
    
    if success_count == len(ARDUINO_PAGES):
        logger.info("\n✓ All Arduino documentation downloaded successfully!")
        logger.info("Next: Run validation script")
    else:
        logger.warning("\n⚠ Some downloads failed. Check errors above.")


if __name__ == "__main__":
    main()
