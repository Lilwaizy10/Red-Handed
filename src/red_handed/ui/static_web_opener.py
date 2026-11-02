from selenium import webdriver
from pathlib import Path

class StaticWebOpener:
    def __init__(self):
        self._html_path = Path(__file__).parent / "index.html"
        self.driver = None
        self.browser_pid = None
    
    def open(self):
        html_url = self._html_path.resolve().as_uri()
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(html_url)
    
    def getPID(self):
        if self.driver is None:
            return
        self.browser_pid = self.driver.capabilities.get("goog:processID")
        
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.browser_pid = None
        
        
