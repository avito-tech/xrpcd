import sys

import xrpcd.consuming


def main():
    script = xrpcd.consuming.XRpcConsumer('xrpcd', 'provider_db', sys.argv[1:])
    script.start()
