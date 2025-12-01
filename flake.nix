{
  description = "Docker image for classroom: sshd + code-server + g++";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        dockerTools = pkgs.dockerTools;
      in {
        packages.default = dockerTools.buildImage {
          name = "nix-class-dev-1";
          #tag = "latest";

          # use a small base to keep things predictable
          fromImage = dockerTools.pullImage {
            imageName = "debian:bookworm-slim";
            imageDigest = "sha256:936abff852736f951dab72d91a1b6337cf04217b2a77a5eaadc7c0f2f1ec1758";
          };

          # packages included in the image root filesystem
          copyToRoot = pkgs.buildEnv {
            name = "class-packages";
            paths = with pkgs; [
                gcc
                gdb
                cmake
                git
                openssh
                sudo
                code-server
            ];
            };

          # Ports we will expose:
          # 22 -> sshd
          # 8443 -> code-server (https)
          config = {
            Cmd = [ "/usr/local/bin/container-entrypoint.sh" ];
            ExposedPorts = {
              "22"   = {};
              "8443" = {};
            };
          };

          # Add helpers and entrypoint into image
          extraCommands = ''
            # create directories normally expected by sshd
            mkdir -p $out/var/run/sshd
            mkdir -p $out/etc
            # put entrypoint and utilities
            mkdir -p $out/usr/local/bin
            cat > $out/usr/local/bin/create_users_from_list.sh <<'EOF'
            #!/bin/sh
            set -eu
            USERS_FILE="/etc/users.csv"
            [ -f "$USERS_FILE" ] || { echo "no users file: $USERS_FILE"; exit 0; }

            # CSV format:
            # username,uid[,pubkey]
            # lines starting with # or empty are ignored
            while IFS= read -r line || [ -n "$line" ]; do
              case "$line" in
                 ""|\#*) continue ;;

              esac
              # split by comma, allow optional 3rd field (pubkey)
              username=$(printf "%s" "$line" | awk -F, '{print $1}' | tr -d '[:space:]')
              uid=$(printf "%s" "$line" | awk -F, '{print $2}' | tr -d '[:space:]')
              pubkey=$(printf "%s" "$line" | awk -F, '{print $3}')
              [ -z "$username" ] && continue

              if id "$username" >/dev/null 2>&1; then
                echo "user $username already exists; skipping"
                continue
              fi

              if [ -n "$uid" ]; then
                # try numeric uid, otherwise create without explicit uid
                case "$uid" in
                  ""|*[!0-9]*)
                    useradd -m -s /bin/bash "$username" || true
                    ;;
                  *)
                    useradd -m -s /bin/bash -u "$uid" "$username" || true
                    ;;
                esac
              else
                useradd -m -s /bin/bash "$username" || true
              fi

              mkdir -p /home/"$username"/.ssh
              chmod 700 /home/"$username"/.ssh
              if [ -n "$pubkey" ]; then
                echo "$pubkey" > /home/"$username"/.ssh/authorized_keys
                chmod 600 /home/"$username"/.ssh/authorized_keys
                chown -R "$username":"$username" /home/"$username"/.ssh
              else
                # lock password by default: admin can set a password later if needed
                passwd -l "$username" 2>/dev/null || true
              fi

              # give minimal sudo so they can install in /tmp if necessary (optional)
              usermod -aG sudo "$username" 2>/dev/null || true

              echo "created user $username"
            done <<'CSV_EOF'
            $(cat /etc/hosts >/dev/null 2>&1 || true)
            CSV_EOF
            EOF

            chmod +x $out/usr/local/bin/create_users_from_list.sh

            cat > $out/usr/local/bin/container-entrypoint.sh <<'EOF'
            #!/bin/sh
            set -e

            # if users.csv exists (mounted to /etc/users.csv), create users
            if [ -f /etc/users.csv ]; then
              /usr/local/bin/create_users_from_list.sh || true
            fi

            # ensure ssh allows pubkey and password for convenience; admin can tweak later
            sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
            sed -i 's/^#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config || true
            sed -i 's/^UsePAM yes/UsePAM no/' /etc/ssh/sshd_config || true

            # start sshd (foreground) and code-server (background)
            # start code-server with no-auth (internal network) — bind to 0.0.0.0:8443
            # IMPORTANT: If accessible over WAN, put a reverse proxy with TLS+auth in front.
            nohup sh -c "code-server --host 0.0.0.0 --port 8443 --auth none" >/var/log/code-server.log 2>&1 &

            # run sshd in foreground (docker will keep container up)
            exec /usr/sbin/sshd -D
            EOF

            chmod +x $out/usr/local/bin/container-entrypoint.sh

            # create a default /etc/users.csv example
            mkdir -p $out/etc
            cat > $out/etc/users.csv <<'CSV'
            # example: username,uid[,pubkey]
            # alice,1001,ssh-rsa AAAAB3...
            CSV
          '';
        };
      });
}
