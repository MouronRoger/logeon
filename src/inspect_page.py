import asyncio
from playwright.async_api import async_playwright
import json

async def log_request(request):
    if 'api' in request.url or 'logeion' in request.url:
        print(f"\nRequest: {request.method} {request.url}")

async def log_response(response):
    if 'api' in response.url or 'logeion' in response.url:
        print(f"\nResponse: {response.status} {response.url}")
        try:
            body = await response.text()
            print(f"Content preview: {body[:200]}")
        except:
            print("Could not get response body")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Monitor network requests
        page.on('request', log_request)
        page.on('response', log_response)
        
        print("Navigating to page...")
        await page.goto("https://logeion.uchicago.edu/ἀγαθός", wait_until='networkidle')
        
        print("\nWaiting for content to load...")
        # Wait for Angular to initialize
        await page.wait_for_selector('[ng-view]', state='attached', timeout=10000)
        # Wait a bit longer for content to load
        await page.wait_for_timeout(5000)
        
        # Try to find any content
        content = await page.evaluate("""
            () => {
                const mainContent = document.querySelector('div[ng-view]');
                return mainContent ? mainContent.innerHTML : 'No content found';
            }
        """)
        
        print("\nMain content:")
        print(content[:1000])
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main()) 