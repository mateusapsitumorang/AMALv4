#!/bin/bash
RECORDINGS_DIR="/opt/CAPEv2/storage/guacrecordings"

inotifywait -m -e create -e close_write "$RECORDINGS_DIR" |
while read dir event file; do
    chown guacd:guacd "$RECORDINGS_DIR/$file"
    chmod 640 "$RECORDINGS_DIR/$file"
done
