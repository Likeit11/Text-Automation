import argparse
from urllib.parse import urlsplit


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # The packaged application has no console; show errors in its startup dialog.
        raise ValueError(message)


def parse_options(argv=None):
    parser = ArgumentParser(description='SMS client: program.exe -- YOUR_PAIRING_KEY')
    parser.add_argument('key', nargs='?', help='Same pairing key as the Android app')
    parser.add_argument('--legacy', action='store_true', help='Use the old unkeyed server')
    args = parser.parse_args(argv)
    if args.legacy:
        if args.key is not None:
            raise ValueError('Do not combine --legacy with a pairing key.')
    elif (args.key is None or not 16 <= len(args.key.encode('utf-8')) <= 128
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in args.key)):
        raise ValueError('연결키는 공백·제어문자 없이 UTF-8 기준 16~128바이트여야 합니다.\n'
                         '사용 예: "프로그램.exe" -- YourPrivateKey_123456\n'
                         '기존 서버 연결: "프로그램.exe" --legacy')
    return args


def connection_urls(urls, key):
    # Never send a pairing key to the old unencrypted HTTP fallback.
    return [url for url in urls if url and (key is None or urlsplit(url).scheme == 'https')]


def accepts_code(data, key, routing_ready):
    return isinstance(data, dict) and (key is None or (routing_ready and data.get('routing') == 'keyed'))
