import socketio

# 1. Enable logger to see handshake details
# 2. request_timeout sets how long to wait before complaining
sio = socketio.Client(logger=True, engineio_logger=True, request_timeout=10)

@sio.event
def connect():
    print("✅ Connected to server")
    
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        cout << "Hello from debug client" << endl;
        return 0;
    }
    """
    print("📤 Sending run_code...")
    # No callback here, just fire and forget for now
    sio.emit('run_code', {'code': code})
    print("... run_code sent.")

@sio.event
def output(data):
    print(f"📥 Received output: {data}")

@sio.event
def connect_error(data):
    print(f"❌ Connection failed: {data}")

@sio.event
def disconnect():
    print("❌ Disconnected from server")

if __name__ == '__main__':
    try:
        # 3. Force 'websocket' transport. Fly.io handles this better than polling.
        sio.connect(
            'https://backend-snowy-wildflower-8765.fly.dev', 
            transports=['websocket'] 
        )
        sio.wait()
    except Exception as e:
        print(f"Exception: {e}")