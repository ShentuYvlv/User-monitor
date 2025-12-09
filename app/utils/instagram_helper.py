import random
import time
import logging
from functools import wraps
import instaloader
from instaloader import ConnectionException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. User-Agent Generator (Ported from instagram_monitor.py)
# ---------------------------------------------------------

def get_random_user_agent() -> str:
    """Returns a random desktop browser user agent string."""
    browser = random.choice(['chrome', 'firefox', 'edge', 'safari'])

    if browser == 'chrome':
        os_choice = random.choice(['mac', 'windows'])
        if os_choice == 'mac':
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{random.randrange(11, 15)}_{random.randrange(4, 9)}) "
                f"AppleWebKit/{random.randrange(530, 537)}.{random.randrange(30, 37)} (KHTML, like Gecko) "
                f"Chrome/{random.randrange(80, 120)}.0.{random.randrange(3000, 4500)}.{random.randrange(60, 125)} "
                f"Safari/{random.randrange(530, 537)}.{random.randrange(30, 36)}"
            )
        else:
            chrome_version = random.randint(80, 120)
            build = random.randint(3000, 4500)
            patch = random.randint(60, 125)
            return (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_version}.0.{build}.{patch} Safari/537.36"
            )

    elif browser == 'firefox':
        os_choice = random.choice(['windows', 'mac', 'linux'])
        version = random.randint(90, 120)
        if os_choice == 'windows':
            return (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}.0) "
                f"Gecko/20100101 Firefox/{version}.0"
            )
        elif os_choice == 'mac':
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{random.randrange(11, 15)}_{random.randrange(0, 10)}; rv:{version}.0) "
                f"Gecko/20100101 Firefox/{version}.0"
            )
        else:
            return (
                f"Mozilla/5.0 (X11; Linux x86_64; rv:{version}.0) "
                f"Gecko/20100101 Firefox/{version}.0"
            )

    elif browser == 'edge':
        os_choice = random.choice(['windows', 'mac'])
        chrome_version = random.randint(80, 120)
        build = random.randint(3000, 4500)
        patch = random.randint(60, 125)
        version_str = f"{chrome_version}.0.{build}.{patch}"
        if os_choice == 'windows':
            return (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{version_str} Safari/537.36 Edg/{version_str}"
            )
        else:
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{random.randrange(11, 15)}_{random.randrange(0, 10)}) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{random.randint(13, 16)}.0 Safari/605.1.15 Edg/{version_str}"
            )

    elif browser == 'safari':
        mac_major = random.randrange(11, 16)
        mac_minor = random.randrange(0, 10)
        webkit_major = random.randint(600, 610)
        webkit_minor = random.randint(1, 20)
        webkit_patch = random.randint(1, 20)
        safari_version = random.randint(13, 16)
        return (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{mac_major}_{mac_minor}) "
            f"AppleWebKit/{webkit_major}.{webkit_minor}.{webkit_patch} (KHTML, like Gecko) "
            f"Version/{safari_version}.0 Safari/{webkit_major}.{webkit_minor}.{webkit_patch}"
        )
    
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# ---------------------------------------------------------
# 2. Request Wrapper (Jitter & Backoff)
# ---------------------------------------------------------

def instagram_wrap_request(orig_request):
    """
    Monkey-patches Instagram request to add human-like jitter and back-off.
    Based on the original script's logic.
    """
    @wraps(orig_request)
    def wrapper(*args, **kwargs):
        # 1. Random Jitter before every request
        sleep_time = random.uniform(0.8, 3.0)
        time.sleep(sleep_time)

        attempt = 0
        backoff = 60
        
        while True:
            try:
                resp = orig_request(*args, **kwargs)
            except Exception as e:
                # Network errors, let them bubble up or retry? 
                # For now let's just let standard logic handle connection errors,
                # but if it's a 429 inside the response we handle it below.
                raise e

            # 2. Handle Rate Limits (429 or 400 checkpoint)
            if resp.status_code == 429 or (resp.status_code == 400 and "checkpoint" in resp.text):
                attempt += 1
                if attempt > 3:
                    logger.error("Giving up after multiple 429/checkpoint errors.")
                    # Let Instaloader handle the final failure
                    return resp
                
                wait = backoff + random.uniform(0, 30)
                logger.warning(f"Rate limit hit ({resp.status_code}). Backing off for {wait:.0f}s (Attempt {attempt}/3)")
                time.sleep(wait)
                backoff *= 2 # Exponential backoff
                continue
            
            return resp
    return wrapper

def apply_anti_detection(session):
    """
    Applies the wrapper to a requests.Session object.
    """
    session.request = instagram_wrap_request(session.request)
