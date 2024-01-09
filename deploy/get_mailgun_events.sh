#!/bin/sh

cd /home/retractobot-project/retractobot
# Add just to the path
export PATH="$PATH:/home/retractobot-project/bin"
just run retrieve_mailgun_events -v 1
