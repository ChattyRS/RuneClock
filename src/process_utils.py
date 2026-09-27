import psutil
import subprocess

def is_process_running(executable_name):
    '''
    Check whether an executable is running.
    '''
    for proc in psutil.process_iter(['name']):
        try:
            # Compare process name case-insensitively
            if proc.info['name'].lower() == executable_name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def kill_process_by_name(executable_name):
    """
    Finds and terminates all running instances of an executable name.
    Example: kill_process_by_name("notepad.exe") or "vlc"
    """
    # Iterate through all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # Check if the process name matches (case-insensitive)
            if proc.info['name'].lower() == executable_name.lower():
                print(f"Terminating {proc.info['name']} (PID: {proc.info['pid']})...")
                
                # Terminate the process gently
                proc.terminate()
                
                # Wait up to 3 seconds for it to exit; if it fails, force kill it
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    print(f"Process PID {proc.info['pid']} refused to close. Force killing...")
                    proc.kill()
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Safe catch for system processes or processes that closed mid-loop
            continue

def run_batch_script(batch_file_path):
    '''
    Run a batch file in a new independent console window
    '''
    process = subprocess.Popen(
        ["cmd.exe", "/c", batch_file_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )