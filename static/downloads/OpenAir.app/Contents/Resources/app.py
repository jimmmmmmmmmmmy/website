import rumps
import requests
import time
from AppKit import NSApplication, NSBundle
from detail_window import DetailWindow
from search_city_window import SearchCityWindow
import logging
import re
import json
from datetime import datetime, timedelta
import sqlite3
import socket
import sys
import os
import tempfile

class SingleInstance:
    def __init__(self):
        self.lockfile = os.path.join(tempfile.gettempdir(), 'openair.lock')
        self.sock = None

    def cleanup(self):
        """Clean up the lock file and socket."""
        try:
            if self.sock:
                self.sock.close()
            if os.path.exists(self.lockfile):
                os.unlink(self.lockfile)
        except Exception as e:
            logging.error(f"Error cleaning up single instance: {e}")

    def is_running(self):
        """Check if another instance is running."""
        try:
            # Clean up any stale lock file
            if os.path.exists(self.lockfile):
                # Check if the process is actually running
                with open(self.lockfile, 'r') as f:
                    pid = int(f.read().strip())
                try:
                    # Check if process is actually running
                    os.kill(pid, 0)
                except OSError:
                    # Process is not running, clean up stale lock file
                    logging.info("Found stale lock file, cleaning up")
                    self.cleanup()
                else:
                    # Process is running
                    return True

            # Create new lock file
            with open(self.lockfile, 'w') as f:
                f.write(str(os.getpid()))

            return False

        except Exception as e:
            logging.error(f"Error in single instance check: {e}")
            # If anything goes wrong, assume it's safe to start
            return False

    def __del__(self):
        self.cleanup()

info = NSBundle.mainBundle().infoDictionary()
info['LSUIElement'] = '1'

logging.basicConfig(filename='openair.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def is_app_running():
    """Check if another instance is running using a socket."""
    try:
        # Try to create a socket with a unique name
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Use abstract namespace for socket
        sock.bind('\0openair_instance_check')
        # Keep the socket open - it will be automatically closed when the app exits
        return False
    except socket.error:
        return True
    
class OpenAir(rumps.App):
    def __init__(self):
        super(OpenAir, self).__init__("AQI")
        self.instance_manager = SingleInstance()
        self.quit_button = "Quit OpenAir"
        self.token = "09975e52f3b1bf07469353eabdeb513092b85f9d"
        self.base_url = "https://api.waqi.info"
        self.user_ip = self.get_user_ip()
        self.current_city = self.get_location_from_ip() or "San Francisco"
        self.current_city_name = self.get_city_name_ip()
        self.temperature_unit = "°F"
        self.format_options = {
            'AQI': True,
            'PM2.5': False,
            'PM10': False,
            'O\u2083': False,
            'NO\u2082': False,
            'SO\u2082': False,
            'CO': False,
            'Temperature': True,
            'Humidity': True,
            'Wind': False
        }
        self.temperature_unit = '°F'
        self.setup_menu()
        self.cached_data = None
        self.last_update_time = 0
        self.db_connection = sqlite3.connect('aqi_data.db')
        self.create_table()
        self.update_interval = 300  # 1 hour in seconds
        self.timer = rumps.Timer(self.update, self.update_interval)
        self.timer.start()
        self.update(None)  # Initial update
        self.detail_window = DetailWindow.alloc().initWithApp_(self) 
        self.prune_old_data()  # Prune old data on startup

    def create_table(self):
        cursor = self.db_connection.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS aqi_data (
            timestamp TEXT PRIMARY KEY,
            city TEXT,
            aqi INTEGER,
            pm25 REAL,
            pm10 REAL,
            o3 REAL,
            no2 REAL,
            so2 REAL,
            co REAL,
            temperature REAL,
            pressure REAL,
            humidity REAL,
            wind REAL
        )
        ''')
        self.db_connection.commit()

    def setup_menu(self):
        format_menu = rumps.MenuItem("Format Options")
        for option in self.format_options:
            if option == 'Temperature':
                temp_menu = rumps.MenuItem("Temperature", callback=self.toggle_format_option)
                temp_menu.add(rumps.MenuItem("°F", callback=self.set_temperature_unit))
                temp_menu.add(rumps.MenuItem("°C", callback=self.set_temperature_unit))

                format_menu.add(temp_menu)
            else:
                item = rumps.MenuItem(option, callback=self.toggle_format_option)
                format_menu.add(item)

        format_menu.add(None)  # Separator
        format_menu.add(rumps.MenuItem("Reset", callback=self.reset_format_options))
        
        self.menu = ["Search City", format_menu, "Details...", None]
        self.update_format_menu()  # Call this to set initial states

    def toggle_format_option(self, sender):
        self.format_options[sender.title] = not sender.state
        self.update_format_menu()
        self.update(None)

    def reset_format_options(self, _):
        for option in self.format_options:
            self.format_options[option] = option in ['AQI', 'Temperature', 'Humidity']
        self.temperature_unit = '°F'
        self.update_format_menu()
        self.update(None)

    def update_format_menu(self):
        format_menu = self.menu["Format Options"]
        for item in format_menu.values():
            if isinstance(item, rumps.MenuItem):
                if item.title in self.format_options:
                    item.state = self.format_options[item.title]
                    if item.title == "Temperature":
                        for subitem in item.values():
                            subitem.state = subitem.title == self.temperature_unit

    def get_user_ip(self):
        try:
            response = requests.get('https://api.ipify.org?format=json')
            return response.json()['ip']
        except:
            return None
        
    def get_city_name_ip(self):
        ip = self.get_user_ip()
        if ip:
            url = f"{self.base_url}/feed/here/?token={self.token}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    return data['data']['city']['name']
        return None

    def get_location_from_ip(self):
        if self.user_ip:
            url = f"{self.base_url}/feed/here/?token={self.token}"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'ok':
                        city = data['data']['city']
                        if isinstance(city, dict):
                            if 'geo' in city:
                                lat, lon = city['geo']
                                return f"{lat:.3f};{lon:.3f}"  # Return rounded coordinates
                            return city.get('name')
                        return city
            except Exception as e:
                logging.error(f"Error getting location from IP: {e}")
        return None

    def applicationSupportsSecureRestorableState_(self, app):
        return True
    
    def parse_api_data(self, data):
        iaqi = data.get('iaqi', {})
        forecast = data.get('forecast', {}).get('daily', {})
        
        visualization_data = {
            'PM2.5': {'current': iaqi.get('pm25', {}).get('v', 0), 'forecast': forecast.get('pm25', [])},
            'PM10': {'current': iaqi.get('pm10', {}).get('v', 0), 'forecast': forecast.get('pm10', [])},
            'O3': {'current': iaqi.get('o3', {}).get('v', 0), 'forecast': forecast.get('o3', [])},
            'NO2': {'current': iaqi.get('no2', {}).get('v', 0), 'forecast': []},
            'SO2': {'current': iaqi.get('so2', {}).get('v', 0), 'forecast': []},
            'CO': {'current': iaqi.get('co', {}).get('v', 0), 'forecast': []},
            'Temp.': {'current': iaqi.get('t', {}).get('v', 0), 'forecast': []},
            'Pressure': {'current': iaqi.get('p', {}).get('v', 0), 'forecast': []},
            'Humidity': {'current': iaqi.get('h', {}).get('v', 0), 'forecast': []},
            'Wind': {'current': iaqi.get('w', {}).get('v', 0), 'forecast': []},
            'UVI': {'current': iaqi.get('uvi', {}).get('v', 0), 'forecast': forecast.get('uvi', [])}
        }
        
        return {
            'aqi': data.get('aqi', 0),
            'iaqi': iaqi,
            'city': data.get('city', {}),
            'visualization_data': visualization_data,
            'raw_data': data  # Include the full raw data for potential future use
        }

    def get_aqi_data(self, location):
        logging.info(f"get_aqi_data called with location: {location}")
        
        if not location:
            logging.error("Location is empty or None")
            return None
        

        
        # Check if the location is in the format of coordinates
        if re.match(r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?$', location):
            # Round coordinates to 3 decimal places
            try:
                lat, lon = map(float, location.split(','))
            except ValueError:
                logging.error(f"Invalid coordinate format: {location}")
                return None
            rounded_location = f"{lat:.3f};{lon:.3f}"
            url = f"{self.base_url}/feed/geo:{rounded_location}/?token={self.token}"
            logging.info(f"Using rounded coordinate-based URL: {url}")
        else:
            # Use the location name directly
            url = f"{self.base_url}/feed/geo:{location}/?token={self.token}"
            logging.info(f"Using city-based URL: {url}")
        
        
        logging.info(f"Sending GET request to: {url}")
        response = requests.get(url, timeout=10)
        logging.info(f"Received response with status code: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        logging.info(f"Parsed JSON response: {json.dumps(data, indent=2)}")
        
        if data['status'] == 'ok':
            self.store_aqi_data(data['data'])
            return data['data']
        else:
            logging.error(f"API returned non-OK status: {data['status']}")
            return None
        
    def store_aqi_data(self, data):
        cursor = self.db_connection.cursor()
        current_time = datetime.now()
        current_hour = current_time.strftime('%Y-%m-%d %H')
        
        try:
            # Check if we already have data for this hour
            cursor.execute('''
            SELECT COUNT(*) FROM aqi_data 
            WHERE strftime('%Y-%m-%d %H', timestamp) = ?
            ''', (current_hour,))
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Update existing record for this hour
                cursor.execute('''
                UPDATE aqi_data 
                SET timestamp = ?, 
                    city = ?,
                    aqi = ?, 
                    pm25 = ?, 
                    pm10 = ?, 
                    o3 = ?, 
                    no2 = ?, 
                    so2 = ?, 
                    co = ?, 
                    temperature = ?, 
                    pressure = ?, 
                    humidity = ?, 
                    wind = ?
                WHERE strftime('%Y-%m-%d %H', timestamp) = ?
                ''', (
                    current_time.isoformat(),
                    str(data['city']['name']),
                    int(data['aqi']),
                    float(data.get('iaqi', {}).get('pm25', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('pm10', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('o3', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('no2', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('so2', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('co', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('t', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('p', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('h', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('w', {}).get('v', 0) or 0),
                    current_hour
                ))
            else:
                # Insert new record
                cursor.execute('''
                INSERT INTO aqi_data
                (timestamp, city, aqi, pm25, pm10, o3, no2, so2, co, temperature, pressure, humidity, wind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    current_time.isoformat(),
                    str(data['city']['name']),
                    int(data['aqi']),
                    float(data.get('iaqi', {}).get('pm25', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('pm10', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('o3', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('no2', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('so2', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('co', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('t', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('p', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('h', {}).get('v', 0) or 0),
                    float(data.get('iaqi', {}).get('w', {}).get('v', 0) or 0)
                ))
            
            self.db_connection.commit()
            logging.info(f"Successfully stored/updated data for hour {current_hour}")
        except Exception as e:
            logging.error(f"Error storing data: {str(e)}")
            self.db_connection.rollback()

    def get_stored_data(self):
        cursor = self.db_connection.cursor()
        twenty_four_hours_ago = (datetime.now() - timedelta(hours=24)).isoformat()
   
        # Get one reading per hour for the last 24 hours
        cursor.execute('''
        WITH HourlyData AS (
            SELECT *,
                strftime('%Y-%m-%d %H', timestamp) as hour,
                ROW_NUMBER() OVER (PARTITION BY strftime('%Y-%m-%d %H', timestamp) 
                                    ORDER BY timestamp DESC) as rn
            FROM aqi_data
            WHERE timestamp > ?
        )
        SELECT timestamp, city, aqi, pm25, pm10, o3, no2, so2, co, 
            temperature, pressure, humidity, wind
        FROM HourlyData
        WHERE rn = 1
        ORDER BY timestamp ASC
        ''', (twenty_four_hours_ago,))

        data = cursor.fetchall()
        logging.info(f"Retrieved {len(data)} hourly readings from the last 24 hours")
        return data
    
    def clean_hourly_duplicates(self):
        """Keep only the most recent reading for each hour."""
        cursor = self.db_connection.cursor()
        
        try:
            # Delete all but the most recent reading for each hour
            cursor.execute('''
            DELETE FROM aqi_data
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM aqi_data
                GROUP BY strftime('%Y-%m-%d %H', timestamp)
            )
            ''')
            rows_deleted = cursor.rowcount
            self.db_connection.commit()
            logging.info(f"Cleaned up {rows_deleted} duplicate hourly readings")
        except Exception as e:
            logging.error(f"Error cleaning hourly duplicates: {str(e)}")
            self.db_connection.rollback()

    def get_coordinates_for_city(self, city):
        # This is a placeholder method. In a real implementation, you would use a geocoding service.
        # For now, we'll return None, but you should implement this properly.
        logging.info(f"Attempting to get coordinates for {city}")
        return None  # Replace this with actual geocoding logic
    
    def update(self, _):
        current_time = time.time()
        if current_time - self.last_update_time > self.update_interval:
            logging.info(f"Updating data for {self.current_city}")
            self.cached_data = self.get_aqi_data(self.current_city)
            if self.cached_data:
                self.store_aqi_data(self.cached_data)
            self.last_update_time = current_time
            self.prune_old_data()  # Prune old data after each update
        
        if self.cached_data:
            logging.info("Data update successful, updating title")
            self.update_title()
        else:
            logging.error("Failed to update data")
            self.title = "Failed to update"

    def update_title(self):
        title_parts = []
        data = self.cached_data
        iaqi = data.get('iaqi', {})

        #if self.format_options['City']:
        #    title_parts.append(self.current_city_name)
        if self.format_options['AQI']:
            title_parts.append(f"AQI: {data['aqi']}")
        if self.format_options['PM2.5']:
            title_parts.append(f"PM2.5: {iaqi.get('pm25', {}).get('v', 'N/A')}")
        if self.format_options['PM10']:
            title_parts.append(f"PM10: {iaqi.get('pm10', {}).get('v', 'N/A')}")
        if self.format_options['O\u2083']:
            title_parts.append(f"O\u2083: {iaqi.get('o3', {}).get('v', 'N/A')}")
        if self.format_options['NO\u2082']:
            title_parts.append(f"NO\u2082 {iaqi.get('no2', {}).get('v', 'N/A')}")
        if self.format_options['SO\u2082']:
            title_parts.append(f"SO\u2082 {iaqi.get('so2', {}).get('v', 'N/A')}")
        if self.format_options['CO']:
            title_parts.append(f"CO {iaqi.get('co', {}).get('v', 'N/A')}")
        if self.format_options['Temperature']:
            temp_c = iaqi.get('t', {}).get('v', 'N/A')
            if temp_c != 'N/A':
                if self.temperature_unit == "°C":
                    temp_display = f"{temp_c}°C"
                else:
                    temp_f = (temp_c * 9/5) + 32
                    temp_display = f"{temp_f:.1f}°F"
            else:
                temp_display = 'N/A'
            title_parts.append(temp_display)
        if self.format_options['Humidity']:
            title_parts.append(f"RH: {iaqi.get('h', {}).get('v', 'N/A')}%")
        if self.format_options['Wind']:
            title_parts.append(f"{iaqi.get('w', {}).get('v', 'N/A')}m/s")

        self.title = " | ".join(title_parts)

    @rumps.clicked("About")
    def search_city(self, _):
        response = rumps.Window('Enter city name:', 'Search City', default_text=self.current_city).run()
        if response.clicked:
            new_city = response.text
            data = self.get_aqi_data(new_city)
            if data:
                self.current_city = new_city
                self.cached_data = data
                self.update(None)
            else:
                rumps.notification("Error", f"Could not find data for {new_city}", "")

    @rumps.clicked("Search City")
    def search_city(self, _):
        if self.search_window is None:
            self.search_window = SearchCityWindow.alloc().initWithApp_(self)
        self.search_window.showWindow()

    @rumps.clicked("Format Options", "Temperature", "°C")
    @rumps.clicked("Format Options", "Temperature", "°F")
    def set_temperature_unit(self, sender):
        self.temperature_unit = sender.title
        self.update_format_menu()
        self.update(None)

    @rumps.clicked("Details...")
    def show_details(self, _):
        if self.cached_data:
            parsed_data = self.parse_api_data(self.cached_data)
            aqi = parsed_data['aqi']
            iaqi = parsed_data['iaqi']
            details = f"City: {self.current_city}\nAQI: {self.cached_data['aqi']}\n"
            details += f"AQI: {aqi}\n"
            details += f"PM2.5: {iaqi.get('pm25', {}).get('v', 'N/A')}\n"
            details += f"PM10: {iaqi.get('pm10', {}).get('v', 'N/A')}\n"
            details += f"O\u2083: {iaqi.get('o3', {}).get('v', 'N/A')}\n"
            details += f"NO\u2082: {iaqi.get('no2', {}).get('v', 'N/A')}\n"
            details += f"SO\u2082: {iaqi.get('so2', {}).get('v', 'N/A')}\n"
            details += f"CO: {iaqi.get('co', {}).get('v', 'N/A')}\n"
            details += f"Temperature: {iaqi.get('t', {}).get('v', 'N/A')}°C\n"
            details += f"Humidity: {iaqi.get('h', {}).get('v', 'N/A')}%\n"
            details += f"Wind: {iaqi.get('w', {}).get('v', 'N/A')} m/s"

            # Is it possible to pass temperature_unit to details?
            self.detail_window.showWindow_withText_andData_andTempUnit_("AQI Details", details, self.cached_data, self.temperature_unit)
        else:
            rumps.notification("Error", "Failed to fetch AQI data", "")

    def terminate(self):
        """Clean up when app terminates."""
        self.instance_manager.cleanup()
        super(OpenAir, self).terminate()

    def prune_old_data(self):
        """Remove data older than 24 hours."""
        cursor = self.db_connection.cursor()
        twenty_four_hours_ago = (datetime.now() - timedelta(hours=24)).isoformat()
        
        try:
            cursor.execute('DELETE FROM aqi_data WHERE timestamp < ?', (twenty_four_hours_ago,))
            rows_deleted = cursor.rowcount
            self.db_connection.commit()
            logging.info(f"Pruned {rows_deleted} readings older than 24 hours")
            
            # After pruning, clean up any remaining hourly duplicates
            self.clean_hourly_duplicates()
        except Exception as e:
            logging.error(f"Error pruning old data: {str(e)}")
            self.db_connection.rollback()


if __name__ == "__main__":
    instance = SingleInstance()
    
    if instance.is_running():
        print("OpenAir is already running")
        sys.exit(0)
    
    try:
        app = OpenAir()
        app.run()
    except Exception as e:
        logging.error(f"Error running app: {e}")
        instance.cleanup()
        raise
    finally:
        instance.cleanup()