import argparse
from urllib.parse import urlsplit


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Let unrecognized arguments fall back to legacy mode without a console.
        raise ValueError(message)


def parse_options(argv=None):
    parser = ArgumentParser(description='SMS client: program.exe -- YOUR_PAIRING_KEY')
    parser.add_argument('key', nargs='?', help='Same pairing key as the Android app')
    parser.add_argument('--legacy', action='store_true', help='Use the old unkeyed server')
    try:
        args = parser.parse_args(argv)
    except ValueError:
        return argparse.Namespace(key=None, legacy=True)
    if (args.legacy or args.key is None or not 4 <= len(args.key) <= 128
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in args.key)):
        return argparse.Namespace(key=None, legacy=True)
    return args


def connection_urls(urls, key):
    # Never send a pairing key to the old unencrypted HTTP fallback.
    return [url for url in urls if url and (key is None or urlsplit(url).scheme == 'https')]


def accepts_code(data, key, routing_ready):
    return isinstance(data, dict) and (key is None or (routing_ready and data.get('routing') == 'keyed'))
