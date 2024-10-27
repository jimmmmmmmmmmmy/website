import os
import plistlib
from pathlib import Path
import subprocess
import logging

class LoginItemManager:
    def __init__(self):
        self.app_name = "OpenAir"
        self.launch_agent_dir = os.path.expanduser("~/Library/LaunchAgents")
        self.plist_name = f"com.user.{self.app_name.lower()}.plist"
        self.plist_path = os.path.join(self.launch_agent_dir, self.plist_name)
        
        # Get absolute path of the running script
        self.script_path = os.path.abspath(__file__)
        self.python_path = subprocess.check_output(["which", "python3"]).decode().strip()
        
        # Create LaunchAgents directory if it doesn't exist
        Path(self.launch_agent_dir).mkdir(parents=True, exist_ok=True)
        
        # Add logging
        logging.info(f"LoginItemManager initialized with plist_path: {self.plist_path}")

    def isLoginItemEnabled(self):
        """Check if launch agent plist exists and is loaded."""
        try:
            # Check if plist exists
            if not os.path.exists(self.plist_path):
                logging.info("Plist file does not exist")
                return False
                
            # Check if launch agent is loaded using launchctl list
            result = subprocess.run(
                ["launchctl", "list"], 
                capture_output=True, 
                text=True
            )
            
            is_enabled = f"com.user.{self.app_name.lower()}" in result.stdout
            logging.info(f"Login item enabled status: {is_enabled}")
            return is_enabled
            
        except Exception as e:
            logging.error(f"Error checking login item status: {e}")
            return False

    def toggleLoginItem_(self, sender):
        """Toggle launch agent."""
        try:
            is_enabled = sender.state()
            logging.info(f"Toggling login item. New state requested: {is_enabled}")
            
            if is_enabled:
                self._create_and_load_launch_agent()
            else:
                self._unload_and_remove_launch_agent()
                
            # Verify the change was successful
            actual_state = self.isLoginItemEnabled()
            logging.info(f"Toggle completed. Actual state: {actual_state}")
            
            # If the actual state doesn't match what was requested, log an error
            if actual_state != is_enabled:
                logging.error("Failed to set desired login item state")
                
            return actual_state
            
        except Exception as e:
            logging.error(f"Error toggling login item: {e}")
            return False

    # Update the _create_and_load_launch_agent method in login_item_manager.py
    def _create_and_load_launch_agent(self):
        """Create and load the launch agent plist."""
        try:
            # Get the app's directory
            app_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Create the plist content with additional keys
            plist_content = {
                "Label": f"com.user.{self.app_name.lower()}",
                "ProgramArguments": [
                    self.python_path,
                    os.path.join(app_dir, "app.py")
                ],
                "RunAtLoad": True,
                "KeepAlive": False,
                "ProcessType": "Interactive",
                "StandardErrorPath": os.path.expanduser(f"~/Library/Logs/{self.app_name}.err.log"),
                "StandardOutPath": os.path.expanduser(f"~/Library/Logs/{self.app_name}.out.log"),
                "WorkingDirectory": app_dir,
                # Add a small delay to allow for system tray to be ready
                "StartInterval": 3,
                # Prevent multiple instances
                "AbandonProcessGroup": True
            }

            # First, try to unload any existing instance
            if os.path.exists(self.plist_path):
                subprocess.run(["launchctl", "unload", self.plist_path], 
                            capture_output=True, check=False)
                os.remove(self.plist_path)

            # Write the new plist file
            with open(self.plist_path, 'wb') as f:
                plistlib.dump(plist_content, f)

            # Set proper permissions
            os.chmod(self.plist_path, 0o644)

            # Load the launch agent
            result = subprocess.run(["launchctl", "load", self.plist_path], 
                                capture_output=True, text=True)
            
            if result.returncode != 0:
                logging.error(f"Failed to load launch agent: {result.stderr}")
                raise Exception(f"Failed to load launch agent: {result.stderr}")
            
            logging.info("Successfully created and loaded launch agent")
            
        except Exception as e:
            logging.error(f"Error creating launch agent: {e}")
            raise

    def _unload_and_remove_launch_agent(self):
        """Unload and remove the launch agent plist."""
        try:
            if os.path.exists(self.plist_path):
                # Unload the launch agent
                result = subprocess.run(["launchctl", "unload", self.plist_path], 
                                    capture_output=True, text=True)
                if result.returncode != 0:
                    logging.error(f"Failed to unload launch agent: {result.stderr}")
                
                # Remove the plist file
                os.remove(self.plist_path)
                logging.info("Successfully unloaded and removed launch agent")
            else:
                logging.info("No launch agent file exists to remove")
                
        except Exception as e:
            logging.error(f"Error removing launch agent: {e}")
            raise