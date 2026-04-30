import configparser
from pathlib import Path
import re

CAPE_CONF = Path("/opt/CAPEv2/conf")

def get_config_value(file, section, key):
    config = configparser.ConfigParser()
    config.read(CAPE_CONF / file)
    
    if config.has_section(section):
        return config.get(section, key, fallback="")
    
    return ""

def save_config_value(file, section, key, value):
    path = CAPE_CONF / file

    with open(path, "r") as f:
        text = f.read()

    pattern = rf"(\[{section}\][^\[]*?{key}\s*=\s*)([^\n]*)"
    text = re.sub(pattern, r"\g<1>" + value, text, flags=re.S)

    with open(path, "w") as f:
        f.write(text)
