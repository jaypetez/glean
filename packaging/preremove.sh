#!/bin/sh
set -e
systemctl stop glean || true
systemctl disable glean || true