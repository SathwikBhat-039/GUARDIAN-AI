import subprocess
import threading
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_backend():
    print("Starting FastAPI Backend...")
    subprocess.run([sys.executable, "server.py"], cwd=BASE_DIR)

def run_frontend():
    print("Starting Vite Frontend...")
    subprocess.run(["npm", "run", "dev"], cwd=os.path.join(BASE_DIR, "avtar-frontend"), shell=True)

if __name__ == "__main__":
    # Start backend in a thread
    backend_thread = threading.Thread(target=run_backend)
    backend_thread.daemon = True
    backend_thread.start()

    # Give backend a moment to start
    time.sleep(2)

    # Start frontend in the main thread
    try:
        run_frontend()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
