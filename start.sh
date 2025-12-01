#!/bin/sh
echo "Starting GadzIT C++ IDE with interactive shell support..."
echo "This may take a moment to download dependencies via Nix..."

nix-shell -p python3 python3Packages.flask python3Packages.flask-socketio python3Packages.ptyprocess python3Packages.eventlet python3Packages.flask-cors gcc --run "python3 app.py"
