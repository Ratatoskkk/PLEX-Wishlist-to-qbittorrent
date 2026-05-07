import psutil
import time
import datetime
import os
import sys

def find_app_pid():
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = p.info.get('cmdline')
            if cmdline:
                # Check if it's running app.py
                cmd_str = ' '.join(cmdline).lower()
                if 'python' in cmd_str and 'app.py' in cmd_str:
                    return p
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def main():
    print("Searching for PlexAither app.py process...")
    process = find_app_pid()
    
    if not process:
        print("Could not find a running app.py process. Please make sure the app is running first.")
        sys.exit(1)
        
    print(f"Found app.py running at PID {process.pid}. Starting performance monitoring (every 10 minutes)...")
    print("Press Ctrl+C to stop tracking.")
    
    log_path = os.path.join(os.path.dirname(__file__), 'performance.log')
    
    try:
        # Initialize cpu_percent
        process.cpu_percent(interval=None)
        
        while True:
            # Check if process is still running
            if not process.is_running():
                print("\nApp process has terminated. Stopping monitor.")
                break
                
            # Block for 1 second to get a meaningful CPU usage snapshot
            cpu_percent = process.cpu_percent(interval=1.0)
            mem_info = process.memory_info()
            ram_mb = mem_info.rss / (1024 * 1024)
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            log_line = f"{now} | CPU: {cpu_percent:05.2f}% | RAM: {ram_mb:06.2f} MB\n"
            with open(log_path, 'a') as f:
                f.write(log_line)
                
            print(f"Logged: {log_line.strip()}")
            
            # Sleep for 10 minutes (600 seconds) - 1 second used for cpu_percent
            time.sleep(599)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")

if __name__ == "__main__":
    main()
