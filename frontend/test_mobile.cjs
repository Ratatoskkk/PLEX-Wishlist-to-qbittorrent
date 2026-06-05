const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 375, height: 812 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  
  try {
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    
    // Wait for data to load if there's an API call
    await page.waitForTimeout(2000); 

    await page.screenshot({ 
      path: 'C:\\Users\\doguk\\.gemini\\antigravity\\brain\\e0e58f16-90b8-4dda-bca5-59dfc05a7a13\\mobile_test.png', 
      fullPage: true 
    });
    console.log('Screenshot saved to mobile_test.png in artifacts dir');
  } catch (error) {
    console.error('Error during test:', error);
  } finally {
    await browser.close();
  }
})();
