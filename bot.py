#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amazon Deals Bot - DealDen Edition
Posts every 2 hours from r/DealDen and other subreddits
"""

import requests
import time
import random
import logging
import sys
import re
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8738482896:AAEDXYJSzf7Hl45mL_a5DcMasZc71oP09Pc"
TELEGRAM_CHANNEL = "@NiceAmazonDeals"
PARTNER_TAG = "oilsandherb06-20"
POST_INTERVAL_HOURS = 2

# Use RSS feeds - more reliable than JSON API
RSS_FEEDS = [
    'https://www.reddit.com/r/DealDen/.rss',
    'https://www.reddit.com/r/DealDen/hot/.rss',
    'https://www.reddit.com/r/amazondeals/.rss',
    'https://www.reddit.com/r/deals/.rss',
    'https://www.reddit.com/r/buildapcsales/.rss',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
posted_asins = set()

def extract_asin(url):
    for pattern in [r'/dp/([A-Z0-9]{10})', r'/gp/product/([A-Z0-9]{10})', r'asin=([A-Z0-9]{10})']:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def resolve_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except:
        return url

def build_affiliate_link(asin):
    return f"https://www.amazon.com/dp/{asin}?tag={PARTNER_TAG}"

def get_product_image(asin):
    for img_url in [
        f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg",
        f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg",
    ]:
        try:
            r = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.amazon.com/'}, timeout=15)
            if r.status_code == 200 and len(r.content) > 2000:
                return r.content
        except:
            continue
    return None

def fetch_from_rss(feed_url):
    """Fetch deals from Reddit RSS feed"""
    deals = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"RSS {r.status_code}: {feed_url[-40:]}")
            return []

        # Parse RSS/Atom feed
        content = r.text
        
        # Extract entries
        entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)
        if not entries:
            # Try RSS format
            entries = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
        
        logger.info(f"Found {len(entries)} entries in {feed_url[-40:]}")

        for entry in entries:
            # Get title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', entry, re.DOTALL)
            title = title_match.group(1) if title_match else ''
            title = re.sub(r'<[^>]+>', '', title).strip()
            title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&#39;', "'")

            # Get content/description
            content_match = re.search(r'<content[^>]*>(.*?)</content>', entry, re.DOTALL)
            if not content_match:
                content_match = re.search(r'<description>(.*?)</description>', entry, re.DOTALL)
            body = content_match.group(1) if content_match else ''

            # Get link
            link_match = re.search(r'<link[^>]*href="([^"]+)"', entry)
            if not link_match:
                link_match = re.search(r'<link>(.*?)</link>', entry)
            post_url = link_match.group(1) if link_match else ''

            # Find Amazon links
            all_text = title + ' ' + body + ' ' + post_url
            amazon_links = re.findall(r'https?://(?:www\.)?amazon\.com[^\s\)"\'<>]+', all_text)
            amazon_links += re.findall(r'https?://amzn\.to/[^\s\)"\'<>]+', all_text)

            asin = None
            for link in amazon_links:
                asin = extract_asin(link)
                if not asin and 'amzn.to' in link:
                    final = resolve_url(link)
                    asin = extract_asin(final)
                if asin:
                    break

            if not asin or asin in posted_asins:
                continue

            # Extract price
            price_match = re.search(r'\$[\d,]+\.?\d*', title + ' ' + body)
            price = price_match.group(0) if price_match else 'Check Price'

            # Extract discount
            disc_match = re.search(r'(\d+)%\s*off', title + ' ' + body, re.IGNORECASE)
            discount = disc_match.group(0) if disc_match else ''

            deals.append({
                'title': title[:80] if title else 'Amazon Deal',
                'asin': asin,
                'link': build_affiliate_link(asin),
                'price': price,
                'discount': discount,
            })

    except Exception as e:
        logger.error(f"RSS error: {e}")

    return deals

def fetch_all_deals():
    all_deals = []
    feeds = RSS_FEEDS.copy()
    random.shuffle(feeds)
    
    for feed in feeds:
        deals = fetch_from_rss(feed)
        for d in deals:
            if d['asin'] not in [x['asin'] for x in all_deals]:
                all_deals.append(d)
    
    logger.info(f"Total unique deals: {len(all_deals)}")
    return all_deals

def send_deal(deal):
    title = deal['title']
    discount_line = f" - {deal['discount']}" if deal['discount'] else ""

    caption = f"""HOT AMAZON DEAL!

{title}

Price: {deal['price']}{discount_line}

GET THIS DEAL: {deal['link']}

#AmazonDeals #Sale #Discount #DailyDeals"""

    try:
        image_data = get_product_image(deal['asin'])
        if image_data:
            files = {"photo": ("product.jpg", image_data, "image/jpeg")}
            data = {"chat_id": TELEGRAM_CHANNEL, "caption": caption}
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                files=files, data=data, timeout=30
            )
            if r.status_code == 200:
                logger.info(f"Posted WITH IMAGE: {title[:40]}")
                return True

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL, "text": caption},
            timeout=15
        )
        if r.status_code == 200:
            logger.info(f"Posted text: {title[:40]}")
            return True

        logger.error(f"Failed: {r.status_code}")
        return False
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False

def post_one_deal():
    logger.info(f"=== Posting at {datetime.now().strftime('%H:%M')} ===")
    deals = fetch_all_deals()
    if not deals:
        logger.error("No deals found!")
        return False
    deal = deals[0]
    success = send_deal(deal)
    if success:
        posted_asins.add(deal['asin'])
    return success

def run_forever():
    logger.info(f"Bot started! Posting every {POST_INTERVAL_HOURS} hours")
    logger.info(f"Channel: {TELEGRAM_CHANNEL}")
    
    post_one_deal()
    
    while True:
        sleep_sec = POST_INTERVAL_HOURS * 3600
        logger.info(f"Next post in {POST_INTERVAL_HOURS} hours...")
        time.sleep(sleep_sec)
        post_one_deal()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        logger.info("TEST MODE")
        post_one_deal()
    else:
        run_forever()
