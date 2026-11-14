#!/bin/sh
set -eu

if [ -f packages.txt ]; then
    sudo apt update
    sudo apt upgrade -y
    sudo xargs apt install -y < packages.txt
fi

if [ -f requirements.txt ]; then
    pip3 install --user -r requirements.txt
fi

pip3 install --user streamlit
echo 'Packages installed and requirements met'
