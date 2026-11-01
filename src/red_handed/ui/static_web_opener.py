from selenium import webdriver
from pathlib import Path

class StaticWebOpener:
    def __init__(self):
        self._html_path = Path(__file__).parent / "index.html"
        self.driver = None
    
    def open(self):
        html_url = self._html_path.resolve().as_uri()
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(html_url)
        #input("Enter:")
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
        
        
