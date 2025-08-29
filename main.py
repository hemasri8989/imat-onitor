import requests
import time
import json
import os
from datetime import datetime
import hashlib
from bs4 import BeautifulSoup
import re

class IMATSlotMonitor:
    def __init__(self):
        # Get these from Replit Secrets
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # IMAT registration URL (you may need to update this)
        self.imat_url = "https://www.nta.ac.in/IMAT"  # Replace with actual IMAT URL
        
        # Session state management
        self.login_url = None  # Will be determined automatically
        self.country_selection_url = None
        self.slot_booking_url = None
        self.is_logged_in = False
        self.country_selected = False
        self.session_initialized = False
        
        # Store previous state to detect changes
        self.previous_state = {}
        
        # Cities to monitor
        self.cities = ['chennai', 'delhi']
        
        # Session for connection pooling and cookie management
        self.session = requests.Session()
        
        # Counter for cache busting
        self.request_counter = 0
        
        # Login credentials (get from environment variables)
        self.username = os.getenv('IMAT_USERNAME')
        self.password = os.getenv('IMAT_PASSWORD')
        
        # Headers to mimic a real browser (will be updated dynamically)
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive',
        }

    def send_telegram_message(self, message):
        """Send notification to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("❌ Telegram credentials not found in environment variables")
            return False
            
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                print("✅ Telegram notification sent successfully")
                return True
            else:
                print(f"❌ Failed to send Telegram message: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error sending Telegram message: {str(e)}")
            return False

    def get_fresh_headers(self, form_submit=False):
        """Generate fresh headers with cache-busting"""
        headers = self.base_headers.copy()
        
        if form_submit:
            # Headers for form submissions
            headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': '/'.join(self.imat_url.split('/')[:3]),
                'Referer': self.imat_url,
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
            })
        else:
            # Regular page load headers
            headers.update({
                'Cache-Control': 'max-age=0',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin' if self.session_initialized else 'none',
                'Sec-Fetch-User': '?1',
            })
            
            if self.session_initialized:
                headers['Referer'] = self.imat_url
        
        return headers

    def login_to_system(self):
        """Handle login process if credentials are provided"""
        if not self.username or not self.password:
            print("⚠️ No login credentials provided - attempting without login")
            return True
        
        try:
            print("🔐 Attempting to login...")
            
            # Get login page first
            response = self.session.get(self.imat_url, headers=self.get_fresh_headers())
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for login form
            login_form = soup.find('form', {'id': 'loginForm'}) or soup.find('form', action=lambda x: x and 'login' in x.lower())
            
            if login_form:
                # Extract form action and method
                action = login_form.get('action', '')
                method = login_form.get('method', 'POST').upper()
                
                if not action.startswith('http'):
                    base_url = '/'.join(self.imat_url.split('/')[:3])
                    action = base_url + action
                
                # Prepare login data
                login_data = {
                    'username': self.username,
                    'password': self.password,
                }
                
                # Add any hidden fields
                for hidden in login_form.find_all('input', type='hidden'):
                    name = hidden.get('name')
                    value = hidden.get('value', '')
                    if name:
                        login_data[name] = value
                
                # Submit login
                login_response = self.session.post(action, data=login_data, headers=self.get_fresh_headers(form_submit=True))
                
                if login_response.status_code == 200:
                    # Check if login was successful (look for indicators)
                    if 'dashboard' in login_response.url.lower() or 'welcome' in login_response.text.lower():
                        print("✅ Login successful")
                        self.is_logged_in = True
                        return True
                    else:
                        print("❌ Login failed - check credentials")
                        return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
        
        return True  # Continue even if no login form found

    def select_country(self, country='India'):
        """Handle country selection if required"""
        try:
            print(f"🌍 Selecting country: {country}")
            
            # Get current page
            response = self.session.get(self.imat_url, headers=self.get_fresh_headers())
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for country selection elements
            country_select = soup.find('select', {'name': lambda x: x and 'country' in x.lower()})
            country_form = soup.find('form', {'id': lambda x: x and 'country' in x.lower() if x else False})
            
            # Method 1: Dropdown selection
            if country_select:
                form = country_select.find_parent('form')
                if form:
                    action = form.get('action', '')
                    if not action.startswith('http'):
                        base_url = '/'.join(self.imat_url.split('/')[:3])
                        action = base_url + action
                    
                    # Find India option value
                    india_option = country_select.find('option', string=re.compile('India', re.I))
                    if india_option:
                        country_data = {country_select.get('name'): india_option.get('value')}
                        
                        # Add hidden fields
                        for hidden in form.find_all('input', type='hidden'):
                            name = hidden.get('name')
                            value = hidden.get('value', '')
                            if name:
                                country_data[name] = value
                        
                        # Submit country selection
                        country_response = self.session.post(action, data=country_data, headers=self.get_fresh_headers(form_submit=True))
                        
                        if country_response.status_code == 200:
                            print("✅ Country selected successfully")
                            self.country_selected = True
                            return True
            
            # Method 2: Look for India link/button
            india_links = soup.find_all('a', string=re.compile('India', re.I))
            for link in india_links:
                href = link.get('href')
                if href:
                    if not href.startswith('http'):
                        base_url = '/'.join(self.imat_url.split('/')[:3])
                        href = base_url + href
                    
                    country_response = self.session.get(href, headers=self.get_fresh_headers())
                    if country_response.status_code == 200:
                        print("✅ Country selected via link")
                        self.country_selected = True
                        return True
            
        except Exception as e:
            print(f"❌ Country selection error: {str(e)}")
        
        return True  # Continue even if no country selection needed

    def navigate_to_slot_page(self):
        """Navigate to the actual slot booking/viewing page"""
        try:
            print("🎯 Navigating to slot booking page...")
            
            response = self.session.get(self.imat_url, headers=self.get_fresh_headers())
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for slot booking links
            slot_keywords = ['slot', 'booking', 'appointment', 'schedule', 'exam center']
            
            for keyword in slot_keywords:
                # Look for links containing these keywords
                links = soup.find_all('a', href=True, string=re.compile(keyword, re.I))
                if not links:
                    links = soup.find_all('a', href=re.compile(keyword, re.I))
                
                for link in links:
                    href = link.get('href')
                    if href:
                        if not href.startswith('http'):
                            base_url = '/'.join(self.imat_url.split('/')[:3])
                            href = base_url + href
                        
                        slot_response = self.session.get(href, headers=self.get_fresh_headers())
                        if slot_response.status_code == 200:
                            self.slot_booking_url = href
                            print(f"✅ Found slot page: {href}")
                            return href
            
            # If no specific slot page found, use the main URL
            return self.imat_url
            
        except Exception as e:
            print(f"❌ Navigation error: {str(e)}")
            return self.imat_url

    def initialize_session(self):
        """Initialize session by handling login and navigation"""
        try:
            print("🚀 Initializing session...")
            
            # Step 1: Login if credentials provided
            if not self.login_to_system():
                return False
            
            # Step 2: Handle country selection
            if not self.select_country():
                return False
            
            # Step 3: Navigate to slot booking page
            self.slot_booking_url = self.navigate_to_slot_page()
            
            self.session_initialized = True
            print("✅ Session initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Session initialization error: {str(e)}")
            return False

    def maintain_session(self):
        """Check and maintain session state"""
        try:
            # Get current page
            current_url = self.slot_booking_url or self.imat_url
            response = self.session.get(current_url, headers=self.get_fresh_headers())
            
            # Check if we've been logged out or redirected
            if ('login' in response.url.lower() or 
                'signin' in response.url.lower() or 
                'country' in response.url.lower()):
                
                print("⚠️ Session expired - reinitializing...")
                return self.initialize_session()
            
            return True
            
        except Exception as e:
            print(f"❌ Session maintenance error: {str(e)}")
            return False

    def get_page_content(self):
        """Fetch the IMAT registration page with session management"""
        self.request_counter += 1
        
        try:
            # Initialize session on first run
            if not self.session_initialized:
                if not self.initialize_session():
                    print("❌ Failed to initialize session")
                    return None
            
            # Maintain session every few requests
            if self.request_counter % 5 == 0:
                if not self.maintain_session():
                    print("❌ Session maintenance failed")
                    return None
            
            # Get the appropriate URL (slot page if available, otherwise main page)
            target_url = self.slot_booking_url or self.imat_url
            
            print(f"🔄 Fetching page (attempt #{self.request_counter})...")
            print(f"🎯 Target URL: {target_url}")
            
            # Make request while maintaining session
            response = self.session.get(
                target_url, 
                headers=self.get_fresh_headers(), 
                timeout=20,
                allow_redirects=True
            )
            
            response.raise_for_status()
            
            # Check if we got redirected back to login/country selection
            if ('login' in response.url.lower() or 
                'signin' in response.url.lower() or 
                'country' in response.url.lower()):
                
                print("⚠️ Detected redirect to login/country page - reinitializing session...")
                if self.initialize_session():
                    # Retry the request
                    target_url = self.slot_booking_url or self.imat_url
                    response = self.session.get(target_url, headers=self.get_fresh_headers(), timeout=20)
                    response.raise_for_status()
                else:
                    return None
            
            print(f"✅ Page fetched successfully (Status: {response.status_code})")
            return response.text
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {str(e)}")
            
            # Try reinitializing session on error
            try:
                print("🔄 Attempting session recovery...")
                if self.initialize_session():
                    time.sleep(3)
                    target_url = self.slot_booking_url or self.imat_url
                    response = self.session.get(target_url, headers=self.get_fresh_headers(), timeout=25)
                    response.raise_for_status()
                    return response.text
                else:
                    return None
            except Exception as retry_e:
                print(f"❌ Recovery failed: {str(retry_e)}")
                return None
                
        except Exception as e:
            print(f"❌ Unexpected error fetching page: {str(e)}")
            return None

    def analyze_slot_status(self, html_content):
        """Analyze the HTML content to detect slot availability"""
        if not html_content:
            return {}
            
        soup = BeautifulSoup(html_content, 'html.parser')
        slot_status = {}
        
        # You'll need to customize these selectors based on the actual IMAT website structure
        # Look for elements that contain city names and their status indicators
        
        for city in self.cities:
            # Common patterns to look for:
            # 1. Colored dots/circles (red, yellow, green)
            # 2. Status text ("Full", "Available", "Limited")
            # 3. Class names indicating status
            
            city_status = self.detect_city_status(soup, city)
            slot_status[city] = city_status
            
        return slot_status

    def detect_city_status(self, soup, city):
        """Detect status for a specific city"""
        # Method 1: Look for colored elements
        city_patterns = [
            f"*[class*='{city}']",
            f"*[id*='{city}']",
            f"*:contains('{city.title()}')",
            f"*:contains('{city.upper()}')"
        ]
        
        for pattern in city_patterns:
            try:
                elements = soup.select(pattern)
                for element in elements:
                    # Check for color indicators in style, class, or data attributes
                    status = self.extract_status_from_element(element)
                    if status:
                        return status
            except:
                continue
        
        # Method 2: Look for general status indicators near city names
        text_content = soup.get_text().lower()
        if city in text_content:
            # Look for status keywords near the city name
            status_keywords = {
                'available': 'green',
                'limited': 'yellow',
                'full': 'red',
                'closed': 'red'
            }
            
            for keyword, color in status_keywords.items():
                if keyword in text_content:
                    return color
        
        return 'unknown'

    def extract_status_from_element(self, element):
        """Extract status from HTML element based on common patterns"""
        # Check class names for color indicators
        class_list = element.get('class', [])
        for class_name in class_list:
            class_lower = class_name.lower()
            if any(color in class_lower for color in ['red', 'green', 'yellow']):
                if 'red' in class_lower:
                    return 'red'
                elif 'green' in class_lower:
                    return 'green'
                elif 'yellow' in class_lower:
                    return 'yellow'
        
        # Check style attribute for colors
        style = element.get('style', '')
        if style:
            if 'red' in style.lower() or '#ff0000' in style.lower() or 'rgb(255,0,0)' in style.lower():
                return 'red'
            elif 'green' in style.lower() or '#00ff00' in style.lower() or 'rgb(0,255,0)' in style.lower():
                return 'green'
            elif 'yellow' in style.lower() or '#ffff00' in style.lower() or 'rgb(255,255,0)' in style.lower():
                return 'yellow'
        
        # Check data attributes
        for attr_name, attr_value in element.attrs.items():
            if 'status' in attr_name.lower() or 'color' in attr_name.lower():
                if any(color in str(attr_value).lower() for color in ['red', 'green', 'yellow']):
                    return str(attr_value).lower()
        
        return None

    def check_for_changes(self, current_status):
        """Check if there are any status changes from red to yellow/green"""
        changes_detected = []
        
        for city, current_color in current_status.items():
            previous_color = self.previous_state.get(city, 'unknown')
            
            # Alert if status changed from red to yellow or green
            if previous_color == 'red' and current_color in ['yellow', 'green']:
                changes_detected.append({
                    'city': city,
                    'previous': previous_color,
                    'current': current_color
                })
                
        return changes_detected

    def format_notification_message(self, changes):
        """Format the notification message"""
        if not changes:
            return None
            
        message = "🚨 <b>IMAT SLOT ALERT!</b> 🚨\n\n"
        message += "📍 <b>Slots may be available in:</b>\n\n"
        
        for change in changes:
            city_name = change['city'].title()
            status_emoji = "🟢" if change['current'] == 'green' else "🟡"
            message += f"{status_emoji} <b>{city_name}</b> - Status changed to {change['current'].upper()}\n"
        
        message += f"\n⏰ <i>Detected at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        message += f"\n🔗 <a href='{self.imat_url}'>Check IMAT Registration</a>"
        
        return message

    def run_monitor(self):
        """Main monitoring loop with enhanced refreshing"""
        print("🚀 Starting IMAT Slot Monitor with Smart Refresh...")
        print(f"📊 Monitoring cities: {', '.join(self.cities)}")
        print(f"🔗 Target URL: {self.imat_url}")
        print("🔄 Auto-refresh enabled with cache-busting")
        
        # Send startup notification
        startup_msg = "🤖 IMAT Slot Monitor started!\n\n📊 Monitoring Chennai and Delhi slots\n⏰ Checking every 5 minutes\n🔄 Smart refresh enabled"
        self.send_telegram_message(startup_msg)
        
        consecutive_failures = 0
        last_successful_check = datetime.now()
        
        while True:
            try:
                current_time = datetime.now()
                print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} - Checking slots (Check #{self.request_counter + 1})...")
                
                # Fetch and analyze page with refreshing
                html_content = self.get_page_content()
                
                if html_content:
                    current_status = self.analyze_slot_status(html_content)
                    consecutive_failures = 0
                    last_successful_check = current_time
                    
                    print(f"📊 Current status: {current_status}")
                    
                    # Check for changes
                    changes = self.check_for_changes(current_status)
                    
                    if changes:
                        print(f"🚨 Changes detected: {changes}")
                        notification_message = self.format_notification_message(changes)
                        if notification_message:
                            self.send_telegram_message(notification_message)
                    else:
                        print("✅ No changes detected")
                    
                    # Update previous state
                    self.previous_state = current_status.copy()
                    
                else:
                    consecutive_failures += 1
                    print(f"❌ Failed to fetch page content (failure #{consecutive_failures})")
                    
                    # Send alert if too many consecutive failures
                    if consecutive_failures >= 3:
                        failure_msg = f"⚠️ IMAT Monitor Alert\n\n❌ Failed to fetch page {consecutive_failures} times in a row\n🕒 Last successful check: {last_successful_check.strftime('%H:%M:%S')}\n\n🔄 Will keep trying..."
                        self.send_telegram_message(failure_msg)
                        consecutive_failures = 0  # Reset to avoid spam
                
                # Dynamic wait time based on time of day
                current_hour = datetime.now().hour
                
                # Check more frequently during business hours (9 AM - 6 PM)
                if 9 <= current_hour <= 18:
                    wait_time = 180  # 3 minutes during business hours
                    print("🕘 Business hours - checking every 3 minutes")
                else:
                    wait_time = 300  # 5 minutes during off hours
                    print("🌙 Off hours - checking every 5 minutes")
                
                print(f"⏳ Waiting {wait_time//60} minutes before next check...")
                time.sleep(wait_time)
                
            except KeyboardInterrupt:
                print("\n🛑 Monitor stopped by user")
                stop_msg = "🛑 IMAT Slot Monitor stopped by user"
                self.send_telegram_message(stop_msg)
                break
            except Exception as e:
                print(f"❌ Error in monitoring loop: {str(e)}")
                error_msg = f"⚠️ IMAT Monitor Error\n\n❌ {str(e)}\n\n🔄 Restarting in 2 minutes..."
                self.send_telegram_message(error_msg)
                time.sleep(120)  # Wait 2 minutes before retrying

def main():
    # Validate environment variables
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        print("❌ Please set TELEGRAM_BOT_TOKEN in environment variables")
        return
    
    if not os.getenv('TELEGRAM_CHAT_ID'):
        print("❌ Please set TELEGRAM_CHAT_ID in environment variables")
        return
    
    # Start monitoring
    monitor = IMATSlotMonitor()
    monitor.run_monitor()

if __name__ == "__main__":
    main()

# Keep the service alive on Render
import threading
import http.server
import socketserver

def start_health_server():
    """Start a simple HTTP server for Render health checks"""
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'IMAT Monitor is running!')
    
    try:
        port = int(os.getenv('PORT', 8080))
        with socketserver.TCPServer(("", port), HealthHandler) as httpd:
            print(f"Health server running on port {port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

# Start health server in background thread
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()

# Run main function
main()
