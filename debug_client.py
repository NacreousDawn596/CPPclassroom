import socketio
import time

sio = socketio.Client()

@sio.event
def connect():
    print("Connected to server")
    # Send run_code event
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        cout << "Hello from debug client" << endl;
        return 0;
    }
    """
    print("Sending run_code...")
    sio.emit('run_code', {'code': code})

@sio.event
def output(data):
    print(f"Received output: {repr(data)}")

@sio.event
def disconnect():
    print("Disconnected from server")

if __name__ == '__main__':
    try:
        sio.connect('http://localhost:5550')
        sio.wait()
    except Exception as e:
        print(f"Connection failed: {e}")
