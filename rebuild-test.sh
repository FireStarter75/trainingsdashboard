#!/bin/bash
# Herbouwt het testbeeld van het dashboard (de code die nu op de schijf staat,
# dus de branch die je hebt uitgecheckt) en start de testomgeving.
set -e
cd /mnt/user/appdata/garmin-dashboard
docker build -t garmin-dashboard:test .
bash start-test.sh
