#!/usr/bin/env python3
import argparse
import os
import zipfile

def package(target, bin_dir, suffix, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    srv_bin = os.path.join(bin_dir, f"stat_server{suffix}")
    cli_bin = os.path.join(bin_dir, f"stat_client{suffix}")

    # 1. server-<target>.zip
    server_zip = os.path.join(output_dir, f"server-{target}.zip")
    with zipfile.ZipFile(server_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(srv_bin):
            zf.write(srv_bin, f"stat_server{suffix}")
        if os.path.exists("config.toml"):
            zf.write("config.toml", "config.toml")
        if os.path.exists("systemd/stat_server.service"):
            zf.write("systemd/stat_server.service", "stat_server.service")

    # 2. client-<target>.zip
    client_zip = os.path.join(output_dir, f"client-{target}.zip")
    with zipfile.ZipFile(client_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(cli_bin):
            zf.write(cli_bin, f"stat_client{suffix}")
        if os.path.exists("systemd/stat_client.service"):
            zf.write("systemd/stat_client.service", "stat_client.service")

    # 3. ServerStatus-<target>.zip (all)
    all_zip = os.path.join(output_dir, f"ServerStatus-{target}.zip")
    with zipfile.ZipFile(all_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(srv_bin):
            zf.write(srv_bin, f"stat_server{suffix}")
        if os.path.exists(cli_bin):
            zf.write(cli_bin, f"stat_client{suffix}")
        if os.path.exists("config.toml"):
            zf.write("config.toml", "config.toml")
        if os.path.exists("systemd/stat_server.service"):
            zf.write("systemd/stat_server.service", "stat_server.service")
        if os.path.exists("systemd/stat_client.service"):
            zf.write("systemd/stat_client.service", "stat_client.service")

    print(f"Packaged: {server_zip}, {client_zip}, {all_zip}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--bin-dir", required=True)
    parser.add_argument("--suffix", default="")
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    package(args.target, args.bin_dir, args.suffix, args.output_dir)
