#!/bin/bash
# Herbouw het dashboard na wijzigingen in app/.
set -e
cd /mnt/user/appdata/garmin-dashboard
docker build -t garmin-dashboard:latest .
bash start.sh
